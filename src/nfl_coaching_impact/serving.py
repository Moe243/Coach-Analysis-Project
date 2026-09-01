"""Transactional PostgreSQL publication for checkpoint-seven serving data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import psycopg
from psycopg.types.json import Jsonb

from .errors import PipelineError
from .pipeline import _validate_existing_version

SCHEMA_VERSION = "checkpoint-7.2"
LOADER_VERSION = "serving-loader-v3"
API_CONTRACT_VERSION = "api-v1.2"
PUBLICATION_NAMESPACE = uuid.UUID("c79812ad-1480-48ec-9972-e94b6f158a31")


@dataclass(frozen=True)
class ServingVersions:
    historical: str
    expected: str
    expected_model: str
    coach: str
    coach_model: str


@dataclass(frozen=True)
class ServingLoadResult:
    load_id: str
    versions: ServingVersions
    reused_existing: bool
    row_counts: dict[str, int]


@dataclass(frozen=True)
class ManualInputSnapshot:
    digest: str
    manifest: dict[str, dict[str, Any]]
    paths: tuple[Path, ...]
    rows: dict[str, list[dict[str, str]]]


def _latest(root: Path) -> tuple[str, Path]:
    pointer = root / "LATEST"
    if not pointer.is_file():
        raise PipelineError(f"missing LATEST pointer: {pointer}")
    version = pointer.read_text(encoding="utf-8").strip()
    path = root / version
    if not path.is_dir():
        raise PipelineError(f"missing version directory: {path}")
    _validate_existing_version(path, version)
    return version, path


def _required(frame: pl.DataFrame, table: str, columns: set[str], key: list[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise PipelineError(f"{table} missing required columns: {missing}")
    nulls = {name: frame[name].null_count() for name in key if frame[name].null_count()}
    if nulls:
        raise PipelineError(f"{table} has null business keys: {nulls}")
    if frame.select(key).n_unique() != frame.height:
        raise PipelineError(f"{table} has duplicate business keys: {key}")


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _payload(row: dict[str, Any]) -> Jsonb:
    return Jsonb({key: _json_value(value) for key, value in row.items()})


def _csv_bytes(content: bytes, path: Path) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PipelineError(f"manual CSV is not valid UTF-8: {path}") from error
    return list(csv.DictReader(io.StringIO(text, newline="")))


def _manifest_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _manual_snapshot(project_root: Path) -> ManualInputSnapshot:
    manual = project_root / "data" / "manual"
    paths = tuple(sorted(manual.glob("*.csv")))
    if not paths:
        raise PipelineError(f"no manual CSV inputs found: {manual}")
    captured = {path.name: path.read_bytes() for path in paths}
    records = {
        path.name: {
            "sha256": hashlib.sha256(captured[path.name]).hexdigest(),
            "byte_size": len(captured[path.name]),
        }
        for path in paths
    }
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(captured[path.name])
    rows = {path.name: _csv_bytes(captured[path.name], path) for path in paths}
    return ManualInputSnapshot(digest.hexdigest(), records, paths, rows)


def _assert_manual_snapshot_unchanged(snapshot: ManualInputSnapshot) -> None:
    manual = snapshot.paths[0].parent
    current_paths = tuple(sorted(manual.glob("*.csv")))
    if current_paths != snapshot.paths:
        raise PipelineError("manual CSV input set changed during serving load")
    changes = []
    for path in snapshot.paths:
        content = path.read_bytes()
        expected = snapshot.manifest[path.name]
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != expected["sha256"] or len(content) != expected["byte_size"]:
            changes.append(path.name)
    if changes:
        raise PipelineError(f"manual CSV inputs changed during serving load: {changes}")


def _serving_load_id(versions: ServingVersions, manual_digest: str) -> uuid.UUID:
    identity = "|".join(
        (
            SCHEMA_VERSION,
            LOADER_VERSION,
            API_CONTRACT_VERSION,
            *versions.__dict__.values(),
            manual_digest,
        )
    )
    return uuid.uuid5(PUBLICATION_NAMESPACE, identity)


def _source_tables(project_root: Path) -> tuple[ServingVersions, dict[str, Any], list[Path]]:
    processed = project_root / "data" / "processed"
    historical_version, historical = _latest(processed / "historical")
    expected_version, expected = _latest(processed / "expected_performance")
    coach_version, coach = _latest(processed / "coach_impact")
    silver = historical / "silver"
    frames = {
        "teams": pl.read_parquet(silver / "teams.parquet"),
        "team_aliases": pl.read_parquet(silver / "team_aliases.parquet"),
        "players": pl.read_parquet(silver / "players.parquet"),
        "player_external_ids": pl.read_parquet(silver / "player_external_ids.parquet"),
        "games": pl.read_parquet(silver / "games.parquet"),
        "qb_games": pl.read_parquet(silver / "qb_game_performance.parquet"),
        "qb_seasons": pl.read_parquet(silver / "qb_team_season_performance.parquet"),
        "source_manifests": pl.read_parquet(silver / "source_manifest.parquet"),
        "historical_manifest": pl.read_parquet(silver / "pipeline_manifest.parquet"),
        "qb_pae": pl.read_parquet(expected / "qb_pae.parquet"),
        "coach_exposures": pl.read_parquet(coach / "coach_modeling_exposures.parquet"),
        "coach_effects": pl.read_parquet(coach / "coach_effect_estimates.parquet"),
        "coach_rankings": pl.read_parquet(coach / "preliminary_coach_rankings.parquet"),
    }
    expected_models = frames["qb_pae"]["model_version"].unique().to_list()
    coach_models = frames["coach_effects"]["coach_model_version"].unique().to_list()
    if len(expected_models) != 1 or len(coach_models) != 1:
        raise PipelineError("model outputs must contain exactly one model version")
    versions = ServingVersions(
        historical_version,
        expected_version,
        str(expected_models[0]),
        coach_version,
        str(coach_models[0]),
    )
    _validate_version_contracts(frames, versions)
    manifest_paths = [
        historical / "OUTPUT_CHECKSUMS.json",
        expected / "OUTPUT_CHECKSUMS.json",
        coach / "OUTPUT_CHECKSUMS.json",
        historical / "RUN_MANIFEST.json",
        expected / "RUN_MANIFEST.json",
        coach / "RUN_MANIFEST.json",
    ]
    return versions, frames, manifest_paths


def _validate_version_contracts(frames: dict[str, Any], versions: ServingVersions) -> None:
    for name in (
        "teams",
        "team_aliases",
        "players",
        "player_external_ids",
        "games",
        "qb_games",
        "qb_seasons",
        "source_manifests",
    ):
        if set(frames[name]["data_version"].unique().to_list()) != {versions.historical}:
            raise PipelineError(f"{name} data version does not match {versions.historical}")
    if set(frames["qb_pae"]["data_version"].unique().to_list()) != {versions.expected}:
        raise PipelineError("PAE data version mismatch")
    for name in ("coach_exposures", "coach_effects", "coach_rankings"):
        if set(frames[name]["data_version"].unique().to_list()) != {versions.coach}:
            raise PipelineError(f"{name} data version mismatch")
        if set(frames[name]["coach_model_version"].unique().to_list()) != {versions.coach_model}:
            raise PipelineError(f"{name} model version mismatch")
    if set(frames["coach_exposures"]["model_version"].unique().to_list()) != {
        versions.expected_model
    }:
        raise PipelineError("coach exposures expected-performance model version mismatch")


def _validate_sources(
    frames: dict[str, Any], manual: ManualInputSnapshot, team_by_abbr: dict[str, str]
) -> None:
    contracts = {
        "teams": ({"team_id", "team_abbr", "team_name"}, ["team_id"]),
        "team_aliases": (
            {"source_system", "alias", "team_id"},
            ["source_system", "alias"],
        ),
        "players": ({"player_id", "display_name"}, ["player_id"]),
        "player_external_ids": (
            {"player_id", "external_system", "external_id"},
            ["external_system", "external_id"],
        ),
        "games": ({"game_id", "season", "home_team_id", "away_team_id", "scope"}, ["game_id"]),
        "qb_games": (
            {"game_id", "player_id", "team_id", "dropbacks"},
            ["game_id", "player_id", "team_id"],
        ),
        "qb_seasons": (
            {"player_id", "team_id", "season", "scope"},
            ["player_id", "team_id", "season"],
        ),
        "qb_pae": (
            {"player_id", "team_id", "season", "performance_above_expectation"},
            ["player_id", "team_id", "season"],
        ),
        "coach_exposures": (
            {"assignment_key", "player_id", "team_id", "season", "exposure_fraction"},
            ["assignment_key", "player_id", "team_id", "season"],
        ),
        "coach_effects": ({"coach_id", "role", "estimated_effect"}, ["coach_id", "role"]),
        "coach_rankings": ({"coach_id", "role", "ranking_status"}, ["coach_id", "role"]),
    }
    for table, (columns, key) in contracts.items():
        _required(frames[table], table, columns, key)
    exposures = frames["coach_exposures"]
    invalid_fraction = exposures.filter(
        (pl.col("exposure_fraction") <= 0)
        | (pl.col("exposure_fraction") > 1)
        | (
            (
                pl.col("exposure_dropbacks")
                - pl.col("observed_dropbacks") * pl.col("exposure_fraction")
            ).abs()
            > 1e-6
        )
    )
    if invalid_fraction.height:
        raise PipelineError("coach exposures contain invalid fractional exposure")
    assignments = manual.rows["coaching_assignments.csv"]
    citations = manual.rows["coach_assignment_sources.csv"]
    cited = {row["assignment_key"] for row in citations}
    unsupported = [
        row["assignment_key"]
        for row in assignments
        if row["verification_status"] == "verified" and row["assignment_key"] not in cited
    ]
    if unsupported:
        raise PipelineError(f"verified assignments without citations: {unsupported[:5]}")
    assignment_by_key = {row["assignment_key"]: row for row in assignments}
    lineage_fields = (
        "coach_id",
        "season",
        "role",
        "start_week",
        "end_week",
        "verification_status",
        "confidence_level",
        "interval_basis",
        "is_shared",
    )
    mismatches: list[dict[str, Any]] = []
    for exposure in frames["coach_exposures"].to_dicts():
        assignment = assignment_by_key.get(exposure["assignment_key"])
        if assignment is None:
            mismatches.append({"assignment_key": exposure["assignment_key"], "issue": "missing"})
            continue
        expected = {
            **{field: assignment[field] for field in lineage_fields},
            "team_id": team_by_abbr.get(assignment["team_id"]),
        }
        actual = {field: exposure[field] for field in (*lineage_fields, "team_id")}
        for field in ("season", "start_week", "end_week"):
            expected[field] = int(expected[field])
        expected["is_shared"] = expected["is_shared"] == "true"
        if actual != expected:
            mismatches.append(
                {
                    "assignment_key": exposure["assignment_key"],
                    "actual": actual,
                    "expected": expected,
                }
            )
    if mismatches:
        raise PipelineError(f"coach exposure assignment lineage mismatch: {mismatches[:3]}")


def load_serving_database(database_url: str, project_root: Path) -> ServingLoadResult:
    """Validate and atomically publish all checkpoint-seven serving facts."""

    versions, frames, manifest_paths = _source_tables(project_root)
    manual = _manual_snapshot(project_root)
    team_by_abbr = dict(frames["teams"].select("team_abbr", "team_id").iter_rows())
    _validate_sources(frames, manual, team_by_abbr)
    load_id = _serving_load_id(versions, manual.digest)
    coaches = manual.rows["coaches.csv"]
    assignments = manual.rows["coaching_assignments.csv"]
    citations = manual.rows["coach_assignment_sources.csv"]
    reviews = manual.rows["coaching_review_queue.csv"]
    counts = {
        name: frame.height for name, frame in frames.items() if isinstance(frame, pl.DataFrame)
    }
    counts.update(
        coaches=len(coaches),
        assignments=len(assignments),
        citations=len(citations),
        reviews=len(reviews),
    )

    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            existing = connection.execute(
                "SELECT 1 FROM serving_loads WHERE load_id = %s", (load_id,)
            ).fetchone()
            if existing:
                loaded_counts = {
                    table: connection.execute(
                        f"SELECT count(*) FROM {table} WHERE load_id = %s", (load_id,)
                    ).fetchone()[0]
                    for table in (
                        "serving_teams",
                        "serving_players",
                        "serving_games",
                        "serving_qb_seasons",
                        "serving_qb_pae",
                        "serving_coaches",
                        "serving_coach_assignments",
                        "serving_coach_effects",
                    )
                }
                if any(value == 0 for value in loaded_counts.values()):
                    raise PipelineError(f"existing serving load is incomplete: {loaded_counts}")
                _assert_manual_snapshot_unchanged(manual)
                connection.execute(
                    "INSERT INTO serving_publication (publication_id, load_id) VALUES (1, %s) "
                    "ON CONFLICT (publication_id) DO UPDATE SET "
                    "load_id = EXCLUDED.load_id, published_at = now()",
                    (load_id,),
                )
                return ServingLoadResult(str(load_id), versions, True, counts)
            connection.execute(
                """INSERT INTO serving_loads
                   (load_id, schema_version, loader_version, api_contract_version,
                    historical_data_version, expected_data_version, expected_model_version,
                    coach_data_version, coach_model_version, manifest_sha256,
                    manual_manifest_sha256)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    load_id,
                    SCHEMA_VERSION,
                    LOADER_VERSION,
                    API_CONTRACT_VERSION,
                    versions.historical,
                    versions.expected,
                    versions.expected_model,
                    versions.coach,
                    versions.coach_model,
                    hashlib.sha256(
                        (_manifest_digest(manifest_paths) + manual.digest).encode()
                    ).hexdigest(),
                    manual.digest,
                ),
            )
            _insert_frames(
                connection,
                load_id,
                frames,
                coaches,
                assignments,
                citations,
                reviews,
                team_by_abbr,
                project_root,
                versions,
                manual.digest,
                manual.manifest,
            )
            _assert_manual_snapshot_unchanged(manual)
            connection.execute(
                "INSERT INTO serving_publication (publication_id, load_id) VALUES (1, %s) "
                "ON CONFLICT (publication_id) DO UPDATE SET "
                "load_id = EXCLUDED.load_id, published_at = now()",
                (load_id,),
            )
    return ServingLoadResult(str(load_id), versions, False, counts)


def _insert_frames(
    connection,
    load_id: uuid.UUID,
    frames: dict[str, Any],
    coaches,
    assignments,
    citations,
    reviews,
    team_by_abbr,
    project_root: Path,
    versions: ServingVersions,
    manual_digest: str,
    manual_manifest: dict[str, dict[str, Any]],
) -> None:
    lid = str(load_id)

    def many(sql: str, rows: list[tuple[Any, ...]]) -> None:
        if rows:
            with connection.cursor() as cursor:
                cursor.executemany(sql, rows)

    many(
        "INSERT INTO serving_teams VALUES (%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["team_id"],
                r["team_abbr"],
                r["team_name"],
                r.get("nflverse_team_id"),
                _payload(r),
            )
            for r in frames["teams"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_team_aliases VALUES (%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["source_system"],
                r["alias"],
                r["team_id"],
                r["first_observed_season"],
                r["last_observed_season"],
                _payload(r),
            )
            for r in frames["team_aliases"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_players VALUES (%s,%s,%s,%s,%s)",
        [
            (lid, r["player_id"], r["display_name"], r.get("position"), _payload(r))
            for r in frames["players"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_player_external_ids VALUES (%s,%s,%s,%s)",
        [
            (lid, r["player_id"], r["external_system"], r["external_id"])
            for r in frames["player_external_ids"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_games VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["game_id"],
                r["season"],
                r["week"],
                r["game_type"],
                r["game_date"],
                r["home_team_id"],
                r["away_team_id"],
                r["scope"],
                _payload(r),
            )
            for r in frames["games"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_qb_games VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["game_id"],
                r["player_id"],
                r["team_id"],
                r["season"],
                r["week"],
                r["dropbacks"],
                r.get("epa_per_dropback"),
                r.get("starter"),
                _payload(r),
            )
            for r in frames["qb_games"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_qb_seasons VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["player_id"],
                r["team_id"],
                r["season"],
                r["scope"],
                r["games"],
                r.get("starts"),
                r["dropbacks"],
                r.get("epa_per_dropback"),
                r.get("cpoe"),
                r.get("success_rate"),
                r.get("sack_rate"),
                r["qualifies_default"],
                r["metric_version"],
                _payload(r),
            )
            for r in frames["qb_seasons"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_qb_pae VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["player_id"],
                r["team_id"],
                r["season"],
                r["data_version"],
                r["model_version"],
                r["expected_epa_per_dropback"],
                r["actual_epa_per_dropback"],
                r["performance_above_expectation"],
                r.get("prediction_interval_low"),
                r.get("prediction_interval_high"),
                r["eligibility_status"],
                r["reliability"],
                r["is_out_of_sample"],
                _payload(r),
            )
            for r in frames["qb_pae"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_coaches VALUES (%s,%s,%s,%s)",
        [(lid, r["coach_id"], r["canonical_name"], r["normalized_name"]) for r in coaches],
    )
    many(
        "INSERT INTO serving_coach_assignments VALUES "
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["assignment_key"],
                r["coach_id"],
                team_by_abbr[r["team_id"]],
                int(r["season"]),
                r["role"],
                int(r["start_week"]),
                int(r["end_week"]),
                r["interval_basis"],
                r["verification_status"],
                r["confidence_level"],
                r["is_interim"] == "true",
                r["is_shared"] == "true",
                r["is_retained"] == "true",
                r["notes"],
                _payload(r),
            )
            for r in assignments
        ],
    )
    many(
        "INSERT INTO serving_coach_citations VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["assignment_key"],
                r["source_url"],
                r["source_title"],
                r["source_type"],
                r["source_accessed_at"],
                r["evidence_locator"],
                r["evidence_note"],
            )
            for r in citations
        ],
    )
    many(
        "INSERT INTO serving_review_queue VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["review_id"],
                team_by_abbr[r["team_id"]],
                int(r["season"]),
                r["role"],
                r["status"],
                r["issue_type"],
                _payload(r),
            )
            for r in reviews
        ],
    )
    many(
        "INSERT INTO serving_coach_exposures VALUES "
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["assignment_key"],
                r["player_id"],
                r["team_id"],
                r["season"],
                r["coach_id"],
                r["role"],
                r["verification_status"],
                r["confidence_level"],
                r["interval_basis"],
                r["is_shared"],
                r["start_week"],
                r["end_week"],
                r["exposure_fraction"],
                r["observed_dropbacks"],
                r["exposure_dropbacks"],
                r.get("coach_interval_pae"),
                r.get("exclusion_reason"),
                _payload(r),
            )
            for r in frames["coach_exposures"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_coach_effects VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["coach_id"],
                r["role"],
                r["data_version"],
                r["coach_model_version"],
                r.get("estimated_effect"),
                r.get("confidence_low"),
                r.get("confidence_high"),
                r["bootstrap_replicates"],
                r["bootstrap_attempted_replicates"],
                r["bootstrap_interval_available"],
                r["interval_estimand"],
                r["identified_effect"],
                r["identification_status"],
                _payload(r),
            )
            for r in frames["coach_effects"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_coach_rankings VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["coach_id"],
                r["role"],
                r["rank_eligible"],
                r.get("rank_exclusion_reason"),
                r["ranking_status"],
                r.get("preliminary_rank"),
                r["verified_dropbacks"],
                r["qualifying_qb_seasons"],
                r["distinct_quarterbacks"],
                _payload(r),
            )
            for r in frames["coach_rankings"].to_dicts()
        ],
    )
    many(
        "INSERT INTO serving_source_manifests VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        [
            (
                lid,
                r["asset_key"],
                r["dataset"],
                r.get("season"),
                r["source_url"],
                r["sha256"],
                r["validation_status"],
                _payload(r),
            )
            for r in frames["source_manifests"].to_dicts()
        ],
    )
    roots = {
        "historical": project_root / "data" / "processed" / "historical" / versions.historical,
        "expected_performance": project_root
        / "data"
        / "processed"
        / "expected_performance"
        / versions.expected,
        "coach_impact": project_root / "data" / "processed" / "coach_impact" / versions.coach,
    }
    manifests = []
    for pipeline_name, root in roots.items():
        manifest = json.loads((root / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
        model_version = manifest.get("model_version") or manifest.get("coach_model_version")
        manifests.append(
            (lid, pipeline_name, manifest["data_version"], model_version, Jsonb(manifest))
        )
    manifests.append(
        (
            lid,
            "manual_inputs",
            manual_digest,
            None,
            Jsonb({"sha256": manual_digest, "files": manual_manifest}),
        )
    )
    many("INSERT INTO serving_pipeline_manifests VALUES (%s,%s,%s,%s,%s)", manifests)

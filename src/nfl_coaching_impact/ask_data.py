"""Build an immutable, local C19 lookup bundle. No model fitting or DB publication."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import tempfile
from pathlib import Path

import polars as pl
import pydantic

from .constants import TEAM_ALIAS_TO_CANONICAL
from .serving_completeness import FORMAL_ROLES, build_serving_coaching_completeness

CONTRACT = "ask-v1"
VERSIONS = {
    "historical": "c3-f6c1aa118ff43b90",
    "enhancements": "enh-04254065cafd92ba",
    "predictive_foundation": "c13-5e3d7a34ea4d1af5",
    "qb_player_state": "c14-43283062e788e686",
    "qb_projection_refinement": "c16r-8c8063c5954e2a22",
    "checkpoint_12_final_play_caller_evidence": "c12-pc-final-cac923f086757e5b",
}
QB_KEY = ["player_id", "team_id", "season"]
SCHEME_FEATURES = (
    "shotgun_rate",
    "no_huddle_rate",
    "pass_rate",
    "early_down_pass_rate",
    "neutral_pass_rate",
    "target_depth_short_rate",
    "target_depth_intermediate_rate",
    "target_depth_deep_rate",
    "average_air_yards",
    "scramble_rate",
    "expected_pass_rate",
    "proe",
)


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def code_identity() -> dict[str, str]:
    root = Path(__file__).parent
    files = [*root.glob("ask*.py"), root / "constants.py", root / "serving_completeness.py"]
    return {p.name: digest(p.read_bytes()) for p in sorted(files)}


def require_key(frame: pl.DataFrame, key: list[str]) -> None:
    if frame.select(pl.any_horizontal(pl.col(key).is_null()).any()).item():
        raise ValueError(f"null lookup key: {key}")
    if frame.select(key).n_unique() != frame.height:
        raise ValueError(f"duplicate lookup key: {key}")


def canonical_team(value: str) -> str:
    return "team_" + TEAM_ALIAS_TO_CANONICAL[value].lower()


class Capture:
    """Hash and parse the same captured input bytes; expose only relative logical IDs."""

    def __init__(self, project: Path):
        self.project = project
        self.hashes: dict[str, str] = {}
        self.sources: dict[str, dict] = {}
        self.captured: dict[Path, bytes] = {}

    def raw(self, path: Path) -> bytes:
        if path not in self.captured:
            self.captured[path] = path.read_bytes()
        content = self.captured[path]
        self.hashes[str(path.relative_to(self.project))] = digest(content)
        return content

    def table(self, family: str, filename: str, alias: str) -> pl.DataFrame:
        version = VERSIONS[family]
        parent = (
            "research/coach_effect/outputs"
            if family.startswith("checkpoint_12")
            else "data/processed"
        )
        directory = self.project / parent / family / version
        if family in {"historical", "enhancements"}:
            manifest = json.loads(self.raw(directory / "RUN_MANIFEST.json"))
            checksums = json.loads(self.raw(directory / "OUTPUT_CHECKSUMS.json"))
            expected = checksums[filename]["sha256"]
        else:
            manifest = json.loads(self.raw(directory / "MANIFEST.json"))
            expected = manifest["output_checksums"][filename]
        if manifest["data_version"] != version:
            raise ValueError("unapproved lookup source identity")
        content = self.raw(directory / filename)
        if digest(content) != expected:
            raise ValueError(f"lookup source checksum mismatch: {alias}")
        self.sources[alias] = {
            "artifact": f"{family}/{version}/{filename}",
            "data_version": version,
            "sha256": expected,
        }
        return (
            pl.read_parquet(io.BytesIO(content))
            if filename.endswith(".parquet")
            else pl.read_csv(io.BytesIO(content), infer_schema_length=None)
        )


def assemble(project: Path) -> tuple[dict, dict]:
    capture = Capture(project)
    table = capture.table
    players = (
        table("historical", "silver/players.parquet", "players")
        .filter(pl.col("position") == "QB")
        .select("player_id", "display_name")
    )
    teams = table("historical", "silver/teams.parquet", "teams").select(
        "team_id", "team_abbr", "team_name"
    )
    stats = table("enhancements", "canonical_qb_team_season_performance.parquet", "history")
    stats = stats.filter((pl.col("scope") == "analysis") & pl.col("season").is_between(2010, 2025))
    pae = table("enhancements", "canonical_qb_pae.parquet", "pae")
    supplemental = table("enhancements", "qb_supplemental_statistics.parquet", "supplemental")
    for frame in (stats, pae, supplemental):
        require_key(frame, QB_KEY)
    if not set(stats["player_id"]) <= set(players["player_id"]):
        raise ValueError("noncanonical QB in historical facts")
    if pae.filter(
        ~pl.col("is_out_of_sample") | (pl.col("training_end_season") >= pl.col("season"))
    ).height:
        raise ValueError("historical PAE is not out of sample")
    for row in pae.to_dicts():
        if row["performance_above_expectation"] is not None and not math.isclose(
            row["actual_epa_per_dropback"] - row["expected_epa_per_dropback"],
            row["performance_above_expectation"],
            abs_tol=1e-12,
        ):
            raise ValueError("invalid PAE arithmetic")
    # Exact frozen source versions replace load_id at this artifact-only boundary.
    # Never join by player-season alone or coalesce missing PAE to zero.
    joined = stats.join(
        pae.select(
            *QB_KEY,
            "expected_epa_per_dropback",
            "performance_above_expectation",
            "prediction_std_error",
            "prediction_interval_low",
            "prediction_interval_high",
            "model_version",
            "eligibility_status",
            "reliability",
            "is_out_of_sample",
        ),
        on=QB_KEY,
        how="left",
        validate="1:1",
    )
    extra = [c for c in supplemental.columns if c not in joined.columns]
    joined = joined.join(
        supplemental.select(*QB_KEY, *extra), on=QB_KEY, how="left", validate="1:1"
    )
    history_fields = [
        *QB_KEY,
        "dropbacks",
        "starts",
        "epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "cpoe",
        "success_rate",
        "sack_rate",
        "attempts",
        "completions",
        "passing_yards",
        "passing_touchdowns",
        "interceptions",
        "rushing_yards",
        "rushing_touchdowns",
        "qualifies_default",
        "eligibility_status",
        "reliability",
        "is_out_of_sample",
        "model_version",
        "prediction_std_error",
        "prediction_interval_low",
        "prediction_interval_high",
        "metric_version",
    ]
    states = table("qb_player_state", "player_states.parquet", "states")
    records = table("qb_player_state", "qb_state_feature_records.parquet", "profiles")
    table("qb_player_state", "qb_feature_registry.csv", "profile_registry")
    require_key(states, ["player_id", "target_season"])
    require_key(records, ["player_id", "target_season", "feature_name"])
    if records.filter(
        (pl.col("source_season") >= pl.col("target_season"))
        | (pl.col("source_available_date") > pl.col("as_of_date"))
    ).height:
        raise ValueError("profile timing violation")
    record_fields = [
        "player_id",
        "target_season",
        "feature_name",
        "feature_value",
        "raw_value",
        "as_of_date",
        "source_season",
        "observation_start_season",
        "observation_end_season",
        "sample_size",
        "denominator",
        "qualified",
        "missingness_reason",
        "reliability",
        "feature_status",
        "estimate_type",
        "estimate_standard_error",
        "interval_low",
        "interval_high",
        "stability_classification",
        "portability_classification",
    ]
    scheme = table("predictive_foundation", "scheme_team_season.csv", "scheme").filter(
        pl.col("feature_name").is_in(SCHEME_FEATURES)
    )
    require_key(scheme, ["team_id", "season", "feature_name"])
    scheme = scheme.with_columns(
        pl.col("team_id").replace_strict(
            {abbr: canonical_team(abbr) for abbr in TEAM_ALIAS_TO_CANONICAL}
        )
    )
    projections = table("qb_projection_refinement", "projections_2026.parquet", "projections")
    require_key(projections, ["player_id", "target_season"])
    if (
        projections.height != 57
        or projections.filter(
            (pl.col("target_season") != 2026)
            | (pl.col("outcome") != "epa")
            | (pl.col("base_model") != "B2")
            | (pl.col("calibration_method") != "BIAS")
            | pl.col("active_roster_claim")
            | (pl.col("model_version") != "qb-calibrated-8c8063c5954e2a22")
        ).height
    ):
        raise ValueError("unapproved forward projection contract")
    pcae = table("checkpoint_12_final_play_caller_evidence", "historical_pcae.csv", "pcae")
    require_key(pcae, ["coach_id", "team_id", "season", "start_week", "end_week"])
    if pcae.filter(
        (pl.col("verification_status") != "verified")
        | pl.col("is_shared")
        | ~pl.col("research_only")
        | pl.col("production_ranking")
    ).height:
        raise ValueError("PCAE requires verified non-shared research attribution")
    pcae = pcae.with_columns(
        pl.col("team_id").replace_strict(
            {abbr: canonical_team(abbr) for abbr in TEAM_ALIAS_TO_CANONICAL}
        )
    )
    manual = {}
    for path in sorted((project / "data/manual").glob("*.csv")):
        content = capture.raw(path)
        manual[path.name] = list(csv.DictReader(io.StringIO(content.decode())))
    # Reuse the serving evidence validator and formal-title overlay, not obsolete base OC rows.
    build_serving_coaching_completeness(manual)
    base = [r for r in manual["coaching_assignments.csv"] if r["role"] not in FORMAL_ROLES]
    assignments = []
    for row in [*base, *manual["coaching_evidence_11b.csv"]]:
        sources = [
            s
            for s in manual["coach_assignment_sources.csv"]
            if s["assignment_key"] == row["assignment_key"]
        ]
        if row.get("source_url"):
            sources.append(
                {
                    k: row[k]
                    for k in (
                        "source_url",
                        "source_type",
                        "source_accessed_at",
                        "evidence_locator",
                        "evidence_note",
                    )
                }
            )
        if row["verification_status"] == "verified" and not sources:
            raise ValueError("verified assignment missing source")
        assignments.append(
            {
                "assignment_key": row["assignment_key"],
                "coach_id": row["coach_id"],
                "coach_name": row["coach_canonical_name"],
                "team_id": canonical_team(row["team_id"]),
                **{k: int(row[k]) for k in ("season", "start_week", "end_week")},
                **{
                    k: row[k]
                    for k in ("role", "interval_basis", "verification_status", "confidence_level")
                },
                **{
                    k: row.get(k) == "true" if k in row else None
                    for k in ("is_shared", "is_interim", "is_retained")
                },
                "is_provisional": row["verification_status"] == "provisional",
                "citations": sources,
            }
        )
    require_key(pl.DataFrame(assignments, infer_schema_length=None), ["assignment_key"])
    # Identity labels may use names, never latest team/status as a predictor.
    names = {r["player_id"]: r["display_name"] for r in players.to_dicts()}
    names.update({r["player_id"]: r["display_name"] for r in states.to_dicts()})
    qb_entities = [
        {"kind": "qb", "id": key, "name": name, "aliases": []}
        for key, name in sorted(names.items())
    ]
    coach_names = {r["coach_id"]: r["canonical_name"] for r in manual["coaches.csv"]}
    coach_names.update({r["coach_id"]: r["coach_canonical_name"] for r in pcae.to_dicts()})
    coach_entities = [
        {
            "kind": "coach",
            "id": key,
            "name": name,
            "aliases": [
                r["alias_name"] for r in manual["coach_aliases.csv"] if r["coach_id"] == key
            ],
        }
        for key, name in sorted(coach_names.items())
    ]
    team_entities = [
        {
            "kind": "team",
            "id": r["team_id"],
            "name": r["team_name"],
            "aliases": [
                r["team_abbr"],
                *r["team_name"].rsplit(" ", 1),
                *[a for a in TEAM_ALIAS_TO_CANONICAL if canonical_team(a) == r["team_id"]],
            ],
        }
        for r in teams.to_dicts()
    ]
    bundle = {
        "entities": [*qb_entities, *coach_entities, *team_entities],
        "history": joined.select(history_fields).sort(QB_KEY).to_dicts(),
        "states": states.sort("player_id", "target_season").to_dicts(),
        "profiles": records.select(record_fields)
        .sort("player_id", "target_season", "feature_name")
        .to_dicts(),
        "scheme": scheme.select(
            "team_id",
            "season",
            "feature_name",
            "raw_value",
            "feature_sample_size",
            "feature_status",
            "missingness_reason",
            "source_dataset",
            "source_covered",
        )
        .sort("season", "team_id", "feature_name")
        .to_dicts(),
        "projections": projections.sort("player_id").to_dicts(),
        "assignments": sorted(assignments, key=lambda r: r["assignment_key"]),
        "pcae": pcae.sort("coach_id", "season", "team_id", "start_week").to_dicts(),
        "sources": capture.sources,
    }
    manual_hashes = {k: v for k, v in capture.hashes.items() if k.startswith("data/manual/")}
    bundle["sources"]["assignments"] = {
        "artifact": "manual/validated-eleven-b-snapshot",
        "data_version": "manual-" + digest(json_bytes(manual_hashes))[:16],
        "sha256": digest(json_bytes(manual_hashes)),
    }
    return bundle, capture.hashes


def build_bundle(project: Path, output: Path) -> Path:
    bundle, inputs = assemble(project)
    code = code_identity()
    identity = {
        "contract": CONTRACT,
        "inputs": inputs,
        "code": code,
        "versions": VERSIONS,
        "python": platform.python_version(),
        "polars": pl.__version__,
        "pydantic": pydantic.__version__,
        "serialization": "sorted-compact-ascii-json-null-no-nan-v1",
    }
    content = json_bytes(bundle)
    identity["bundle_sha256"] = digest(content)
    version = "c19-" + digest(json_bytes(identity))[:16]
    manifest = {
        "data_version": version,
        "contract": CONTRACT,
        "identity": identity,
        "output_checksums": {"analytical_bundle.json": digest(content)},
        "counts": {k: len(v) for k, v in bundle.items() if isinstance(v, list)},
    }
    output.mkdir(parents=True, exist_ok=True)
    destination = output / version
    with tempfile.TemporaryDirectory(prefix=".c19-", dir=output) as staging:
        stage = Path(staging)
        (stage / "analytical_bundle.json").write_bytes(content)
        (stage / "MANIFEST.json").write_bytes(json_bytes(manifest))
        if destination.exists():
            for name in ("analytical_bundle.json", "MANIFEST.json"):
                if (destination / name).read_bytes() != (stage / name).read_bytes():
                    raise ValueError("immutable C19 publication differs")
        else:
            os.replace(stage, destination)
        # TemporaryDirectory tolerates a moved staging directory.
    with tempfile.NamedTemporaryFile(dir=output, prefix=".LATEST-", delete=False) as pointer:
        pointer.write((version + "\n").encode())
    os.replace(pointer.name, output / "LATEST")
    return destination

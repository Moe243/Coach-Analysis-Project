"""Deterministic Checkpoint Eleven coaching coverage and historical PCAE research.

This module writes only to the ignored research output directory. It does not
load serving tables or produce a production Coach Effect score or ranking.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import scipy
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nfl_coaching_impact.constants import CANONICAL_TEAM_IDS, TEAM_ALIAS_TO_CANONICAL
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_ANALYSIS_SEASONS,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    HISTORICAL_PCAE_WARMUP_SEASONS,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
    RANDOM_SEED,
)
from research.coach_effect.phase_2_play_calling.analysis import (
    ExpectedPlayModels,
    score_expected_decisions,
)

ROLES = (
    "head_coach",
    "offensive_coordinator",
    "quarterbacks_coach",
    "play_caller",
)
PLAY_KEY = ("game_id", "play_id")
OUTPUT_NAMES = (
    "coaching_coverage.csv",
    "unresolved_play_callers.csv",
    "eligibility_reconciliation.csv",
    "season_attribution.csv",
    "historical_pcae.csv",
)
PBP_COLUMNS = tuple(
    sorted(
        {
            *PLAY_KEY,
            "season",
            "season_type",
            "week",
            "posteam",
            "play_type",
            "epa",
            "two_point_attempt",
            *PLAY_CALL_FEATURES,
        }
    )
)


@dataclass(frozen=True)
class HistoricalPcaeResult:
    output_path: Path
    data_version: str
    model_version: str
    eligibility_version: str
    season_attribution: pl.DataFrame
    pcae: pl.DataFrame


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_source_hashes(project_root: Path, expected: dict[str, str]) -> None:
    changed = [
        relative
        for relative, digest in expected.items()
        if _sha256(project_root / relative) != digest
    ]
    if changed:
        raise ValueError(f"checkpoint-eleven inputs changed during build: {sorted(changed)}")


def build_coaching_coverage(project_root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return the complete 2,048-cell role matrix and unresolved caller queue."""

    manual = project_root / "data" / "manual"
    assignments = _read_csv(manual / "coaching_assignments.csv")
    reviews = _read_csv(manual / "coaching_review_queue.csv")
    citations = _read_csv(manual / "coach_assignment_sources.csv")
    citations_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in citations:
        citations_by_key[row["assignment_key"]].append(row)
    assignments_by_grain: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        assignments_by_grain[(int(row["season"]), row["team_id"], row["role"])].append(row)
    season_weeks_by_team: dict[tuple[int, str], set[int]] = defaultdict(set)
    for row in assignments:
        if row["role"] == "head_coach":
            season_weeks_by_team[(int(row["season"]), row["team_id"])].update(
                range(int(row["start_week"]), int(row["end_week"]) + 1)
            )
    reviews_by_grain: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in reviews:
        if row["status"] == "open":
            reviews_by_grain[(int(row["season"]), row["team_id"], row["role"])].append(row)

    records: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for season in HISTORICAL_PCAE_ANALYSIS_SEASONS:
        for team in sorted(CANONICAL_TEAM_IDS):
            for role in ROLES:
                grain = (season, team, role)
                role_assignments = sorted(
                    assignments_by_grain[grain],
                    key=lambda row: (
                        int(row["start_week"]),
                        int(row["end_week"]),
                        row["assignment_key"],
                    ),
                )
                role_reviews = sorted(reviews_by_grain[grain], key=lambda row: row["review_id"])
                statuses = {row["verification_status"] for row in role_assignments}
                expected_weeks = season_weeks_by_team[(season, team)]
                verified_weeks = {
                    week
                    for row in role_assignments
                    if row["verification_status"] == "verified"
                    for week in range(int(row["start_week"]), int(row["end_week"]) + 1)
                }
                supported_weeks = {
                    week
                    for row in role_assignments
                    if row["verification_status"] in {"verified", "provisional"}
                    for week in range(int(row["start_week"]), int(row["end_week"]) + 1)
                }
                if "conflicting" in statuses:
                    status = "conflicting"
                elif expected_weeks <= verified_weeks:
                    status = "verified"
                elif expected_weeks <= supported_weeks and "provisional" in statuses:
                    status = "provisional"
                elif "verified" in statuses:
                    status = "partial_verified"
                elif "provisional" in statuses:
                    status = "provisional"
                elif role_assignments:
                    status = "unverified"
                elif any(row["issue_type"] == "missing_formal_role" for row in role_reviews):
                    status = "missing"
                else:
                    status = "manual_review"
                assignment_keys = [row["assignment_key"] for row in role_assignments]
                source_urls = sorted(
                    {
                        citation["source_url"]
                        for key in assignment_keys
                        for citation in citations_by_key[key]
                    }
                    | {row["source_url"] for row in role_reviews}
                )
                record = {
                    "season": season,
                    "team_id": team,
                    "role": role,
                    "coverage_status": status,
                    "assignment_keys": "|".join(assignment_keys),
                    "coach_ids": "|".join(
                        dict.fromkeys(row["coach_id"] for row in role_assignments)
                    ),
                    "coach_names": "|".join(
                        dict.fromkeys(row["coach_canonical_name"] for row in role_assignments)
                    ),
                    "intervals": "|".join(
                        f"{row['start_week']}-{row['end_week']}:{row['interval_basis']}"
                        for row in role_assignments
                    ),
                    "verification_statuses": "|".join(
                        dict.fromkeys(row["verification_status"] for row in role_assignments)
                    ),
                    "confidence_levels": "|".join(
                        dict.fromkeys(row["confidence_level"] for row in role_assignments)
                    ),
                    "review_ids": "|".join(row["review_id"] for row in role_reviews),
                    "review_issue_types": "|".join(
                        dict.fromkeys(row["issue_type"] for row in role_reviews)
                    ),
                    "source_urls": "|".join(source_urls),
                }
                records.append(record)
                if role == "play_caller" and status != "verified":
                    unresolved.append(record.copy())
                elif role == "play_caller" and role_reviews:
                    unresolved.append(record.copy())
    coverage = pl.DataFrame(records).sort("season", "team_id", "role")
    unresolved_frame = pl.DataFrame(unresolved, schema=coverage.schema).sort(
        "season", "team_id", "role"
    )
    if coverage.height != 16 * 32 * 4:
        raise ValueError(f"coaching coverage must contain 2,048 cells, found {coverage.height}")
    if coverage.select("season", "team_id", "role").n_unique() != coverage.height:
        raise ValueError("coaching coverage contains duplicate team-season-role cells")
    return coverage, unresolved_frame


def prepare_historical_plays(raw: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, int]]:
    """Apply the v2 decision-play contract and return a transparent audit."""

    required = {
        *PLAY_KEY,
        "season",
        "season_type",
        "week",
        "posteam",
        "play_type",
        "epa",
        "down",
        "two_point_attempt",
        *PLAY_CALL_FEATURES,
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"play-by-play is missing required columns: {missing}")
    candidate = raw.filter(
        (pl.col("season_type") == "REG") & pl.col("play_type").is_in(["pass", "run"])
    )
    null_counts = candidate.select(
        pl.col("game_id").is_null().sum().alias("game_id"),
        pl.col("play_id").is_null().sum().alias("play_id"),
        pl.col("posteam").is_null().sum().alias("posteam"),
        pl.col("week").is_null().sum().alias("week"),
    ).row(0, named=True)
    if any(null_counts.values()):
        raise ValueError(f"candidate plays contain null identifiers: {null_counts}")
    if candidate.select(PLAY_KEY).n_unique() != candidate.height:
        raise ValueError("candidate plays contain duplicate (game_id, play_id) keys")
    two_point = candidate.filter(pl.col("two_point_attempt") == 1)
    invalid_two_point = two_point.filter(pl.col("down").is_not_null())
    if invalid_two_point.height:
        raise ValueError("two-point decision plays unexpectedly contain a scrimmage down")
    eligible = candidate.filter(
        (pl.col("two_point_attempt").fill_null(0) != 1)
        & pl.col("epa").is_not_null()
        & pl.col("epa").is_finite()
    )
    missing_down = eligible.filter(pl.col("down").is_null())
    if missing_down.height:
        sample = missing_down.select("season", "game_id", "play_id").head(5).to_dicts()
        raise ValueError(f"eligible scrimmage plays lack down; sample={sample}")
    normalized = eligible.with_columns(
        pl.col("posteam")
        .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
        .alias("team_id")
    )
    unresolved_team = normalized.filter(pl.col("team_id").is_null())
    if unresolved_team.height:
        raise ValueError(
            "eligible plays contain unresolved teams: "
            f"{unresolved_team['posteam'].unique().sort().to_list()}"
        )
    audit = {
        "regular_season_run_pass": candidate.height,
        "two_point_conversions_excluded": two_point.height,
        "nonfinite_epa_excluded": candidate.filter(
            (pl.col("two_point_attempt").fill_null(0) != 1)
            & (pl.col("epa").is_null() | ~pl.col("epa").is_finite())
        ).height,
        "eligible_plays": normalized.height,
    }
    return normalized.sort("season", "week", "game_id", "play_id"), audit


def fit_historical_models(
    training: pl.DataFrame, target: pl.DataFrame, target_season: int
) -> tuple[ExpectedPlayModels, pl.DataFrame]:
    """Fit the unchanged models on strictly earlier seasons and score one target."""

    if training.is_empty() or training["season"].max() >= target_season:
        raise ValueError("historical PCAE training must use strictly earlier seasons")
    if target.is_empty() or set(target["season"].unique()) != {target_season}:
        raise ValueError("target frame must contain exactly the requested season")
    if (
        training.filter(pl.col("play_type") == "pass").is_empty()
        or training.filter(pl.col("play_type") == "run").is_empty()
    ):
        raise ValueError("historical training data must contain pass and run plays")

    def pipeline(estimator: object) -> Pipeline:
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", estimator),
            ]
        )

    def matrix(frame: pl.DataFrame) -> np.ndarray:
        return frame.select(PLAY_CALL_FEATURES).cast(pl.Float64).to_numpy()

    pass_training = training.filter(pl.col("play_type") == "pass")
    run_training = training.filter(pl.col("play_type") == "run")
    call_model = pipeline(LogisticRegression(max_iter=2_000, random_state=RANDOM_SEED)).fit(
        matrix(training), (training["play_type"] == "pass").cast(pl.Int8).to_numpy()
    )
    pass_epa_model = pipeline(Ridge(alpha=10.0)).fit(
        matrix(pass_training), pass_training["epa"].to_numpy()
    )
    run_epa_model = pipeline(Ridge(alpha=10.0)).fit(
        matrix(run_training), run_training["epa"].to_numpy()
    )
    train_seasons = tuple(sorted(training["season"].unique().to_list()))
    models = ExpectedPlayModels(
        call_model,
        pass_epa_model,
        run_epa_model,
        train_seasons=train_seasons,
        test_season=target_season,
    )
    scored = score_expected_decisions(target, models)
    return models, scored


def attribute_verified_calls(
    scored: pl.DataFrame, assignments: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Attribute only one-to-one, verified, explicit weekly caller intervals."""

    callers = assignments.filter(
        (pl.col("role") == "play_caller")
        & (pl.col("verification_status") == "verified")
        & (pl.col("interval_basis") != "season_designation")
        & pl.col("primary_source_url").is_not_null()
        & (pl.col("primary_source_url").str.strip_chars() != "")
    )
    joined = scored.join(
        callers,
        on=["season", "team_id"],
        how="inner",
        validate="m:m",
    ).filter(pl.col("week").is_between(pl.col("start_week"), pl.col("end_week")))
    if joined.is_empty():
        return joined, scored.with_columns(pl.lit("no_verified_interval").alias("reason"))
    joined = joined.with_columns(pl.len().over(PLAY_KEY).alias("matching_callers"))
    safe = joined.filter((pl.col("matching_callers") == 1) & ~pl.col("is_shared"))
    ambiguous_keys = (
        joined.filter((pl.col("matching_callers") != 1) | pl.col("is_shared"))
        .select(PLAY_KEY)
        .unique()
    )
    matched_keys = safe.select(PLAY_KEY).unique()
    unresolved = (
        scored.join(matched_keys, on=PLAY_KEY, how="anti")
        .join(
            ambiguous_keys.with_columns(pl.lit(True).alias("ambiguous")),
            on=PLAY_KEY,
            how="left",
        )
        .with_columns(
            pl.when(pl.col("ambiguous").fill_null(False))
            .then(pl.lit("shared_or_ambiguous_interval"))
            .otherwise(pl.lit("no_verified_interval"))
            .alias("reason")
        )
        .drop("ambiguous")
    )
    return safe.sort("season", "week", "game_id", "play_id"), unresolved.sort(
        "season", "week", "game_id", "play_id"
    )


def aggregate_historical_pcae(attributed: pl.DataFrame) -> pl.DataFrame:
    """Aggregate the unchanged league-centered PCAE formula without rankings."""

    if attributed.is_empty():
        return pl.DataFrame()
    league = attributed.group_by("season").agg(
        pl.col("call_value").mean().alias("league_average_call_value")
    )
    return (
        attributed.group_by(
            "coach_id",
            "coach_canonical_name",
            "team_id",
            "season",
            "start_week",
            "end_week",
            "verification_status",
            "confidence_level",
            "is_shared",
            maintain_order=True,
        )
        .agg(
            pl.len().alias("eligible_play_count"),
            pl.len().alias("attributed_play_count"),
            pl.col("call_value").mean().alias("average_call_value"),
        )
        .join(league, on="season", validate="m:1")
        .with_columns(
            (pl.col("average_call_value") - pl.col("league_average_call_value")).alias("pcae"),
            pl.lit(HISTORICAL_PCAE_MODEL_VERSION).alias("model_version"),
            pl.lit(HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION).alias("play_eligibility_version"),
            pl.lit(False).alias("ranking_output"),
        )
        .sort("season", "team_id", "coach_id", "start_week")
    )


def _write_csv(frame: pl.DataFrame, path: Path) -> None:
    frame.write_csv(path, line_terminator="\n")


def run_checkpoint_eleven(
    project_root: Path, output_root: Path | None = None
) -> HistoricalPcaeResult:
    """Build deterministic, research-only Checkpoint Eleven outputs from local assets."""

    historical_root = project_root / "data" / "processed" / "historical"
    historical_version = (historical_root / "LATEST").read_text(encoding="utf-8").strip()
    bronze = historical_root / historical_version / "bronze" / "play_by_play"
    manual = project_root / "data" / "manual"
    manual_hashes = {
        str(path.relative_to(project_root)): _sha256(path) for path in sorted(manual.glob("*.csv"))
    }
    assignments = pl.read_csv(manual / "coaching_assignments.csv", infer_schema_length=None)
    target_seasons = sorted(
        assignments.filter(
            (pl.col("role") == "play_caller")
            & (pl.col("verification_status") == "verified")
            & (pl.col("interval_basis") != "season_designation")
        )["season"]
        .unique()
        .to_list()
    )
    frames: dict[int, pl.DataFrame] = {}
    eligibility_records: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}
    for season in (*HISTORICAL_PCAE_WARMUP_SEASONS, *HISTORICAL_PCAE_ANALYSIS_SEASONS):
        path = bronze / f"season={season}" / "play_by_play.parquet"
        source_hashes[str(path.relative_to(project_root))] = _sha256(path)
        prepared, audit = prepare_historical_plays(pl.read_parquet(path, columns=PBP_COLUMNS))
        frames[season] = prepared
        eligibility_records.append({"season": season, **audit})

    coverage, unresolved_callers = build_coaching_coverage(project_root)
    scored_targets: list[pl.DataFrame] = []
    for season in target_seasons:
        training = pl.concat(
            [frames[value] for value in frames if value < season], how="diagonal_relaxed"
        )
        _, scored = fit_historical_models(training, frames[season], season)
        scored_targets.append(scored)
    scored = pl.concat(scored_targets, how="diagonal_relaxed") if scored_targets else pl.DataFrame()
    attributed, unresolved_plays = attribute_verified_calls(scored, assignments)
    pcae = aggregate_historical_pcae(attributed)

    eligibility = pl.DataFrame(eligibility_records).sort("season")
    attribution_records = []
    for season in HISTORICAL_PCAE_ANALYSIS_SEASONS:
        eligible = frames[season].height
        attributed_count = (
            attributed.filter(pl.col("season") == season).select(PLAY_KEY).n_unique()
            if not attributed.is_empty()
            else 0
        )
        unresolved_count = (
            unresolved_plays.filter(pl.col("season") == season).height
            if season in target_seasons
            else eligible
        )
        attribution_records.append(
            {
                "season": season,
                "eligible_plays": eligible,
                "attributed_plays": attributed_count,
                "unattributed_plays": unresolved_count,
                "attribution_rate": attributed_count / eligible if eligible else 0.0,
                "model_available": season in target_seasons,
            }
        )
    season_attribution = pl.DataFrame(attribution_records).sort("season")

    input_hashes = {**manual_hashes, **source_hashes}
    _verify_source_hashes(project_root, input_hashes)
    identity = {
        "historical_data_version": historical_version,
        "model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "play_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "call_value_formula": CALL_VALUE_FORMULA,
        "pcae_formula": PCAE_FORMULA,
        "features": PLAY_CALL_FEATURES,
        "model_specification": {
            "call_model": "LogisticRegression(max_iter=2000)",
            "epa_models": "Ridge(alpha=10.0)",
            "preprocessing": "median imputation then standard scaling",
            "random_seed": RANDOM_SEED,
            "dependencies": {
                "numpy": np.__version__,
                "polars": pl.__version__,
                "scipy": scipy.__version__,
                "scikit_learn": sklearn.__version__,
            },
            "source_hashes": {
                str(path.relative_to(project_root)): _sha256(path)
                for path in (
                    Path(__file__),
                    project_root / "research/coach_effect/config.py",
                    project_root / "research/coach_effect/phase_2_play_calling/analysis.py",
                )
            },
        },
        "manual_sources": manual_hashes,
        "pbp_sources": source_hashes,
        "target_seasons": target_seasons,
    }
    data_version = (
        "c11-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    if not pcae.is_empty():
        pcae = pcae.with_columns(
            pl.lit(data_version).alias("data_version"),
            pl.lit(True).alias("shared_or_ambiguous_plays_excluded"),
        )
    root = output_root or project_root / "research" / "coach_effect" / "outputs" / "checkpoint_11"
    destination = root / data_version
    temporary = root / f".{data_version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    _write_csv(coverage, temporary / "coaching_coverage.csv")
    _write_csv(unresolved_callers, temporary / "unresolved_play_callers.csv")
    _write_csv(eligibility, temporary / "eligibility_reconciliation.csv")
    _write_csv(season_attribution, temporary / "season_attribution.csv")
    _write_csv(pcae, temporary / "historical_pcae.csv")
    checksums = {name: _sha256(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "data_version": data_version,
        "research_only": True,
        "production_coach_effect": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {
            "coaching_coverage": coverage.height,
            "unresolved_play_callers": unresolved_callers.height,
            "eligibility_reconciliation": eligibility.height,
            "season_attribution": season_attribution.height,
            "historical_pcae": pcae.height,
        },
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _verify_source_hashes(project_root, input_hashes)
    if destination.exists():
        for name, expected in checksums.items():
            if _sha256(destination / name) != expected:
                raise ValueError(f"existing research output differs: {name}")
        shutil.rmtree(temporary)
    else:
        temporary.replace(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "LATEST").write_text(data_version + "\n", encoding="utf-8")
    return HistoricalPcaeResult(
        output_path=destination,
        data_version=data_version,
        model_version=HISTORICAL_PCAE_MODEL_VERSION,
        eligibility_version=HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        season_attribution=season_attribution,
        pcae=pcae,
    )

"""Prompt 8 research-only historical evidence and offensive scheme expansion.

This module writes only beneath the ignored ``research/coach_effect/outputs`` tree. It does not
change serving data, production models, database state, API contracts, or frontend behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import nflreadpy
import numpy as np
import polars as pl
import scipy
import sklearn

from nfl_coaching_impact.coaching import normalize_coach_name
from nfl_coaching_impact.constants import TEAM_ALIAS_TO_CANONICAL
from research.coach_effect.checkpoint_eleven import (
    PBP_COLUMNS,
    _sha256,
    _write_csv,
    aggregate_historical_pcae,
    attribute_verified_calls,
    fit_historical_models,
    prepare_historical_plays,
)
from research.coach_effect.checkpoint_eleven_b import (
    _evidence_assignments,
    build_evidence_coverage,
)
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
    RANDOM_SEED,
)

PROMPT8_SPECIFICATION = "checkpoint-twelve-data-expansion-v1"
PROMPT6_VERSION = "c12-8cd15ae6015e900b"
PROMPT7_VERSION = "c12-review-7897e3d57dd8b22a"
EVIDENCE_FILE = "research/coach_effect/play_caller_evidence_prompt8.csv"
SOURCE_ACCESS_DATE = "2026-09-08"
ANALYSIS_SEASONS = tuple(range(2010, 2026))
PARTICIPATION_SEASONS = tuple(range(2016, 2026))
FTN_SEASONS = tuple(range(2022, 2026))
MIN_CORE_TEAM_SEASON_COVERAGE = 0.90
MIN_DESCRIPTIVE_TEAM_SEASON_COVERAGE = 0.50
MIN_PERSONNEL_TEAM_PLAYS = 100
MIN_FEATURE_MOVE_PAIRS = 5
PLACEBO_REPLICATES = 250
EXPECTED_STARTING_CALLER_COUNTS = {
    "verified": 119,
    "partial": 1,
    "provisional": 125,
    "unresolved": 267,
}
PLAY_CALLER_GATE = 256
TARGET_FOLD_GATE = 5
COMMON_FUTURE_GATE = 150
PBP_SCHEME_COLUMNS = (
    "game_id",
    "play_id",
    "season",
    "season_type",
    "week",
    "posteam",
    "play_type",
    "two_point_attempt",
    "epa",
    "success",
    "down",
    "qtr",
    "yardline_100",
    "game_seconds_remaining",
    "score_differential",
    "pass_attempt",
    "rush_attempt",
    "shotgun",
    "no_huddle",
    "qb_dropback",
    "qb_kneel",
    "qb_spike",
    "qb_scramble",
    "sack",
    "rusher_player_id",
    "pass_length",
    "pass_location",
    "air_yards",
    "xpass",
    "pass_oe",
)
OUTPUT_NAMES = (
    "play_caller_completeness.csv",
    "play_caller_evidence_review.csv",
    "new_verified_play_caller_intervals.csv",
    "play_caller_source_lineage.csv",
    "remaining_play_caller_priority.csv",
    "pcae_attribution_by_season.csv",
    "historical_pcae.csv",
    "common_qp_availability.csv",
    "future_fold_matrix.csv",
    "repeat_play_callers.csv",
    "different_qb_samples.csv",
    "different_team_samples.csv",
    "scheme_feature_availability.csv",
    "personnel_profiles.csv",
    "personnel_family_profiles.csv",
    "formation_profiles.csv",
    "mechanic_profiles.csv",
    "tendency_profiles.csv",
    "qb_usage_profiles.csv",
    "situational_profiles.csv",
    "outcome_profiles.csv",
    "team_season_scheme_fingerprints.csv",
    "scheme_feature_correlations.csv",
    "coach_role_scheme_associations.csv",
    "scheme_feature_stability.csv",
    "scheme_moves.csv",
    "scheme_portability.csv",
    "scheme_feature_portability.csv",
    "scheme_specificity_placebos.csv",
    "scheme_persistence.csv",
    "multiple_move_coaches.csv",
    "final_equation_readiness.csv",
)

PROFILE_COLUMNS = (
    "team_id",
    "season",
    "profile_family",
    "feature_name",
    "raw_count",
    "eligible_plays",
    "raw_value",
    "source_dataset",
    "source_hash",
    "definition_version",
    "missingness_reason",
)

PROFILE_SCHEMA = {
    "team_id": pl.String,
    "season": pl.Int64,
    "profile_family": pl.String,
    "feature_name": pl.String,
    "raw_count": pl.Int64,
    "eligible_plays": pl.Int64,
    "raw_value": pl.Float64,
    "source_dataset": pl.String,
    "source_hash": pl.String,
    "definition_version": pl.String,
    "missingness_reason": pl.String,
}


@dataclass(frozen=True)
class Prompt8Sources:
    historical_version: str
    historical_root: Path
    pbp_root: Path
    games_path: Path
    enhancement_version: str
    pae_path: Path
    source_cache: Path


@dataclass(frozen=True)
class Prompt8Result:
    output_path: Path
    data_version: str
    caller_coverage: pl.DataFrame
    feature_availability: pl.DataFrame
    readiness: pl.DataFrame


def _latest(root: Path) -> str:
    value = (root / "LATEST").read_text(encoding="utf-8").strip()
    if not value or not (root / value).is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return value


def _sources(project_root: Path, source_cache: Path | None = None) -> Prompt8Sources:
    historical_base = project_root / "data/processed/historical"
    historical_version = _latest(historical_base)
    historical_root = historical_base / historical_version
    enhancement_base = project_root / "data/processed/enhancements"
    enhancement_version = _latest(enhancement_base)
    cache = source_cache or (
        project_root / "research/coach_effect/outputs/checkpoint_12_data_expansion/source_cache"
    )
    return Prompt8Sources(
        historical_version=historical_version,
        historical_root=historical_root,
        pbp_root=historical_root / "bronze/play_by_play",
        games_path=historical_root / "silver/games.parquet",
        enhancement_version=enhancement_version,
        pae_path=(enhancement_base / enhancement_version / "canonical_qb_pae.parquet"),
        source_cache=cache,
    )


def _canonical_team(value: str) -> str:
    team = TEAM_ALIAS_TO_CANONICAL.get(value)
    if team is None:
        raise ValueError(f"unresolved team identifier: {value}")
    return team


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _stable_seed(label: str) -> int:
    digest = hashlib.sha256(f"{RANDOM_SEED}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _cosine_distance(left: np.ndarray, right: np.ndarray) -> float | None:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return None if denominator == 0 else float(1 - np.dot(left, right) / denominator)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _write_parquet_cache(frame: pl.DataFrame, path: Path, sort_by: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    frame.sort(*sort_by).write_parquet(
        temporary,
        compression="zstd",
        statistics=True,
        row_group_size=100_000,
    )
    temporary.replace(path)


def load_scheme_sources(
    project_root: Path,
    *,
    source_cache: Path | None = None,
    allow_network: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, str]]:
    """Load source-cached official participation and FTN releases.

    The cached bytes are the source contract for deterministic rebuilds. Analytical outputs drop
    execution-specific fields such as FTN ``date_pulled`` but retain the exact cache hashes.
    """

    sources = _sources(project_root, source_cache)
    participation_path = sources.source_cache / "nflverse_participation_2016_2025.parquet"
    ftn_path = sources.source_cache / "nflverse_ftn_2022_2025.parquet"
    if not participation_path.exists():
        if not allow_network:
            raise FileNotFoundError(f"missing source cache: {participation_path}")
        participation = nflreadpy.load_participation(list(PARTICIPATION_SEASONS))
        _write_parquet_cache(
            participation,
            participation_path,
            ("nflverse_game_id", "play_id"),
        )
    if not ftn_path.exists():
        if not allow_network:
            raise FileNotFoundError(f"missing source cache: {ftn_path}")
        ftn = nflreadpy.load_ftn_charting(list(FTN_SEASONS))
        _write_parquet_cache(
            ftn,
            ftn_path,
            ("season", "nflverse_game_id", "nflverse_play_id"),
        )
    participation = pl.read_parquet(participation_path)
    ftn = pl.read_parquet(ftn_path)
    required_participation = {
        "nflverse_game_id",
        "play_id",
        "possession_team",
        "offense_formation",
        "offense_personnel",
        "n_offense",
    }
    required_ftn = {
        "nflverse_game_id",
        "nflverse_play_id",
        "season",
        "week",
        "qb_location",
        "is_motion",
        "is_play_action",
        "is_screen_pass",
        "is_rpo",
    }
    if missing := sorted(required_participation - set(participation.columns)):
        raise ValueError(f"participation cache missing columns: {missing}")
    if missing := sorted(required_ftn - set(ftn.columns)):
        raise ValueError(f"FTN cache missing columns: {missing}")
    hashes = {
        "nflverse_participation_2016_2025.parquet": _sha256(participation_path),
        "nflverse_ftn_2022_2025.parquet": _sha256(ftn_path),
    }
    return participation, ftn, hashes


def load_and_validate_play_caller_evidence(project_root: Path) -> pl.DataFrame:
    """Validate the source-backed research overlay and its exact top-25 audit."""

    path = project_root / EVIDENCE_FILE
    frame = pl.read_csv(path, infer_schema_length=None, null_values=[]).with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        (pl.col("is_shared") == "true").alias("is_shared"),
    )
    allowed_interval = {"verified", "provisional", "unresolved"}
    allowed_cell = {"verified", "partial", "provisional", "unresolved"}
    if set(frame["interval_status"]) - allowed_interval:
        raise ValueError("Prompt 8 evidence contains an invalid interval status")
    if set(frame["cell_status"]) - allowed_cell:
        raise ValueError("Prompt 8 evidence contains an invalid cell status")
    top = frame.filter(pl.col("batch") == "top25")
    ranks = sorted(set(top["priority_rank"].drop_nulls().cast(pl.Int64).to_list()))
    if ranks != list(range(1, 26)):
        raise ValueError(f"Prompt 8 top-25 evidence is incomplete: {ranks}")
    if top.select("season", "team_id").n_unique() != 25:
        raise ValueError("Prompt 8 top-25 must contain 25 unique team-season cells")

    for row in frame.to_dicts():
        season = int(row["season"])
        last_week = 18 if season >= 2021 else 17
        if not 2010 <= season <= 2025 or not 1 <= row["start_week"] <= row["end_week"] <= last_week:
            raise ValueError(f"invalid evidence interval: {season}-{row['team_id']}")
        expected = f"coach-{normalize_coach_name(row['coach_canonical_name'])}"
        if row["coach_id"] != expected:
            raise ValueError(f"canonical coach mismatch: {row['coach_id']} != {expected}")
        for field in ("primary_source_url", "secondary_source_url"):
            value = row[field]
            if value and urlparse(value).scheme != "https":
                raise ValueError(f"non-HTTPS evidence source: {value}")
        if row["interval_status"] == "verified":
            evidence = row["evidence_summary"].casefold()
            if not any(term in evidence for term in ("caller", "calling", "play-calling")):
                raise ValueError(f"verified evidence lacks explicit play-calling language: {row}")

    for cell in frame.partition_by(["season", "team_id"], as_dict=False):
        statuses = set(cell["cell_status"])
        if len(statuses) != 1:
            raise ValueError("one reviewed cell contains contradictory cell statuses")
        verified = cell.filter(pl.col("interval_status") == "verified").sort("start_week")
        for left, right in zip(verified.to_dicts(), verified.to_dicts()[1:], strict=False):
            if right["start_week"] <= left["end_week"] and not (
                left["is_shared"] and right["is_shared"]
            ):
                raise ValueError(f"overlapping non-shared evidence intervals: {left} / {right}")
    return frame.sort("batch", "priority_rank", "season", "team_id", "start_week", "coach_id")


def build_prompt8_assignments(project_root: Path, evidence: pl.DataFrame) -> list[dict[str, str]]:
    """Overlay only researched verified/partial cells without mutating manual production CSVs."""

    base = _evidence_assignments(project_root)
    replacement_cells = {
        (int(row["season"]), row["team_id"])
        for row in evidence.filter(pl.col("cell_status").is_in(["verified", "partial"]))
        .select("season", "team_id")
        .unique()
        .to_dicts()
    }
    rows = [
        row
        for row in base
        if not (
            row["role"] == "play_caller"
            and (int(row["season"]), row["team_id"]) in replacement_cells
        )
    ]
    for item in evidence.filter(
        pl.struct("season", "team_id").map_elements(
            lambda value: (int(value["season"]), value["team_id"]) in replacement_cells,
            return_dtype=pl.Boolean,
        )
    ).to_dicts():
        status = item["interval_status"]
        if status == "unresolved":
            continue
        slug = item["coach_id"].removeprefix("coach-")
        assignment = {
            "assignment_key": (
                f"p8-{item['season']}-{item['team_id']}-play_caller-"
                f"{item['start_week']:02d}-{item['end_week']:02d}-{slug}"
            ),
            "season": str(item["season"]),
            "team_id": item["team_id"],
            "coach_id": item["coach_id"],
            "coach_canonical_name": item["coach_canonical_name"],
            "role": "play_caller",
            "start_week": str(item["start_week"]),
            "end_week": str(item["end_week"]),
            "start_date": "",
            "end_date": "",
            "is_interim": "false",
            "is_shared": str(bool(item["is_shared"])).lower(),
            "is_retained": "false",
            "verification_status": status,
            "confidence_level": "high" if status == "verified" else "medium",
            "interval_basis": (
                "source_verified_weeks" if status == "verified" else "season_designation"
            ),
            "primary_source_url": item["primary_source_url"],
            "notes": item["evidence_summary"],
        }
        rows.append(assignment)
    keys = [row["assignment_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Prompt 8 assignments contain duplicate keys")
    return rows


def build_play_caller_coverage(
    project_root: Path, evidence: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Return starting/ending 512-cell states plus evidence-backed new intervals."""

    starting, _ = build_evidence_coverage(project_root)
    starting = (
        starting.filter(pl.col("role") == "play_caller")
        .with_columns(
            pl.col("coverage_status")
            .replace({"verified_person": "verified"})
            .alias("starting_status")
        )
        .select("season", "team_id", "starting_status")
    )
    actual_start = dict(starting.group_by("starting_status").len().iter_rows())
    if actual_start != EXPECTED_STARTING_CALLER_COUNTS:
        raise ValueError(
            f"Prompt 8 starting coverage drift: {actual_start} != {EXPECTED_STARTING_CALLER_COUNTS}"
        )
    cell_review = evidence.group_by("season", "team_id").agg(
        pl.first("cell_status").alias("reviewed_status"),
        pl.first("batch").alias("batch"),
        pl.first("priority_rank").alias("priority_rank"),
    )
    coverage = (
        starting.join(cell_review, on=["season", "team_id"], how="left", validate="1:1")
        .with_columns(
            pl.coalesce("reviewed_status", "starting_status").alias("ending_status"),
            pl.col("reviewed_status").is_not_null().alias("researched"),
        )
        .sort("season", "team_id")
    )
    if coverage.height != 512 or coverage.select("season", "team_id").n_unique() != 512:
        raise ValueError("Prompt 8 coverage must preserve the exact 512-cell matrix")
    intervals = evidence.filter(pl.col("interval_status") == "verified").with_columns(
        (
            pl.col("season").cast(pl.String)
            + "-"
            + pl.col("team_id")
            + "-play_caller-"
            + pl.col("start_week").cast(pl.String).str.pad_start(2, "0")
            + "-"
            + pl.col("end_week").cast(pl.String).str.pad_start(2, "0")
            + "-"
            + pl.col("coach_id").str.strip_prefix("coach-")
        ).alias("research_assignment_key")
    )
    if intervals["research_assignment_key"].n_unique() != intervals.height:
        raise ValueError("Prompt 8 verified interval keys are not unique")
    newly_verified_cells = coverage.filter(
        (pl.col("starting_status") != "verified") & (pl.col("ending_status") == "verified")
    )
    return coverage, newly_verified_cells, intervals


def load_scheme_pbp(project_root: Path) -> tuple[pl.DataFrame, dict[str, str]]:
    """Load validated regular-season PBP fields used by the retrospective scheme audit."""

    sources = _sources(project_root)
    frames: list[pl.DataFrame] = []
    hashes: dict[str, str] = {}
    for season in ANALYSIS_SEASONS:
        path = sources.pbp_root / f"season={season}" / "play_by_play.parquet"
        schema = pl.read_parquet_schema(path)
        missing = sorted(set(PBP_SCHEME_COLUMNS) - set(schema))
        if missing:
            raise ValueError(f"scheme PBP {season} missing columns: {missing}")
        raw = pl.read_parquet(path, columns=PBP_SCHEME_COLUMNS)
        nulls = raw.select(
            pl.col("game_id").is_null().sum().alias("game_id"),
            pl.col("play_id").is_null().sum().alias("play_id"),
        ).row(0, named=True)
        duplicate_count = raw.height - raw.select("game_id", "play_id").n_unique()
        if any(nulls.values()) or duplicate_count:
            sample = (
                raw.filter(pl.col("game_id").is_null() | pl.col("play_id").is_null())
                .select("game_id", "play_id")
                .head(5)
                .to_dicts()
            )
            raise ValueError(
                f"scheme PBP {season} invalid play keys: nulls={nulls}; "
                f"duplicates={duplicate_count}; sample={sample}"
            )
        frame = raw.filter(pl.col("season_type") == "REG").with_columns(
            pl.col("play_id").cast(pl.Int64),
            pl.col("posteam")
            .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
            .alias("team_id"),
        )
        unresolved = frame.filter(pl.col("posteam").is_not_null() & pl.col("team_id").is_null())
        if unresolved.height:
            raise ValueError(
                f"scheme PBP {season} unresolved teams: "
                f"{unresolved['posteam'].unique().sort().to_list()}"
            )
        frames.append(frame)
        hashes[str(path.relative_to(project_root))] = _sha256(path)
    return pl.concat(frames, how="vertical_relaxed").sort("season", "game_id", "play_id"), hashes


def _profile_rate(
    denominator: pl.DataFrame,
    *,
    family: str,
    feature: str,
    hit: pl.Expr,
    source_dataset: str,
    source_hash: str,
    definition_version: str,
) -> pl.DataFrame:
    if denominator.is_empty():
        return pl.DataFrame(schema=PROFILE_SCHEMA)
    return (
        denominator.group_by("team_id", "season")
        .agg(
            hit.cast(pl.Int64).sum().alias("raw_count"),
            pl.len().alias("eligible_plays"),
        )
        .with_columns(
            pl.lit(family).alias("profile_family"),
            pl.lit(feature).alias("feature_name"),
            (pl.col("raw_count") / pl.col("eligible_plays")).alias("raw_value"),
            pl.lit(source_dataset).alias("source_dataset"),
            pl.lit(source_hash).alias("source_hash"),
            pl.lit(definition_version).alias("definition_version"),
            pl.lit(None, dtype=pl.String).alias("missingness_reason"),
        )
        .select(PROFILE_COLUMNS)
        .sort("season", "team_id", "feature_name")
    )


def _profile_mean(
    denominator: pl.DataFrame,
    *,
    family: str,
    feature: str,
    value: str,
    source_dataset: str,
    source_hash: str,
    definition_version: str,
) -> pl.DataFrame:
    available = denominator.filter(pl.col(value).is_not_null() & pl.col(value).is_finite())
    if available.is_empty():
        return pl.DataFrame(schema=PROFILE_SCHEMA)
    return (
        available.group_by("team_id", "season")
        .agg(
            pl.len().alias("raw_count"),
            pl.len().alias("eligible_plays"),
            pl.col(value).mean().alias("raw_value"),
        )
        .with_columns(
            pl.lit(family).alias("profile_family"),
            pl.lit(feature).alias("feature_name"),
            pl.lit(source_dataset).alias("source_dataset"),
            pl.lit(source_hash).alias("source_hash"),
            pl.lit(definition_version).alias("definition_version"),
            pl.lit(None, dtype=pl.String).alias("missingness_reason"),
        )
        .select(PROFILE_COLUMNS)
        .sort("season", "team_id", "feature_name")
    )


def _profile_quantile(
    denominator: pl.DataFrame,
    *,
    family: str,
    feature: str,
    value: str,
    quantile: float,
    source_dataset: str,
    source_hash: str,
    definition_version: str,
) -> pl.DataFrame:
    available = denominator.filter(pl.col(value).is_not_null() & pl.col(value).is_finite())
    if available.is_empty():
        return pl.DataFrame(schema=PROFILE_SCHEMA)
    return (
        available.group_by("team_id", "season")
        .agg(
            pl.len().alias("raw_count"),
            pl.len().alias("eligible_plays"),
            pl.col(value).quantile(quantile, interpolation="linear").alias("raw_value"),
        )
        .with_columns(
            pl.lit(family).alias("profile_family"),
            pl.lit(feature).alias("feature_name"),
            pl.lit(source_dataset).alias("source_dataset"),
            pl.lit(source_hash).alias("source_hash"),
            pl.lit(definition_version).alias("definition_version"),
            pl.lit(None, dtype=pl.String).alias("missingness_reason"),
        )
        .select(PROFILE_COLUMNS)
        .sort("season", "team_id", "feature_name")
    )


def build_pbp_profiles(
    pbp: pl.DataFrame, pbp_hashes: dict[str, str]
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Derive retrospective tendencies, QB usage, situations, and outcomes separately."""

    source_hash = hashlib.sha256(
        "".join(f"{key}:{pbp_hashes[key]}" for key in sorted(pbp_hashes)).encode()
    ).hexdigest()
    scrimmage = pbp.filter(
        pl.col("team_id").is_not_null()
        & pl.col("play_type").is_in(["pass", "run"])
        & (pl.col("two_point_attempt").fill_null(0) != 1)
        & (pl.col("qb_kneel").fill_null(0) != 1)
    )
    passes = scrimmage.filter(pl.col("play_type") == "pass")
    tendencies = pl.concat(
        [
            _profile_rate(
                scrimmage,
                family="tendency",
                feature="shotgun_rate",
                hit=pl.col("shotgun").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-pbp-field-v1",
            ),
            _profile_rate(
                scrimmage,
                family="tendency",
                feature="no_huddle_rate",
                hit=pl.col("no_huddle").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-pbp-field-v1",
            ),
            _profile_rate(
                scrimmage,
                family="tendency",
                feature="pass_rate",
                hit=pl.col("play_type") == "pass",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="run-pass-scrimmage-v1",
            ),
            _profile_mean(
                scrimmage,
                family="tendency",
                feature="expected_pass_rate",
                value="xpass",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="nflverse-xpass-retrospective-v1",
            ),
            _profile_mean(
                scrimmage,
                family="tendency",
                feature="proe_mean",
                value="pass_oe",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="nflverse-pass-oe-v1",
            ),
        ],
        how="vertical_relaxed",
    )
    air_yard_passes = passes.filter(pl.col("air_yards").is_not_null())
    qb_usage = pl.concat(
        [
            _profile_rate(
                air_yard_passes,
                family="qb_usage",
                feature=feature,
                hit=predicate,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="air-yards-buckets-0-9-10-19-20plus-v1",
            )
            for feature, predicate in (
                ("target_depth_short_rate", pl.col("air_yards") <= 9),
                (
                    "target_depth_intermediate_rate",
                    pl.col("air_yards").is_between(10, 19),
                ),
                ("target_depth_deep_rate", pl.col("air_yards") >= 20),
            )
        ]
        + [
            _profile_mean(
                passes,
                family="qb_usage",
                feature="average_air_yards",
                value="air_yards",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="eligible-pass-air-yards-v1",
            ),
            _profile_quantile(
                passes,
                family="qb_usage",
                feature="median_air_yards",
                value="air_yards",
                quantile=0.5,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="eligible-pass-air-yards-v1",
            ),
            _profile_quantile(
                passes,
                family="qb_usage",
                feature="p90_air_yards",
                value="air_yards",
                quantile=0.9,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="eligible-pass-air-yards-v1",
            ),
            _profile_rate(
                passes,
                family="qb_usage",
                feature="pass_location_left_rate",
                hit=pl.col("pass_location") == "left",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-pass-location-v1",
            ),
            _profile_rate(
                passes,
                family="qb_usage",
                feature="pass_location_right_rate",
                hit=pl.col("pass_location") == "right",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-pass-location-v1",
            ),
            _profile_rate(
                passes,
                family="qb_usage",
                feature="pass_location_middle_rate",
                hit=pl.col("pass_location") == "middle",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-pass-location-v1",
            ),
            _profile_rate(
                scrimmage,
                family="qb_usage",
                feature="scramble_rate",
                hit=pl.col("qb_scramble").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="explicit-qb-scramble-v1",
            ),
        ],
        how="vertical_relaxed",
    )
    situations: list[pl.DataFrame] = []
    situation_contracts = (
        ("early_down_pass_rate", pl.col("down").is_in([1, 2])),
        (
            "neutral_pass_rate",
            pl.col("down").is_in([1, 2])
            & pl.col("score_differential").is_between(-7, 7)
            & (pl.col("game_seconds_remaining") > 120),
        ),
        ("red_zone_pass_rate", pl.col("yardline_100") <= 20),
        ("third_down_pass_rate", pl.col("down") == 3),
        ("fourth_down_pass_rate", pl.col("down") == 4),
    )
    for feature, predicate in situation_contracts:
        denominator = scrimmage.filter(predicate)
        situations.append(
            _profile_rate(
                denominator,
                family="situational",
                feature=feature,
                hit=pl.col("play_type") == "pass",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="situation-run-pass-v1",
            )
        )
    red_zone = scrimmage.filter(pl.col("yardline_100") <= 20)
    situations.append(
        _profile_rate(
            red_zone,
            family="situational",
            feature="red_zone_rush_rate",
            hit=pl.col("play_type") == "run",
            source_dataset="nflverse_pbp",
            source_hash=source_hash,
            definition_version="red-zone-20-run-pass-v1",
        )
    )
    situations.append(
        _profile_mean(
            passes.filter(pl.col("down") == 3),
            family="situational",
            feature="third_down_average_air_yards",
            value="air_yards",
            source_dataset="nflverse_pbp",
            source_hash=source_hash,
            definition_version="third-down-pass-air-yards-v1",
        )
    )
    fourth = pbp.filter(
        pl.col("team_id").is_not_null()
        & (pl.col("down") == 4)
        & pl.col("play_type").is_in(["pass", "run", "punt", "field_goal"])
    )
    situations.append(
        _profile_rate(
            fourth,
            family="situational",
            feature="fourth_down_go_rate",
            hit=pl.col("play_type").is_in(["pass", "run"]),
            source_dataset="nflverse_pbp",
            source_hash=source_hash,
            definition_version="fourth-down-choice-v1",
        )
    )
    finite = scrimmage.filter(pl.col("epa").is_not_null() & pl.col("epa").is_finite())
    outcomes = pl.concat(
        [
            _profile_mean(
                finite,
                family="outcome",
                feature="offensive_epa_per_play",
                value="epa",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_mean(
                finite.filter(pl.col("play_type") == "pass"),
                family="outcome",
                feature="pass_epa_per_play",
                value="epa",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_mean(
                finite.filter(pl.col("play_type") == "run"),
                family="outcome",
                feature="rush_epa_per_play",
                value="epa",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_rate(
                finite,
                family="outcome",
                feature="success_rate",
                hit=pl.col("success").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_rate(
                finite.filter(pl.col("play_type") == "pass"),
                family="outcome",
                feature="pass_success_rate",
                hit=pl.col("success").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_rate(
                finite.filter(pl.col("play_type") == "run"),
                family="outcome",
                feature="rush_success_rate",
                hit=pl.col("success").fill_null(0) == 1,
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_mean(
                finite.filter(pl.col("air_yards") >= 20),
                family="outcome",
                feature="deep_pass_epa",
                value="epa",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
            _profile_mean(
                finite.filter(pl.col("qb_scramble").fill_null(0) == 1),
                family="outcome",
                feature="scramble_epa",
                value="epa",
                source_dataset="nflverse_pbp",
                source_hash=source_hash,
                definition_version="retrospective-outcome-v1",
            ),
        ],
        how="vertical_relaxed",
    )
    return (
        tendencies,
        qb_usage,
        pl.concat(situations, how="vertical_relaxed"),
        outcomes,
    )


_PERSONNEL_TOKEN = re.compile(r"(?:^|,\s*)(\d+)\s+([A-Z]+)")
_DEFENSIVE_OR_SPECIAL_POSITIONS = {
    "CB",
    "DB",
    "DE",
    "DL",
    "DT",
    "FS",
    "ILB",
    "K",
    "LB",
    "LS",
    "MLB",
    "NT",
    "OLB",
    "P",
    "S",
    "SS",
}
_OFFENSIVE_POSITIONS = {"C", "FB", "G", "OL", "QB", "RB", "T", "TE", "WR"}


def parse_offense_personnel(value: str | None) -> dict[str, Any]:
    """Parse explicit nflverse personnel text without guessing unknown groupings."""

    empty = {
        "personnel_group": None,
        "running_backs": None,
        "tight_ends": None,
        "wide_receivers": None,
        "parse_reason": "missing_source_value",
    }
    if value is None or not value.strip():
        return empty
    tokens = {position: int(count) for count, position in _PERSONNEL_TOKEN.findall(value.upper())}
    positions = set(tokens)
    if (
        not tokens
        or positions & _DEFENSIVE_OR_SPECIAL_POSITIONS
        or positions - _OFFENSIVE_POSITIONS
    ):
        return {**empty, "parse_reason": "non_offensive_or_unparseable"}
    backs = tokens.get("RB", 0) + tokens.get("FB", 0)
    tight_ends = tokens.get("TE", 0)
    receivers = tokens.get("WR", 0)
    skill_count = backs + tight_ends + receivers
    if skill_count == 0 or skill_count > 5 or max(backs, tight_ends, receivers) > 5:
        return {**empty, "parse_reason": "invalid_skill_position_counts"}
    return {
        "personnel_group": f"{backs}{tight_ends}",
        "running_backs": backs,
        "tight_ends": tight_ends,
        "wide_receivers": receivers,
        "parse_reason": None,
    }


def _validate_enrichment_keys(frame: pl.DataFrame, *, key: Sequence[str], label: str) -> None:
    nulls = frame.select([pl.col(column).is_null().sum().alias(column) for column in key]).row(
        0, named=True
    )
    duplicates = frame.height - frame.select(key).n_unique()
    if any(nulls.values()) or duplicates:
        sample = (
            frame.filter(pl.any_horizontal([pl.col(column).is_null() for column in key]))
            .select(key)
            .head(5)
            .to_dicts()
        )
        raise ValueError(
            f"{label} invalid keys: nulls={nulls}; duplicates={duplicates}; sample={sample}"
        )


def build_participation_profiles(
    participation: pl.DataFrame,
    pbp: pl.DataFrame,
    source_hash: str,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build explicit personnel and formation profiles on exact source play keys."""

    selected = participation.select(
        pl.col("nflverse_game_id").alias("game_id"),
        pl.col("play_id").cast(pl.Int64),
        "possession_team",
        "offense_formation",
        "offense_personnel",
        "n_offense",
    )
    _validate_enrichment_keys(selected, key=("game_id", "play_id"), label="participation")
    eligible = pbp.filter(
        pl.col("team_id").is_not_null()
        & pl.col("play_type").is_in(["pass", "run"])
        & (pl.col("two_point_attempt").fill_null(0) != 1)
        & (pl.col("qb_kneel").fill_null(0) != 1)
    ).select("game_id", "play_id", "season", "team_id")
    matched = (
        selected.join(eligible, on=["game_id", "play_id"], how="inner", validate="1:1")
        .with_columns(
            pl.col("possession_team")
            .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
            .alias("participation_team_id"),
            pl.col("offense_formation").str.to_uppercase(),
            pl.col("offense_personnel")
            .map_elements(
                parse_offense_personnel,
                return_dtype=pl.Struct(
                    {
                        "personnel_group": pl.String,
                        "running_backs": pl.Int64,
                        "tight_ends": pl.Int64,
                        "wide_receivers": pl.Int64,
                        "parse_reason": pl.String,
                    }
                ),
            )
            .alias("personnel"),
        )
        .unnest("personnel")
    )
    mismatch = matched.filter(
        pl.col("participation_team_id").is_null()
        | (pl.col("participation_team_id") != pl.col("team_id"))
    )
    if mismatch.height:
        sample = (
            mismatch.select("game_id", "play_id", "possession_team", "team_id").head(5).to_dicts()
        )
        raise ValueError(f"participation/PBP team mismatch; sample={sample}")

    parsed = matched.filter(pl.col("personnel_group").is_not_null())
    personnel_denominators = parsed.group_by("team_id", "season").agg(
        pl.len().alias("eligible_plays")
    )
    personnel_groups = parsed.select("personnel_group").unique().sort("personnel_group")
    personnel = (
        personnel_denominators.join(personnel_groups, how="cross")
        .join(
            parsed.group_by("team_id", "season", "personnel_group").agg(
                pl.len().alias("raw_count")
            ),
            on=["team_id", "season", "personnel_group"],
            how="left",
            validate="1:1",
        )
        .with_columns(pl.col("raw_count").fill_null(0))
        .with_columns(
            pl.lit("personnel_group").alias("profile_family"),
            (pl.lit("personnel_") + pl.col("personnel_group") + pl.lit("_rate")).alias(
                "feature_name"
            ),
            (pl.col("raw_count") / pl.col("eligible_plays")).alias("raw_value"),
            pl.lit("nflverse_participation").alias("source_dataset"),
            pl.lit(source_hash).alias("source_hash"),
            pl.lit("explicit-offense-personnel-v1").alias("definition_version"),
            pl.lit(None, dtype=pl.String).alias("missingness_reason"),
        )
        .select(PROFILE_COLUMNS)
        .sort("season", "team_id", "feature_name")
    )
    family_contracts = (
        ("personnel_family_11_rate", (pl.col("running_backs") == 1) & (pl.col("tight_ends") == 1)),
        ("personnel_family_multiple_te_rate", pl.col("tight_ends") >= 2),
        ("personnel_family_multiple_back_rate", pl.col("running_backs") >= 2),
        (
            "personnel_family_spread_rate",
            (pl.col("running_backs") <= 1)
            & (pl.col("tight_ends") <= 1)
            & (pl.col("wide_receivers") >= 3),
        ),
        (
            "personnel_family_heavy_rate",
            (pl.col("running_backs") >= 2) | (pl.col("tight_ends") >= 2),
        ),
        ("personnel_family_empty_backfield_rate", pl.col("running_backs") == 0),
    )
    families = pl.concat(
        [
            _profile_rate(
                parsed,
                family="personnel_family",
                feature=feature,
                hit=predicate,
                source_dataset="nflverse_participation",
                source_hash=source_hash,
                definition_version="personnel-family-v1",
            )
            for feature, predicate in family_contracts
        ],
        how="vertical_relaxed",
    )
    explicit_formation = matched.filter(pl.col("offense_formation").is_not_null())
    formation_values = sorted(explicit_formation["offense_formation"].unique().to_list())
    formations = pl.concat(
        [
            _profile_rate(
                explicit_formation,
                family="formation",
                feature=f"formation_{value.lower().replace(' ', '_')}_rate",
                hit=pl.col("offense_formation") == value,
                source_dataset="nflverse_participation",
                source_hash=source_hash,
                definition_version="explicit-formation-v1",
            )
            for value in formation_values
        ],
        how="vertical_relaxed",
    )
    missingness = (
        matched.group_by("team_id", "season")
        .agg(
            pl.len().alias("matched_plays"),
            pl.col("personnel_group").is_not_null().sum().alias("parsed_personnel_plays"),
            pl.col("offense_formation").is_not_null().sum().alias("formation_plays"),
            (pl.col("n_offense") == 11).sum().alias("eleven_player_plays"),
        )
        .sort("season", "team_id")
    )
    return personnel, families, formations, missingness


def build_ftn_profiles(
    ftn: pl.DataFrame, pbp: pl.DataFrame, source_hash: str
) -> tuple[pl.DataFrame, pl.DataFrame]:
    selected = ftn.select(
        pl.col("nflverse_game_id").alias("game_id"),
        pl.col("nflverse_play_id").cast(pl.Int64).alias("play_id"),
        "season",
        "week",
        "qb_location",
        "is_motion",
        "is_play_action",
        "is_screen_pass",
        "is_rpo",
    )
    _validate_enrichment_keys(selected, key=("game_id", "play_id"), label="FTN")
    eligible = pbp.filter(
        pl.col("team_id").is_not_null()
        & pl.col("play_type").is_in(["pass", "run"])
        & (pl.col("two_point_attempt").fill_null(0) != 1)
        & (pl.col("qb_kneel").fill_null(0) != 1)
    ).select("game_id", "play_id", "team_id", pl.col("season").alias("pbp_season"))
    matched = selected.join(eligible, on=["game_id", "play_id"], how="inner", validate="1:1")
    mismatch = matched.filter(pl.col("season") != pl.col("pbp_season"))
    if mismatch.height:
        raise ValueError(f"FTN/PBP season mismatch; rows={mismatch.height}")
    mechanic_contracts = (
        ("motion_rate", "is_motion"),
        ("play_action_rate", "is_play_action"),
        ("screen_rate", "is_screen_pass"),
        ("rpo_rate", "is_rpo"),
    )
    mechanics = pl.concat(
        [
            _profile_rate(
                matched.filter(pl.col(column).is_not_null()),
                family="mechanic",
                feature=feature,
                hit=pl.col(column).cast(pl.Boolean),
                source_dataset="nflverse_ftn_charting",
                source_hash=source_hash,
                definition_version="explicit-ftn-flag-v1",
            )
            for feature, column in mechanic_contracts
        ],
        how="vertical_relaxed",
    )
    location = matched.filter(pl.col("qb_location").is_in(["S", "U", "P"]))
    formations = pl.concat(
        [
            _profile_rate(
                location,
                family="formation",
                feature=feature,
                hit=pl.col("qb_location") == code,
                source_dataset="nflverse_ftn_charting",
                source_hash=source_hash,
                definition_version="explicit-ftn-qb-location-v1",
            )
            for feature, code in (
                ("ftn_shotgun_rate", "S"),
                ("ftn_under_center_rate", "U"),
                ("ftn_pistol_rate", "P"),
            )
        ],
        how="vertical_relaxed",
    )
    return mechanics, formations


def build_feature_availability(
    profiles: pl.DataFrame,
    participation_missingness: pl.DataFrame,
) -> pl.DataFrame:
    """Classify candidate fields explicitly; coverage never promotes a causal feature."""

    core = {
        "shotgun_rate",
        "no_huddle_rate",
        "pass_rate",
        "expected_pass_rate",
        "proe_mean",
        "early_down_pass_rate",
        "neutral_pass_rate",
        "target_depth_short_rate",
        "target_depth_intermediate_rate",
        "target_depth_deep_rate",
        "average_air_yards",
        "scramble_rate",
    }
    experimental = {
        "motion_rate",
        "play_action_rate",
        "screen_rate",
        "rpo_rate",
        "ftn_shotgun_rate",
        "ftn_under_center_rate",
        "ftn_pistol_rate",
    }
    records: list[dict[str, Any]] = []
    source_fields = {
        "nflverse_participation": "offense_personnel|offense_formation|n_offense",
        "nflverse_ftn_charting": ("qb_location|is_motion|is_play_action|is_screen_pass|is_rpo"),
        "nflverse_pbp": (
            "play_type|shotgun|no_huddle|xpass|pass_oe|down|yardline_100|"
            "game_seconds_remaining|score_differential|air_yards|pass_location|"
            "qb_scramble|epa|success"
        ),
        "none": "none",
    }
    for feature in sorted(profiles["feature_name"].unique().to_list()):
        frame = profiles.filter(pl.col("feature_name") == feature)
        seasons = sorted(frame["season"].unique().to_list())
        observed_cells = frame.select("team_id", "season").n_unique()
        possible_cells = sum(32 for _ in range(min(seasons), max(seasons) + 1))
        coverage = observed_cells / possible_cells if possible_cells else 0.0
        if feature in core and coverage >= MIN_CORE_TEAM_SEASON_COVERAGE:
            status = "CORE"
            rationale = "broad structured coverage; retrospective descriptive scheme input"
        elif feature in experimental:
            status = "EXPERIMENTAL"
            rationale = "structured but short 2022-2025 FTN history"
        else:
            status = "DESCRIPTIVE"
            rationale = "structured descriptive field; limited history, coverage, or rarity"
        first = frame.sort("season", "team_id").row(0, named=True)
        records.append(
            {
                "feature_name": feature,
                "profile_family": first["profile_family"],
                "status": status,
                "first_season": min(seasons),
                "last_season": max(seasons),
                "observed_team_seasons": observed_cells,
                "possible_team_seasons_in_source_window": possible_cells,
                "team_season_coverage": coverage,
                "total_eligible_plays": int(frame["eligible_plays"].sum()),
                "source_dataset": first["source_dataset"],
                "source_fields": source_fields.get(
                    first["source_dataset"], "fixture_or_external_contract"
                ),
                "definition_version": first["definition_version"],
                "missingness_rule": "null outside explicit structured-source coverage",
                "use_restriction": "research-only; no causal ownership or final equation",
                "rationale": rationale,
            }
        )
    personnel_coverage = (
        float(participation_missingness["parsed_personnel_plays"].sum())
        / float(participation_missingness["matched_plays"].sum())
        if participation_missingness.height
        else 0.0
    )
    records.extend(
        [
            {
                "feature_name": "designed_qb_run_rate",
                "profile_family": "qb_usage",
                "status": "UNAVAILABLE",
                "first_season": None,
                "last_season": None,
                "observed_team_seasons": 0,
                "possible_team_seasons_in_source_window": 512,
                "team_season_coverage": 0.0,
                "total_eligible_plays": 0,
                "source_dataset": "none",
                "source_fields": "none",
                "definition_version": "unavailable-v1",
                "missingness_rule": (
                    "do not infer designed runs from play text or non-scramble rushes"
                ),
                "use_restriction": "unavailable; excluded from research fingerprints",
                "rationale": "no approved structured field cleanly separates designed QB runs",
            },
            {
                "feature_name": "personnel_parse_coverage",
                "profile_family": "data_quality",
                "status": "DESCRIPTIVE",
                "first_season": 2016,
                "last_season": 2025,
                "observed_team_seasons": participation_missingness.height,
                "possible_team_seasons_in_source_window": 320,
                "team_season_coverage": personnel_coverage,
                "total_eligible_plays": int(participation_missingness["matched_plays"].sum()),
                "source_dataset": "nflverse_participation",
                "source_fields": source_fields["nflverse_participation"],
                "definition_version": "explicit-offense-personnel-v1",
                "missingness_rule": "invalid or non-offensive strings remain unparsed",
                "use_restriction": "quality diagnostic only",
                "rationale": "reports the denominator actually parseable without heuristics",
            },
        ]
    )
    return pl.DataFrame(records).sort("profile_family", "feature_name")


def build_scheme_fingerprints(profiles: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create deterministic wide team-season fingerprints with raw and within-season z values."""

    choices = profiles.filter(pl.col("profile_family") != "outcome")
    if choices.select("team_id", "season", "feature_name").n_unique() != choices.height:
        raise ValueError("scheme profiles contain duplicate team-season-feature keys")
    standardized = choices.with_columns(
        pl.when(pl.col("raw_value").std(ddof=0).over("season") > 0)
        .then(
            (pl.col("raw_value") - pl.col("raw_value").mean().over("season"))
            / pl.col("raw_value").std(ddof=0).over("season")
        )
        .otherwise(None)
        .alias("z_value")
    )
    long = standardized.rename({"z_value": "standardized_value"}).sort(
        "season", "team_id", "profile_family", "feature_name"
    )
    raw = long.pivot(on="feature_name", index=["team_id", "season"], values="raw_value")
    z = long.with_columns((pl.col("feature_name") + pl.lit("_z")).alias("feature_name")).pivot(
        on="feature_name", index=["team_id", "season"], values="standardized_value"
    )
    wide = raw.join(z, on=["team_id", "season"], how="full", coalesce=True).sort(
        "season", "team_id"
    )
    return wide, long


def build_scheme_feature_correlations(fingerprints: pl.DataFrame) -> pl.DataFrame:
    features = sorted(
        column
        for column in fingerprints.columns
        if column not in {"team_id", "season"} and not column.endswith("_z")
    )
    records: list[dict[str, Any]] = []
    for index, left in enumerate(features):
        for right in features[index + 1 :]:
            pairs = fingerprints.drop_nulls([left, right])
            if pairs.height < 20:
                continue
            correlation = _pearson(pairs[left].to_list(), pairs[right].to_list())
            records.append(
                {
                    "left_feature": left,
                    "right_feature": right,
                    "paired_team_seasons": pairs.height,
                    "pearson": correlation,
                    "absolute_pearson": abs(correlation) if correlation is not None else None,
                    "action": "document_only_no_feature_dropped",
                }
            )
    return pl.DataFrame(records).sort(
        "absolute_pearson", "left_feature", "right_feature", descending=[True, False, False]
    )


def build_coach_role_scheme_associations(
    assignments: list[dict[str, str]], fingerprints: pl.DataFrame
) -> pl.DataFrame:
    frame = pl.DataFrame(assignments, infer_schema_length=None).with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        (pl.col("is_interim") == "true").alias("is_interim"),
        (pl.col("is_shared") == "true").alias("is_shared"),
        (pl.col("is_retained") == "true").alias("is_retained"),
    )
    verified = frame.filter(
        (pl.col("verification_status") == "verified")
        & pl.col("primary_source_url").is_not_null()
        & (pl.col("primary_source_url").str.strip_chars() != "")
    )
    associated = verified.join(
        fingerprints, on=["team_id", "season"], how="inner", validate="m:1"
    ).with_columns(
        pl.lit("team_season_context").alias("scheme_observation_grain"),
        pl.lit(False).alias("exact_weekly_scheme_ownership"),
        ((pl.col("end_week") - pl.col("start_week") + 1) * 50 >= MIN_PERSONNEL_TEAM_PLAYS).alias(
            "interval_specific_research_feasible_proxy"
        ),
        pl.lit(
            "full team-season fingerprint; assignment interval preserved; "
            "no equal or causal ownership"
        ).alias("attribution_limitation"),
    )
    if associated["assignment_key"].n_unique() != associated.height:
        raise ValueError("scheme association lost assignment grain")
    return associated.sort("role", "season", "team_id", "start_week", "assignment_key")


def build_scheme_stability(fingerprints: pl.DataFrame, associations: pl.DataFrame) -> pl.DataFrame:
    features = sorted(
        column
        for column in fingerprints.columns
        if column not in {"team_id", "season"} and not column.endswith("_z")
    )
    records: list[dict[str, Any]] = []
    previous = fingerprints.with_columns((pl.col("season") + 1).alias("season"))
    team_pairs = fingerprints.join(
        previous,
        on=["team_id", "season"],
        how="inner",
        suffix="_prior",
        validate="1:1",
    )
    for feature in features:
        available = team_pairs.drop_nulls([feature, f"{feature}_prior"])
        records.append(
            {
                "comparison": "same_team_year_over_year",
                "role": None,
                "feature_name": feature,
                "pairs": available.height,
                "pearson": _pearson(
                    available[f"{feature}_prior"].to_list(), available[feature].to_list()
                ),
                "chronology": "season_minus_1_to_season",
            }
        )
    compact = associations.select("coach_id", "role", "team_id", "season", *features).unique(
        ["coach_id", "role", "team_id", "season"]
    )
    prior = compact.with_columns((pl.col("season") + 1).alias("season"))
    coach_pairs = compact.join(
        prior,
        on=["coach_id", "role", "season"],
        how="inner",
        suffix="_prior",
        validate="m:m",
    )
    for role in sorted(compact["role"].unique().to_list()):
        role_pairs = coach_pairs.filter(pl.col("role") == role)
        for feature in features:
            available = role_pairs.drop_nulls([feature, f"{feature}_prior"])
            records.append(
                {
                    "comparison": "same_coach_role_year_over_year",
                    "role": role,
                    "feature_name": feature,
                    "pairs": available.height,
                    "pearson": _pearson(
                        available[f"{feature}_prior"].to_list(), available[feature].to_list()
                    ),
                    "chronology": "consecutive_seasons_only",
                }
            )
    return pl.DataFrame(records).sort("comparison", "role", "feature_name", nulls_last=True)


def _movement_roles(associations: pl.DataFrame) -> pl.DataFrame:
    base = associations.select(
        "coach_id", "coach_canonical_name", "role", "team_id", "season"
    ).unique()
    grouped = base.group_by("coach_id", "coach_canonical_name", "team_id", "season").agg(
        pl.col("role").unique().sort().alias("roles")
    )
    additions: list[pl.DataFrame] = []
    for synthetic, required in (
        ("offensive_coordinator+play_caller", {"offensive_coordinator", "play_caller"}),
        ("head_coach+play_caller", {"head_coach", "play_caller"}),
    ):
        selected = grouped.filter(
            pl.col("roles").map_elements(
                lambda values, needed=required: needed.issubset(set(values)),
                return_dtype=pl.Boolean,
            )
        ).select("coach_id", "coach_canonical_name", "team_id", "season")
        if selected.height:
            additions.append(
                selected.with_columns(pl.lit(synthetic).alias("role")).select(base.columns)
            )
    return pl.concat([base, *additions], how="vertical_relaxed").sort(
        "role", "coach_id", "season", "team_id"
    )


def _scheme_distance(left: np.ndarray, right: np.ndarray) -> dict[str, float | None]:
    return {
        "euclidean": float(np.linalg.norm(left - right)),
        "manhattan": float(np.abs(left - right).sum()),
        "cosine": _cosine_distance(left, right),
        "correlation": None
        if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0
        else float(1 - np.corrcoef(left, right)[0, 1]),
    }


def build_scheme_moves(
    fingerprints: pl.DataFrame, associations: pl.DataFrame
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """Audit all consecutive-season verified role moves without selecting a final metric."""

    role_rows = _movement_roles(associations)
    lookup = {(row["team_id"], int(row["season"])): row for row in fingerprints.to_dicts()}
    z_features = sorted(column for column in fingerprints.columns if column.endswith("_z"))
    moves: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    prior_roles = role_rows.rename(
        {
            "coach_canonical_name": "prior_coach_name",
            "team_id": "prior_team_id",
            "season": "prior_season",
        }
    )
    transitions = (
        role_rows.join(prior_roles, on=["role", "coach_id"], how="inner", validate="m:m")
        .filter(
            (pl.col("season") == pl.col("prior_season") + 1)
            & (pl.col("team_id") != pl.col("prior_team_id"))
        )
        .sort("role", "coach_id", "season", "prior_team_id", "team_id")
    )
    for current in transitions.to_dicts():
        if current:
            season = int(current["season"])
            prior = {
                "season": current["prior_season"],
                "team_id": current["prior_team_id"],
            }
            old = lookup.get((prior["team_id"], season - 1))
            destination_before = lookup.get((current["team_id"], season - 1))
            destination_after = lookup.get((current["team_id"], season))
            if not all((old, destination_before, destination_after)):
                continue
            available = [
                feature
                for feature in z_features
                if all(
                    _finite(row.get(feature)) is not None
                    for row in (old, destination_before, destination_after)
                )
            ]
            if len(available) < 3:
                continue
            old_vector = np.asarray([old[feature] for feature in available], dtype=float)
            before_vector = np.asarray(
                [destination_before[feature] for feature in available], dtype=float
            )
            after_vector = np.asarray(
                [destination_after[feature] for feature in available], dtype=float
            )
            before = _scheme_distance(old_vector, before_vector)
            after = _scheme_distance(old_vector, after_vector)
            move_id = (
                f"{current['role']}:{current['coach_id']}:{season}:"
                f"{prior['team_id']}->{current['team_id']}"
            )
            moves.append(
                {
                    "move_id": move_id,
                    "role": current["role"],
                    "coach_id": current["coach_id"],
                    "coach_name": current["coach_canonical_name"],
                    "season": season,
                    "origin_team_id": prior["team_id"],
                    "destination_team_id": current["team_id"],
                    "feature_count": len(available),
                    "euclidean_before": before["euclidean"],
                    "euclidean_after": after["euclidean"],
                    "euclidean_adoption": before["euclidean"] - after["euclidean"],
                    "manhattan_before": before["manhattan"],
                    "manhattan_after": after["manhattan"],
                    "manhattan_adoption": before["manhattan"] - after["manhattan"],
                    "cosine_before": before["cosine"],
                    "cosine_after": after["cosine"],
                    "correlation_before": before["correlation"],
                    "correlation_after": after["correlation"],
                    "chronology": "origin_S-1_vs_destination_S-1_and_S",
                    "causal_claim": False,
                }
            )
            for feature in available:
                raw = feature.removesuffix("_z")
                before_gap = abs(destination_before[feature] - old[feature])
                after_gap = abs(destination_after[feature] - old[feature])
                feature_rows.append(
                    {
                        "move_id": move_id,
                        "role": current["role"],
                        "coach_id": current["coach_id"],
                        "season": season,
                        "feature_name": raw,
                        "origin_prior_z": old[feature],
                        "destination_prior_z": destination_before[feature],
                        "destination_after_z": destination_after[feature],
                        "destination_change_z": destination_after[feature]
                        - destination_before[feature],
                        "distance_change_toward_origin": before_gap - after_gap,
                        "moved_toward_origin": after_gap < before_gap,
                    }
                )
    move_frame = pl.DataFrame(moves) if moves else pl.DataFrame()
    feature_frame = pl.DataFrame(feature_rows) if feature_rows else pl.DataFrame()
    if move_frame.is_empty():
        empty = pl.DataFrame()
        return move_frame, empty, feature_frame, empty, empty, empty
    portability = (
        move_frame.group_by("role")
        .agg(
            pl.len().alias("moves"),
            pl.col("coach_id").n_unique().alias("coaches"),
            pl.col("euclidean_adoption").mean().alias("mean_euclidean_adoption"),
            pl.col("manhattan_adoption").mean().alias("mean_manhattan_adoption"),
            (pl.col("euclidean_adoption") > 0).mean().alias("share_moving_toward_origin"),
        )
        .with_columns(pl.lit("descriptive_association_only").alias("interpretation"))
        .sort("role")
    )
    feature_portability = (
        feature_frame.group_by("role", "feature_name")
        .agg(
            pl.len().alias("moves"),
            pl.col("distance_change_toward_origin").mean().alias("mean_adoption"),
            pl.col("moved_toward_origin").mean().alias("share_toward_origin"),
        )
        .sort("role", "feature_name")
    )

    placebo_rows: list[dict[str, Any]] = []
    all_rows = fingerprints.to_dicts()
    for move in move_frame.to_dicts():
        season = int(move["season"])
        before = lookup[(move["destination_team_id"], season - 1)]
        after = lookup[(move["destination_team_id"], season)]
        available = [
            feature
            for feature in z_features
            if all(_finite(row.get(feature)) is not None for row in (before, after))
        ]
        candidates = [
            row
            for row in all_rows
            if row["season"] == season - 1
            and row["team_id"] not in {move["origin_team_id"], move["destination_team_id"]}
            and all(_finite(row.get(feature)) is not None for feature in available)
        ]
        if not candidates or len(available) < 3:
            continue
        rng = np.random.default_rng(_stable_seed(f"move-placebo:{move['move_id']}"))
        before_vector = np.asarray([before[feature] for feature in available])
        after_vector = np.asarray([after[feature] for feature in available])
        draws: list[float] = []
        for index in rng.integers(0, len(candidates), size=PLACEBO_REPLICATES):
            pseudo = np.asarray([candidates[index][feature] for feature in available])
            draws.append(
                float(
                    np.linalg.norm(before_vector - pseudo) - np.linalg.norm(after_vector - pseudo)
                )
            )
        placebo_rows.append(
            {
                "move_id": move["move_id"],
                "role": move["role"],
                "observed_adoption": move["euclidean_adoption"],
                "placebo_replicates": len(draws),
                "placebo_mean": float(np.mean(draws)),
                "placebo_low": float(np.quantile(draws, 0.025)),
                "placebo_high": float(np.quantile(draws, 0.975)),
                "observed_minus_placebo_mean": move["euclidean_adoption"] - float(np.mean(draws)),
            }
        )
    placebos = pl.DataFrame(placebo_rows).sort("role", "move_id")

    persistence_rows: list[dict[str, Any]] = []
    for move in move_frame.to_dicts():
        season = int(move["season"])
        old = lookup.get((move["origin_team_id"], season - 1))
        current = lookup.get((move["destination_team_id"], season))
        following = lookup.get((move["destination_team_id"], season + 1))
        if not all((old, current, following)):
            continue
        available = [
            feature
            for feature in z_features
            if all(_finite(row.get(feature)) is not None for row in (old, current, following))
        ]
        if len(available) < 3:
            continue
        old_v = np.asarray([old[feature] for feature in available])
        current_v = np.asarray([current[feature] for feature in available])
        following_v = np.asarray([following[feature] for feature in available])
        persistence_rows.append(
            {
                "move_id": move["move_id"],
                "role": move["role"],
                "coach_id": move["coach_id"],
                "season": season,
                "feature_count": len(available),
                "distance_at_move": float(np.linalg.norm(current_v - old_v)),
                "distance_following_season": float(np.linalg.norm(following_v - old_v)),
                "persistence_change": float(
                    np.linalg.norm(current_v - old_v) - np.linalg.norm(following_v - old_v)
                ),
                "coach_remained_with_destination": bool(
                    role_rows.filter(
                        (pl.col("role") == move["role"])
                        & (pl.col("coach_id") == move["coach_id"])
                        & (pl.col("team_id") == move["destination_team_id"])
                        & (pl.col("season") == season + 1)
                    ).height
                ),
            }
        )
    persistence = pl.DataFrame(persistence_rows).sort("role", "move_id")
    multiple = (
        move_frame.group_by("role", "coach_id", "coach_name")
        .agg(
            pl.len().alias("moves"),
            pl.col("season").sort().cast(pl.String).str.join("|").alias("move_seasons"),
            pl.col("destination_team_id").sort_by("season").str.join("|").alias("destinations"),
            pl.col("euclidean_adoption").mean().alias("mean_euclidean_adoption"),
        )
        .filter(pl.col("moves") >= 2)
        .sort("role", "coach_id")
    )
    return (
        move_frame.sort("role", "season", "coach_id"),
        portability,
        feature_portability,
        placebos,
        persistence,
        multiple,
    )


def rebuild_new_pcae_attribution(
    project_root: Path,
    evidence: pl.DataFrame,
    coverage: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, str]]:
    """Run the unchanged PCAE model only for newly qualifying verified intervals."""

    sources = _sources(project_root)
    existing_root = project_root / "research/coach_effect/outputs/checkpoint_11b"
    existing_version = _latest(existing_root)
    existing = pl.read_csv(existing_root / existing_version / "historical_pcae.csv")
    candidate_cells = coverage.filter(
        (pl.col("starting_status") != "verified") & pl.col("researched")
    ).select("season", "team_id")
    candidate_intervals = (
        evidence.filter(pl.col("interval_status") == "verified")
        .join(candidate_cells, on=["season", "team_id"], how="inner", validate="m:1")
        .with_columns(
            (
                pl.col("season").cast(pl.String)
                + "-"
                + pl.col("team_id")
                + "-play_caller-"
                + pl.col("start_week").cast(pl.String).str.pad_start(2, "0")
                + "-"
                + pl.col("end_week").cast(pl.String).str.pad_start(2, "0")
                + "-"
                + pl.col("coach_id").str.strip_prefix("coach-")
            ).alias("assignment_key"),
            pl.lit("play_caller").alias("role"),
            pl.lit("verified").alias("verification_status"),
            pl.lit("high").alias("confidence_level"),
            pl.lit("source_verified_weeks").alias("interval_basis"),
            pl.lit(False).alias("is_interim"),
            pl.lit(False).alias("is_retained"),
            pl.col("primary_source_url"),
        )
        .select(
            "assignment_key",
            "season",
            "team_id",
            "coach_id",
            "coach_canonical_name",
            "role",
            "start_week",
            "end_week",
            "is_interim",
            "is_shared",
            "is_retained",
            "verification_status",
            "confidence_level",
            "interval_basis",
            "primary_source_url",
        )
    )
    seasons = sorted(candidate_intervals["season"].unique().to_list())
    if not seasons:
        season_counts = (
            existing.group_by("season")
            .agg(pl.col("attributed_play_count").sum().alias("attributed_plays"))
            .sort("season")
        )
        return existing, season_counts, {}
    frames: dict[int, pl.DataFrame] = {}
    source_hashes: dict[str, str] = {}
    max_target = max(seasons)
    for season in range(1999, max_target + 1):
        path = sources.pbp_root / f"season={season}" / "play_by_play.parquet"
        prepared, _ = prepare_historical_plays(pl.read_parquet(path, columns=PBP_COLUMNS))
        frames[season] = prepared
        source_hashes[str(path.relative_to(project_root))] = _sha256(path)
    additions: list[pl.DataFrame] = []
    for season in seasons:
        training = pl.concat(
            [frames[value] for value in frames if value < season], how="vertical_relaxed"
        )
        _, scored = fit_historical_models(training, frames[season], season)
        attributed, _ = attribute_verified_calls(
            scored, candidate_intervals.filter(pl.col("season") == season)
        )
        if attributed.height:
            additions.append(aggregate_historical_pcae(attributed))
    new_pcae = pl.concat(additions, how="vertical_relaxed") if additions else pl.DataFrame()
    existing_key = ["coach_id", "team_id", "season", "start_week", "end_week"]
    if (
        new_pcae.height
        and existing.join(new_pcae.select(existing_key), on=existing_key, how="inner").height
    ):
        raise ValueError("new PCAE attribution overlaps the frozen Checkpoint Eleven-B output")
    if new_pcae.height:
        new_pcae = new_pcae.with_columns(
            pl.lit("prompt8-pending-content-version").alias("data_version"),
            pl.lit(True).alias("shared_or_ambiguous_plays_excluded"),
        ).select(existing.columns)
        combined = pl.concat([existing, new_pcae], how="vertical_relaxed")
    else:
        combined = existing
    if combined.filter(pl.col("is_shared")).height:
        raise ValueError("shared play-calling was individually attributed")
    season_counts = (
        combined.group_by("season")
        .agg(
            pl.col("attributed_play_count").sum().alias("attributed_plays"),
            pl.col("coach_id").n_unique().alias("attributed_callers"),
            pl.len().alias("caller_intervals"),
        )
        .sort("season")
    )
    return (
        combined.sort("season", "team_id", "coach_id", "start_week"),
        season_counts,
        source_hashes,
    )


def build_common_qp_availability(
    project_root: Path,
    assignments: list[dict[str, str]],
    pcae: pl.DataFrame,
    coverage: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Recompute availability only; no Models 1-6 or equation weights are fitted."""

    caller = (
        pl.DataFrame(assignments, infer_schema_length=None)
        .with_columns(
            pl.col("season", "start_week", "end_week").cast(pl.Int64),
            (pl.col("is_shared") == "true").alias("is_shared"),
        )
        .filter(
            (pl.col("role") == "play_caller")
            & (pl.col("verification_status") == "verified")
            & (pl.col("interval_basis") != "season_designation")
            & ~pl.col("is_shared")
        )
    )
    enhancement = _sources(project_root)
    game_path = enhancement.pae_path.parent / "canonical_qb_game_performance.parquet"
    games = (
        pl.read_parquet(game_path)
        .select("season", "week", "player_id", "team_id", "dropbacks")
        .with_columns(
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase(),
            pl.col("dropbacks").cast(pl.Float64),
        )
    )
    exposure = (
        games.join(caller, on=["season", "team_id"], how="inner", validate="m:m")
        .filter(pl.col("week").is_between(pl.col("start_week"), pl.col("end_week")))
        .group_by("coach_id", "coach_canonical_name", "team_id", "season", "player_id")
        .agg(pl.col("dropbacks").sum().alias("q_exposure"))
    )
    candidate = pl.read_csv(
        project_root
        / "research/coach_effect/outputs/checkpoint_12"
        / PROMPT6_VERSION
        / "joined_research_table.csv"
    )
    q_signal = (
        candidate.select(
            "player_id",
            "team_id",
            "season",
            "quarterback_name",
            "full_season_q_development_signal",
        )
        .unique()
        .with_columns(
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase(),
            pl.col("full_season_q_development_signal").cast(pl.Float64, strict=False),
        )
    )
    q = exposure.join(
        q_signal, on=["player_id", "team_id", "season"], how="left", validate="m:1"
    ).filter(pl.col("full_season_q_development_signal").is_not_null())
    q_season = q.group_by("coach_id", "coach_canonical_name", "team_id", "season").agg(
        (
            (pl.col("full_season_q_development_signal") * pl.col("q_exposure")).sum()
            / pl.col("q_exposure").sum()
        ).alias("q_development_signal"),
        pl.col("q_exposure").sum(),
        pl.col("player_id").n_unique().alias("quarterbacks"),
        pl.col("player_id").unique().sort().str.join("|").alias("player_ids"),
    )
    p_season = pcae.group_by("coach_id", "coach_canonical_name", "team_id", "season").agg(
        (
            (pl.col("pcae") * pl.col("attributed_play_count")).sum()
            / pl.col("attributed_play_count").sum()
        ).alias("pcae"),
        pl.col("attributed_play_count").sum().alias("p_exposure"),
    )
    common = q_season.join(
        p_season,
        on=["coach_id", "coach_canonical_name", "team_id", "season"],
        validate="1:1",
    ).sort("season", "coach_id", "team_id")
    history_rows: list[dict[str, Any]] = []
    for row in common.to_dicts():
        history = common.filter(
            (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
        )
        if history.is_empty():
            continue
        history_rows.append(
            {
                **row,
                "prior_common_coach_seasons": history.height,
                "history_max_season": int(history["season"].max()),
            }
        )
    future = pl.DataFrame(history_rows) if history_rows else pl.DataFrame()
    fold_rows: list[dict[str, Any]] = []
    for season in ANALYSIS_SEASONS:
        target = future.filter(pl.col("season") == season).height if future.height else 0
        training = future.filter(pl.col("season") < season).height if future.height else 0
        ending = coverage.filter(pl.col("season") == season)
        counts = dict(ending.group_by("ending_status").len().iter_rows())
        eligible = target >= 2 and training >= 10
        fold_rows.append(
            {
                "season": season,
                "common_qp_rows": common.filter(pl.col("season") == season).height,
                "future_target_rows": target,
                "prior_training_rows": training,
                "eligible_as_target": eligible,
                "reason": "eligible" if eligible else "requires_2_target_and_10_prior_rows",
                "verified_caller_cells": counts.get("verified", 0),
                "partial_caller_cells": counts.get("partial", 0),
                "provisional_caller_cells": counts.get("provisional", 0),
                "unresolved_caller_cells": counts.get("unresolved", 0),
            }
        )
    folds = pl.DataFrame(fold_rows)
    repeat = (
        common.group_by("coach_id", "coach_canonical_name")
        .agg(
            pl.col("season").n_unique().alias("seasons"),
            pl.col("team_id").n_unique().alias("teams"),
            pl.col("quarterbacks").sum().alias("quarterback_observations"),
            pl.col("season").sort().cast(pl.String).str.join("|").alias("season_list"),
        )
        .filter(pl.col("seasons") >= 2)
        .sort("coach_id")
    )
    qb_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []
    for group in common.partition_by("coach_id", as_dict=False):
        ordered = group.sort("season", "team_id").to_dicts()
        for prior, current in zip(ordered, ordered[1:], strict=False):
            if int(current["season"]) != int(prior["season"]) + 1:
                continue
            prior_players = set(str(prior["player_ids"]).split("|"))
            current_players = set(str(current["player_ids"]).split("|"))
            if prior_players != current_players:
                qb_rows.append(
                    {
                        "coach_id": current["coach_id"],
                        "prior_season": prior["season"],
                        "season": current["season"],
                        "prior_team_id": prior["team_id"],
                        "team_id": current["team_id"],
                        "prior_player_ids": "|".join(sorted(prior_players)),
                        "player_ids": "|".join(sorted(current_players)),
                    }
                )
            if prior["team_id"] != current["team_id"]:
                team_rows.append(
                    {
                        "coach_id": current["coach_id"],
                        "prior_season": prior["season"],
                        "season": current["season"],
                        "prior_team_id": prior["team_id"],
                        "team_id": current["team_id"],
                    }
                )
    different_qb = pl.DataFrame(qb_rows) if qb_rows else pl.DataFrame()
    different_team = pl.DataFrame(team_rows) if team_rows else pl.DataFrame()
    return common, folds, repeat, different_qb, different_team


def build_remaining_priority(
    project_root: Path, coverage: pl.DataFrame, evidence: pl.DataFrame
) -> pl.DataFrame:
    previous = pl.read_csv(
        project_root
        / "research/coach_effect/outputs/checkpoint_12_review"
        / PROMPT7_VERSION
        / "play_caller_verification_priority.csv"
    )
    researched = evidence.select("season", "team_id").unique()
    return (
        previous.join(researched, on=["season", "team_id"], how="anti")
        .drop("priority_rank", "current_status", "review_version")
        .join(
            coverage.select("season", "team_id", pl.col("ending_status").alias("current_status")),
            on=["season", "team_id"],
            validate="1:1",
        )
        .sort("priority_score", "season", "team_id", descending=[True, True, False])
        .with_row_index("priority_rank", offset=1)
        .with_columns(pl.lit("post_prompt8_batch_1").alias("priority_version"))
    )


def build_source_lineage(evidence: pl.DataFrame) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for row in evidence.to_dicts():
        for source_position, field in enumerate(
            ("primary_source_url", "secondary_source_url"), start=1
        ):
            if not row[field]:
                continue
            records.append(
                {
                    "season": row["season"],
                    "team_id": row["team_id"],
                    "coach_id": row["coach_id"],
                    "start_week": row["start_week"],
                    "end_week": row["end_week"],
                    "interval_status": row["interval_status"],
                    "cell_status": row["cell_status"],
                    "source_family": row["source_family"],
                    "source_position": source_position,
                    "source_url": row[field],
                    "access_date": SOURCE_ACCESS_DATE,
                    "evidence_summary": row["evidence_summary"],
                    "continuity_basis": row["continuity_basis"],
                    "false_positive_check": "explicit_play_calling_required",
                }
            )
    return pl.DataFrame(records).sort(
        "season", "team_id", "start_week", "coach_id", "source_position"
    )


def _verify_files(project_root: Path, hashes: dict[str, str]) -> None:
    changed = [
        relative
        for relative, digest in hashes.items()
        if _sha256(project_root / relative) != digest
    ]
    if changed:
        raise ValueError(f"Prompt 8 source bytes changed during build: {sorted(changed)}")


def _add_research_contract(frame: pl.DataFrame, data_version: str) -> pl.DataFrame:
    if frame.is_empty() and not frame.columns:
        return pl.DataFrame(
            schema={
                "research_data_version": pl.String,
                "research_only": pl.Boolean,
                "production_ranking": pl.Boolean,
            }
        )
    names = set(frame.columns)
    expressions: list[pl.Expr] = []
    if "research_data_version" not in names:
        expressions.append(pl.lit(data_version).alias("research_data_version"))
    if "research_only" not in names:
        expressions.append(pl.lit(True).alias("research_only"))
    if "production_ranking" not in names:
        expressions.append(pl.lit(False).alias("production_ranking"))
    contracted = frame.with_columns(*expressions) if expressions else frame
    float_columns = [
        name for name, dtype in contracted.schema.items() if dtype in {pl.Float32, pl.Float64}
    ]
    return contracted.with_columns(pl.col(float_columns).round(10)) if float_columns else contracted


def run_checkpoint_twelve_data_expansion(
    project_root: Path,
    output_root: Path | None = None,
    *,
    source_cache: Path | None = None,
    allow_network: bool = True,
) -> Prompt8Result:
    """Build Prompt 8 deterministic, research-only data-readiness artifacts."""

    evidence = load_and_validate_play_caller_evidence(project_root)
    coverage, new_cells, new_intervals = build_play_caller_coverage(project_root, evidence)
    assignments = build_prompt8_assignments(project_root, evidence)
    participation, ftn, cache_hashes = load_scheme_sources(
        project_root, source_cache=source_cache, allow_network=allow_network
    )
    pbp, pbp_hashes = load_scheme_pbp(project_root)
    tendencies, qb_usage, situations, outcomes = build_pbp_profiles(pbp, pbp_hashes)
    personnel, families, formations, participation_missingness = build_participation_profiles(
        participation,
        pbp,
        cache_hashes["nflverse_participation_2016_2025.parquet"],
    )
    mechanics, ftn_formations = build_ftn_profiles(
        ftn, pbp, cache_hashes["nflverse_ftn_2022_2025.parquet"]
    )
    formations = pl.concat([formations, ftn_formations], how="vertical_relaxed")
    all_profiles = pl.concat(
        [personnel, families, formations, mechanics, tendencies, qb_usage, situations, outcomes],
        how="vertical_relaxed",
    ).sort("season", "team_id", "profile_family", "feature_name")
    availability = build_feature_availability(all_profiles, participation_missingness)
    fingerprints_wide, fingerprints_long = build_scheme_fingerprints(all_profiles)
    correlations = build_scheme_feature_correlations(fingerprints_wide)
    associations = build_coach_role_scheme_associations(assignments, fingerprints_wide)
    stability = build_scheme_stability(fingerprints_wide, associations)
    (
        moves,
        portability,
        feature_portability,
        placebos,
        persistence,
        multiple_moves,
    ) = build_scheme_moves(fingerprints_wide, associations)
    del pbp

    historical_pcae, pcae_by_season, pcae_pbp_hashes = rebuild_new_pcae_attribution(
        project_root, evidence, coverage
    )
    common, folds, repeat, different_qb, different_team = build_common_qp_availability(
        project_root, assignments, historical_pcae, coverage
    )
    caller_counts = dict(coverage.group_by("ending_status").len().iter_rows())
    eligible_folds = folds.filter(pl.col("eligible_as_target")).height
    common_future = int(folds["future_target_rows"].sum())
    resampling_counts = {
        "seasons": common["season"].n_unique() if common.height else 0,
        "coaches": common["coach_id"].n_unique() if common.height else 0,
        "teams": common["team_id"].n_unique() if common.height else 0,
        "quarterbacks": int(common["quarterbacks"].sum()) if common.height else 0,
    }
    gates = {
        "verified_play_caller_coverage": caller_counts.get("verified", 0) >= PLAY_CALLER_GATE,
        "chronological_target_folds": eligible_folds >= TARGET_FOLD_GATE,
        "common_future_qp_rows": common_future >= COMMON_FUTURE_GATE,
        "resampling_feasibility": (
            resampling_counts["seasons"] >= 5
            and resampling_counts["coaches"] >= 20
            and resampling_counts["teams"] >= 20
            and resampling_counts["quarterbacks"] >= 30
        ),
    }
    readiness = pl.DataFrame(
        [
            {
                "gate": "A_verified_play_caller_coverage",
                "threshold": ">=256 verified cells",
                "observed": str(caller_counts.get("verified", 0)),
                "result": "PASS" if gates["verified_play_caller_coverage"] else "FAIL",
                "detail": "evidence standard was not weakened",
            },
            {
                "gate": "B_chronological_target_folds",
                "threshold": ">=5 eligible target seasons",
                "observed": str(eligible_folds),
                "result": "PASS" if gates["chronological_target_folds"] else "FAIL",
                "detail": "each target requires >=2 rows and >=10 strictly prior rows",
            },
            {
                "gate": "C_common_future_qp_rows",
                "threshold": ">=150 future target rows",
                "observed": str(common_future),
                "result": "PASS" if gates["common_future_qp_rows"] else "FAIL",
                "detail": "availability only; no final joint model fitted",
            },
            {
                "gate": "D_resampling_feasibility",
                "threshold": ">=5 seasons, >=20 coaches/teams, >=30 QB observations",
                "observed": json.dumps(resampling_counts, sort_keys=True),
                "result": "PASS" if gates["resampling_feasibility"] else "FAIL",
                "detail": "minimum units for season/coach/team/QB resampling",
            },
            {
                "gate": "FINAL_EQUATION_RERUN_READINESS",
                "threshold": "all four gates pass",
                "observed": "all_pass" if all(gates.values()) else "one_or_more_failed",
                "result": "READY" if all(gates.values()) else "NOT READY",
                "detail": "Prompt 8 stops at data readiness; no final equation was fitted",
            },
        ]
    )
    remaining = build_remaining_priority(project_root, coverage, evidence)
    lineage = build_source_lineage(evidence)

    sources = _sources(project_root, source_cache)
    input_paths = [
        project_root / EVIDENCE_FILE,
        project_root / "research/coach_effect/checkpoint_twelve_data_expansion.py",
        project_root / "research/coach_effect/checkpoint_eleven.py",
        project_root / "research/coach_effect/checkpoint_eleven_b.py",
        project_root / "research/coach_effect/config.py",
        sources.pae_path,
        sources.pae_path.parent / "canonical_qb_game_performance.parquet",
        project_root
        / "research/coach_effect/outputs/checkpoint_11b"
        / _latest(project_root / "research/coach_effect/outputs/checkpoint_11b")
        / "historical_pcae.csv",
        project_root
        / "research/coach_effect/outputs/checkpoint_12"
        / PROMPT6_VERSION
        / "joined_research_table.csv",
        project_root
        / "research/coach_effect/outputs/checkpoint_12_review"
        / PROMPT7_VERSION
        / "play_caller_verification_priority.csv",
        sources.source_cache / "nflverse_participation_2016_2025.parquet",
        sources.source_cache / "nflverse_ftn_2022_2025.parquet",
        *sorted((project_root / "data/manual").glob("*.csv")),
    ]
    input_hashes = {str(path.relative_to(project_root)): _sha256(path) for path in input_paths}
    input_hashes.update(pbp_hashes)
    input_hashes.update(pcae_pbp_hashes)
    identity = {
        "specification": PROMPT8_SPECIFICATION,
        "prompt6_version": PROMPT6_VERSION,
        "prompt7_version": PROMPT7_VERSION,
        "historical_data_version": sources.historical_version,
        "enhancement_data_version": sources.enhancement_version,
        "pcae_model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "pcae_play_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "call_value_formula": CALL_VALUE_FORMULA,
        "pcae_formula": PCAE_FORMULA,
        "play_call_features": PLAY_CALL_FEATURES,
        "analysis_seasons": ANALYSIS_SEASONS,
        "participation_seasons": PARTICIPATION_SEASONS,
        "ftn_seasons": FTN_SEASONS,
        "thresholds": {
            "play_caller_gate": PLAY_CALLER_GATE,
            "target_fold_gate": TARGET_FOLD_GATE,
            "common_future_gate": COMMON_FUTURE_GATE,
            "min_personnel_team_plays": MIN_PERSONNEL_TEAM_PLAYS,
            "placebo_replicates": PLACEBO_REPLICATES,
        },
        "dependencies": {
            "nflreadpy": nflreadpy.__version__,
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_hashes": dict(sorted(input_hashes.items())),
    }
    data_version = (
        "c12-data-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    historical_pcae = historical_pcae.with_columns(pl.lit(data_version).alias("data_version"))
    fingerprints_long = fingerprints_long.with_columns(
        pl.lit(sources.historical_version).alias("historical_source_version"),
        pl.lit(data_version).alias("build_version"),
    )
    outputs = {
        "play_caller_completeness.csv": coverage,
        "play_caller_evidence_review.csv": evidence,
        "new_verified_play_caller_intervals.csv": new_intervals,
        "play_caller_source_lineage.csv": lineage,
        "remaining_play_caller_priority.csv": remaining,
        "pcae_attribution_by_season.csv": pcae_by_season,
        "historical_pcae.csv": historical_pcae,
        "common_qp_availability.csv": common,
        "future_fold_matrix.csv": folds,
        "repeat_play_callers.csv": repeat,
        "different_qb_samples.csv": different_qb,
        "different_team_samples.csv": different_team,
        "scheme_feature_availability.csv": availability,
        "personnel_profiles.csv": personnel,
        "personnel_family_profiles.csv": families,
        "formation_profiles.csv": formations,
        "mechanic_profiles.csv": mechanics,
        "tendency_profiles.csv": tendencies,
        "qb_usage_profiles.csv": qb_usage,
        "situational_profiles.csv": situations,
        "outcome_profiles.csv": outcomes,
        "team_season_scheme_fingerprints.csv": fingerprints_long,
        "scheme_feature_correlations.csv": correlations,
        "coach_role_scheme_associations.csv": associations,
        "scheme_feature_stability.csv": stability,
        "scheme_moves.csv": moves,
        "scheme_portability.csv": portability,
        "scheme_feature_portability.csv": feature_portability,
        "scheme_specificity_placebos.csv": placebos,
        "scheme_persistence.csv": persistence,
        "multiple_move_coaches.csv": multiple_moves,
        "final_equation_readiness.csv": readiness,
    }
    if set(outputs) != set(OUTPUT_NAMES):
        raise ValueError("Prompt 8 output contract drift")
    outputs = {name: _add_research_contract(frame, data_version) for name, frame in outputs.items()}
    _verify_files(project_root, input_hashes)
    root = (
        output_root or project_root / "research/coach_effect/outputs/checkpoint_12_data_expansion"
    )
    destination = root / data_version
    temporary = root / f".{data_version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    for name in OUTPUT_NAMES:
        _write_csv(outputs[name], temporary / name)
    checksums = {name: _sha256(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "data_version": data_version,
        "research_only": True,
        "production_model": False,
        "production_ranking": False,
        "final_equation_fitted": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {name: outputs[name].height for name in OUTPUT_NAMES},
    }
    _write_json(temporary / "MANIFEST.json", manifest)
    _verify_files(project_root, input_hashes)
    if destination.exists():
        expected_files = {"MANIFEST.json", *OUTPUT_NAMES}
        actual_files = {path.name for path in destination.iterdir() if path.is_file()}
        if actual_files != expected_files:
            raise ValueError("existing Prompt 8 publication has unexpected files")
        for name in expected_files:
            if _sha256(destination / name) != _sha256(temporary / name):
                raise ValueError(f"existing Prompt 8 deterministic output differs: {name}")
        shutil.rmtree(temporary)
    else:
        temporary.replace(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "LATEST").write_text(data_version + "\n", encoding="utf-8")
    return Prompt8Result(
        output_path=destination,
        data_version=data_version,
        caller_coverage=outputs["play_caller_completeness.csv"],
        feature_availability=outputs["scheme_feature_availability.csv"],
        readiness=outputs["final_equation_readiness.csv"],
    )

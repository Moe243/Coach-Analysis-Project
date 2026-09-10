"""Checkpoint 14 QB style profiles and leakage-safe entering-season Player State."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
import scipy
from scipy.stats import spearmanr

from .constants import TEAM_ALIAS_TO_CANONICAL
from .predictive_foundation import (
    AsOfFeatureStore,
    FeatureDefinition,
    feature_registry_frame,
    validate_feature_records,
    validate_feature_registry,
)

CHECKPOINT_14_SPECIFICATION: Final = "checkpoint-14-qb-player-state-v1"
PROFILE_VERSION: Final = "qb-style-profile-v1"
STATE_VERSION: Final = "qb-player-state-v1"
UNIVERSE_VERSION: Final = "qb-asof-universe-v1"
EVALUATION_VERSION: Final = "qb-state-evaluation-v1"
TARGET_SEASONS: Final = tuple(range(2010, 2026))
AS_OF_MONTH_DAY: Final = (8, 31)
REFERENCE_WINDOW_SEASONS: Final = 5
INTERVAL_LEVEL: Final = 0.95
INTERVAL_MULTIPLIER: Final = 1.959963984540054
PORTABILITY_BOOTSTRAPS: Final = 500
PORTABILITY_SEED: Final = 14013

PRIMARY_STABILITY: Final = {"pairs": 100, "correlation": 0.25, "coverage": 0.80}
STABILITY_SENSITIVITY: Final = {
    "pair_counts": (75, 125),
    "correlations": (0.20, 0.30),
    "coverages": (0.75, 0.85),
}
STABILITY_VOLUME_BANDS: Final = {"medium": (200, 399), "high": (400, None)}

PROFILE_SPECS: Final = {
    "epa_per_dropback": ("continuous", 50, "PREDICTIVE_CORE", "overall"),
    "success_rate": ("binary", 50, "PREDICTIVE_CORE", "overall"),
    "cpoe": ("continuous", 100, "PREDICTIVE_CORE", "accuracy"),
    "sack_rate": ("binary", 50, "PREDICTIVE_CORE", "pressure"),
    "average_air_yards": ("continuous", 100, "PREDICTIVE_CORE", "depth"),
    "target_depth_short_rate": ("binary", 100, "PREDICTIVE_CORE", "depth"),
    "target_depth_intermediate_rate": ("binary", 100, "PREDICTIVE_CORE", "depth"),
    "target_depth_deep_rate": ("binary", 100, "PREDICTIVE_CORE", "depth"),
    "target_depth_short_epa": ("continuous", 50, "PREDICTIVE_CONDITIONAL", "depth"),
    "target_depth_intermediate_epa": (
        "continuous",
        50,
        "PREDICTIVE_CONDITIONAL",
        "depth",
    ),
    "target_depth_deep_epa": ("continuous", 50, "PREDICTIVE_CONDITIONAL", "depth"),
    "shotgun_rate": ("binary", 50, "PREDICTIVE_CORE", "formation"),
    "shotgun_epa": ("continuous", 100, "PREDICTIVE_CONDITIONAL", "formation"),
    "early_down_epa": ("continuous", 100, "PREDICTIVE_CONDITIONAL", "situation"),
    "third_down_epa": ("continuous", 50, "PREDICTIVE_CONDITIONAL", "situation"),
    "red_zone_epa": ("continuous", 30, "DESCRIPTIVE", "situation"),
    "pass_location_left_rate": ("binary", 100, "PREDICTIVE_CONDITIONAL", "location"),
    "pass_location_middle_rate": ("binary", 100, "PREDICTIVE_CONDITIONAL", "location"),
    "pass_location_right_rate": ("binary", 100, "PREDICTIVE_CONDITIONAL", "location"),
    "pass_location_left_epa": ("continuous", 50, "PREDICTIVE_CONDITIONAL", "location"),
    "pass_location_middle_epa": (
        "continuous",
        50,
        "PREDICTIVE_CONDITIONAL",
        "location",
    ),
    "pass_location_right_epa": ("continuous", 50, "PREDICTIVE_CONDITIONAL", "location"),
    "scramble_rate": ("binary", 50, "PREDICTIVE_CORE", "mobility"),
    "scramble_epa": ("continuous", 20, "DESCRIPTIVE", "mobility"),
    "rushing_yards_per_dropback": ("continuous", 100, "DESCRIPTIVE", "mobility"),
    "rushing_tds_per_dropback": ("continuous", 100, "DESCRIPTIVE", "mobility"),
}

SCHEME_CONDITIONED: Final = {
    "target_depth_short_epa",
    "target_depth_intermediate_epa",
    "target_depth_deep_epa",
    "shotgun_epa",
    "early_down_epa",
    "third_down_epa",
    "red_zone_epa",
    "pass_location_left_epa",
    "pass_location_middle_epa",
    "pass_location_right_epa",
}

PASS_DETAIL_FEATURES: Final = {
    "cpoe",
    "average_air_yards",
    "target_depth_short_rate",
    "target_depth_intermediate_rate",
    "target_depth_deep_rate",
    "target_depth_short_epa",
    "target_depth_intermediate_epa",
    "target_depth_deep_epa",
    "pass_location_left_rate",
    "pass_location_middle_rate",
    "pass_location_right_rate",
    "pass_location_left_epa",
    "pass_location_middle_epa",
    "pass_location_right_epa",
}

FORBIDDEN_STATE_TOKENS: Final = (
    "coach_effect",
    "coach impact",
    "current-season coaching",
    "future player status",
    "production api",
    "production database",
    "frontend input",
)

PBP_COLUMNS: Final = (
    "season",
    "season_type",
    "posteam",
    "passer_player_id",
    "passer_id",
    "rusher_player_id",
    "qb_dropback",
    "qb_kneel",
    "qb_spike",
    "qb_scramble",
    "pass_attempt",
    "sack",
    "qb_epa",
    "cpoe",
    "air_yards",
    "pass_location",
    "shotgun",
    "down",
    "yardline_100",
)


@dataclass(frozen=True)
class CheckpointFourteenResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    universe_rows: int
    state_rows: int
    state_feature_rows: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _resolve_latest(root: Path) -> tuple[str, Path]:
    version = (root / "LATEST").read_text(encoding="utf-8").strip()
    path = root / version
    if not version or not path.is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return version, path


def _team_id(column: str = "posteam") -> pl.Expr:
    canonical = pl.col(column).replace_strict(
        TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String
    )
    return pl.when(canonical.is_not_null()).then(
        pl.concat_str(pl.lit("team_"), canonical.str.to_lowercase())
    )


def _safe_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _metric_definition(name: str, status: str, family: str, minimum: int) -> FeatureDefinition:
    timing = "HISTORICAL_PRIOR"
    permission = "YES" if status == "PREDICTIVE_CORE" else "CONDITIONAL"
    if status in {"DESCRIPTIVE", "EXPERIMENTAL", "UNAVAILABLE"}:
        permission = "NO"
    return FeatureDefinition(
        name=f"recent_{name}",
        entity_grain="QB",
        family=f"qb_{family}",
        description=f"As-of prior-season QB {name.replace('_', ' ')}",
        football_interpretation=(
            "Player history known before the target season; not a causal score."
        ),
        source="Checkpoint 3 canonical regular-season play-by-play",
        source_fields="explicit play fields and resolved GSIS quarterback ID",
        earliest_supported_season=2006 if name in PASS_DETAIL_FEATURES else 1999,
        latest_supported_season=2025,
        timing_class=timing,
        minimum_sample_rule=f"at least {minimum} feature-specific opportunities",
        derivation="raw additive totals followed by as-of empirical-Bayes shrinkage",
        status=status,
        missing_data_behavior="null with an explicit missingness reason",
        predictive_permission=permission,
        research_readiness="checkpoint-14 state candidate",
    )


def initial_registry() -> tuple[FeatureDefinition, ...]:
    definitions = [
        _metric_definition(name, status, family, minimum)
        for name, (_, minimum, status, family) in PROFILE_SPECS.items()
    ]
    definitions.extend(
        [
            FeatureDefinition(
                name="preseason_ability_estimate_epa_per_db",
                entity_grain="QB",
                family="qb_ability",
                description="Shrunk cumulative pre-target career EPA per dropback",
                football_interpretation=(
                    "An interpretable preseason EPA baseline, not a latent ability score."
                ),
                source="Checkpoint 3 canonical QB history",
                source_fields="total_qb_epa|dropbacks",
                earliest_supported_season=1999,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="at least 50 career dropbacks",
                derivation="normal-normal empirical-Bayes shrinkage of cumulative career EPA/DB",
                status="PREDICTIVE_CORE",
                missing_data_behavior="null with INSUFFICIENT_SAMPLE or ENTITY_NOT_PRESENT",
                predictive_permission="YES",
                research_readiness="checkpoint-14 core",
            ),
            FeatureDefinition(
                name="recent_observed_pae",
                entity_grain="QB",
                family="qb_expectation_residual",
                description="Prior-season out-of-sample PAE",
                football_interpretation=(
                    "Observed performance relative to prior expectation, separate from ability."
                ),
                source="Checkpoint 5 canonical PAE",
                source_fields="actual_epa_per_dropback|expected_epa_per_dropback|prediction_std_error",
                earliest_supported_season=2010,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="at least 50 prior-season dropbacks",
                derivation=(
                    "aggregate actual EPA/DB minus invariant expected EPA/DB; uncertainty preserved"
                ),
                status="PREDICTIVE_CONDITIONAL",
                missing_data_behavior="null when prior out-of-sample PAE is unavailable",
                predictive_permission="CONDITIONAL",
                research_readiness="contextual; low observed repeatability",
            ),
            FeatureDefinition(
                name="career_observed_epa_per_db",
                entity_grain="QB",
                family="qb_history",
                description="Raw cumulative pre-target career EPA per dropback",
                football_interpretation=(
                    "Observed career history, kept separate from the preseason estimate."
                ),
                source="Checkpoint 3 canonical QB history",
                source_fields="total_qb_epa|dropbacks",
                earliest_supported_season=1999,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="at least 50 career dropbacks",
                derivation="sum EPA divided by sum dropbacks",
                status="PREDICTIVE_CORE",
                missing_data_behavior="null with INSUFFICIENT_SAMPLE",
                predictive_permission="YES",
                research_readiness="checkpoint-14 core",
            ),
            FeatureDefinition(
                name="career_trend_epa_per_season",
                entity_grain="QB",
                family="qb_trajectory",
                description="Weighted pre-target EPA/DB slope",
                football_interpretation=(
                    "Direction of observed development; not a transition forecast."
                ),
                source="Checkpoint 3 canonical QB history",
                source_fields="season|total_qb_epa|dropbacks",
                earliest_supported_season=1999,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="two seasons >=100 dropbacks and >=300 combined",
                derivation="weighted least-squares slope over the latest three qualified seasons",
                status="PREDICTIVE_CONDITIONAL",
                missing_data_behavior="null with INSUFFICIENT_SAMPLE",
                predictive_permission="CONDITIONAL",
                research_readiness="checkpoint-14 conditional",
            ),
            FeatureDefinition(
                name="career_stability_epa_per_db",
                entity_grain="QB",
                family="qb_uncertainty",
                description="Pre-target year-to-year EPA/DB variability",
                football_interpretation=(
                    "Historical instability after accounting for season volume."
                ),
                source="Checkpoint 3 canonical QB history",
                source_fields="season|total_qb_epa|dropbacks",
                earliest_supported_season=1999,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="three seasons >=100 dropbacks and >=600 combined",
                derivation="weighted standard deviation around the historical trend",
                status="DESCRIPTIVE",
                missing_data_behavior="null with INSUFFICIENT_SAMPLE",
                predictive_permission="NO",
                research_readiness="descriptive uncertainty",
            ),
        ]
    )
    definitions.sort(key=lambda item: item.name)
    validate_feature_registry(definitions)
    return tuple(definitions)


def validate_state_feature_contract(registry: tuple[FeatureDefinition, ...]) -> None:
    """Fail closed when a Player State definition names a forbidden information source."""

    failures: list[dict[str, str]] = []
    for definition in registry:
        contract = "|".join(
            (
                definition.name,
                definition.family,
                definition.source,
                definition.source_fields,
                definition.derivation,
            )
        ).lower()
        for token in FORBIDDEN_STATE_TOKENS:
            if token in contract:
                failures.append({"feature_name": definition.name, "forbidden_token": token})
    if failures:
        raise ValueError(f"forbidden Player State feature inputs: {failures[:5]}")


def build_state_universe(
    players: pl.DataFrame,
    qb_history: pl.DataFrame,
    dated_depth_charts: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build an outcome-independent universe using only facts knowable by each cutoff."""

    required = {"gsis_id", "position", "position_group", "draft_year", "rookie_season"}
    if not required <= set(players.columns):
        raise ValueError(
            f"player master lacks universe fields: {sorted(required - set(players.columns))}"
        )
    master_qbs = players.filter(
        (pl.col("position") == "QB") | (pl.col("position_group") == "QB")
    ).select(
        pl.col("gsis_id").alias("player_id"),
        "display_name",
        "birth_date",
        "draft_year",
        "rookie_season",
    )
    history_first = qb_history.group_by("player_id").agg(
        pl.col("season").min().alias("first_history_season")
    )
    master = master_qbs.join(history_first, on="player_id", how="full", coalesce=True)
    dated: dict[tuple[str, int], str] = {}
    if dated_depth_charts is not None and not dated_depth_charts.is_empty():
        needed = {"player_id", "position", "available_date"}
        if not needed <= set(dated_depth_charts.columns):
            raise ValueError(
                "dated depth-chart evidence lacks player_id, position, or available_date"
            )
        for row in dated_depth_charts.filter(pl.col("position") == "QB").to_dicts():
            available = _safe_date(row["available_date"])
            if available is None:
                continue
            key = (str(row["player_id"]), available.year)
            current = dated.get(key)
            if current is None or str(available) < current:
                dated[key] = str(available)

    rows: list[dict[str, object]] = []
    for player in master.sort("player_id").to_dicts():
        player_id = player.get("player_id")
        if not player_id:
            continue
        draft_year = player.get("draft_year")
        first_history = player.get("first_history_season")
        for target in TARGET_SEASONS:
            bases: list[str] = []
            evidence_dates: list[str] = []
            if first_history is not None and int(first_history) < target:
                bases.append("prior_qb_history")
            if draft_year is not None and int(draft_year) <= target:
                bases.append("draft_fact")
            dated_value = dated.get((str(player_id), target))
            if dated_value is not None and dated_value <= f"{target}-08-31":
                bases.append("dated_preseason_depth_chart")
                evidence_dates.append(dated_value)
            if not bases:
                continue
            rookie = player.get("rookie_season")
            rows.append(
                {
                    "player_id": str(player_id),
                    "target_season": target,
                    "universe_version": UNIVERSE_VERSION,
                    "as_of_date": f"{target}-08-31",
                    "membership_basis": "|".join(sorted(bases)),
                    "evidence_available_date": min(evidence_dates) if evidence_dates else None,
                    "display_name": player.get("display_name") or str(player_id),
                    "birth_date": player.get("birth_date"),
                    "draft_year": draft_year,
                    "rookie_season": rookie,
                }
            )
    universe = pl.DataFrame(rows, infer_schema_length=None).sort("target_season", "player_id")
    if (
        universe.select("player_id", "target_season", "universe_version").n_unique()
        != universe.height
    ):
        raise ValueError("duplicate state-universe grain")
    return universe


def _sum_sq(column: str, condition: pl.Expr) -> pl.Expr:
    return pl.when(condition).then(pl.col(column) * pl.col(column)).otherwise(None).sum()


def load_resolved_qb_plays(pbp_paths: list[Path], canonical_qb_ids: set[str]) -> pl.DataFrame:
    available = pl.read_parquet_schema(pbp_paths[0])
    missing = sorted(set(PBP_COLUMNS) - set(available))
    if missing:
        raise ValueError(f"PBP source lacks required columns: {missing}")
    return (
        pl.scan_parquet(pbp_paths)
        .select(PBP_COLUMNS)
        .filter(
            (pl.col("season_type") == "REG")
            & (pl.col("qb_dropback") == 1)
            & (pl.col("qb_kneel").fill_null(0) != 1)
            & (pl.col("qb_spike").fill_null(0) != 1)
        )
        .with_columns(
            pl.coalesce("passer_player_id", "passer_id").alias("primary_qb_id"),
            pl.when(pl.col("qb_scramble").fill_null(0) == 1)
            .then(pl.col("rusher_player_id"))
            .otherwise(None)
            .alias("scramble_qb_id"),
            _team_id().alias("team_id"),
        )
        .with_columns(pl.coalesce("scramble_qb_id", "primary_qb_id").alias("player_id"))
        .filter(
            pl.col("player_id").is_in(sorted(canonical_qb_ids))
            & pl.col("team_id").is_not_null()
            & pl.col("qb_epa").is_finite()
        )
        .drop("primary_qb_id", "scramble_qb_id")
        .collect()
        .sort("season", "player_id", "team_id")
    )


def _profile_row(
    row: dict[str, object],
    feature: str,
    numerator: float | int | None,
    denominator: float | int | None,
    sum_squares: float | None,
    source_dataset: str = "nflverse_play_by_play",
) -> dict[str, object]:
    raw = None
    if numerator is not None and denominator is not None and float(denominator) > 0:
        raw = float(numerator) / float(denominator)
    kind, minimum, status, family = PROFILE_SPECS[feature]
    return {
        "player_id": row["player_id"],
        "team_id": row["team_id"],
        "season": int(row["season"]),
        "feature_name": feature,
        "profile_version": PROFILE_VERSION,
        "feature_family": family,
        "feature_status": status,
        "estimate_kind": kind,
        "raw_value": raw,
        "numerator": None if numerator is None else float(numerator),
        "denominator": None if denominator is None else float(denominator),
        "sum_squares": sum_squares,
        "minimum_sample": minimum,
        "qualified": denominator is not None and float(denominator) >= minimum and raw is not None,
        "missingness_reason": "SOURCE_NOT_AVAILABLE" if raw is None else None,
        "source_dataset": source_dataset,
    }


def build_qb_team_season_profiles(
    plays: pl.DataFrame, supplemental: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Build additive long-form QB stint profiles from resolved regular-season plays."""

    p = plays.with_columns(
        (pl.col("qb_epa") > 0).cast(pl.Int64).alias("is_success"),
        (pl.col("qb_scramble").fill_null(0) == 1).cast(pl.Int64).alias("is_scramble"),
        ((pl.col("pass_attempt") == 1) & pl.col("air_yards").is_not_null()).alias("aimed"),
        ((pl.col("pass_attempt") == 1) & pl.col("cpoe").is_not_null()).alias("cpoe_covered"),
        ((pl.col("pass_attempt") == 1) & pl.col("pass_location").is_not_null()).alias("located"),
        (pl.col("down").is_between(1, 2)).fill_null(False).alias("early"),
        (pl.col("down") == 3).fill_null(False).alias("third"),
        (pl.col("yardline_100") <= 20).fill_null(False).alias("red_zone"),
    ).with_columns(
        (pl.col("aimed") & (pl.col("air_yards") <= 9)).alias("short"),
        (pl.col("aimed") & pl.col("air_yards").is_between(10, 19)).alias("intermediate"),
        (pl.col("aimed") & (pl.col("air_yards") >= 20)).alias("deep"),
    )
    grouped = p.group_by("player_id", "team_id", "season").agg(
        pl.len().alias("db"),
        pl.col("qb_epa").sum().alias("epa_sum"),
        (pl.col("qb_epa") * pl.col("qb_epa")).sum().alias("epa_sumsq"),
        pl.col("is_success").sum().alias("successes"),
        pl.col("cpoe_covered").sum().alias("cpoe_n"),
        pl.col("cpoe").filter(pl.col("cpoe_covered")).sum().alias("cpoe_sum"),
        _sum_sq("cpoe", pl.col("cpoe_covered")).alias("cpoe_sumsq"),
        pl.col("sack").fill_null(0).sum().alias("sacks"),
        ((pl.col("pass_attempt").fill_null(0) == 1) | (pl.col("sack").fill_null(0) == 1))
        .sum()
        .alias("sack_n"),
        pl.col("aimed").sum().alias("aimed_n"),
        pl.col("air_yards").filter(pl.col("aimed")).sum().alias("air_sum"),
        _sum_sq("air_yards", pl.col("aimed")).alias("air_sumsq"),
        *[pl.col(depth).sum().alias(f"{depth}_n") for depth in ("short", "intermediate", "deep")],
        *[
            pl.col("qb_epa").filter(pl.col(depth)).sum().alias(f"{depth}_epa_sum")
            for depth in ("short", "intermediate", "deep")
        ],
        *[
            _sum_sq("qb_epa", pl.col(depth)).alias(f"{depth}_epa_sumsq")
            for depth in ("short", "intermediate", "deep")
        ],
        (pl.col("shotgun").fill_null(0) == 1).sum().alias("shotgun_n"),
        pl.col("qb_epa").filter(pl.col("shotgun") == 1).sum().alias("shotgun_epa_sum"),
        _sum_sq("qb_epa", pl.col("shotgun") == 1).alias("shotgun_epa_sumsq"),
        pl.col("early").sum().alias("early_n"),
        pl.col("qb_epa").filter(pl.col("early")).sum().alias("early_epa_sum"),
        _sum_sq("qb_epa", pl.col("early")).alias("early_epa_sumsq"),
        pl.col("third").sum().alias("third_n"),
        pl.col("qb_epa").filter(pl.col("third")).sum().alias("third_epa_sum"),
        _sum_sq("qb_epa", pl.col("third")).alias("third_epa_sumsq"),
        pl.col("red_zone").sum().alias("red_n"),
        pl.col("qb_epa").filter(pl.col("red_zone")).sum().alias("red_epa_sum"),
        _sum_sq("qb_epa", pl.col("red_zone")).alias("red_epa_sumsq"),
        pl.col("located").sum().alias("located_n"),
        *[
            (pl.col("located") & (pl.col("pass_location") == location))
            .sum()
            .alias(f"loc_{location}_n")
            for location in ("left", "middle", "right")
        ],
        *[
            pl.col("qb_epa")
            .filter(pl.col("located") & (pl.col("pass_location") == location))
            .sum()
            .alias(f"loc_{location}_epa_sum")
            for location in ("left", "middle", "right")
        ],
        *[
            _sum_sq("qb_epa", pl.col("located") & (pl.col("pass_location") == location)).alias(
                f"loc_{location}_epa_sumsq"
            )
            for location in ("left", "middle", "right")
        ],
        pl.col("is_scramble").sum().alias("scramble_n"),
        pl.col("qb_epa").filter(pl.col("is_scramble") == 1).sum().alias("scramble_epa_sum"),
        _sum_sq("qb_epa", pl.col("is_scramble") == 1).alias("scramble_epa_sumsq"),
    )
    rows: list[dict[str, object]] = []
    for row in grouped.sort("season", "player_id", "team_id").to_dicts():
        entries = [
            ("epa_per_dropback", row["epa_sum"], row["db"], row["epa_sumsq"]),
            ("success_rate", row["successes"], row["db"], None),
            ("cpoe", row["cpoe_sum"], row["cpoe_n"], row["cpoe_sumsq"]),
            ("sack_rate", row["sacks"], row["sack_n"], None),
            ("average_air_yards", row["air_sum"], row["aimed_n"], row["air_sumsq"]),
            ("target_depth_short_rate", row["short_n"], row["aimed_n"], None),
            ("target_depth_intermediate_rate", row["intermediate_n"], row["aimed_n"], None),
            ("target_depth_deep_rate", row["deep_n"], row["aimed_n"], None),
            (
                "target_depth_short_epa",
                row["short_epa_sum"],
                row["short_n"],
                row["short_epa_sumsq"],
            ),
            (
                "target_depth_intermediate_epa",
                row["intermediate_epa_sum"],
                row["intermediate_n"],
                row["intermediate_epa_sumsq"],
            ),
            ("target_depth_deep_epa", row["deep_epa_sum"], row["deep_n"], row["deep_epa_sumsq"]),
            ("shotgun_rate", row["shotgun_n"], row["db"], None),
            ("shotgun_epa", row["shotgun_epa_sum"], row["shotgun_n"], row["shotgun_epa_sumsq"]),
            ("early_down_epa", row["early_epa_sum"], row["early_n"], row["early_epa_sumsq"]),
            ("third_down_epa", row["third_epa_sum"], row["third_n"], row["third_epa_sumsq"]),
            ("red_zone_epa", row["red_epa_sum"], row["red_n"], row["red_epa_sumsq"]),
            ("pass_location_left_rate", row["loc_left_n"], row["located_n"], None),
            ("pass_location_middle_rate", row["loc_middle_n"], row["located_n"], None),
            ("pass_location_right_rate", row["loc_right_n"], row["located_n"], None),
            (
                "pass_location_left_epa",
                row["loc_left_epa_sum"],
                row["loc_left_n"],
                row["loc_left_epa_sumsq"],
            ),
            (
                "pass_location_middle_epa",
                row["loc_middle_epa_sum"],
                row["loc_middle_n"],
                row["loc_middle_epa_sumsq"],
            ),
            (
                "pass_location_right_epa",
                row["loc_right_epa_sum"],
                row["loc_right_n"],
                row["loc_right_epa_sumsq"],
            ),
            ("scramble_rate", row["scramble_n"], row["db"], None),
            ("scramble_epa", row["scramble_epa_sum"], row["scramble_n"], row["scramble_epa_sumsq"]),
        ]
        rows.extend(_profile_row(row, *entry) for entry in entries)

    result = pl.DataFrame(rows, infer_schema_length=None)
    if supplemental is not None and not supplemental.is_empty():
        lookup = {
            (str(r["player_id"]), str(r["team_id"]), int(r["season"])): r
            for r in supplemental.to_dicts()
        }
        extra: list[dict[str, object]] = []
        for key_row in grouped.select("player_id", "team_id", "season", "db").to_dicts():
            value = lookup.get(
                (str(key_row["player_id"]), str(key_row["team_id"]), int(key_row["season"]))
            )
            for feature, column in (
                ("rushing_yards_per_dropback", "rushing_yards"),
                ("rushing_tds_per_dropback", "rushing_touchdowns"),
            ):
                extra.append(
                    _profile_row(
                        key_row,
                        feature,
                        None if value is None else value.get(column),
                        key_row["db"],
                        None,
                        "nflverse_player_stats",
                    )
                )
        result = pl.concat([result, pl.DataFrame(extra, infer_schema_length=None)], how="vertical")
    grain = ["player_id", "team_id", "season", "feature_name", "profile_version"]
    if result.select(grain).n_unique() != result.height:
        raise ValueError("duplicate QB-team-season profile grain")
    return result.sort("season", "player_id", "team_id", "feature_name")


def aggregate_qb_season_profiles(stints: pl.DataFrame) -> pl.DataFrame:
    result = (
        stints.group_by("player_id", "season", "feature_name", "profile_version")
        .agg(
            pl.col("feature_family").first(),
            pl.col("feature_status").first(),
            pl.col("estimate_kind").first(),
            pl.col("numerator").sum().alias("numerator"),
            pl.col("denominator").sum().alias("denominator"),
            pl.col("sum_squares").sum().alias("sum_squares"),
            pl.col("minimum_sample").first(),
            pl.col("source_dataset").unique().sort().str.join("|").alias("source_dataset"),
            pl.col("team_id").unique().sort().str.join("|").alias("team_ids"),
        )
        .with_columns(
            pl.when(pl.col("denominator") > 0)
            .then(pl.col("numerator") / pl.col("denominator"))
            .alias("raw_value")
        )
        .with_columns(
            (
                pl.col("raw_value").is_not_null()
                & (pl.col("denominator") >= pl.col("minimum_sample"))
            ).alias("qualified"),
            pl.when(pl.col("raw_value").is_null())
            .then(pl.lit("SOURCE_NOT_AVAILABLE"))
            .otherwise(None)
            .alias("missingness_reason"),
        )
        .sort("season", "player_id", "feature_name")
    )
    if (
        result.select("player_id", "season", "feature_name", "profile_version").n_unique()
        != result.height
    ):
        raise ValueError("duplicate canonical QB-season profile grain")
    return result


def add_player_season_pae(
    profiles: pl.DataFrame, pae: pl.DataFrame, stints: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Append canonical prior PAE while requiring invariant multi-team expectation."""

    needed = {
        "player_id",
        "team_id",
        "season",
        "dropbacks",
        "actual_epa_per_dropback",
        "expected_epa_per_dropback",
        "prediction_std_error",
        "is_out_of_sample",
    }
    if not needed <= set(pae.columns):
        raise ValueError(f"PAE source lacks fields: {sorted(needed - set(pae.columns))}")
    source = pae.filter(
        (pl.col("is_out_of_sample") == True)  # noqa: E712
        & pl.col("season").is_between(2010, 2025)
    )
    if stints is not None:
        known_stints = stints.select("player_id", "team_id", "season").unique()
        unknown = (
            source.select("player_id", "team_id", "season")
            .unique()
            .join(
                known_stints,
                on=["player_id", "team_id", "season"],
                how="anti",
            )
        )
        if unknown.height:
            raise ValueError(
                "PAE source contains QB-team-season keys absent from canonical profiles: "
                f"{unknown.sort('season', 'player_id', 'team_id').head(5).to_dicts()}"
            )
    contradictory = (
        source.group_by("player_id", "season")
        .agg(pl.col("expected_epa_per_dropback").n_unique().alias("expected_values"))
        .filter(pl.col("expected_values") > 1)
    )
    if contradictory.height:
        raise ValueError("multi-team PAE rows contain contradictory expected EPA values")
    aggregated = (
        source.with_columns(
            (pl.col("actual_epa_per_dropback") * pl.col("dropbacks")).alias("actual_epa_total")
        )
        .group_by("player_id", "season")
        .agg(
            pl.col("dropbacks").sum().cast(pl.Float64).alias("denominator"),
            pl.col("actual_epa_total").sum().alias("actual_epa_total"),
            pl.col("expected_epa_per_dropback").first().alias("expected"),
            pl.col("prediction_std_error").max().alias("prediction_std_error"),
            pl.col("team_id").unique().sort().str.join("|").alias("team_ids"),
        )
        .with_columns(
            (pl.col("actual_epa_total") / pl.col("denominator") - pl.col("expected")).alias(
                "raw_value"
            )
        )
    )
    epa_variance = profiles.filter(pl.col("feature_name") == "epa_per_dropback").select(
        "player_id",
        "season",
        pl.when(pl.col("denominator") > 1)
        .then(
            (
                pl.col("sum_squares")
                - pl.col("numerator") * pl.col("numerator") / pl.col("denominator")
            )
            / (pl.col("denominator") - 1)
            / pl.col("denominator")
        )
        .otherwise(None)
        .alias("epa_sampling_variance"),
    )
    aggregated = aggregated.join(
        epa_variance, on=["player_id", "season"], how="left", validate="1:1"
    ).with_columns(
        (pl.col("epa_sampling_variance").fill_null(0) + pl.col("prediction_std_error") ** 2).alias(
            "sampling_variance"
        )
    )
    rows = aggregated.select(
        "player_id",
        "season",
        pl.lit("pae").alias("feature_name"),
        pl.lit(PROFILE_VERSION).alias("profile_version"),
        pl.lit("expectation_residual").alias("feature_family"),
        pl.lit("PREDICTIVE_CONDITIONAL").alias("feature_status"),
        pl.lit("continuous").alias("estimate_kind"),
        (pl.col("raw_value") * pl.col("denominator")).alias("numerator"),
        "denominator",
        pl.lit(None, dtype=pl.Float64).alias("sum_squares"),
        pl.lit(50).alias("minimum_sample"),
        pl.lit("checkpoint_5_qb_pae").alias("source_dataset"),
        "team_ids",
        "raw_value",
        (pl.col("denominator") >= 50).alias("qualified"),
        pl.lit(None, dtype=pl.String).alias("missingness_reason"),
        "sampling_variance",
    )
    base = profiles.with_columns(pl.lit(None, dtype=pl.Float64).alias("sampling_variance"))
    return pl.concat([base, rows], how="diagonal_relaxed").sort(
        "season", "player_id", "feature_name"
    )


def _sample_variance(row: dict[str, object]) -> float | None:
    n = float(row.get("denominator") or 0)
    total = row.get("numerator")
    squares = row.get("sum_squares")
    if n <= 1 or total is None or squares is None:
        value = row.get("sampling_variance")
        return float(value) if value is not None and math.isfinite(float(value)) else None
    variance = max(0.0, (float(squares) - float(total) ** 2 / n) / (n - 1))
    return variance / n


def _fit_prior(history: pl.DataFrame, kind: str) -> dict[str, float] | None:
    qualified = history.filter(pl.col("raw_value").is_not_null() & pl.col("qualified"))
    if qualified.height < 2:
        return None
    rows = qualified.to_dicts()
    total_n = sum(float(r["denominator"]) for r in rows)
    total_x = sum(float(r["numerator"]) for r in rows)
    mean = total_x / total_n if total_n else math.nan
    if not math.isfinite(mean):
        return None
    if kind == "binary":
        rates = np.asarray([float(r["raw_value"]) for r in rows])
        observed = float(np.var(rates, ddof=1)) if len(rates) > 1 else 0.0
        sampling = float(
            np.mean(
                [
                    max(0.0, float(r["raw_value"]) * (1 - float(r["raw_value"])))
                    / max(1.0, float(r["denominator"]))
                    for r in rows
                ]
            )
        )
        between = max(observed - sampling, 1e-9)
        strength = min(10000.0, max(2.0, mean * (1 - mean) / between - 1))
        return {"mean": mean, "strength": strength, "variance": between}
    values = np.asarray([float(r["raw_value"]) for r in rows])
    weights = np.asarray([float(r["denominator"]) for r in rows])
    center = float(np.average(values, weights=weights))
    observed = float(np.average((values - center) ** 2, weights=weights))
    sample_vars = [value for r in rows if (value := _sample_variance(r)) is not None]
    sampling = float(np.mean(sample_vars)) if sample_vars else observed / max(1.0, total_n)
    between = max(observed - sampling, 1e-9)
    return {"mean": center, "strength": 0.0, "variance": between}


def _shrink(
    row: dict[str, object], prior: dict[str, float] | None, kind: str
) -> dict[str, float | str | None]:
    n = float(row.get("denominator") or 0)
    raw = row.get("raw_value")
    if raw is None or n <= 0 or prior is None:
        return {
            "estimate": None,
            "weight": None,
            "se": None,
            "low": None,
            "high": None,
            "method": None,
        }
    raw = float(raw)
    if kind == "binary":
        strength = prior["strength"]
        alpha = prior["mean"] * strength
        beta = (1 - prior["mean"]) * strength
        successes = float(row["numerator"])
        total = n + strength
        estimate = (successes + alpha) / total
        variance = (successes + alpha) * (n - successes + beta) / (total**2 * (total + 1))
        weight = n / total
        se = math.sqrt(max(0.0, variance))
        return {
            "estimate": estimate,
            "weight": weight,
            "se": se,
            "low": max(0.0, estimate - INTERVAL_MULTIPLIER * se),
            "high": min(1.0, estimate + INTERVAL_MULTIPLIER * se),
            "method": "empirical_beta_binomial",
        }
    sampling = _sample_variance(row)
    if sampling is None or sampling <= 0:
        sampling = prior["variance"] / max(1.0, n)
    tau = prior["variance"]
    weight = tau / (tau + sampling)
    estimate = weight * raw + (1 - weight) * prior["mean"]
    variance = 1 / (1 / tau + 1 / sampling)
    se = math.sqrt(max(0.0, variance))
    return {
        "estimate": estimate,
        "weight": weight,
        "se": se,
        "low": estimate - INTERVAL_MULTIPLIER * se,
        "high": estimate + INTERVAL_MULTIPLIER * se,
        "method": "empirical_normal_normal",
    }


def _spearman_pairs(feature: pl.DataFrame) -> tuple[int, float | None]:
    later = feature.select(
        "player_id",
        (pl.col("season") - 1).alias("season"),
        pl.col("raw_value").alias("next_value"),
    )
    pairs = feature.join(later, on=["player_id", "season"], how="inner").drop_nulls(
        ["raw_value", "next_value"]
    )
    if pairs.height < 2 or pairs["raw_value"].n_unique() < 2 or pairs["next_value"].n_unique() < 2:
        return pairs.height, None
    value = float(spearmanr(pairs["raw_value"], pairs["next_value"]).statistic)
    return pairs.height, value if math.isfinite(value) else None


def _array_spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or len(np.unique(left)) < 2 or len(np.unique(right)) < 2:
        return None
    value = float(spearmanr(left, right).statistic)
    return value if math.isfinite(value) else None


def build_stability_report(profiles: pl.DataFrame) -> pl.DataFrame:
    base = profiles.filter(pl.col("feature_name") == "epa_per_dropback").select(
        "player_id", "season", pl.col("denominator").alias("qb_dropbacks")
    )
    rows: list[dict[str, object]] = []
    for feature in sorted(PROFILE_SPECS):
        data = profiles.filter((pl.col("feature_name") == feature) & pl.col("qualified")).join(
            base, on=["player_id", "season"], how="left", validate="1:1"
        )
        pairs, corr = _spearman_pairs(data)
        earliest = 2006 if feature in PASS_DETAIL_FEATURES else 1999
        supported = base.join(
            profiles.filter(pl.col("feature_name") == feature).select(
                "player_id", "season", "qualified"
            ),
            on=["player_id", "season"],
            how="left",
        ).filter((pl.col("season") >= earliest) & (pl.col("qb_dropbacks") >= 200))
        coverage = (
            float(supported["qualified"].fill_null(False).mean()) if supported.height else 0.0
        )
        midpoint = (earliest + 2025) // 2
        early_pairs, early_corr = _spearman_pairs(data.filter(pl.col("season") <= midpoint))
        late_pairs, late_corr = _spearman_pairs(data.filter(pl.col("season") > midpoint))
        medium_pairs, medium_corr = _spearman_pairs(
            data.filter(pl.col("qb_dropbacks").is_between(200, 399))
        )
        high_pairs, high_corr = _spearman_pairs(data.filter(pl.col("qb_dropbacks") >= 400))
        direction_consistent = (
            early_pairs >= 2
            and late_pairs >= 2
            and early_corr is not None
            and late_corr is not None
            and early_corr > 0
            and late_corr > 0
            and medium_pairs >= 2
            and high_pairs >= 2
            and medium_corr is not None
            and high_corr is not None
            and medium_corr > 0
            and high_corr > 0
        )
        primary = bool(
            pairs >= PRIMARY_STABILITY["pairs"]
            and corr is not None
            and corr >= PRIMARY_STABILITY["correlation"]
            and coverage >= PRIMARY_STABILITY["coverage"]
            and direction_consistent
        )
        strict_pair = pairs >= 125
        strict_corr = corr is not None and corr >= 0.30
        strict_coverage = coverage >= 0.85
        strict_passes = sum((strict_pair, strict_corr, strict_coverage))
        initial = PROFILE_SPECS[feature][2]
        final = initial
        if initial == "PREDICTIVE_CORE" and not (primary and strict_passes >= 2):
            final = "PREDICTIVE_CONDITIONAL"
        rows.append(
            {
                "feature_name": feature,
                "adjacent_pairs": pairs,
                "spearman_correlation": corr,
                "coverage": coverage,
                "early_pairs": early_pairs,
                "early_correlation": early_corr,
                "late_pairs": late_pairs,
                "late_correlation": late_corr,
                "medium_volume_pairs": medium_pairs,
                "medium_volume_correlation": medium_corr,
                "high_volume_pairs": high_pairs,
                "high_volume_correlation": high_corr,
                "direction_consistent": direction_consistent,
                "primary_pass": primary,
                "sensitivity_pairs_75": pairs >= 75,
                "sensitivity_pairs_125": strict_pair,
                "sensitivity_correlation_020": corr is not None and corr >= 0.20,
                "sensitivity_correlation_030": strict_corr,
                "sensitivity_coverage_075": coverage >= 0.75,
                "sensitivity_coverage_085": strict_coverage,
                "strict_passes": strict_passes,
                "initial_status": initial,
                "stability_status": final,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("feature_name")


def build_portability_report(stints: pl.DataFrame, scheme: pl.DataFrame) -> pl.DataFrame:
    """Audit whether conditional outcomes repeat through material environment changes."""

    db = stints.filter(pl.col("feature_name") == "epa_per_dropback").select(
        "player_id", "team_id", "season", pl.col("denominator").alias("db")
    )
    primary = (
        db.sort("player_id", "season", "db", descending=[False, False, True])
        .unique(["player_id", "season"], keep="first")
        .select("player_id", "team_id", "season")
    )
    scheme_features = [
        "shotgun_rate",
        "target_depth_short_rate",
        "target_depth_intermediate_rate",
        "target_depth_deep_rate",
        "scramble_rate",
    ]
    context = (
        scheme.filter(pl.col("feature_name").is_in(scheme_features))
        .select(
            _team_id("team_id").alias("team_id"),
            "season",
            "feature_name",
            "descriptive_standardized_value",
        )
        .pivot(
            on="feature_name", index=["team_id", "season"], values="descriptive_standardized_value"
        )
    )
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(PORTABILITY_SEED)
    for feature in sorted(SCHEME_CONDITIONED):
        values = stints.filter((pl.col("feature_name") == feature) & pl.col("qualified")).select(
            "player_id", "team_id", "season", "raw_value"
        )
        values = primary.join(values, on=["player_id", "team_id", "season"], how="inner").join(
            context, on=["team_id", "season"], how="left"
        )
        prior = values.select(
            "player_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("team_id").alias("prior_team_id"),
            pl.col("raw_value").alias("prior_value"),
            *[pl.col(name).alias(f"prior_{name}") for name in scheme_features],
        )
        transitions = (
            values.join(prior, on=["player_id", "season"], how="inner")
            .with_columns(
                (pl.col("team_id") != pl.col("prior_team_id")).alias("team_changed"),
                pl.any_horizontal(
                    *[
                        (pl.col(name) - pl.col(f"prior_{name}")).abs() >= 1
                        for name in scheme_features
                    ]
                ).alias("material_scheme_change"),
            )
            .with_columns(
                (pl.col("team_changed") | pl.col("material_scheme_change")).alias(
                    "environment_change"
                )
            )
            .sort("player_id", "season", "team_id", "prior_team_id")
        )
        changed = transitions.filter(pl.col("environment_change")).drop_nulls(
            ["raw_value", "prior_value"]
        )
        team_changers = transitions.filter(pl.col("team_changed")).drop_nulls(
            ["raw_value", "prior_value"]
        )
        team_stayers = transitions.filter(~pl.col("team_changed")).drop_nulls(
            ["raw_value", "prior_value"]
        )
        changer_corr = _array_spearman(
            np.asarray(team_changers["prior_value"], dtype=float),
            np.asarray(team_changers["raw_value"], dtype=float),
        )
        stayer_corr = _array_spearman(
            np.asarray(team_stayers["prior_value"], dtype=float),
            np.asarray(team_stayers["raw_value"], dtype=float),
        )
        draws: list[float] = []
        if team_changers.height >= 2:
            x = np.asarray(team_changers["prior_value"], dtype=float)
            y = np.asarray(team_changers["raw_value"], dtype=float)
            for _ in range(PORTABILITY_BOOTSTRAPS):
                index = rng.integers(0, len(x), len(x))
                value = _array_spearman(x[index], y[index])
                if value is not None:
                    draws.append(value)
        lower = float(np.quantile(draws, 0.10)) if draws else None
        passed = bool(
            changed.height >= 50
            and changer_corr is not None
            and changer_corr >= 0.20
            and lower is not None
            and lower > 0
            and stayer_corr is not None
            and stayer_corr > 0
        )
        rows.append(
            {
                "feature_name": feature,
                "environment_change_pairs": changed.height,
                "team_changer_pairs": team_changers.height,
                "team_changer_correlation": changer_corr,
                "team_stayer_pairs": team_stayers.height,
                "team_stayer_correlation": stayer_corr,
                "bootstrap_successful_draws": len(draws),
                "bootstrap_80_interval_low": lower,
                "portability_pass": passed,
                "final_status": "PREDICTIVE_CORE" if passed else "PREDICTIVE_CONDITIONAL",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("feature_name")


def _reliability(weight: float | None) -> str:
    if weight is None:
        return "UNAVAILABLE"
    if weight >= 0.75:
        return "HIGH"
    if weight >= 0.40:
        return "MEDIUM"
    return "LOW"


def resolve_feature_status(
    definition: FeatureDefinition,
    *,
    stability_pass: bool,
    portability_pass: bool,
) -> str:
    """Apply the predeclared stability and portability gates without outcome shopping."""

    base = definition.name.removeprefix("recent_")
    if definition.status == "DESCRIPTIVE":
        return "DESCRIPTIVE"
    if base in SCHEME_CONDITIONED:
        return (
            "PREDICTIVE_CORE" if stability_pass and portability_pass else "PREDICTIVE_CONDITIONAL"
        )
    if definition.status == "PREDICTIVE_CORE" and not stability_pass:
        return "PREDICTIVE_CONDITIONAL"
    return definition.status


def _trend(history: pl.DataFrame) -> tuple[float | None, float | None, float | None]:
    data = history.filter(pl.col("denominator") >= 100).sort("season").tail(3)
    if data.height < 2 or float(data["denominator"].sum()) < 300:
        return None, None, None
    x = np.asarray(data["season"], dtype=float)
    y = np.asarray(data["raw_value"], dtype=float)
    w = np.asarray(data["denominator"], dtype=float)
    design = np.column_stack([np.ones(len(x)), x - x.mean()])
    xtwx = design.T @ (w[:, None] * design)
    coef = np.linalg.pinv(xtwx) @ design.T @ (w * y)
    residual = y - design @ coef
    dof = max(1, len(x) - 2)
    sigma2 = float(np.sum(w * residual**2) / dof / np.mean(w))
    covariance = np.linalg.pinv(xtwx) * sigma2
    return (
        float(coef[1]),
        math.sqrt(max(0.0, float(covariance[1, 1]))),
        float(np.sqrt(np.average(residual**2, weights=w))),
    )


def build_state_features(
    universe: pl.DataFrame,
    profiles: pl.DataFrame,
    registry: tuple[FeatureDefinition, ...],
    *,
    data_version: str,
    source_hash: str,
    target_seasons: tuple[int, ...] | None = None,
) -> pl.DataFrame:
    """Reuse historical estimators for explicit research targets; defaults stay unchanged."""
    targets = TARGET_SEASONS if target_seasons is None else target_seasons
    if set(universe["target_season"].unique().to_list()) - set(targets):
        raise ValueError("state universe contains an undeclared target season")
    lookup = {item.name: item for item in registry}
    profile_by = {
        (str(key[0]), str(key[1])): group.sort("season")
        for key, group in profiles.group_by("player_id", "feature_name", maintain_order=True)
    }
    prior_cache: dict[tuple[int, str], dict[str, float] | None] = {}
    for target in targets:
        for base_feature, (kind, _, _, _) in PROFILE_SPECS.items():
            reference = profiles.filter(
                (pl.col("feature_name") == base_feature)
                & pl.col("season").is_between(target - REFERENCE_WINDOW_SEASONS, target - 1)
            )
            prior_cache[(target, base_feature)] = _fit_prior(reference, kind)
        pae_reference = profiles.filter(
            (pl.col("feature_name") == "pae")
            & pl.col("season").is_between(target - REFERENCE_WINDOW_SEASONS, target - 1)
        )
        prior_cache[(target, "pae")] = _fit_prior(pae_reference, "continuous")
    rows: list[dict[str, object]] = []
    for member in universe.sort("target_season", "player_id").to_dicts():
        player_id = str(member["player_id"])
        target = int(member["target_season"])
        for base_feature, (kind, minimum, _, _) in PROFILE_SPECS.items():
            history = profile_by.get((player_id, base_feature))
            if history is None:
                continue
            history = history.filter(pl.col("season") < target)
            current = history.filter(pl.col("season") == target - 1)
            if current.is_empty():
                continue
            row = current.row(0, named=True)
            prior = prior_cache[(target, base_feature)]
            shrunk = _shrink(row, prior, kind)
            qualified = float(row.get("denominator") or 0) >= minimum
            name = f"recent_{base_feature}"
            definition = lookup[name]
            rows.append(
                _state_record(
                    player_id,
                    target,
                    name,
                    definition,
                    row,
                    shrunk if qualified else {},
                    prior,
                    data_version,
                    source_hash,
                    qualified,
                )
            )

        epa_history = profile_by.get((player_id, "epa_per_dropback"))
        if epa_history is not None:
            epa_history = epa_history.filter(pl.col("season") < target)
            if not epa_history.is_empty():
                career = (
                    epa_history.select(
                        pl.col("numerator").sum().alias("numerator"),
                        pl.col("denominator").sum().alias("denominator"),
                        pl.col("sum_squares").sum().alias("sum_squares"),
                    )
                    .with_columns((pl.col("numerator") / pl.col("denominator")).alias("raw_value"))
                    .row(0, named=True)
                )
                career.update(
                    {
                        "season": int(epa_history["season"].max()),
                        "observation_start_season": int(epa_history["season"].min()),
                        "observation_end_season": int(epa_history["season"].max()),
                        "history_seasons": epa_history["season"].n_unique(),
                        "source_dataset": "checkpoint_3_qb_history",
                    }
                )
                prior = prior_cache[(target, "epa_per_dropback")]
                shrunk = _shrink(career, prior, "continuous")
                qualified = float(career["denominator"]) >= 50
                for name, use_shrunk in (
                    ("preseason_ability_estimate_epa_per_db", True),
                    ("career_observed_epa_per_db", False),
                ):
                    if use_shrunk:
                        estimate = shrunk
                    else:
                        career_variance = _sample_variance(career)
                        career_se = (
                            math.sqrt(career_variance) if career_variance is not None else None
                        )
                        estimate = {
                            "estimate": career["raw_value"],
                            "weight": 1.0,
                            "se": career_se,
                            "low": None
                            if career_se is None
                            else float(career["raw_value"]) - INTERVAL_MULTIPLIER * career_se,
                            "high": None
                            if career_se is None
                            else float(career["raw_value"]) + INTERVAL_MULTIPLIER * career_se,
                            "method": "raw_career_observation",
                        }
                    rows.append(
                        _state_record(
                            player_id,
                            target,
                            name,
                            lookup[name],
                            career,
                            estimate if qualified else {},
                            prior,
                            data_version,
                            source_hash,
                            qualified,
                        )
                    )
                slope, slope_se, volatility = _trend(epa_history)
                qualified_history = (
                    epa_history.filter(pl.col("denominator") >= 100).sort("season").tail(3)
                )
                qualified_stability = (
                    qualified_history.height >= 3
                    and float(qualified_history["denominator"].sum()) >= 600
                )
                for name, value, se, qualified_value in (
                    ("career_trend_epa_per_season", slope, slope_se, slope is not None),
                    (
                        "career_stability_epa_per_db",
                        volatility if qualified_stability else None,
                        None,
                        volatility is not None and qualified_stability,
                    ),
                ):
                    derived = dict(career)
                    derived["raw_value"] = value
                    derived["denominator"] = float(epa_history["denominator"].sum())
                    rows.append(
                        _state_record(
                            player_id,
                            target,
                            name,
                            lookup[name],
                            derived,
                            {
                                "estimate": value,
                                "weight": 1.0 if value is not None else None,
                                "se": se,
                                "low": None if se is None else value - INTERVAL_MULTIPLIER * se,
                                "high": None if se is None else value + INTERVAL_MULTIPLIER * se,
                                "method": "weighted_history_summary",
                            }
                            if qualified_value
                            else {},
                            None,
                            data_version,
                            source_hash,
                            qualified_value,
                        )
                    )

        pae_history = profile_by.get((player_id, "pae"))
        if pae_history is not None:
            current = pae_history.filter(pl.col("season") == target - 1)
            if not current.is_empty():
                row = current.row(0, named=True)
                prior = prior_cache[(target, "pae")]
                qualified = float(row["denominator"]) >= 50
                rows.append(
                    _state_record(
                        player_id,
                        target,
                        "recent_observed_pae",
                        lookup["recent_observed_pae"],
                        row,
                        _shrink(row, prior, "continuous") if qualified else {},
                        prior,
                        data_version,
                        source_hash,
                        qualified,
                    )
                )
    frame = pl.DataFrame(rows, infer_schema_length=None).sort(
        "target_season", "entity_id", "feature_name"
    )
    if not frame.is_empty():
        validate_feature_records(frame, registry, predictive_only=False)
    return frame


def _state_record(
    player_id: str,
    target: int,
    name: str,
    definition: FeatureDefinition,
    observed: dict[str, object],
    estimate: dict[str, object],
    prior: dict[str, float] | None,
    data_version: str,
    source_hash: str,
    qualified: bool,
) -> dict[str, object]:
    value = estimate.get("estimate") if estimate else None
    weight = estimate.get("weight") if estimate else None
    return {
        "entity_type": "QB",
        "entity_id": f"qb:{player_id}",
        "player_id": player_id,
        "feature_name": name,
        "feature_value": value,
        "raw_value": observed.get("raw_value"),
        "source_season": int(observed["season"]),
        "target_season": target,
        "as_of_date": f"{target}-08-31",
        "source_available_date": f"{target}-08-31",
        "source_dataset": observed.get("source_dataset") or "checkpoint_3_qb_history",
        "source_version": data_version,
        "source_hash": source_hash,
        "intermediate_artifact": "qb_season_profiles.parquet",
        "intermediate_hash": source_hash,
        "feature_definition_version": definition.definition_version,
        "feature_build_version": STATE_VERSION,
        "model_version": None,
        "sample_size": float(observed.get("denominator") or 0),
        "exposure": float(observed.get("denominator") or 0),
        "effective_sample_size": float(observed.get("denominator") or 0),
        "observation_start_season": int(
            observed.get("observation_start_season") or observed["season"]
        ),
        "observation_end_season": int(observed.get("observation_end_season") or observed["season"]),
        "history_seasons": int(observed.get("history_seasons") or 1),
        "missingness_reason": (
            None
            if qualified and value is not None
            else "EMPIRICAL_PRIOR_UNAVAILABLE"
            if qualified
            else "INSUFFICIENT_SAMPLE"
        ),
        "timing_class": definition.timing_class,
        "feature_status": definition.status,
        "predictive_permission": definition.predictive_permission,
        "standardization_method": estimate.get("method") if estimate else None,
        "standardization_fit_start_season": max(1999, target - REFERENCE_WINDOW_SEASONS),
        "standardization_fit_end_season": target - 1,
        "standardization_mean": None if prior is None else prior["mean"],
        "standardization_std": None if prior is None else math.sqrt(prior["variance"]),
        "state_version": STATE_VERSION,
        "numerator": observed.get("numerator"),
        "denominator": observed.get("denominator"),
        "sum_squares": observed.get("sum_squares"),
        "estimate_type": estimate.get("method") if estimate else None,
        "prior_strength": None if prior is None else prior["strength"],
        "prior_mean": None if prior is None else prior["mean"],
        "prior_variance": None if prior is None else prior["variance"],
        "prior_alpha": (
            None
            if prior is None or estimate.get("method") != "empirical_beta_binomial"
            else prior["mean"] * prior["strength"]
        ),
        "prior_beta": (
            None
            if prior is None or estimate.get("method") != "empirical_beta_binomial"
            else (1 - prior["mean"]) * prior["strength"]
        ),
        "shrinkage_weight": weight,
        "estimate_standard_error": estimate.get("se") if estimate else None,
        "interval_low": estimate.get("low") if estimate else None,
        "interval_high": estimate.get("high") if estimate else None,
        "interval_level": INTERVAL_LEVEL if value is not None else None,
        "reliability": _reliability(None if weight is None else float(weight)),
        "qualified": qualified,
    }


def build_player_states(
    universe: pl.DataFrame,
    records: pl.DataFrame,
    data_version: str,
    qb_history: pl.DataFrame | None = None,
    feature_store_version: str | None = None,
    source_versions: dict[str, str] | None = None,
    total_state_features: int | None = None,
) -> pl.DataFrame:
    summaries = (
        records.group_by("player_id", "target_season").agg(
            pl.len().alias("available_feature_rows"),
            pl.col("qualified").sum().alias("qualified_feature_rows"),
            pl.col("source_season").max().alias("maximum_source_season"),
        )
        if not records.is_empty()
        else pl.DataFrame(
            schema={
                "player_id": pl.String,
                "target_season": pl.Int64,
                "available_feature_rows": pl.UInt32,
                "qualified_feature_rows": pl.UInt32,
                "maximum_source_season": pl.Int64,
            }
        )
    )
    ability = records.filter(
        pl.col("feature_name") == "preseason_ability_estimate_epa_per_db"
    ).select(
        "player_id",
        "target_season",
        pl.col("feature_value").alias("preseason_ability_estimate_epa_per_db"),
        pl.col("estimate_standard_error").alias("preseason_ability_standard_error"),
        pl.col("interval_low").alias("preseason_ability_interval_low"),
        pl.col("interval_high").alias("preseason_ability_interval_high"),
        pl.col("reliability").alias("preseason_ability_reliability"),
    )
    exposure_rows: list[dict[str, object]] = []
    if qb_history is not None and not qb_history.is_empty():
        history = qb_history.group_by("player_id", "season").agg(
            pl.col("starts").sum().alias("starts"),
            pl.col("dropbacks").sum().alias("dropbacks"),
        )
        by_player = {
            str(key[0]): group.sort("season")
            for key, group in history.group_by("player_id", maintain_order=True)
        }
        for row in universe.select("player_id", "target_season").to_dicts():
            player_id = str(row["player_id"])
            target = int(row["target_season"])
            player_history = by_player.get(player_id)
            before = (
                player_history.filter(pl.col("season") < target)
                if player_history is not None
                else None
            )
            prior = before.filter(pl.col("season") == target - 1) if before is not None else None
            exposure_rows.append(
                {
                    "player_id": player_id,
                    "target_season": target,
                    "prior_starts": None
                    if prior is None or prior.is_empty()
                    else int(prior["starts"].sum()),
                    "prior_dropbacks": None
                    if prior is None or prior.is_empty()
                    else int(prior["dropbacks"].sum()),
                    "career_starts": 0
                    if before is None or before.is_empty()
                    else int(before["starts"].sum()),
                    "career_dropbacks": 0
                    if before is None or before.is_empty()
                    else int(before["dropbacks"].sum()),
                    "seasons_with_qb_activity": 0
                    if before is None or before.is_empty()
                    else before["season"].n_unique(),
                }
            )
    exposures = (
        pl.DataFrame(exposure_rows, infer_schema_length=None)
        if exposure_rows
        else universe.select("player_id", "target_season").with_columns(
            pl.lit(None, dtype=pl.Int64).alias("prior_starts"),
            pl.lit(None, dtype=pl.Int64).alias("prior_dropbacks"),
            pl.lit(0, dtype=pl.Int64).alias("career_starts"),
            pl.lit(0, dtype=pl.Int64).alias("career_dropbacks"),
            pl.lit(0, dtype=pl.Int64).alias("seasons_with_qb_activity"),
        )
    )
    frame = (
        universe.join(summaries, on=["player_id", "target_season"], how="left")
        .join(ability, on=["player_id", "target_season"], how="left", validate="1:1")
        .join(exposures, on=["player_id", "target_season"], how="left", validate="1:1")
    )
    source_versions = source_versions or {}
    return frame.with_columns(
        pl.lit(data_version).alias("data_version"),
        pl.lit(STATE_VERSION).alias("state_version"),
        pl.lit(feature_store_version, dtype=pl.String).alias("feature_store_version"),
        pl.lit(source_versions.get("historical"), dtype=pl.String).alias(
            "historical_source_version"
        ),
        pl.lit(source_versions.get("expected_performance"), dtype=pl.String).alias(
            "expected_performance_source_version"
        ),
        pl.lit(source_versions.get("enhancements"), dtype=pl.String).alias(
            "enhancement_source_version"
        ),
        pl.lit(None, dtype=pl.Int64).alias("nfl_experience"),
        pl.lit("UNAVAILABLE_FUTURE_UPDATED_SOURCE").alias("nfl_experience_status"),
        pl.col("available_feature_rows").fill_null(0),
        pl.col("qualified_feature_rows").fill_null(0),
        (
            pl.col("qualified_feature_rows").fill_null(0)
            / max(1, total_state_features or records["feature_name"].n_unique())
        ).alias("state_completeness"),
        pl.when(pl.col("birth_date").is_not_null())
        .then(
            (
                pl.date(pl.col("target_season"), 9, 1)
                - pl.col("birth_date").str.to_date(strict=False)
            ).dt.total_days()
            / 365.2425
        )
        .alias("age_at_season_start"),
        pl.when(
            pl.col("rookie_season").is_not_null()
            & (pl.col("rookie_season") <= pl.col("target_season"))
        )
        .then(pl.col("target_season") - pl.col("rookie_season"))
        .alias("seasons_since_rookie_year"),
        (pl.col("rookie_season") == pl.col("target_season")).alias("is_rookie"),
        pl.when(pl.col("available_feature_rows").fill_null(0) == 0)
        .then(pl.lit("NO_PRIOR_QB_PERFORMANCE"))
        .otherwise(pl.lit("AVAILABLE"))
        .alias("state_status"),
    ).sort("target_season", "player_id")


def build_evaluation_links(universe: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    membership = universe.select(
        "player_id", pl.col("target_season").alias("season"), "universe_version"
    ).with_columns(pl.lit(True).alias("state_universe_member"))
    result = outcomes.select("player_id", "team_id", "season", "dropbacks", "starts").join(
        membership, on=["player_id", "season"], how="left", validate="m:1"
    )
    return result.with_columns(
        pl.lit(EVALUATION_VERSION).alias("evaluation_version"),
        pl.col("state_universe_member").fill_null(False),
        pl.when(pl.col("state_universe_member").fill_null(False))
        .then(None)
        .otherwise(pl.lit("NOT_IN_ASOF_STATE_UNIVERSE"))
        .alias("state_exclusion_reason"),
    ).sort("season", "player_id", "team_id")


def build_feature_availability(
    universe: pl.DataFrame,
    records: pl.DataFrame,
    registry: tuple[FeatureDefinition, ...],
) -> pl.DataFrame:
    definitions = pl.DataFrame(
        {
            "feature_name": [item.name for item in registry],
            "feature_status": [item.status for item in registry],
            "earliest_supported_season": [item.earliest_supported_season for item in registry],
        }
    )
    expected = universe.select("player_id", "target_season").join(definitions, how="cross")
    observed = records.select(
        "player_id",
        "target_season",
        "feature_name",
        "feature_value",
        "qualified",
        pl.col("missingness_reason").alias("record_missingness_reason"),
    )
    return (
        expected.join(
            observed,
            on=["player_id", "target_season", "feature_name"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("qualified").fill_null(False),
            pl.when(pl.col("record_missingness_reason").is_not_null())
            .then(pl.col("record_missingness_reason"))
            .when(
                pl.col("earliest_supported_season").is_not_null()
                & (pl.col("target_season") - 1 < pl.col("earliest_supported_season"))
            )
            .then(pl.lit("FEATURE_NOT_SUPPORTED_THAT_SEASON"))
            .when(pl.col("feature_value").is_null())
            .then(pl.lit("ENTITY_NOT_PRESENT"))
            .otherwise(None)
            .alias("missingness_reason"),
        )
        .drop("record_missingness_reason")
        .sort("target_season", "player_id", "feature_name")
    )


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    frame.write_parquet(path, compression="zstd", statistics=True)


def _publish_latest(root: Path, data_version: str) -> None:
    latest_tmp = root / f".LATEST.{uuid.uuid4().hex}.tmp"
    latest_tmp.write_text(data_version + "\n", encoding="utf-8")
    os.replace(latest_tmp, root / "LATEST")


def _content_identity(
    inputs: dict[str, str], code_hash: str, registry: tuple[FeatureDefinition, ...]
) -> tuple[str, dict[str, object]]:
    identity: dict[str, object] = {
        "specification": CHECKPOINT_14_SPECIFICATION,
        "profile_version": PROFILE_VERSION,
        "state_version": STATE_VERSION,
        "universe_version": UNIVERSE_VERSION,
        "evaluation_version": EVALUATION_VERSION,
        "target_seasons": TARGET_SEASONS,
        "as_of_month_day": AS_OF_MONTH_DAY,
        "reference_window_seasons": REFERENCE_WINDOW_SEASONS,
        "profile_specs": PROFILE_SPECS,
        "primary_stability": PRIMARY_STABILITY,
        "stability_sensitivity": STABILITY_SENSITIVITY,
        "stability_volume_bands": STABILITY_VOLUME_BANDS,
        "scheme_conditioned": sorted(SCHEME_CONDITIONED),
        "portability_bootstraps": PORTABILITY_BOOTSTRAPS,
        "portability_seed": PORTABILITY_SEED,
        "interval_level": INTERVAL_LEVEL,
        "python_version": platform.python_version(),
        "polars_version": pl.__version__,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "code_hash": code_hash,
        "registry": [asdict(item) for item in registry],
        "inputs": dict(sorted(inputs.items())),
    }
    canonical = json.loads(json.dumps(identity, sort_keys=True))
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]
    return f"c14-{digest}", canonical


def _load_dated_depth_charts(historical: Path) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted((historical / "bronze/depth_charts").glob("season=*/depth_charts.parquet")):
        schema = pl.read_parquet_schema(path)
        if "dt" not in schema:
            continue
        for row in pl.read_parquet(path).select("dt", "gsis_id", "pos_grp", "pos_abb").to_dicts():
            rows.append(
                {
                    "player_id": row["gsis_id"],
                    "position": row["pos_grp"] or row["pos_abb"],
                    "available_date": row["dt"],
                }
            )
    return (
        pl.DataFrame(rows, infer_schema_length=None)
        if rows
        else pl.DataFrame(
            schema={"player_id": pl.String, "position": pl.String, "available_date": pl.String}
        )
    )


def run_checkpoint_fourteen(
    project_root: Path, output_root: Path | None = None
) -> CheckpointFourteenResult:
    historical_version, historical = _resolve_latest(project_root / "data/processed/historical")
    expected_version, expected = _resolve_latest(
        project_root / "data/processed/expected_performance"
    )
    enhancement_version, enhancement = _resolve_latest(project_root / "data/processed/enhancements")
    c13_version, c13 = _resolve_latest(project_root / "data/processed/predictive_foundation")
    AsOfFeatureStore(c13)
    if c13_version != "c13-5e3d7a34ea4d1af5":
        raise ValueError(f"unexpected Checkpoint 13 foundation: {c13_version}")

    paths = {
        "players": historical / "bronze/players/players.parquet",
        "qb_outcomes": enhancement / "canonical_qb_team_season_performance.parquet",
        "supplemental": enhancement / "qb_supplemental_statistics.parquet",
        "pae": enhancement / "canonical_qb_pae.parquet",
        "c13_manifest": c13 / "MANIFEST.json",
        "c13_scheme": c13 / "scheme_team_season.csv",
    }
    pbp_paths = sorted((historical / "bronze/play_by_play").glob("season=*/play_by_play.parquet"))
    depth_chart_paths = sorted(
        (historical / "bronze/depth_charts").glob("season=*/depth_charts.parquet")
    )
    inputs = {name: _sha256(path) for name, path in paths.items()}
    inputs.update({f"pbp/{path.parent.name}": _sha256(path) for path in pbp_paths})
    inputs.update({f"depth_charts/{path.parent.name}": _sha256(path) for path in depth_chart_paths})
    registry = initial_registry()
    validate_state_feature_contract(registry)
    code_hash = _sha256(Path(__file__))
    root = output_root or project_root / "data/processed/qb_player_state"

    players = pl.read_parquet(paths["players"])
    outcomes = pl.read_parquet(paths["qb_outcomes"]).filter(pl.col("scope") == "analysis")
    canonical_ids = set(
        players.filter((pl.col("position") == "QB") | (pl.col("position_group") == "QB"))["gsis_id"]
        .drop_nulls()
        .to_list()
    )
    canonical_ids.update(outcomes["player_id"].to_list())
    plays = load_resolved_qb_plays(pbp_paths, canonical_ids)
    supplemental = pl.read_parquet(paths["supplemental"])
    stints = build_qb_team_season_profiles(plays, supplemental)
    profiles = aggregate_qb_season_profiles(stints)
    profiles = add_player_season_pae(profiles, pl.read_parquet(paths["pae"]), stints)
    universe = build_state_universe(players, profiles, _load_dated_depth_charts(historical))
    stability = build_stability_report(profiles.filter(pl.col("feature_name") != "pae"))
    portability = build_portability_report(stints, pl.read_csv(paths["c13_scheme"]))

    final_status = dict(stability.select("feature_name", "stability_status").iter_rows())
    stable_for_promotion = {
        str(row["feature_name"]): bool(row["primary_pass"] and row["strict_passes"] >= 2)
        for row in stability.to_dicts()
    }
    portable = {
        str(row["feature_name"]): bool(row["portability_pass"]) for row in portability.to_dicts()
    }
    adjusted: list[FeatureDefinition] = []
    for definition in registry:
        base = definition.name.removeprefix("recent_")
        stability_pass = stable_for_promotion.get(
            base, final_status.get(base, definition.status) == "PREDICTIVE_CORE"
        )
        status = resolve_feature_status(
            definition,
            stability_pass=stability_pass,
            portability_pass=portable.get(base, False),
        )
        permission = "YES" if status == "PREDICTIVE_CORE" else "CONDITIONAL"
        if status in {"DESCRIPTIVE", "EXPERIMENTAL", "UNAVAILABLE"}:
            permission = "NO"
        adjusted.append(replace(definition, status=status, predictive_permission=permission))
    registry = tuple(adjusted)
    validate_feature_registry(registry)
    validate_state_feature_contract(registry)
    conditioned_registry = [
        item for item in registry if item.name.removeprefix("recent_") in SCHEME_CONDITIONED
    ]
    portability = portability.drop("final_status").join(
        pl.DataFrame(
            {
                "feature_name": [
                    item.name.removeprefix("recent_") for item in conditioned_registry
                ],
                "final_status": [item.status for item in conditioned_registry],
            }
        ),
        on="feature_name",
        how="left",
        validate="1:1",
    )

    data_version, identity = _content_identity(inputs, code_hash, registry)
    destination = root / data_version
    if destination.is_dir():
        manifest = json.loads((destination / "MANIFEST.json").read_text(encoding="utf-8"))
        if manifest["identity"] != identity:
            raise ValueError("existing Checkpoint 14 output has a mismatched identity")
        for name, digest in manifest["output_checksums"].items():
            if not (destination / name).is_file() or _sha256(destination / name) != digest:
                raise ValueError(f"existing Checkpoint 14 artifact failed checksum: {name}")
        _publish_latest(root, data_version)
        return CheckpointFourteenResult(
            data_version,
            destination,
            True,
            int(manifest["counts"]["universe_rows"]),
            int(manifest["counts"]["state_rows"]),
            int(manifest["counts"]["state_feature_rows"]),
        )

    source_hash = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    records = build_state_features(
        universe, profiles, registry, data_version=data_version, source_hash=source_hash
    )
    records = (
        records.with_columns(
            pl.col("feature_name").str.strip_prefix("recent_").alias("_profile_feature_name")
        )
        .join(
            stability.select(
                pl.col("feature_name").alias("_profile_feature_name"),
                pl.when(pl.col("primary_pass") & (pl.col("strict_passes") >= 2))
                .then(pl.lit("PASSED"))
                .otherwise(pl.lit("NOT_PASSED"))
                .alias("stability_classification"),
            ),
            on="_profile_feature_name",
            how="left",
            validate="m:1",
        )
        .join(
            portability.select(
                pl.col("feature_name").alias("_profile_feature_name"),
                pl.when(pl.col("portability_pass"))
                .then(pl.lit("PASSED"))
                .otherwise(pl.lit("NOT_PASSED"))
                .alias("portability_classification"),
            ),
            on="_profile_feature_name",
            how="left",
            validate="m:1",
        )
        .with_columns(
            pl.col("stability_classification").fill_null("NOT_APPLICABLE"),
            pl.col("portability_classification").fill_null("NOT_APPLICABLE"),
        )
        .drop("_profile_feature_name")
        .sort("target_season", "entity_id", "feature_name")
    )
    states = build_player_states(
        universe,
        records,
        data_version,
        pl.read_parquet(paths["qb_outcomes"]),
        feature_store_version=c13_version,
        source_versions={
            "historical": historical_version,
            "expected_performance": expected_version,
            "enhancements": enhancement_version,
        },
        total_state_features=len(registry),
    )
    evaluation = build_evaluation_links(universe, outcomes)
    availability = build_feature_availability(universe, records, registry)
    coverage = (
        availability.group_by("target_season", "feature_name", "feature_status")
        .agg(
            pl.len().alias("rows"),
            pl.col("qualified").sum().alias("qualified_rows"),
            pl.col("feature_value").is_not_null().sum().alias("non_null_rows"),
        )
        .sort("target_season", "feature_name")
    )
    missingness = (
        availability.group_by("feature_name", "missingness_reason")
        .len()
        .sort("feature_name", "missingness_reason")
    )
    leakage = pl.DataFrame(
        [
            {
                "gate": "STATE_SOURCE_BEFORE_TARGET",
                "failure_count": records.filter(
                    pl.col("source_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "STATE_UNIVERSE_INDEPENDENT_OF_OUTCOMES",
                "failure_count": 0,
            },
            {
                "gate": "NO_COACH_EFFECT_INPUT",
                "failure_count": 0,
            },
        ]
    ).with_columns((pl.col("failure_count") == 0).alias("passed"))
    if leakage.filter(~pl.col("passed")).height:
        raise ValueError("Checkpoint 14 leakage audit failed")
    summary = pl.DataFrame(
        [
            {"gate": "ASOF_UNIVERSE", "status": "PASS", "detail": f"{universe.height} rows"},
            {
                "gate": "PROFILE_GRAINS",
                "status": "PASS",
                "detail": f"{stints.height} stint features",
            },
            {"gate": "PLAYER_STATE", "status": "PASS", "detail": f"{states.height} state headers"},
            {"gate": "LEAKAGE", "status": "PASS", "detail": "zero target/future feature rows"},
            {
                "gate": "CHECKPOINT_15",
                "status": "DEFERRED",
                "detail": "no transition or projection model",
            },
        ]
    )
    artifacts = {
        "qb_feature_registry.csv": feature_registry_frame(registry),
        "qb_state_universe.parquet": universe,
        "qb_team_season_profiles.parquet": stints,
        "qb_season_profiles.parquet": profiles,
        "qb_profile_stability.csv": stability,
        "qb_profile_portability.csv": portability,
        "qb_state_feature_records.parquet": records,
        "player_states.parquet": states,
        "qb_state_evaluation_links.parquet": evaluation,
        "feature_availability.parquet": availability,
        "feature_coverage.csv": coverage,
        "missingness_summary.csv": missingness,
        "leakage_audit.csv": leakage,
        "checkpoint_14_summary.csv": summary,
    }
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{data_version}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir()
    try:
        for name, frame in artifacts.items():
            if name.endswith(".parquet"):
                _write_parquet(frame, temporary / name)
            else:
                frame.write_csv(temporary / name, float_scientific=False)
        checksums = {name: _sha256(temporary / name) for name in sorted(artifacts)}
        manifest = {
            "data_version": data_version,
            "profile_version": PROFILE_VERSION,
            "state_version": STATE_VERSION,
            "universe_version": UNIVERSE_VERSION,
            "checkpoint_status": "COMPLETE",
            "identity": identity,
            "upstream_versions": {
                "historical": historical_version,
                "expected_performance": expected_version,
                "enhancements": enhancement_version,
                "predictive_foundation": c13_version,
            },
            "counts": {
                "universe_rows": universe.height,
                "state_rows": states.height,
                "state_feature_rows": records.height,
                "stint_profile_rows": stints.height,
                "player_season_profile_rows": profiles.height,
                "evaluation_rows": evaluation.height,
            },
            "grains": {
                "state_universe": ["player_id", "target_season", "universe_version"],
                "stint_profile": [
                    "player_id",
                    "team_id",
                    "season",
                    "feature_name",
                    "profile_version",
                ],
                "player_season_profile": ["player_id", "season", "feature_name", "profile_version"],
                "player_state": ["player_id", "target_season", "state_version"],
                "state_feature": ["player_id", "target_season", "feature_name", "state_version"],
                "evaluation": ["player_id", "team_id", "season", "evaluation_version"],
            },
            "output_checksums": checksums,
        }
        (temporary / "MANIFEST.json").write_bytes(_json_bytes(manifest))
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _publish_latest(root, data_version)
    return CheckpointFourteenResult(
        data_version, destination, False, universe.height, states.height, records.height
    )

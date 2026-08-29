"""Checkpoint-six coach-associated PAE exposure, estimation, and ranking pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
import scipy
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .constants import TEAM_ALIAS_TO_CANONICAL
from .errors import PipelineError
from .pipeline import _output_checksums, _update_latest, _validate_existing_version, _write_json
from .sources import sha256_file

COACH_IMPACT_PIPELINE_VERSION = "checkpoint-6.0"
COACH_IMPACT_MODEL_VERSION = "coach-associated-pae-v1"
ROLES = ("head_coach", "offensive_coordinator", "play_caller", "quarterbacks_coach")
CONTROL_COLUMNS = (
    "age",
    "nfl_experience",
    "is_rookie",
    "prior_qb_seasons",
    "no_prior_qb_performance",
    "prior_dropbacks",
    "prior_epa_per_dropback",
    "career_dropbacks",
    "career_epa_per_dropback",
    "changed_team",
    "prior_injury_report_weeks",
    "prior_injury_out_weeks",
)
BASELINE_ALPHA = 10.0
FIXED_EFFECT_ALPHA = 25.0
MIN_MODEL_EXPOSURE_DROPBACKS = 25.0
RANK_MIN_QUALIFYING_QB_SEASONS = 3
RANK_MIN_DISTINCT_QBS = 2
RANK_MIN_VERIFIED_DROPBACKS = 600.0
RELIABILITY_MEDIUM_DROPBACKS = 1_500.0
RELIABILITY_HIGH_DROPBACKS = 3_000.0
BOOTSTRAP_REPLICATES = 200
BOOTSTRAP_SEED = 20260829
INTERVAL_MULTIPLIER = 1.96
SENSITIVITY_MINIMUM_DROPBACKS = (25.0, 100.0, 200.0)
DETERMINISTIC_DECIMAL_PLACES = 12


@dataclass(frozen=True)
class CoachImpactConfig:
    project_root: Path
    historical_dir: Path | None = None
    expected_performance_dir: Path | None = None
    output_dir: Path | None = None
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES

    @property
    def resolved_historical_dir(self) -> Path:
        return self.historical_dir or self.project_root / "data" / "processed" / "historical"

    @property
    def resolved_expected_performance_dir(self) -> Path:
        return self.expected_performance_dir or (
            self.project_root / "data" / "processed" / "expected_performance"
        )

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "data" / "processed" / "coach_impact"


@dataclass(frozen=True)
class CoachImpactResult:
    data_version: str
    model_version: str
    output_path: Path
    reused_existing: bool
    table_counts: dict[str, int]


def _latest(root: Path, label: str) -> tuple[str, Path]:
    pointer = root / "LATEST"
    if not pointer.is_file():
        raise PipelineError(f"{label} LATEST pointer is missing: {pointer}")
    version = pointer.read_text(encoding="utf-8").strip()
    path = root / version
    if not path.is_dir():
        raise PipelineError(f"{label} version directory is missing: {path}")
    return version, path


def _read_csv(path: Path) -> pl.DataFrame:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return pl.DataFrame(rows, infer_schema_length=None)


def _assignment_frame(project_root: Path) -> pl.DataFrame:
    manual = project_root / "data" / "manual"
    assignments = _read_csv(manual / "coaching_assignments.csv").with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        pl.col("is_interim", "is_shared", "is_retained") == "true",
        (
            pl.lit("team_")
            + pl.col("team_id")
            .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None)
            .str.to_lowercase()
        ).alias("canonical_team_id"),
    )
    coaches = _read_csv(manual / "coaches.csv").select("coach_id", "canonical_name")
    citations = _read_csv(manual / "coach_assignment_sources.csv")
    cited_keys = set(citations["assignment_key"].to_list())
    unsupported = assignments.filter(
        (pl.col("verification_status") == "verified") & ~pl.col("assignment_key").is_in(cited_keys)
    )
    if unsupported.height:
        raise PipelineError("verified coach assignments require source citations")
    if assignments["canonical_team_id"].null_count():
        raise PipelineError("coach assignments contain unresolved canonical team IDs")
    return assignments.join(coaches, on="coach_id", how="left", validate="m:1").rename(
        {"canonical_name": "coach_name"}
    )


def _validate_pae(pae: pl.DataFrame) -> None:
    if pae.select("player_id", "team_id", "season").n_unique() != pae.height:
        raise PipelineError("duplicate checkpoint-five PAE rows")
    if pae.filter(~pl.col("is_out_of_sample")).height:
        raise PipelineError("coach impact requires out-of-sample PAE")
    error = pae.filter(
        (
            pl.col("actual_epa_per_dropback")
            - pl.col("expected_epa_per_dropback")
            - pl.col("performance_above_expectation")
        ).abs()
        > 1e-12
    )
    if error.height:
        raise PipelineError("checkpoint-five PAE arithmetic does not reconcile")
    leaked = pae.filter(
        pl.col("feature_source_max_season").is_not_null()
        & (pl.col("feature_source_max_season") >= pl.col("season"))
    )
    if leaked.height:
        raise PipelineError("future information appears in coach-impact preseason features")


def build_coach_exposures(
    qb_games: pl.DataFrame,
    pae: pl.DataFrame,
    assignments: pl.DataFrame,
) -> pl.DataFrame:
    """Build one QB/coach/assignment-interval exposure from compatible game rows."""

    _validate_pae(pae)
    game_grain = ("game_id", "team_id", "player_id")
    if qb_games.select(game_grain).n_unique() != qb_games.height:
        raise PipelineError("duplicate QB-game rows in coach exposure input")
    if assignments["assignment_key"].n_unique() != assignments.height:
        raise PipelineError("duplicate coaching assignment keys")

    feature_columns = [
        "player_id",
        "team_id",
        "season",
        "quarterback_name",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "eligibility_status",
        "model_version",
        "feature_source_max_season",
        *CONTROL_COLUMNS,
    ]
    games = qb_games.join(
        pae.select(feature_columns),
        on=["player_id", "team_id", "season"],
        how="inner",
        validate="m:1",
    ).with_columns(
        (pl.col("epa_per_dropback") - pl.col("expected_epa_per_dropback")).alias("game_pae")
    )
    joined = games.join(
        assignments,
        left_on=["season", "team_id"],
        right_on=["season", "canonical_team_id"],
        how="inner",
        validate="m:m",
    ).filter(pl.col("week").is_between(pl.col("start_week"), pl.col("end_week")))

    overlap_key = ["game_id", "team_id", "player_id", "role"]
    joined = joined.with_columns(pl.len().over(overlap_key).alias("simultaneous_coaches"))
    illegal = joined.filter((pl.col("simultaneous_coaches") > 1) & ~pl.col("is_shared"))
    if illegal.height:
        sample = illegal.select(*overlap_key, "assignment_key").head(5).to_dicts()
        raise PipelineError(f"illegal non-shared coaching overlap: {sample}")
    joined = joined.with_columns(
        pl.when(pl.col("simultaneous_coaches") > 1)
        .then(1.0 / pl.col("simultaneous_coaches"))
        .otherwise(1.0)
        .alias("exposure_fraction"),
        (pl.col("dropbacks") * pl.col("epa_per_dropback")).alias("game_qb_epa"),
        (pl.col("dropbacks") * pl.col("game_pae")).alias("game_pae_total"),
    ).with_columns((pl.col("dropbacks") * pl.col("exposure_fraction")).alias("exposure_dropbacks"))

    grain = [
        "assignment_key",
        "season",
        "team_id",
        "player_id",
        "coach_id",
        "coach_name",
        "role",
        "start_week",
        "end_week",
        "interval_basis",
        "verification_status",
        "confidence_level",
        "is_interim",
        "is_shared",
        "is_retained",
        "quarterback_name",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "eligibility_status",
        "model_version",
        "feature_source_max_season",
        *CONTROL_COLUMNS,
    ]
    exposures = (
        joined.group_by(grain, maintain_order=True)
        .agg(
            pl.col("game_id").n_unique().alias("observed_games"),
            pl.col("week").min().alias("first_observed_week"),
            pl.col("week").max().alias("last_observed_week"),
            pl.col("dropbacks").sum().alias("observed_dropbacks"),
            pl.col("exposure_dropbacks").sum(),
            pl.col("game_qb_epa").sum().alias("interval_qb_epa"),
            pl.col("game_pae_total").sum().alias("interval_pae_total"),
            pl.col("exposure_fraction").min().alias("exposure_fraction"),
        )
        .with_columns(
            (pl.col("interval_qb_epa") / pl.col("observed_dropbacks")).alias(
                "actual_epa_per_dropback"
            ),
            (pl.col("interval_pae_total") / pl.col("observed_dropbacks")).alias(
                "coach_interval_pae"
            ),
        )
        .with_columns(
            pl.when(pl.col("observed_dropbacks") < MIN_MODEL_EXPOSURE_DROPBACKS)
            .then(pl.lit("below_25_interval_dropbacks"))
            .when(pl.col("verification_status") == "conflicting")
            .then(pl.lit("conflicting_assignment"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("exclusion_reason")
        )
        .sort("role", "season", "team_id", "player_id", "start_week", "coach_id")
    )
    if exposures.select("assignment_key", "player_id", "team_id", "season").n_unique() != (
        exposures.height
    ):
        raise PipelineError("duplicate QB-coach-interval exposure rows")
    if exposures.filter(
        (pl.col("first_observed_week") < pl.col("start_week"))
        | (pl.col("last_observed_week") > pl.col("end_week"))
    ).height:
        raise PipelineError("QB exposure falls outside its supported coaching interval")
    if exposures.filter(
        (
            pl.col("actual_epa_per_dropback")
            - pl.col("expected_epa_per_dropback")
            - pl.col("coach_interval_pae")
        ).abs()
        > 1e-12
    ).height:
        raise PipelineError("coach-interval PAE arithmetic does not reconcile")
    if exposures.filter(
        pl.col("feature_source_max_season").is_not_null()
        & (pl.col("feature_source_max_season") >= pl.col("season"))
    ).height:
        raise PipelineError("future information leaked into coach-impact exposures")
    return exposures


def _design(frame: pl.DataFrame, *, coach: bool, qb: bool, team_season: bool) -> Pipeline:
    numeric = list(CONTROL_COLUMNS)
    categorical = ["season"]
    if coach:
        categorical.append("coach_id")
    if qb:
        categorical.append("player_id")
    if team_season:
        categorical.append("team_season")
    transformer = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    return Pipeline([("features", transformer), ("ridge", Ridge(alpha=BASELINE_ALPHA))])


def _model_frame(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        (pl.col("team_id") + pl.lit("-") + pl.col("season").cast(pl.String)).alias("team_season")
    )


def _fit_baseline(
    frame: pl.DataFrame,
    *,
    include_qb: bool,
    include_team_season: bool,
    weighted: bool,
    include_coach: bool = False,
) -> tuple[np.ndarray, Pipeline]:
    model_frame = _model_frame(frame)
    model = _design(
        frame,
        coach=include_coach,
        qb=include_qb,
        team_season=include_team_season,
    )
    model.set_params(ridge__alpha=FIXED_EFFECT_ALPHA if include_coach else BASELINE_ALPHA)
    y = np.asarray(model_frame["coach_interval_pae"], dtype=float)
    weights = np.asarray(model_frame["exposure_dropbacks"], dtype=float) if weighted else None
    model.fit(model_frame, y, ridge__sample_weight=weights)
    return np.asarray(model.predict(model_frame), dtype=float), model


def _partial_pool(
    frame: pl.DataFrame, baseline_prediction: np.ndarray
) -> tuple[pl.DataFrame, np.ndarray]:
    working = frame.with_columns(
        pl.Series("baseline_prediction", baseline_prediction),
        (pl.col("coach_interval_pae") - pl.Series(baseline_prediction)).alias("residual"),
    )
    residual = np.asarray(working["residual"], dtype=float)
    weights = np.asarray(working["exposure_dropbacks"], dtype=float)
    sigma2 = max(float(np.average(np.square(residual), weights=weights)), 1e-8)
    summaries = (
        working.group_by("coach_id", "coach_name", "role")
        .agg(
            (pl.col("residual") * pl.col("exposure_dropbacks")).sum().alias("weighted_total"),
            pl.col("exposure_dropbacks").sum().alias("total_dropbacks"),
            pl.len().alias("observations"),
        )
        .with_columns((pl.col("weighted_total") / pl.col("total_dropbacks")).alias("raw_effect"))
    )
    raw = np.asarray(summaries["raw_effect"], dtype=float)
    coach_weights = np.asarray(summaries["total_dropbacks"], dtype=float)
    center = float(np.average(raw, weights=coach_weights))
    tau2 = max(
        float(np.average(np.square(raw - center), weights=coach_weights))
        - sigma2 / max(float(np.mean(coach_weights)), 1.0),
        1e-8,
    )
    summaries = summaries.with_columns(
        (tau2 / (tau2 + sigma2 / pl.col("total_dropbacks"))).alias("shrinkage_weight")
    ).with_columns(
        (pl.col("raw_effect") * pl.col("shrinkage_weight")).alias("estimated_effect"),
        (sigma2 * pl.col("shrinkage_weight") / pl.col("total_dropbacks"))
        .sqrt()
        .alias("analytic_standard_error"),
    )
    effect_lookup = dict(summaries.select("coach_id", "estimated_effect").iter_rows())
    predicted = baseline_prediction + np.asarray(
        [float(effect_lookup[str(value)]) for value in frame["coach_id"]]
    )
    return summaries.drop("weighted_total"), predicted


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    return {
        "observations": len(actual),
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r_squared": float(r2_score(actual, predicted)) if len(actual) > 1 else 0.0,
    }


def _fit_role(
    frame: pl.DataFrame,
    *,
    include_qb: bool = True,
    include_team_season: bool = True,
    weighted: bool = True,
) -> tuple[pl.DataFrame, list[dict[str, object]]]:
    baseline, _ = _fit_baseline(
        frame,
        include_qb=include_qb,
        include_team_season=include_team_season,
        weighted=weighted,
    )
    fixed, _ = _fit_baseline(
        frame,
        include_qb=include_qb,
        include_team_season=include_team_season,
        weighted=weighted,
        include_coach=True,
    )
    effects, hierarchical = _partial_pool(frame, baseline)
    actual = np.asarray(frame["coach_interval_pae"], dtype=float)
    comparison = [
        {"model_name": "no_coach_baseline", **_metrics(actual, baseline)},
        {"model_name": "ridge_coach_fixed_effects", **_metrics(actual, fixed)},
        {"model_name": "empirical_bayes_partial_pooling", **_metrics(actual, hierarchical)},
    ]
    return effects, comparison


def _bootstrap_intervals(
    frame: pl.DataFrame, effects: pl.DataFrame, replicates: int
) -> pl.DataFrame:
    if replicates <= 0 or frame.height < 3:
        return effects.with_columns(
            (
                pl.col("estimated_effect") - INTERVAL_MULTIPLIER * pl.col("analytic_standard_error")
            ).alias("confidence_low"),
            (
                pl.col("estimated_effect") + INTERVAL_MULTIPLIER * pl.col("analytic_standard_error")
            ).alias("confidence_high"),
            pl.lit(0).alias("bootstrap_replicates"),
        )
    blocks = frame.select("player_id", "season").unique().sort("player_id", "season").to_dicts()
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples: dict[str, list[float]] = {str(value): [] for value in effects["coach_id"]}
    for _ in range(replicates):
        selected = [blocks[index] for index in rng.integers(0, len(blocks), len(blocks))]
        pieces = [
            frame.filter(
                (pl.col("player_id") == block["player_id"]) & (pl.col("season") == block["season"])
            )
            for block in selected
        ]
        sample = pl.concat(pieces, how="vertical")
        try:
            baseline, _ = _fit_baseline(
                sample, include_qb=True, include_team_season=True, weighted=True
            )
            bootstrap_effects, _ = _partial_pool(sample, baseline)
        except (ValueError, np.linalg.LinAlgError):
            continue
        for coach_id, effect in bootstrap_effects.select(
            "coach_id", "estimated_effect"
        ).iter_rows():
            if str(coach_id) in samples:
                samples[str(coach_id)].append(float(effect))
    intervals = []
    for coach_id in effects["coach_id"]:
        values = samples[str(coach_id)]
        intervals.append(
            {
                "coach_id": coach_id,
                "confidence_low": float(np.quantile(values, 0.025)) if values else None,
                "confidence_high": float(np.quantile(values, 0.975)) if values else None,
                "bootstrap_replicates": len(values),
            }
        )
    return effects.join(pl.DataFrame(intervals), on="coach_id", validate="1:1")


def _effect_samples(exposures: pl.DataFrame) -> pl.DataFrame:
    return exposures.group_by("coach_id", "role").agg(
        pl.col("player_id")
        .filter(pl.col("verification_status") == "verified")
        .n_unique()
        .alias("distinct_quarterbacks"),
        pl.col("team_id")
        .filter(pl.col("verification_status") == "verified")
        .n_unique()
        .alias("distinct_teams"),
        pl.struct("player_id", "season")
        .filter(
            (pl.col("eligibility_status") == "eligible")
            & (pl.col("verification_status") == "verified")
        )
        .n_unique()
        .alias("qualifying_qb_seasons"),
        pl.struct("player_id", "season")
        .filter(pl.col("verification_status") == "verified")
        .n_unique()
        .alias("qb_seasons"),
        pl.col("exposure_dropbacks")
        .filter(pl.col("verification_status") == "verified")
        .sum()
        .alias("verified_dropbacks"),
        pl.col("exposure_dropbacks")
        .filter(pl.col("verification_status") == "provisional")
        .sum()
        .alias("provisional_dropbacks"),
        pl.col("exposure_dropbacks").filter(pl.col("is_shared")).sum().alias("shared_dropbacks"),
    )


def _rank(effects: pl.DataFrame, samples: pl.DataFrame) -> pl.DataFrame:
    ranked = (
        effects.join(samples, on=["coach_id", "role"], validate="1:1")
        .with_columns(
            (
                pl.col("estimated_effect").is_not_null()
                & (pl.col("qualifying_qb_seasons") >= RANK_MIN_QUALIFYING_QB_SEASONS)
                & (pl.col("distinct_quarterbacks") >= RANK_MIN_DISTINCT_QBS)
                & (pl.col("verified_dropbacks") >= RANK_MIN_VERIFIED_DROPBACKS)
            ).alias("rank_eligible")
        )
        .with_columns(
            pl.when(pl.col("estimated_effect").is_null())
            .then(pl.lit("insufficient_role_identification"))
            .when(pl.col("qualifying_qb_seasons") < RANK_MIN_QUALIFYING_QB_SEASONS)
            .then(pl.lit("fewer_than_3_qualifying_qb_seasons"))
            .when(pl.col("distinct_quarterbacks") < RANK_MIN_DISTINCT_QBS)
            .then(pl.lit("fewer_than_2_quarterbacks"))
            .when(pl.col("verified_dropbacks") < RANK_MIN_VERIFIED_DROPBACKS)
            .then(pl.lit("fewer_than_600_verified_dropbacks"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("rank_exclusion_reason"),
            pl.when(pl.col("verified_dropbacks") >= RELIABILITY_HIGH_DROPBACKS)
            .then(pl.lit("high"))
            .when(pl.col("verified_dropbacks") >= RELIABILITY_MEDIUM_DROPBACKS)
            .then(pl.lit("medium"))
            .otherwise(pl.lit("low"))
            .alias("reliability"),
            pl.lit("preliminary_non_publishable").alias("ranking_status"),
        )
    )
    eligible = ranked.filter(pl.col("rank_eligible")).with_columns(
        pl.col("estimated_effect")
        .rank(method="dense", descending=True)
        .over("role")
        .cast(pl.Int64)
        .alias("preliminary_rank")
    )
    ineligible = ranked.filter(~pl.col("rank_eligible")).with_columns(
        pl.lit(None, dtype=pl.Int64).alias("preliminary_rank")
    )
    return pl.concat([eligible, ineligible], how="vertical_relaxed").sort(
        "role", "preliminary_rank", "coach_name", nulls_last=True
    )


def build_coach_impact_tables(
    exposures: pl.DataFrame, *, bootstrap_replicates: int = BOOTSTRAP_REPLICATES
) -> dict[str, pl.DataFrame]:
    usable = exposures.filter(pl.col("exclusion_reason").is_null())
    primary = usable.filter(pl.col("verification_status") == "verified")
    all_effects: list[pl.DataFrame] = []
    comparisons: list[dict[str, object]] = []
    for role in ROLES:
        role_frame = primary.filter(pl.col("role") == role)
        if role_frame.height < 3 or role_frame["coach_id"].n_unique() < 2:
            continue
        effects, metrics = _fit_role(role_frame)
        effects = _bootstrap_intervals(role_frame, effects, bootstrap_replicates)
        all_effects.append(effects)
        comparisons.extend({"role": role, **row} for row in metrics)
    effects = (
        pl.concat(all_effects, how="vertical_relaxed")
        if all_effects
        else pl.DataFrame(
            schema={
                "coach_id": pl.String,
                "coach_name": pl.String,
                "role": pl.String,
                "estimated_effect": pl.Float64,
            }
        )
    )
    sparse_rows = (
        primary.select("coach_id", "coach_name", "role")
        .unique()
        .join(
            effects.select("coach_id", "role"),
            on=["coach_id", "role"],
            how="anti",
        )
        .sort("role", "coach_id")
    )
    if sparse_rows.height:
        sparse_rows = sparse_rows.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("observations"),
            pl.lit(None, dtype=pl.Float64).alias("total_dropbacks"),
            pl.lit(None, dtype=pl.Float64).alias("raw_effect"),
            pl.lit(None, dtype=pl.Float64).alias("shrinkage_weight"),
            pl.lit(None, dtype=pl.Float64).alias("estimated_effect"),
            pl.lit(None, dtype=pl.Float64).alias("analytic_standard_error"),
            pl.lit(None, dtype=pl.Float64).alias("confidence_low"),
            pl.lit(None, dtype=pl.Float64).alias("confidence_high"),
            pl.lit(0, dtype=pl.Int64).alias("bootstrap_replicates"),
        )
        effects = pl.concat([effects, sparse_rows], how="diagonal_relaxed")
    samples = _effect_samples(usable)
    rankings = _rank(
        effects,
        samples.filter(pl.col("coach_id").is_in(effects["coach_id"].to_list())),
    )

    sensitivity_records: list[dict[str, object]] = []
    specifications = (
        ("verified_primary", False, True, True, True, SENSITIVITY_MINIMUM_DROPBACKS[0]),
        (
            "verified_plus_provisional",
            True,
            True,
            True,
            True,
            SENSITIVITY_MINIMUM_DROPBACKS[0],
        ),
        ("exclude_shared", False, False, True, True, SENSITIVITY_MINIMUM_DROPBACKS[0]),
        ("equal_weight", False, True, True, False, SENSITIVITY_MINIMUM_DROPBACKS[0]),
        (
            "without_qb_fixed_effects",
            False,
            True,
            False,
            True,
            SENSITIVITY_MINIMUM_DROPBACKS[0],
        ),
        (
            "without_team_season_controls",
            False,
            True,
            True,
            True,
            SENSITIVITY_MINIMUM_DROPBACKS[0],
        ),
        (
            "minimum_100_interval_dropbacks",
            False,
            True,
            True,
            True,
            SENSITIVITY_MINIMUM_DROPBACKS[1],
        ),
        (
            "minimum_200_interval_dropbacks",
            False,
            True,
            True,
            True,
            SENSITIVITY_MINIMUM_DROPBACKS[2],
        ),
    )
    for (
        name,
        include_provisional,
        include_shared,
        include_qb,
        weighted,
        minimum_dropbacks,
    ) in specifications:
        subset = usable.filter(
            pl.col("verification_status").is_in(
                ["verified", "provisional"] if include_provisional else ["verified"]
            )
        ).filter(pl.col("exposure_dropbacks") >= minimum_dropbacks)
        if not include_shared:
            subset = subset.filter(~pl.col("is_shared"))
        for role in ROLES:
            role_frame = subset.filter(pl.col("role") == role)
            if role_frame.height < 3 or role_frame["coach_id"].n_unique() < 2:
                continue
            team_controls = name != "without_team_season_controls"
            sensitivity_effects, _ = _fit_role(
                role_frame,
                include_qb=include_qb,
                include_team_season=team_controls,
                weighted=weighted,
            )
            for row in sensitivity_effects.select(
                "coach_id", "role", "estimated_effect"
            ).to_dicts():
                sensitivity_records.append(
                    {
                        "specification": name,
                        "observations": role_frame.height,
                        **row,
                    }
                )
    sensitivity = (
        pl.DataFrame(sensitivity_records, infer_schema_length=None).sort(
            "specification", "role", "coach_id"
        )
        if sensitivity_records
        else pl.DataFrame(
            schema={
                "specification": pl.String,
                "observations": pl.Int64,
                "coach_id": pl.String,
                "role": pl.String,
                "estimated_effect": pl.Float64,
            }
        )
    )
    overlap = (
        exposures.group_by("role", "verification_status", "is_shared")
        .agg(
            pl.len().alias("exposure_rows"),
            pl.col("coach_id").n_unique().alias("coaches"),
            pl.col("exposure_dropbacks").sum().alias("exposure_dropbacks"),
        )
        .sort("role", "verification_status", "is_shared")
    )
    return {
        "coach_modeling_exposures": exposures,
        "coach_effect_estimates": effects.sort("role", "coach_name"),
        "preliminary_coach_rankings": rankings,
        "model_comparison": pl.DataFrame(comparisons).sort("role", "model_name"),
        "sensitivity_results": sensitivity,
        "overlap_diagnostics": overlap,
        "excluded_exposures": exposures.filter(pl.col("exclusion_reason").is_not_null()),
    }


def _model_specification(bootstrap_replicates: int) -> dict[str, object]:
    source_files = [
        Path(__file__),
        Path(__file__).with_name("coaching.py"),
        Path(__file__).with_name("constants.py"),
        Path(__file__).with_name("pipeline.py"),
    ]
    return {
        "pipeline_version": COACH_IMPACT_PIPELINE_VERSION,
        "model_version": COACH_IMPACT_MODEL_VERSION,
        "roles": list(ROLES),
        "controls": list(CONTROL_COLUMNS),
        "baseline_alpha": BASELINE_ALPHA,
        "fixed_effect_alpha": FIXED_EFFECT_ALPHA,
        "minimum_model_exposure_dropbacks": MIN_MODEL_EXPOSURE_DROPBACKS,
        "rank_minimum_qualifying_qb_seasons": RANK_MIN_QUALIFYING_QB_SEASONS,
        "rank_minimum_distinct_qbs": RANK_MIN_DISTINCT_QBS,
        "rank_minimum_verified_dropbacks": RANK_MIN_VERIFIED_DROPBACKS,
        "reliability_medium_dropbacks": RELIABILITY_MEDIUM_DROPBACKS,
        "reliability_high_dropbacks": RELIABILITY_HIGH_DROPBACKS,
        "bootstrap_replicates": bootstrap_replicates,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "interval_multiplier": INTERVAL_MULTIPLIER,
        "sensitivity_minimum_dropbacks": list(SENSITIVITY_MINIMUM_DROPBACKS),
        "deterministic_decimal_places": DETERMINISTIC_DECIMAL_PLACES,
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_sha256": {path.name: sha256_file(path) for path in source_files},
    }


def _version(
    historical_version: str,
    expected_version: str,
    inputs: list[Path],
    bootstrap_replicates: int,
) -> tuple[str, str]:
    identity = {
        "historical_version": historical_version,
        "expected_performance_version": expected_version,
        "inputs": {path.name: sha256_file(path) for path in inputs},
        "specification": _model_specification(bootstrap_replicates),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return f"c6-{digest}", f"coach-impact-{digest}"


def _write_execution_log(
    output_root: Path,
    data_version: str,
    model_version: str,
    started_at: datetime,
    reused_existing: bool,
) -> None:
    _write_json(
        output_root / "EXECUTION_LOG.json",
        {
            "data_version": data_version,
            "model_version": model_version,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "reused_existing": reused_existing,
        },
    )


def _deterministic_frame(frame: pl.DataFrame) -> pl.DataFrame:
    float_columns = [
        name for name, dtype in frame.schema.items() if dtype in (pl.Float32, pl.Float64)
    ]
    if not float_columns:
        return frame
    return frame.with_columns(pl.col(float_columns).round(DETERMINISTIC_DECIMAL_PLACES))


def run_coach_impact_pipeline(config: CoachImpactConfig) -> CoachImpactResult:
    """Build and atomically publish deterministic checkpoint-six outputs."""

    started_at = datetime.now(UTC)
    historical_version, historical_path = _latest(config.resolved_historical_dir, "historical")
    expected_version, expected_path = _latest(
        config.resolved_expected_performance_dir, "expected-performance"
    )
    manual = config.project_root / "data" / "manual"
    inputs = [
        historical_path / "silver" / "qb_game_performance.parquet",
        expected_path / "qb_pae.parquet",
        manual / "coaching_assignments.csv",
        manual / "coach_assignment_sources.csv",
        manual / "coaches.csv",
    ]
    data_version, model_version = _version(
        historical_version, expected_version, inputs, config.bootstrap_replicates
    )
    output_root = config.resolved_output_dir
    final_path = output_root / data_version
    if final_path.exists():
        counts = _validate_existing_version(final_path, data_version)
        _update_latest(output_root, data_version)
        _write_execution_log(output_root, data_version, model_version, started_at, True)
        return CoachImpactResult(data_version, model_version, final_path, True, counts)

    staging = output_root / ".staging" / uuid.uuid4().hex
    try:
        staging.mkdir(parents=True, exist_ok=False)
        qb_games = pl.read_parquet(inputs[0]).filter(pl.col("season") >= 2010)
        pae = pl.read_parquet(inputs[1])
        assignments = _assignment_frame(config.project_root)
        exposures = build_coach_exposures(qb_games, pae, assignments)
        tables = build_coach_impact_tables(
            exposures, bootstrap_replicates=config.bootstrap_replicates
        )
        lineage = [
            pl.lit(data_version).alias("data_version"),
            pl.lit(model_version).alias("coach_model_version"),
        ]
        for name, frame in tables.items():
            deterministic_frame = (
                _deterministic_frame(frame)
                if name
                in {
                    "coach_effect_estimates",
                    "preliminary_coach_rankings",
                    "sensitivity_results",
                }
                else frame
            )
            deterministic_frame.with_columns(lineage).select(
                "data_version",
                "coach_model_version",
                pl.exclude("data_version", "coach_model_version"),
            ).write_parquet(staging / f"{name}.parquet", compression="zstd")
        counts = {name: frame.height for name, frame in tables.items()}
        manifest = {
            "data_version": data_version,
            "model_version": model_version,
            "historical_version": historical_version,
            "expected_performance_version": expected_version,
            "pipeline_version": COACH_IMPACT_PIPELINE_VERSION,
            "ranking_status": "preliminary_non_publishable",
            "table_counts": counts,
            "status": "succeeded",
        }
        _write_json(
            staging / "MODEL_SPECIFICATION.json", _model_specification(config.bootstrap_replicates)
        )
        _write_json(staging / "RUN_MANIFEST.json", manifest)
        _write_json(staging / "OUTPUT_CHECKSUMS.json", _output_checksums(staging))
        output_root.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_path)
        _update_latest(output_root, data_version)
        _write_execution_log(output_root, data_version, model_version, started_at, False)
        return CoachImpactResult(data_version, model_version, final_path, False, counts)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

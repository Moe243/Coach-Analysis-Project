"""Deterministic, research-only Coach Effect equation analysis.

This module consumes frozen production/research artifacts and writes only beneath the ignored
``research/coach_effect/outputs/checkpoint_12`` directory.  It never writes serving data, model
artifacts, database state, API contracts, or frontend assets.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import scipy
import sklearn
from scipy.stats import rankdata, spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nfl_coaching_impact.coach_impact import build_coach_exposures
from nfl_coaching_impact.constants import TEAM_ALIAS_TO_CANONICAL
from nfl_coaching_impact.sources import sha256_file
from research.coach_effect.checkpoint_eleven import _write_csv
from research.coach_effect.checkpoint_eleven_b import _evidence_assignments
from research.coach_effect.config import (
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    PAE_FORMULA,
)

PRODUCTION_LOAD_ID = "22680407-d503-5290-bda2-18f4cbcb622a"
EXPECTED_PAE_DATA_VERSION = "c5-8fd5d1aba2598c59"
EXPECTED_PAE_MODEL_VERSION = "expected-performance-8fd5d1aba2598c59"
EXPECTED_PCAE_DATA_VERSION = "c11b-bbf7d43d0e4c4c05"
RESEARCH_SPECIFICATION = "coach-effect-equation-research-v1"
RANDOM_SEED = 20260907
PERMUTATIONS = 1_000
BOOTSTRAP_REPLICATES = 500
MOVEMENT_ALPHA = 10.0
JOINT_ALPHA = 10.0
MIN_MOVEMENT_TRAINING_ROWS = 30
MIN_INTERVAL_DROPBACKS = 25.0
Q_SHRINKAGE_K_VALUES = (200.0, 400.0, 600.0)
P_SHRINKAGE_K_VALUES = (500.0, 1_000.0, 2_000.0)
ROLES = ("head_coach", "offensive_coordinator", "quarterbacks_coach", "play_caller")
PAE_KEY = ("load_id", "player_id", "team_id", "season")
Q_FEATURES = (
    "prior_pae",
    "prior_actual_epa_per_dropback",
    "prior_expected_epa_per_dropback",
    "prior_cpoe",
    "prior_success_rate",
    "prior_sack_rate",
    "prior_dropbacks",
    "age",
    "nfl_experience",
    "changed_team_numeric",
    "season",
)
ENVIRONMENT_FEATURES = (
    "prior_protection_score",
    "wr_quality_score",
    "te_quality_score",
    "receiving_quality_score",
    "run_quality_score",
    "sos_pass_defense_strength",
    "expected_epa_per_dropback",
)
SCHEME_FEATURES = (
    "personnel_11_rate",
    "personnel_12_rate",
    "personnel_21_rate",
    "shotgun_rate",
    "motion_rate",
    "play_action_rate",
    "screen_rate",
    "rpo_rate",
    "no_huddle_rate",
    "early_down_pass_rate",
)
AVAILABLE_SCHEME_FEATURES = ("shotgun_rate", "no_huddle_rate", "early_down_pass_rate")
CORE_SCORE_COMPONENTS = ("q_development_signal", "pcae")
OUTPUT_NAMES = (
    "joined_research_table.csv",
    "fold_definitions.csv",
    "sample_sizes.csv",
    "q_estimates.csv",
    "pcae_estimates.csv",
    "reliability.csv",
    "future_validation.csv",
    "qb_holdouts.csv",
    "team_holdouts.csv",
    "placebos.csv",
    "environment_sensitivity.csv",
    "scheme_portability.csv",
    "model_comparisons.csv",
    "weights.csv",
    "shrinkage.csv",
    "confidence.csv",
    "suppression.csv",
    "presentation_0_100.csv",
    "role_readiness.csv",
)


@dataclass(frozen=True)
class ResearchSources:
    historical_version: str
    enhancement_version: str
    pae_path: Path
    qb_games_path: Path
    environment_path: Path
    team_statistics_path: Path
    pcae_path: Path
    pcae_manifest_path: Path
    pbp_root: Path


def _latest(root: Path) -> str:
    value = (root / "LATEST").read_text(encoding="utf-8").strip()
    if not value or not (root / value).is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return value


def _sources(project_root: Path) -> ResearchSources:
    historical_root = project_root / "data/processed/historical"
    enhancement_root = project_root / "data/processed/enhancements"
    historical_version = _latest(historical_root)
    enhancement_version = _latest(enhancement_root)
    enhancement = enhancement_root / enhancement_version
    pcae_root = project_root / "research/coach_effect/outputs/checkpoint_11b"
    pcae_version = _latest(pcae_root)
    if pcae_version != EXPECTED_PCAE_DATA_VERSION:
        raise ValueError(
            f"checkpoint-twelve requires PCAE {EXPECTED_PCAE_DATA_VERSION}, got {pcae_version}"
        )
    pcae = pcae_root / pcae_version
    return ResearchSources(
        historical_version=historical_version,
        enhancement_version=enhancement_version,
        pae_path=enhancement / "canonical_qb_pae.parquet",
        qb_games_path=enhancement / "canonical_qb_game_performance.parquet",
        environment_path=enhancement / "inherited_environment_features.parquet",
        team_statistics_path=enhancement / "team_season_statistics.parquet",
        pcae_path=pcae / "historical_pcae.csv",
        pcae_manifest_path=pcae / "MANIFEST.json",
        pbp_root=(historical_root / historical_version / "bronze/play_by_play"),
    )


def _stable_seed(label: str) -> int:
    digest = hashlib.sha256(f"{RANDOM_SEED}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _pearson(left: Iterable[float], right: Iterable[float]) -> float | None:
    x = np.asarray(list(left), dtype=float)
    y = np.asarray(list(right), dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(left: Iterable[float], right: Iterable[float]) -> float | None:
    x = np.asarray(list(left), dtype=float)
    y = np.asarray(list(right), dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(spearmanr(x, y).statistic)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int | None]:
    if len(actual) == 0:
        return {
            "n": 0,
            "pearson": None,
            "spearman": None,
            "rmse": None,
            "mae": None,
            "direction_accuracy": None,
            "calibration_slope": None,
            "calibration_intercept": None,
        }
    calibration = LinearRegression().fit(predicted.reshape(-1, 1), actual)
    return {
        "n": len(actual),
        "pearson": _pearson(actual, predicted),
        "spearman": _spearman(actual, predicted),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "mae": float(mean_absolute_error(actual, predicted)),
        "direction_accuracy": float(np.mean(np.sign(actual) == np.sign(predicted))),
        "calibration_slope": float(calibration.coef_[0]),
        "calibration_intercept": float(calibration.intercept_),
    }


def _canonical_team(team_id: str) -> str:
    canonical = TEAM_ALIAS_TO_CANONICAL.get(team_id)
    if canonical is None:
        raise ValueError(f"unresolved coaching team ID: {team_id}")
    return f"team_{canonical.lower()}"


def _assignment_frame(project_root: Path) -> pl.DataFrame:
    rows = _evidence_assignments(project_root)
    assignments = (
        pl.DataFrame(rows, infer_schema_length=None)
        .with_columns(
            pl.col("season", "start_week", "end_week").cast(pl.Int64),
            (pl.col("is_interim") == "true").alias("is_interim"),
            (pl.col("is_shared") == "true").alias("is_shared"),
            (pl.col("is_retained") == "true").alias("is_retained"),
            pl.col("team_id")
            .map_elements(_canonical_team, return_dtype=pl.String)
            .alias("canonical_team_id"),
            pl.col("coach_canonical_name").alias("coach_name"),
        )
        .filter(pl.col("verification_status") == "verified")
    )
    if assignments["assignment_key"].n_unique() != assignments.height:
        raise ValueError("verified evidence has duplicate assignment keys")
    unsupported_callers = assignments.filter(
        (pl.col("role") == "play_caller")
        & (
            (pl.col("primary_source_url").is_null())
            | (pl.col("primary_source_url").str.strip_chars() == "")
        )
    )
    if unsupported_callers.height:
        raise ValueError("play-caller research rows require explicit source evidence")
    return assignments.filter(
        (pl.col("role") != "play_caller") | (pl.col("interval_basis") != "season_designation")
    )


def _load_pae(path: Path) -> pl.DataFrame:
    pae = pl.read_parquet(path).with_columns(pl.lit(PRODUCTION_LOAD_ID).alias("load_id"))
    if pae["data_version"].unique().to_list() != [EXPECTED_PAE_DATA_VERSION]:
        raise ValueError("unexpected canonical PAE data version")
    if pae["model_version"].unique().to_list() != [EXPECTED_PAE_MODEL_VERSION]:
        raise ValueError("unexpected canonical PAE model version")
    if pae.select(PAE_KEY).n_unique() != pae.height:
        raise ValueError("canonical PAE has duplicate full-lineage keys")
    if pae.filter(~pl.col("is_out_of_sample")).height:
        raise ValueError("checkpoint-twelve requires out-of-sample PAE")
    mismatch = pae.filter(
        (
            pl.col("actual_epa_per_dropback")
            - pl.col("expected_epa_per_dropback")
            - pl.col("performance_above_expectation")
        ).abs()
        > 1e-12
    )
    if mismatch.height:
        raise ValueError("PAE arithmetic does not reconcile")
    leaked = pae.filter(
        pl.col("feature_source_max_season").is_not_null()
        & (pl.col("feature_source_max_season") >= pl.col("season"))
    )
    if leaked.height:
        raise ValueError("PAE contains target/future-season features")
    return pae.sort("season", "player_id", "team_id")


def _ridge_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=MOVEMENT_ALPHA)),
        ]
    )


def fit_training_only_ridge(
    training: pl.DataFrame,
    scoring: pl.DataFrame,
    *,
    features: tuple[str, ...],
    outcome: str,
    weight: str | None = None,
    alpha: float = MOVEMENT_ALPHA,
) -> tuple[np.ndarray, Pipeline]:
    """Fit preprocessing and Ridge only on the supplied training frame."""

    if training.is_empty() or scoring.is_empty():
        raise ValueError("training and scoring frames must be nonempty")
    pipeline = _ridge_pipeline()
    pipeline.set_params(ridge__alpha=alpha)
    sample_weight = training[weight].to_numpy() if weight else None
    pipeline.fit(
        training.select(features).cast(pl.Float64).to_numpy(),
        training[outcome].to_numpy(),
        ridge__sample_weight=sample_weight,
    )
    prediction = pipeline.predict(scoring.select(features).cast(pl.Float64).to_numpy())
    return np.asarray(prediction, dtype=float), pipeline


def _player_season_history(pae: pl.DataFrame) -> pl.DataFrame:
    player_seasons = (
        pae.group_by("player_id", "season")
        .agg(
            (
                (pl.col("performance_above_expectation") * pl.col("dropbacks")).sum()
                / pl.col("dropbacks").sum()
            ).alias("prior_pae"),
            (
                (pl.col("actual_epa_per_dropback") * pl.col("dropbacks")).sum()
                / pl.col("dropbacks").sum()
            ).alias("prior_actual_epa_per_dropback"),
            (
                (pl.col("expected_epa_per_dropback") * pl.col("dropbacks")).sum()
                / pl.col("dropbacks").sum()
            ).alias("prior_expected_epa_per_dropback"),
            pl.col("dropbacks").sum().alias("prior_pae_dropbacks"),
        )
        .with_columns((pl.col("season") + 1).alias("season"))
    )
    return pae.join(player_seasons, on=["player_id", "season"], how="inner", validate="m:1")


def rolling_movement_predictions(pae: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Score QB normal progression with expanding folds ending before each target season."""

    transitions = _player_season_history(pae).with_columns(
        (pl.col("performance_above_expectation") - pl.col("prior_pae")).alias(
            "actual_qb_delta_pae"
        ),
        pl.col("changed_team").cast(pl.Int8).alias("changed_team_numeric"),
    )
    predictions: list[pl.DataFrame] = []
    folds: list[dict[str, Any]] = []
    for target_season in sorted(transitions["season"].unique().to_list()):
        train = transitions.filter(pl.col("season") < target_season)
        test = transitions.filter(pl.col("season") == target_season)
        if train.height < MIN_MOVEMENT_TRAINING_ROWS or test.is_empty():
            continue
        if train["season"].max() >= target_season:
            raise ValueError("movement fold includes target or future season")
        predicted, model = fit_training_only_ridge(
            train,
            test,
            features=Q_FEATURES,
            outcome="actual_qb_delta_pae",
            weight="dropbacks",
        )
        predictions.append(
            test.select(*PAE_KEY, "prior_pae", "actual_qb_delta_pae").with_columns(
                pl.Series("expected_normal_qb_delta", predicted),
                (pl.col("actual_qb_delta_pae") - pl.Series(predicted)).alias(
                    "full_season_q_development_signal"
                ),
            )
        )
        scale = model.named_steps["scale"]
        folds.append(
            {
                "fold_family": "qb_normal_progression",
                "target_season": target_season,
                "training_start_season": int(train["season"].min()),
                "training_end_season": int(train["season"].max()),
                "training_rows": train.height,
                "test_rows": test.height,
                "preprocessing_fit_scope": "training_only",
                "feature_center_sha256": hashlib.sha256(
                    np.asarray(scale.mean_, dtype=np.float64).tobytes()
                ).hexdigest(),
                "residualization_fit_scope": "not_applicable",
            }
        )
    if not predictions:
        raise ValueError("no leakage-safe QB-movement folds were available")
    return (
        pl.concat(predictions).sort("season", "player_id", "team_id"),
        pl.DataFrame(folds).sort("target_season"),
    )


def _map_pcae(assignments: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    if pcae["data_version"].unique().to_list() != [EXPECTED_PCAE_DATA_VERSION]:
        raise ValueError("unexpected PCAE data version")
    if pcae.filter(pl.col("verification_status") != "verified").height:
        raise ValueError("PCAE contains non-verified attribution")
    if pcae.filter(pl.col("attributed_play_count") <= 0).height:
        raise ValueError("PCAE zero-attribution rows must remain missing")
    pcae = pcae.with_columns(
        pl.col("team_id").map_elements(_canonical_team, return_dtype=pl.String).alias("team_id")
    )
    caller_assignments = assignments.filter(pl.col("role") == "play_caller").select(
        "coach_id",
        pl.col("canonical_team_id").alias("team_id"),
        "season",
        "start_week",
        "end_week",
        "assignment_key",
        "interval_basis",
        "primary_source_url",
    )
    keys = ["coach_id", "team_id", "season", "start_week", "end_week"]
    mapped = pcae.join(caller_assignments, on=keys, how="left", validate="1:1")
    if mapped["assignment_key"].null_count():
        sample = mapped.filter(pl.col("assignment_key").is_null()).select(keys).head(5).to_dicts()
        raise ValueError(f"PCAE does not map to verified assignments: {sample}")
    if mapped["assignment_key"].n_unique() != mapped.height:
        raise ValueError("multiple PCAE rows mapped to one assignment")
    return mapped.sort("season", "team_id", "start_week", "coach_id")


def build_joined_research_table(
    project_root: Path,
    sources: ResearchSources,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build the complete interval-aware research table and movement folds."""

    pae = _load_pae(sources.pae_path)
    assignments = _assignment_frame(project_root)
    games = pl.read_parquet(sources.qb_games_path).filter(pl.col("season") >= 2010)
    exposures = build_coach_exposures(games, pae, assignments).with_columns(
        pl.lit(PRODUCTION_LOAD_ID).alias("load_id"),
        pl.lit(EXPECTED_PAE_DATA_VERSION).alias("pae_data_version"),
        pl.lit(EXPECTED_PCAE_DATA_VERSION).alias("pcae_data_version"),
    )
    exposures = exposures.join(
        pae.select(
            *PAE_KEY,
            "prior_cpoe",
            "prior_success_rate",
            "prior_sack_rate",
            "prior_interception_rate",
            "prior_touchdown_rate",
        ),
        on=list(PAE_KEY),
        validate="m:1",
    )
    movement, folds = rolling_movement_predictions(pae)
    joined = exposures.join(movement, on=list(PAE_KEY), how="left", validate="m:1").with_columns(
        (pl.col("coach_interval_pae") - pl.col("prior_pae")).alias("interval_actual_qb_delta_pae"),
        (
            pl.col("coach_interval_pae") - pl.col("prior_pae") - pl.col("expected_normal_qb_delta")
        ).alias("q_development_signal"),
    )
    environment = pl.read_parquet(sources.environment_path).rename(
        {
            "data_version": "environment_data_version",
            "feature_source_max_season": "environment_feature_source_max_season",
            "feature_version": "environment_feature_version",
        }
    )
    joined = joined.join(environment, on=["team_id", "season"], how="left", validate="m:1")
    raw_pcae = pl.read_csv(sources.pcae_path, infer_schema_length=None)
    mapped_pcae = _map_pcae(assignments, raw_pcae)
    pcae_columns = mapped_pcae.select(
        "assignment_key",
        "eligible_play_count",
        "attributed_play_count",
        "average_call_value",
        "league_average_call_value",
        "pcae",
        pl.col("model_version").alias("pcae_model_version"),
        "play_eligibility_version",
    )
    joined = joined.join(pcae_columns, on="assignment_key", how="left", validate="m:1")
    invalid_pcae = joined.filter(pl.col("pcae").is_not_null() & (pl.col("role") != "play_caller"))
    if invalid_pcae.height:
        raise ValueError("PCAE attached outside the verified play-caller role")
    if (
        joined.select("assignment_key", "player_id", "team_id", "season").n_unique()
        != joined.height
    ):
        raise ValueError("joined research table has duplicate assignment/QB/team/season rows")
    selected = joined.select(
        "load_id",
        "assignment_key",
        "coach_id",
        "coach_name",
        "player_id",
        "quarterback_name",
        "team_id",
        "season",
        "role",
        "start_week",
        "end_week",
        "interval_basis",
        pl.col("verification_status").alias("verification"),
        "confidence_level",
        "is_interim",
        "is_shared",
        "is_retained",
        "observed_games",
        "observed_dropbacks",
        "exposure_dropbacks",
        "exposure_fraction",
        "eligibility_status",
        "exclusion_reason",
        "actual_epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "coach_interval_pae",
        "prior_pae",
        "actual_qb_delta_pae",
        "expected_normal_qb_delta",
        "full_season_q_development_signal",
        "interval_actual_qb_delta_pae",
        "q_development_signal",
        "eligible_play_count",
        "attributed_play_count",
        "average_call_value",
        "league_average_call_value",
        "pcae",
        "age",
        "nfl_experience",
        "prior_dropbacks",
        "prior_epa_per_dropback",
        "prior_cpoe",
        "prior_success_rate",
        "prior_sack_rate",
        "prior_interception_rate",
        "prior_touchdown_rate",
        "changed_team",
        *ENVIRONMENT_FEATURES[:-1],
        "feature_source_max_season",
        "environment_feature_source_max_season",
        "pae_data_version",
        pl.col("model_version").alias("pae_model_version"),
        "pcae_data_version",
        "pcae_model_version",
        "play_eligibility_version",
        "environment_data_version",
        "environment_feature_version",
    ).sort("role", "season", "team_id", "start_week", "coach_id", "player_id")
    leaked = selected.filter(
        (
            pl.col("feature_source_max_season").is_not_null()
            & (pl.col("feature_source_max_season") >= pl.col("season"))
        )
        | (
            pl.col("environment_feature_source_max_season").is_not_null()
            & (pl.col("environment_feature_source_max_season") >= pl.col("season"))
        )
    )
    if leaked.height:
        raise ValueError("joined research context contains target/future-season inputs")
    return selected, folds, mapped_pcae


def _weighted_signal_table(
    frame: pl.DataFrame,
    *,
    signal: str,
    weight: str,
    group: tuple[str, ...],
) -> pl.DataFrame:
    return (
        frame.filter(
            pl.col(signal).is_not_null()
            & pl.col(signal).is_finite()
            & pl.col(weight).is_not_null()
            & (pl.col(weight) > 0)
        )
        .group_by(*group)
        .agg(
            ((pl.col(signal) * pl.col(weight)).sum() / pl.col(weight).sum()).alias(signal),
            pl.col(weight).sum().alias("signal_exposure"),
        )
        .sort(*group)
    )


def empirical_bayes(
    observations: pl.DataFrame,
    *,
    signal: str,
    exposure: str,
    group_columns: tuple[str, ...] = ("role", "coach_id", "coach_name"),
) -> pl.DataFrame:
    """Shrink group means with a method-of-moments normal-normal estimator."""

    usable = observations.filter(
        pl.col(signal).is_not_null() & pl.col(signal).is_finite() & (pl.col(exposure) > 0)
    )
    means = usable.group_by(*group_columns).agg(
        ((pl.col(signal) * pl.col(exposure)).sum() / pl.col(exposure).sum()).alias("raw_estimate"),
        pl.col(exposure).sum().alias("total_exposure"),
        pl.len().alias("observations"),
        pl.col("season").n_unique().alias("seasons") if "season" in usable.columns else pl.len(),
        (
            pl.col("player_id").n_unique().alias("unique_qbs")
            if "player_id" in usable.columns
            else pl.lit(None, dtype=pl.UInt32).alias("unique_qbs")
        ),
        (
            pl.col("team_id").n_unique().alias("unique_teams")
            if "team_id" in usable.columns
            else pl.lit(None, dtype=pl.UInt32).alias("unique_teams")
        ),
    )
    joined = usable.join(means.select(*group_columns, "raw_estimate"), on=list(group_columns))
    residual_df = max(usable.height - means.height, 1)
    sigma2 = max(
        float(
            joined.select(
                (pl.col(exposure) * (pl.col(signal) - pl.col("raw_estimate")) ** 2).sum()
            ).item()
            / residual_df
        ),
        1e-12,
    )
    raw = means["raw_estimate"].to_numpy()
    total = means["total_exposure"].to_numpy()
    center = float(np.average(raw, weights=total))
    sampling = sigma2 / total
    tau2 = max(
        float(np.average((raw - center) ** 2, weights=total)) - float(np.mean(sampling)),
        0.0,
    )
    variance_boundary = tau2 <= 0
    shrinkage = tau2 / (tau2 + sampling) if not variance_boundary else np.zeros_like(sampling)
    posterior = center + shrinkage * (raw - center)
    posterior_variance = 1.0 / (1.0 / tau2 + 1.0 / sampling) if not variance_boundary else sampling
    return (
        means.with_columns(
            pl.Series("sampling_variance", sampling),
            pl.lit(sigma2).alias("residual_variance"),
            pl.lit(float(tau2)).alias("between_coach_variance"),
            pl.lit(center).alias("prior_center"),
            pl.Series("shrinkage_weight", shrinkage),
            pl.Series("posterior_estimate", posterior),
            pl.Series("posterior_standard_error", np.sqrt(posterior_variance)),
            pl.lit(variance_boundary).alias("variance_component_at_boundary"),
            pl.lit(
                "normal_normal_posterior"
                if not variance_boundary
                else "sampling_variance_fallback_at_zero_between_coach_boundary"
            ).alias("interval_method"),
        )
        .with_columns(
            (pl.col("posterior_estimate") - 1.96 * pl.col("posterior_standard_error")).alias(
                "interval_low"
            ),
            (pl.col("posterior_estimate") + 1.96 * pl.col("posterior_standard_error")).alias(
                "interval_high"
            ),
        )
        .sort(*group_columns)
    )


def _q_observations(joined: pl.DataFrame) -> pl.DataFrame:
    return joined.filter(
        pl.col("q_development_signal").is_not_null()
        & (pl.col("exposure_dropbacks") >= MIN_INTERVAL_DROPBACKS)
        & (pl.col("verification") == "verified")
    )


def build_estimates(
    joined: pl.DataFrame, mapped_pcae: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    q = _q_observations(joined)
    q_estimates = empirical_bayes(
        q,
        signal="q_development_signal",
        exposure="exposure_dropbacks",
    ).with_columns(pl.lit("q_development").alias("signal"))
    p_observations = mapped_pcae.rename(
        {"coach_canonical_name": "coach_name", "attributed_play_count": "signal_exposure"}
    ).with_columns(pl.lit("play_caller").alias("role"))
    p_estimates = empirical_bayes(
        p_observations,
        signal="pcae",
        exposure="signal_exposure",
    ).with_columns(pl.lit("pcae").alias("signal"))
    shrinkage_rows: list[pl.DataFrame] = []
    for family, observations, signal, exposure, values in (
        ("q_development", q, "q_development_signal", "exposure_dropbacks", Q_SHRINKAGE_K_VALUES),
        ("pcae", p_observations, "pcae", "signal_exposure", P_SHRINKAGE_K_VALUES),
    ):
        raw = observations.group_by("role", "coach_id", "coach_name").agg(
            ((pl.col(signal) * pl.col(exposure)).sum() / pl.col(exposure).sum()).alias(
                "raw_estimate"
            ),
            pl.col(exposure).sum().alias("total_exposure"),
        )
        for value in values:
            shrinkage_rows.append(
                raw.with_columns(
                    pl.lit(family).alias("signal"),
                    pl.lit("exposure_over_exposure_plus_k").alias("method"),
                    pl.lit(value).alias("k"),
                    (pl.col("total_exposure") / (pl.col("total_exposure") + value)).alias(
                        "shrinkage_weight"
                    ),
                ).with_columns(
                    (pl.col("raw_estimate") * pl.col("shrinkage_weight")).alias("shrunken_estimate")
                )
            )
    for family, estimates in (("q_development", q_estimates), ("pcae", p_estimates)):
        shrinkage_rows.append(
            estimates.select(
                "role",
                "coach_id",
                "coach_name",
                pl.lit(family).alias("signal"),
                pl.lit("empirical_bayes_normal_normal").alias("method"),
                pl.lit(None, dtype=pl.Float64).alias("k"),
                "raw_estimate",
                "total_exposure",
                "shrinkage_weight",
                pl.col("posterior_estimate").alias("shrunken_estimate"),
            )
        )
    shrinkage = pl.concat(shrinkage_rows, how="diagonal_relaxed").sort(
        "signal", "role", "method", "k", "coach_id"
    )
    return q_estimates, p_estimates, shrinkage


def _coach_seasons(
    frame: pl.DataFrame, *, signal: str, exposure: str, role: str | None = None
) -> pl.DataFrame:
    source = frame.filter(pl.col("role") == role) if role else frame
    return _weighted_signal_table(
        source,
        signal=signal,
        weight=exposure,
        group=("coach_id", "coach_name", "season"),
    )


def _repeatability_row(
    table: pl.DataFrame,
    *,
    role: str,
    signal_name: str,
    signal: str,
) -> dict[str, Any]:
    counts = table.group_by("coach_id").len()
    repeated = table.join(
        counts.filter(pl.col("len") >= 2).select("coach_id"), on="coach_id", how="inner"
    )
    coaches = repeated["coach_id"].n_unique()
    if coaches < 2:
        return {
            "signal": signal_name,
            "role": role,
            "coach_seasons": table.height,
            "repeat_coaches": coaches,
            "consecutive_pairs": 0,
            "pearson": None,
            "spearman": None,
            "same_direction_rate": None,
            "within_coach_variance": None,
            "between_coach_variance": None,
            "one_season_reliability": None,
            "two_season_reliability": None,
            "multi_season_reliability": None,
            "bootstrap_pearson_low": None,
            "bootstrap_pearson_high": None,
        }
    prior = table.select(
        "coach_id", (pl.col("season") + 1).alias("season"), pl.col(signal).alias("prior_signal")
    )
    pairs = table.join(prior, on=["coach_id", "season"], how="inner", validate="1:1")
    values = [group[signal].to_numpy() for _, group in repeated.group_by("coach_id")]
    counts_array = np.asarray([len(item) for item in values], dtype=float)
    grand = float(repeated[signal].mean())
    between_ss = sum(len(item) * (float(np.mean(item)) - grand) ** 2 for item in values)
    within_ss = sum(float(np.sum((item - np.mean(item)) ** 2)) for item in values)
    between_ms = between_ss / (coaches - 1)
    within_df = int(counts_array.sum() - coaches)
    within_ms = within_ss / within_df if within_df else 0.0
    k_bar = float(counts_array.mean())
    denominator = between_ms + (k_bar - 1) * within_ms
    icc_raw = (between_ms - within_ms) / denominator if denominator else 0.0
    reliability = max(0.0, min(1.0, icc_raw))
    two = 2 * reliability / (1 + reliability) if reliability else 0.0
    multi = k_bar * reliability / (1 + (k_bar - 1) * reliability) if reliability else 0.0
    boot: list[float] = []
    coach_ids = sorted(repeated["coach_id"].unique().to_list())
    rng = np.random.default_rng(_stable_seed(f"reliability:{role}:{signal_name}"))
    for _ in range(BOOTSTRAP_REPLICATES):
        selected = rng.choice(coach_ids, len(coach_ids), replace=True)
        left: list[float] = []
        right: list[float] = []
        for coach_id in selected:
            coach_pairs = pairs.filter(pl.col("coach_id") == coach_id)
            left.extend(coach_pairs["prior_signal"].to_list())
            right.extend(coach_pairs[signal].to_list())
        correlation = _pearson(left, right)
        if correlation is not None:
            boot.append(correlation)
    return {
        "signal": signal_name,
        "role": role,
        "coach_seasons": table.height,
        "repeat_coaches": coaches,
        "consecutive_pairs": pairs.height,
        "pearson": _pearson(pairs["prior_signal"], pairs[signal]),
        "spearman": _spearman(pairs["prior_signal"], pairs[signal]),
        "same_direction_rate": (
            float(((pairs["prior_signal"] * pairs[signal]) > 0).mean()) if pairs.height else None
        ),
        "within_coach_variance": float(within_ms),
        "between_coach_variance": float(between_ms),
        "one_season_reliability": reliability,
        "two_season_reliability": two,
        "multi_season_reliability": multi,
        "bootstrap_pearson_low": float(np.quantile(boot, 0.025)) if boot else None,
        "bootstrap_pearson_high": float(np.quantile(boot, 0.975)) if boot else None,
    }


def build_reliability(
    joined: pl.DataFrame, mapped_pcae: pl.DataFrame
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    q = _q_observations(joined)
    tables: dict[str, pl.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for role in ROLES:
        table = _coach_seasons(
            q,
            signal="q_development_signal",
            exposure="exposure_dropbacks",
            role=role,
        )
        tables[f"q:{role}"] = table
        rows.append(
            _repeatability_row(
                table,
                role=role,
                signal_name="q_development",
                signal="q_development_signal",
            )
        )
    p = mapped_pcae.rename(
        {"coach_canonical_name": "coach_name", "attributed_play_count": "signal_exposure"}
    ).with_columns(pl.lit("play_caller").alias("role"))
    p_table = _coach_seasons(p, signal="pcae", exposure="signal_exposure")
    tables["pcae:play_caller"] = p_table
    rows.append(
        _repeatability_row(
            p_table,
            role="play_caller",
            signal_name="pcae",
            signal="pcae",
        )
    )
    return pl.DataFrame(rows).sort("signal", "role"), tables


def _portability_summary(
    observations: pl.DataFrame,
    *,
    role: str,
    signal_name: str,
    signal: str,
    exposure: str,
    holdout: str,
) -> dict[str, Any]:
    grouped = (
        observations.group_by("coach_id", holdout)
        .agg(
            ((pl.col(signal) * pl.col(exposure)).sum() / pl.col(exposure).sum()).alias("actual"),
            (pl.col(signal) * pl.col(exposure)).sum().alias("weighted_total"),
            pl.col(exposure).sum().alias("weight"),
        )
        .join(
            observations.group_by("coach_id").agg(
                (pl.col(signal) * pl.col(exposure)).sum().alias("coach_total"),
                pl.col(exposure).sum().alias("coach_weight"),
                pl.col(holdout).n_unique().alias("distinct_groups"),
            ),
            on="coach_id",
            validate="m:1",
        )
        .filter(pl.col("distinct_groups") >= 2)
        .with_columns(
            (
                (pl.col("coach_total") - pl.col("weighted_total"))
                / (pl.col("coach_weight") - pl.col("weight"))
            ).alias("prediction")
        )
        .filter(pl.col("prediction").is_finite())
    )
    actual = grouped["actual"].to_numpy()
    predicted = grouped["prediction"].to_numpy()
    metrics = _metrics(actual, predicted)
    boot: list[float] = []
    coach_ids = sorted(grouped["coach_id"].unique().to_list())
    rng = np.random.default_rng(_stable_seed(f"holdout:{role}:{signal_name}:{holdout}"))
    for _ in range(BOOTSTRAP_REPLICATES):
        selected = rng.choice(coach_ids, len(coach_ids), replace=True)
        pieces = [grouped.filter(pl.col("coach_id") == value) for value in selected]
        sample = pl.concat(pieces) if pieces else pl.DataFrame()
        correlation = _pearson(sample["actual"], sample["prediction"]) if sample.height else None
        if correlation is not None:
            boot.append(correlation)
    return {
        "signal": signal_name,
        "role": role,
        "holdout_dimension": holdout,
        "groups": grouped.height,
        "coaches": grouped["coach_id"].n_unique(),
        **metrics,
        "bootstrap_pearson_low": float(np.quantile(boot, 0.025)) if boot else None,
        "bootstrap_pearson_high": float(np.quantile(boot, 0.975)) if boot else None,
    }


def build_portability(
    joined: pl.DataFrame, mapped_pcae: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    q = _q_observations(joined)
    qb_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []
    for role in ROLES:
        role_rows = q.filter(pl.col("role") == role)
        qb_rows.append(
            _portability_summary(
                role_rows,
                role=role,
                signal_name="q_development",
                signal="q_development_signal",
                exposure="exposure_dropbacks",
                holdout="player_id",
            )
        )
        team_rows.append(
            _portability_summary(
                role_rows,
                role=role,
                signal_name="q_development",
                signal="q_development_signal",
                exposure="exposure_dropbacks",
                holdout="team_id",
            )
        )
    p = mapped_pcae.rename({"attributed_play_count": "signal_exposure"}).with_columns(
        pl.lit("play_caller").alias("role")
    )
    team_rows.append(
        _portability_summary(
            p,
            role="play_caller",
            signal_name="pcae",
            signal="pcae",
            exposure="signal_exposure",
            holdout="team_id",
        )
    )
    common = q.filter(
        (pl.col("role") == "play_caller") & pl.col("pcae").is_not_null()
    ).with_columns(((pl.col("q_development_signal") + pl.col("pcae")) / 2).alias("combined_signal"))
    team_rows.append(
        _portability_summary(
            common,
            role="play_caller",
            signal_name="equal_q_p",
            signal="combined_signal",
            exposure="exposure_dropbacks",
            holdout="team_id",
        )
    )
    return pl.DataFrame(qb_rows).sort("role"), pl.DataFrame(team_rows).sort("signal", "role")


def _history_pairs(common: pl.DataFrame, team_statistics: pl.DataFrame) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for row in common.sort("season", "coach_id", "team_id").to_dicts():
        history = common.filter(
            (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
        )
        if history.is_empty():
            continue
        records.append(
            {
                **row,
                "history_q": float(
                    np.average(history["q_development_signal"], weights=history["q_exposure"])
                ),
                "history_p": float(np.average(history["pcae"], weights=history["p_exposure"])),
                "history_seasons": history["season"].n_unique(),
            }
        )
    frame = pl.DataFrame(records) if records else pl.DataFrame()
    if frame.is_empty():
        return frame
    prior_offense = team_statistics.select(
        "team_id",
        (pl.col("season") + 1).alias("season"),
        pl.col("team_offensive_epa_per_play").alias("prior_team_offensive_epa"),
    )
    return frame.join(prior_offense, on=["team_id", "season"], how="left", validate="m:1")


def training_residual_components(
    train_q: np.ndarray,
    train_p: np.ndarray,
    score_q: np.ndarray,
    score_p: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Residualize Q/P using training rows only and transform training/scoring rows."""

    q_on_p = LinearRegression().fit(train_p.reshape(-1, 1), train_q)
    p_on_q = LinearRegression().fit(train_q.reshape(-1, 1), train_p)
    train_unique_q = train_q - q_on_p.predict(train_p.reshape(-1, 1))
    train_unique_p = train_p - p_on_q.predict(train_q.reshape(-1, 1))
    score_unique_q = score_q - q_on_p.predict(score_p.reshape(-1, 1))
    score_unique_p = score_p - p_on_q.predict(score_q.reshape(-1, 1))
    return (
        train_unique_q,
        train_unique_p,
        (train_q + train_p) / 2,
        score_unique_q,
        score_unique_p,
        (score_q + score_p) / 2,
    )


def build_future_models(
    joined: pl.DataFrame,
    mapped_pcae: pl.DataFrame,
    team_statistics: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    q = _q_observations(joined).filter(pl.col("role") == "play_caller")
    q_season = _weighted_signal_table(
        q,
        signal="q_development_signal",
        weight="exposure_dropbacks",
        group=("coach_id", "coach_name", "team_id", "season"),
    ).rename({"signal_exposure": "q_exposure"})
    p_season = _weighted_signal_table(
        mapped_pcae,
        signal="pcae",
        weight="attributed_play_count",
        group=("coach_id", "coach_canonical_name", "team_id", "season"),
    ).rename(
        {
            "coach_canonical_name": "coach_name",
            "signal_exposure": "p_exposure",
        }
    )
    common = q_season.join(
        p_season, on=["coach_id", "coach_name", "team_id", "season"], validate="1:1"
    )
    pairs = _history_pairs(common, team_statistics)
    predictions: list[pl.DataFrame] = []
    weights: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    if pairs.is_empty():
        return pl.DataFrame(), pl.DataFrame(), pl.DataFrame(), pl.DataFrame()
    for target in sorted(pairs["season"].unique().to_list()):
        train = pairs.filter(pl.col("season") < target)
        test = pairs.filter(pl.col("season") == target)
        if train.height < 10 or test.height < 2:
            continue
        if train["season"].max() >= target:
            raise ValueError("joint-model fold includes target/future season")
        q_center = float(train["q_development_signal"].mean())
        p_center = float(train["pcae"].mean())
        q_scale = float(train["q_development_signal"].std(ddof=0))
        p_scale = float(train["pcae"].std(ddof=0))
        if q_scale == 0 or p_scale == 0:
            continue
        train_q = (train["history_q"].to_numpy() - q_center) / q_scale
        train_p = (train["history_p"].to_numpy() - p_center) / p_scale
        test_q = (test["history_q"].to_numpy() - q_center) / q_scale
        test_p = (test["history_p"].to_numpy() - p_center) / p_scale
        y_train = (
            (train["q_development_signal"].to_numpy() - q_center) / q_scale
            + (train["pcae"].to_numpy() - p_center) / p_scale
        ) / 2
        y_test = (
            (test["q_development_signal"].to_numpy() - q_center) / q_scale
            + (test["pcae"].to_numpy() - p_center) / p_scale
        ) / 2
        model_1 = Ridge(alpha=JOINT_ALPHA).fit(train_q.reshape(-1, 1), y_train)
        model_2 = Ridge(alpha=JOINT_ALPHA).fit(train_p.reshape(-1, 1), y_train)
        model_4 = Ridge(alpha=JOINT_ALPHA).fit(np.column_stack([train_q, train_p]), y_train)
        components = training_residual_components(train_q, train_p, test_q, test_p)
        train_decomp = np.column_stack(components[:3])
        test_decomp = np.column_stack(components[3:])
        model_5 = Ridge(alpha=JOINT_ALPHA).fit(train_decomp, y_train)
        models = {
            "model_1_q_only": model_1.predict(test_q.reshape(-1, 1)),
            "model_2_pcae_only": model_2.predict(test_p.reshape(-1, 1)),
            "model_3_equal_q_p": (test_q + test_p) / 2,
            "model_4_learned_joint": model_4.predict(np.column_stack([test_q, test_p])),
            "model_5_overlap_decomposition": model_5.predict(test_decomp),
            "baseline_simple_historical_average": (test_q + test_p) / 2,
        }
        if train["prior_team_offensive_epa"].null_count() < train.height:
            train_prior = train.filter(pl.col("prior_team_offensive_epa").is_not_null())
            if train_prior.height >= 5 and test["prior_team_offensive_epa"].null_count() == 0:
                prior = Ridge(alpha=JOINT_ALPHA).fit(
                    train_prior.select("prior_team_offensive_epa").to_numpy(),
                    y_train[train["prior_team_offensive_epa"].is_not_null().to_numpy()],
                )
                models["baseline_prior_season_offense"] = prior.predict(
                    test.select("prior_team_offensive_epa").to_numpy()
                )
        for model_name, values in models.items():
            predictions.append(
                test.select("coach_id", "coach_name", "team_id", "season").with_columns(
                    pl.lit(target).alias("target_season"),
                    pl.lit(model_name).alias("model"),
                    pl.Series("actual_future_signal", y_test),
                    pl.Series("predicted_future_signal", values),
                )
            )
        for model_name, model, feature_names in (
            ("model_1_q_only", model_1, ("history_q",)),
            ("model_2_pcae_only", model_2, ("history_p",)),
            ("model_4_learned_joint", model_4, ("history_q", "history_p")),
            (
                "model_5_overlap_decomposition",
                model_5,
                ("unique_q", "unique_p", "shared_signal"),
            ),
        ):
            for feature, coefficient in zip(feature_names, model.coef_, strict=True):
                weights.append(
                    {
                        "target_season": target,
                        "model": model_name,
                        "feature": feature,
                        "coefficient": float(coefficient),
                        "intercept": float(model.intercept_),
                        "training_rows": train.height,
                    }
                )
        fold_rows.append(
            {
                "fold_family": "joint_coach_signal",
                "target_season": target,
                "training_start_season": int(train["season"].min()),
                "training_end_season": int(train["season"].max()),
                "training_rows": train.height,
                "test_rows": test.height,
                "preprocessing_fit_scope": "training_only",
                "feature_center_sha256": hashlib.sha256(
                    np.asarray([q_center, p_center], dtype=np.float64).tobytes()
                ).hexdigest(),
                "residualization_fit_scope": "training_only",
            }
        )
    future = pl.concat(predictions, how="diagonal_relaxed") if predictions else pl.DataFrame()
    comparison_rows: list[dict[str, Any]] = []
    if not future.is_empty():
        for model_name in sorted(future["model"].unique().to_list()):
            rows = future.filter(pl.col("model") == model_name)
            comparison_rows.append(
                {
                    "model": model_name,
                    "candidate_status": (
                        "candidate" if model_name.startswith("model_") else "baseline"
                    ),
                    **_metrics(
                        rows["actual_future_signal"].to_numpy(),
                        rows["predicted_future_signal"].to_numpy(),
                    ),
                }
            )
    overlap = _pearson(common["q_development_signal"], common["pcae"])
    comparison_rows.append(
        {
            "model": "diagnostic_q_p_overlap",
            "candidate_status": "diagnostic_not_candidate",
            "n": common.height,
            "pearson": overlap,
            "spearman": _spearman(common["q_development_signal"], common["pcae"]),
            "rmse": None,
            "mae": None,
            "direction_accuracy": float(
                np.mean(
                    np.sign(common["q_development_signal"].to_numpy())
                    == np.sign(common["pcae"].to_numpy())
                )
            ),
            "calibration_slope": None,
            "calibration_intercept": None,
            "shared_variance": overlap**2 if overlap is not None else None,
        }
    )
    comparison_rows.extend(
        {
            "model": name,
            "candidate_status": "same_season_descriptive_not_selectable",
            "n": common.height,
            "pearson": None,
            "spearman": None,
            "rmse": None,
            "mae": None,
            "direction_accuracy": None,
            "calibration_slope": None,
            "calibration_intercept": None,
        }
        for name in ("raw_team_epa", "offensive_rank", "record")
    )
    comparison_rows.append(
        {
            "model": "model_6_core_plus_scheme",
            "candidate_status": "excluded_scheme_gate_failed",
            "n": 0,
            "pearson": None,
            "spearman": None,
            "rmse": None,
            "mae": None,
            "direction_accuracy": None,
            "calibration_slope": None,
            "calibration_intercept": None,
        }
    )
    for row in comparison_rows:
        row.setdefault("shared_variance", None)
    return (
        future.sort("target_season", "model", "coach_id") if not future.is_empty() else future,
        pl.DataFrame(comparison_rows).sort("model"),
        (
            pl.DataFrame(weights).sort("target_season", "model", "feature")
            if weights
            else pl.DataFrame()
        ),
        pl.DataFrame(fold_rows).sort("target_season") if fold_rows else pl.DataFrame(),
    )


def _array_table_statistics(
    coaches: np.ndarray, seasons: np.ndarray, values: np.ndarray
) -> dict[str, float | None]:
    by_coach: dict[str, list[float]] = defaultdict(list)
    by_coach_season: dict[tuple[str, int], float] = {}
    for coach, season, value in zip(coaches, seasons, values, strict=True):
        coach_id = str(coach)
        by_coach[coach_id].append(float(value))
        by_coach_season[(coach_id, int(season))] = float(value)
    coach_means = np.asarray([np.mean(items) for items in by_coach.values()], dtype=float)
    previous: list[float] = []
    current: list[float] = []
    predicted: list[float] = []
    actual: list[float] = []
    histories: dict[str, list[float]] = defaultdict(list)
    order = np.lexsort((coaches.astype(str), seasons))
    for index in order:
        coach_id = str(coaches[index])
        season = int(seasons[index])
        value = float(values[index])
        prior_value = by_coach_season.get((coach_id, season - 1))
        if prior_value is not None:
            previous.append(prior_value)
            current.append(value)
        if histories[coach_id]:
            predicted.append(float(np.mean(histories[coach_id])))
            actual.append(value)
        histories[coach_id].append(value)
    return {
        "between_coach_variance": (float(np.var(coach_means)) if len(coach_means) > 1 else 0.0),
        "repeatability": _pearson(previous, current),
        "future_prediction": _pearson(actual, predicted),
    }


def _array_group_portability(
    coaches: np.ndarray,
    groups: np.ndarray,
    values: np.ndarray,
    weights: np.ndarray,
) -> float | None:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    group_totals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    groups_by_coach: dict[str, set[str]] = defaultdict(set)
    for coach, group, value, weight in zip(coaches, groups, values, weights, strict=True):
        coach_id = str(coach)
        group_id = str(group)
        totals[coach_id][0] += float(value * weight)
        totals[coach_id][1] += float(weight)
        group_totals[(coach_id, group_id)][0] += float(value * weight)
        group_totals[(coach_id, group_id)][1] += float(weight)
        groups_by_coach[coach_id].add(group_id)
    actual: list[float] = []
    predicted: list[float] = []
    for (coach_id, _), (weighted_total, weight) in group_totals.items():
        if len(groups_by_coach[coach_id]) < 2:
            continue
        remaining_weight = totals[coach_id][1] - weight
        if remaining_weight <= 0:
            continue
        actual.append(weighted_total / weight)
        predicted.append((totals[coach_id][0] - weighted_total) / remaining_weight)
    return _pearson(actual, predicted)


def _portability_placebo_row(
    table: pl.DataFrame,
    *,
    signal_name: str,
    role: str,
    signal: str,
    exposure: str,
    group: str,
) -> dict[str, Any]:
    coaches = table["coach_id"].to_numpy().astype(str)
    seasons = table["season"].to_numpy().astype(int)
    groups = table[group].to_numpy().astype(str)
    values = table[signal].to_numpy().astype(float)
    weights = table[exposure].to_numpy().astype(float)
    observed = _array_group_portability(coaches, groups, values, weights)
    rng = np.random.default_rng(_stable_seed(f"placebo:{signal_name}:{role}:{group}"))
    season_indices = [np.flatnonzero(seasons == season) for season in np.unique(seasons)]
    nulls: list[float] = []
    for _ in range(PERMUTATIONS):
        permuted = coaches.copy()
        for indices in season_indices:
            permuted[indices] = rng.permutation(permuted[indices])
        statistic = _array_group_portability(permuted, groups, values, weights)
        if statistic is not None and math.isfinite(statistic):
            nulls.append(statistic)
    return {
        "signal": signal_name,
        "role": role,
        "metric": f"different_{'qb' if group == 'player_id' else 'team'}_portability",
        "observed": observed,
        "permutations": PERMUTATIONS,
        "null_mean": float(np.mean(nulls)) if nulls else None,
        "null_standard_deviation": float(np.std(nulls)) if nulls else None,
        "observed_percentile": (
            float(np.mean(np.asarray(nulls) <= observed))
            if nulls and observed is not None
            else None
        ),
        "empirical_p_value": (
            float((1 + np.sum(np.asarray(nulls) >= observed)) / (len(nulls) + 1))
            if nulls and observed is not None
            else None
        ),
    }


def build_placebos(
    signal_tables: dict[str, pl.DataFrame],
    joined: pl.DataFrame | None = None,
    mapped_pcae: pl.DataFrame | None = None,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, table in sorted(signal_tables.items()):
        signal_name, role = label.split(":", 1)
        signal = "pcae" if signal_name == "pcae" else "q_development_signal"
        coaches = table["coach_id"].to_numpy().astype(str)
        seasons = table["season"].to_numpy().astype(int)
        values = table[signal].to_numpy().astype(float)
        observed = _array_table_statistics(coaches, seasons, values)
        rng = np.random.default_rng(_stable_seed(f"placebo:{label}"))
        season_indices = [np.flatnonzero(seasons == season) for season in np.unique(seasons)]
        nulls: dict[str, list[float]] = defaultdict(list)
        for _ in range(PERMUTATIONS):
            permuted = coaches.copy()
            for indices in season_indices:
                permuted[indices] = rng.permutation(permuted[indices])
            statistics = _array_table_statistics(permuted, seasons, values)
            for metric, value in statistics.items():
                if value is not None and math.isfinite(value):
                    nulls[metric].append(float(value))
        for metric, value in observed.items():
            samples = nulls[metric]
            rows.append(
                {
                    "signal": signal_name,
                    "role": role,
                    "metric": metric,
                    "observed": value,
                    "permutations": PERMUTATIONS,
                    "null_mean": float(np.mean(samples)) if samples else None,
                    "null_standard_deviation": float(np.std(samples)) if samples else None,
                    "observed_percentile": (
                        float(np.mean(np.asarray(samples) <= value))
                        if samples and value is not None
                        else None
                    ),
                    "empirical_p_value": (
                        float((1 + np.sum(np.asarray(samples) >= value)) / (len(samples) + 1))
                        if samples and value is not None
                        else None
                    ),
                }
            )
    if joined is not None:
        q = _q_observations(joined)
        for role in ROLES:
            role_rows = q.filter(pl.col("role") == role)
            for group in ("player_id", "team_id"):
                rows.append(
                    _portability_placebo_row(
                        role_rows,
                        signal_name="q",
                        role=role,
                        signal="q_development_signal",
                        exposure="exposure_dropbacks",
                        group=group,
                    )
                )
    if mapped_pcae is not None:
        p = mapped_pcae.with_columns(pl.lit("play_caller").alias("role"))
        rows.append(
            _portability_placebo_row(
                p,
                signal_name="pcae",
                role="play_caller",
                signal="pcae",
                exposure="attributed_play_count",
                group="team_id",
            )
        )
    return pl.DataFrame(rows).sort("signal", "role", "metric")


def build_environment_sensitivity(joined: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    q = _q_observations(joined)
    for role in ROLES:
        role_rows = q.filter(pl.col("role") == role)
        history_records: list[dict[str, Any]] = []
        for row in role_rows.sort("season", "coach_id", "player_id").to_dicts():
            prior = role_rows.filter(
                (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
            )
            if prior.is_empty():
                continue
            history_records.append(
                {
                    **row,
                    "coach_history": float(
                        np.average(
                            prior["q_development_signal"],
                            weights=prior["exposure_dropbacks"],
                        )
                    ),
                }
            )
        history_rows = pl.DataFrame(history_records) if history_records else pl.DataFrame()
        if history_rows.is_empty():
            continue
        predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for target in sorted(history_rows["season"].unique().to_list()):
            train_model = history_rows.filter(pl.col("season") < target)
            test_model = history_rows.filter(pl.col("season") == target)
            if train_model.height < 30 or test_model.is_empty():
                continue
            for name, features in (
                ("coach_history_only", ("coach_history",)),
                (
                    "coach_history_plus_preseason_environment",
                    ("coach_history", *ENVIRONMENT_FEATURES),
                ),
            ):
                predicted, _ = fit_training_only_ridge(
                    train_model,
                    test_model,
                    features=features,
                    outcome="q_development_signal",
                    weight="exposure_dropbacks",
                )
                predictions[name].extend(
                    zip(test_model["q_development_signal"].to_list(), predicted, strict=True)
                )
        for name, values in predictions.items():
            actual = np.asarray([value[0] for value in values], dtype=float)
            predicted = np.asarray([value[1] for value in values], dtype=float)
            rows.append(
                {
                    "role": role,
                    "specification": name,
                    "context_is_score_component": False,
                    "same_season_availability_included": False,
                    **_metrics(actual, predicted),
                }
            )
    return pl.DataFrame(rows).sort("role", "specification")


def _scheme_fingerprints(sources: ResearchSources) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for season in range(2010, 2026):
        path = sources.pbp_root / f"season={season}/play_by_play.parquet"
        plays = pl.read_parquet(
            path,
            columns=[
                "season",
                "season_type",
                "posteam",
                "play_type",
                "down",
                "shotgun",
                "no_huddle",
            ],
        ).filter(
            (pl.col("season_type") == "REG")
            & pl.col("play_type").is_in(["pass", "run"])
            & pl.col("posteam").is_not_null()
        )
        frames.append(
            plays.group_by("season", "posteam").agg(
                pl.col("shotgun").cast(pl.Float64).mean().alias("shotgun_rate"),
                pl.col("no_huddle").cast(pl.Float64).mean().alias("no_huddle_rate"),
                pl.when(pl.col("down").is_in([1, 2]))
                .then((pl.col("play_type") == "pass").cast(pl.Float64))
                .otherwise(None)
                .mean()
                .alias("early_down_pass_rate"),
                pl.len().alias("scheme_plays"),
            )
        )
    return (
        pl.concat(frames)
        .with_columns(
            pl.col("posteam").map_elements(_canonical_team, return_dtype=pl.String).alias("team_id")
        )
        .drop("posteam")
        .sort("season", "team_id")
    )


def _distance(left: np.ndarray, right: np.ndarray, method: str) -> float:
    if method == "standardized_euclidean":
        return float(np.linalg.norm(left - right))
    if method == "manhattan":
        return float(np.abs(left - right).sum())
    if method == "cosine":
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return 1.0 - float(np.dot(left, right) / denominator) if denominator else 0.0
    if method == "correlation":
        correlation = _pearson(left, right)
        return 1.0 - correlation if correlation is not None else 1.0
    raise ValueError(f"unsupported scheme distance: {method}")


def scheme_component_gate(
    available_features: Iterable[str], diagnostics: dict[str, bool]
) -> tuple[bool, str]:
    missing = sorted(set(SCHEME_FEATURES) - set(available_features))
    if missing:
        return False, "missing_required_features:" + "|".join(missing)
    failed = sorted(name for name, passed in diagnostics.items() if not passed)
    if failed:
        return False, "failed_evidence_gates:" + "|".join(failed)
    return True, "all_scheme_component_gates_passed"


def build_scheme_portability(
    assignments: pl.DataFrame,
    sources: ResearchSources,
    pae: pl.DataFrame,
    mapped_pcae: pl.DataFrame,
) -> tuple[pl.DataFrame, bool, str]:
    fingerprints = _scheme_fingerprints(sources)
    rows: list[dict[str, Any]] = []
    for feature in SCHEME_FEATURES:
        rows.append(
            {
                "record_type": "feature_coverage",
                "feature": feature,
                "source_status": (
                    "available" if feature in AVAILABLE_SCHEME_FEATURES else "unavailable"
                ),
                "method": None,
                "coach_id": None,
                "season": None,
                "from_team_id": None,
                "to_team_id": None,
                "actual_adoption": None,
                "placebo_percentile": None,
                "empirical_p_value": None,
                "persistence_adoption": None,
                "future_pae": None,
                "future_pcae": None,
            }
        )
    oc = assignments.filter(pl.col("role") == "offensive_coordinator").select(
        "coach_id",
        "coach_name",
        "season",
        pl.col("canonical_team_id").alias("team_id"),
    )
    coach_seasons = (
        oc.group_by("coach_id", "coach_name", "season")
        .agg(pl.col("team_id").unique().alias("teams"))
        .filter(pl.col("teams").list.len() == 1)
        .with_columns(pl.col("teams").list.first().alias("team_id"))
        .drop("teams")
    )
    prior = coach_seasons.select(
        "coach_id",
        (pl.col("season") + 1).alias("season"),
        pl.col("team_id").alias("from_team_id"),
    )
    moves = coach_seasons.join(prior, on=["coach_id", "season"], how="inner").filter(
        pl.col("team_id") != pl.col("from_team_id")
    )
    pae_team = pae.group_by("team_id", "season").agg(
        (
            (pl.col("performance_above_expectation") * pl.col("dropbacks")).sum()
            / pl.col("dropbacks").sum()
        ).alias("team_pae")
    )
    p_team = mapped_pcae.group_by("team_id", "season").agg(
        (
            (pl.col("pcae") * pl.col("attributed_play_count")).sum()
            / pl.col("attributed_play_count").sum()
        ).alias("team_pcae")
    )
    methods = ("standardized_euclidean", "manhattan", "cosine", "correlation")
    rng = np.random.default_rng(_stable_seed("scheme_placebos"))
    for move in moves.sort("season", "coach_id").to_dicts():
        season = int(move["season"])
        from_team = move["from_team_id"]
        to_team = move["team_id"]
        prior_pool = fingerprints.filter(pl.col("season") == season - 1)
        from_rows = prior_pool.filter(pl.col("team_id") == from_team)
        to_prior_rows = prior_pool.filter(pl.col("team_id") == to_team)
        to_current_rows = fingerprints.filter(
            (pl.col("season") == season) & (pl.col("team_id") == to_team)
        )
        if from_rows.height != 1 or to_prior_rows.height != 1 or to_current_rows.height != 1:
            continue
        training = fingerprints.filter(pl.col("season") < season)
        center = training.select(AVAILABLE_SCHEME_FEATURES).mean().row(0)
        scale = training.select(AVAILABLE_SCHEME_FEATURES).std(ddof=0).row(0)
        if any(value in (None, 0) for value in scale):
            continue
        center_array = np.asarray(center, dtype=float)
        scale_array = np.asarray(scale, dtype=float)

        def vector(
            frame: pl.DataFrame,
            center_values: np.ndarray = center_array,
            scale_values: np.ndarray = scale_array,
        ) -> np.ndarray:
            values = np.asarray(frame.select(AVAILABLE_SCHEME_FEATURES).row(0), dtype=float)
            return (values - center_values) / scale_values

        coach_prior = vector(from_rows)
        team_prior = vector(to_prior_rows)
        team_current = vector(to_current_rows)
        future_pae = pae_team.filter(
            (pl.col("team_id") == to_team) & (pl.col("season") == season + 1)
        )
        future_p = p_team.filter((pl.col("team_id") == to_team) & (pl.col("season") == season + 1))
        persists = (
            coach_seasons.filter(
                (pl.col("coach_id") == move["coach_id"])
                & (pl.col("team_id") == to_team)
                & (pl.col("season") == season + 1)
            ).height
            == 1
        )
        next_rows = fingerprints.filter(
            (pl.col("team_id") == to_team) & (pl.col("season") == season + 1)
        )
        candidates = prior_pool.filter(~pl.col("team_id").is_in([from_team, to_team]))
        candidate_vectors = [
            (np.asarray(item, dtype=float) - center_array) / scale_array
            for item in candidates.select(AVAILABLE_SCHEME_FEATURES).iter_rows()
        ]
        for method in methods:
            before = _distance(team_prior, coach_prior, method)
            after = _distance(team_current, coach_prior, method)
            adoption = before - after
            placebo: list[float] = []
            if candidate_vectors:
                indices = rng.integers(0, len(candidate_vectors), PERMUTATIONS)
                placebo = [
                    _distance(team_prior, candidate_vectors[index], method)
                    - _distance(team_current, candidate_vectors[index], method)
                    for index in indices
                ]
            persistence = None
            if persists and next_rows.height == 1:
                persistence = before - _distance(vector(next_rows), coach_prior, method)
            rows.append(
                {
                    "record_type": "move",
                    "feature": "|".join(AVAILABLE_SCHEME_FEATURES),
                    "source_status": "partial_3_of_10",
                    "method": method,
                    "coach_id": move["coach_id"],
                    "season": season,
                    "from_team_id": from_team,
                    "to_team_id": to_team,
                    "actual_adoption": adoption,
                    "placebo_percentile": (
                        float(np.mean(np.asarray(placebo) <= adoption)) if placebo else None
                    ),
                    "empirical_p_value": (
                        float((1 + np.sum(np.asarray(placebo) >= adoption)) / (len(placebo) + 1))
                        if placebo
                        else None
                    ),
                    "persistence_adoption": persistence,
                    "future_pae": future_pae["team_pae"].item() if future_pae.height == 1 else None,
                    "future_pcae": future_p["team_pcae"].item() if future_p.height == 1 else None,
                }
            )
    move_rows = [row for row in rows if row["record_type"] == "move"]
    for method in methods:
        method_rows = [row for row in move_rows if row["method"] == method]
        adoption = [float(row["actual_adoption"]) for row in method_rows]
        percentiles = [float(row["placebo_percentile"]) for row in method_rows]
        persistent = [
            float(row["persistence_adoption"])
            for row in method_rows
            if row["persistence_adoption"] is not None
        ]
        future_pae_values = [
            (float(row["actual_adoption"]), float(row["future_pae"]))
            for row in method_rows
            if row["future_pae"] is not None
        ]
        future_pcae_values = [
            (float(row["actual_adoption"]), float(row["future_pcae"]))
            for row in method_rows
            if row["future_pcae"] is not None
        ]
        rows.append(
            {
                "record_type": "method_summary",
                "feature": "|".join(AVAILABLE_SCHEME_FEATURES),
                "source_status": "partial_3_of_10_unadjusted_diagnostic",
                "method": method,
                "coach_id": None,
                "season": None,
                "from_team_id": None,
                "to_team_id": None,
                "actual_adoption": float(np.mean(adoption)) if adoption else None,
                "placebo_percentile": float(np.mean(percentiles)) if percentiles else None,
                "empirical_p_value": None,
                "persistence_adoption": float(np.mean(persistent)) if persistent else None,
                "future_pae": None,
                "future_pcae": None,
                "moves": len(method_rows),
                "share_toward_actual": (
                    float(np.mean(np.asarray(adoption) > 0)) if adoption else None
                ),
                "share_above_placebo_median": (
                    float(np.mean(np.asarray(percentiles) > 0.50)) if percentiles else None
                ),
                "share_above_placebo_75th": (
                    float(np.mean(np.asarray(percentiles) > 0.75)) if percentiles else None
                ),
                "future_pae_correlation": (
                    _pearson(
                        [item[0] for item in future_pae_values],
                        [item[1] for item in future_pae_values],
                    )
                    if future_pae_values
                    else None
                ),
                "future_pcae_correlation": (
                    _pearson(
                        [item[0] for item in future_pcae_values],
                        [item[1] for item in future_pcae_values],
                    )
                    if future_pcae_values
                    else None
                ),
            }
        )
    move_counts: dict[str, int] = defaultdict(int)
    unique_moves = {
        (
            str(row["coach_id"]),
            int(row["season"]),
            str(row["from_team_id"]),
            str(row["to_team_id"]),
        )
        for row in move_rows
    }
    for coach_id, _, _, _ in unique_moves:
        move_counts[coach_id] += 1
    rows.append(
        {
            "record_type": "multi_team_summary",
            "feature": "|".join(AVAILABLE_SCHEME_FEATURES),
            "source_status": "partial_3_of_10_unadjusted_diagnostic",
            "method": "all",
            "coach_id": None,
            "season": None,
            "from_team_id": None,
            "to_team_id": None,
            "actual_adoption": None,
            "placebo_percentile": None,
            "empirical_p_value": None,
            "persistence_adoption": None,
            "future_pae": None,
            "future_pcae": None,
            "moves": len(unique_moves),
            "coaches_with_multiple_moves": sum(value >= 2 for value in move_counts.values()),
        }
    )
    diagnostics = {
        "portability": False,
        "specificity": False,
        "persistence": False,
        "multi_team_repeatability": False,
        "future_association": False,
        "placebo_separation": False,
        "incremental_out_of_sample_value": False,
    }
    passed, reason = scheme_component_gate(AVAILABLE_SCHEME_FEATURES, diagnostics)
    rows.append(
        {
            "record_type": "component_gate",
            "feature": "|".join(AVAILABLE_SCHEME_FEATURES),
            "source_status": reason,
            "method": None,
            "coach_id": None,
            "season": None,
            "from_team_id": None,
            "to_team_id": None,
            "actual_adoption": None,
            "placebo_percentile": None,
            "empirical_p_value": None,
            "persistence_adoption": None,
            "future_pae": None,
            "future_pcae": None,
        }
    )
    optional_columns = (
        "moves",
        "share_toward_actual",
        "share_above_placebo_median",
        "share_above_placebo_75th",
        "future_pae_correlation",
        "future_pcae_correlation",
        "coaches_with_multiple_moves",
    )
    for row in rows:
        for column in optional_columns:
            row.setdefault(column, None)
    return (
        pl.DataFrame(rows, infer_schema_length=None).sort(
            "record_type", "season", "coach_id", "method"
        ),
        passed,
        reason,
    )


def build_sample_sizes(joined: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for role in ROLES:
        frame = joined.filter(pl.col("role") == role)
        attributed = (
            frame.filter(pl.col("pcae").is_not_null())
            .group_by("assignment_key")
            .agg(pl.col("attributed_play_count").first())
        )
        rows.append(
            {
                "role": role,
                "joined_rows": frame.height,
                "assignments": frame["assignment_key"].n_unique(),
                "coaches": frame["coach_id"].n_unique(),
                "qbs": frame["player_id"].n_unique(),
                "teams": frame["team_id"].n_unique(),
                "seasons": frame["season"].n_unique(),
                "exposure_dropbacks": float(frame["exposure_dropbacks"].sum()),
                "eligible_200_dropback_rows": frame.filter(
                    pl.col("eligibility_status") == "eligible"
                )
                .select("player_id", "team_id", "season")
                .n_unique(),
                "q_signal_rows": frame.filter(pl.col("q_development_signal").is_not_null()).height,
                "pcae_rows": frame.filter(pl.col("pcae").is_not_null())[
                    "assignment_key"
                ].n_unique(),
                "attributed_plays": (
                    int(attributed["attributed_play_count"].sum()) if attributed.height else 0
                ),
            }
        )
    return pl.DataFrame(rows).sort("role")


def build_confidence_and_suppression(
    q_estimates: pl.DataFrame, p_estimates: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    combined = pl.concat(
        [
            q_estimates.select(
                "signal",
                "role",
                "coach_id",
                "coach_name",
                "total_exposure",
                "observations",
                "seasons",
                "unique_qbs",
                "unique_teams",
                "posterior_estimate",
                "posterior_standard_error",
                "interval_low",
                "interval_high",
                "shrinkage_weight",
                "variance_component_at_boundary",
                "interval_method",
            ),
            p_estimates.select(
                "signal",
                "role",
                "coach_id",
                "coach_name",
                "total_exposure",
                "observations",
                "seasons",
                "unique_qbs",
                "unique_teams",
                "posterior_estimate",
                "posterior_standard_error",
                "interval_low",
                "interval_high",
                "shrinkage_weight",
                "variance_component_at_boundary",
                "interval_method",
            ),
        ],
        how="diagonal_relaxed",
    ).with_columns((pl.col("interval_high") - pl.col("interval_low")).alias("interval_width"))
    confidence = combined.with_columns(
        pl.when((pl.col("seasons") >= 4) & (pl.col("total_exposure") >= 1_500))
        .then(pl.lit("high"))
        .when((pl.col("seasons") >= 2) & (pl.col("total_exposure") >= 600))
        .then(pl.lit("medium"))
        .otherwise(pl.lit("low"))
        .alias("evidence_grade"),
        pl.lit("evidence_grade_plus_interval").alias("confidence_recommendation"),
        pl.lit(False).alias("confidence_multiplies_score"),
    )
    suppression = confidence.with_columns(
        pl.when(
            (pl.col("seasons") >= 3)
            & ((pl.col("unique_qbs") >= 2) | pl.col("unique_qbs").is_null())
            & (pl.col("total_exposure") >= 600)
        )
        .then(pl.lit("eligible_research"))
        .when((pl.col("seasons") >= 2) & (pl.col("total_exposure") >= 200))
        .then(pl.lit("provisional_research"))
        .otherwise(pl.lit("suppressed_research"))
        .alias("eligibility_recommendation"),
        pl.lit("research_only_not_publishable").alias("publication_status"),
    )
    return confidence.sort("signal", "role", "coach_id"), suppression.sort(
        "signal", "role", "coach_id"
    )


def build_presentation(suppression: pl.DataFrame) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for _, group in suppression.group_by("signal", "role"):
        group = group.sort("coach_id")
        values = group["posterior_estimate"].to_numpy()
        percentile = rankdata(values, method="average") / len(values) * 100
        scale = float(np.std(values))
        # At a zero between-coach variance boundary every posterior is the same
        # mathematical value. BLAS/reduction order can still leave sub-epsilon
        # differences in the group mean and standard deviation; treating those as
        # signal makes the display score both misleading and nondeterministic.
        if np.ptp(values) <= 1e-12:
            bounded = np.full(len(values), 50.0)
        else:
            bounded = 50 + 50 * np.tanh((values - float(np.mean(values))) / (2 * scale))
        reliability_percentile = 50 + (percentile - 50) * group["shrinkage_weight"].to_numpy()
        frames.append(
            group.select("signal", "role", "coach_id", "eligibility_recommendation").with_columns(
                pl.Series("percentile_0_100", percentile),
                pl.Series("reliability_adjusted_percentile_0_100", reliability_percentile),
                pl.Series("bounded_standardized_0_100", bounded),
                pl.lit("presentation_only_research_not_publishable").alias("status"),
            )
        )
    return pl.concat(frames).sort("signal", "role", "coach_id")


def build_role_readiness(
    reliability: pl.DataFrame,
    qb_holdouts: pl.DataFrame,
    team_holdouts: pl.DataFrame,
    placebos: pl.DataFrame,
    *,
    scheme_passed: bool,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for role in ROLES:
        q_reliability = reliability.filter(
            (pl.col("role") == role) & (pl.col("signal") == "q_development")
        )
        q_qb = qb_holdouts.filter(pl.col("role") == role)
        q_team = team_holdouts.filter(
            (pl.col("role") == role) & (pl.col("signal") == "q_development")
        )
        q_placebo = placebos.filter(
            (pl.col("role") == role)
            & (pl.col("signal") == "q")
            & (pl.col("metric") == "future_prediction")
        )
        reliability_value = q_reliability["one_season_reliability"].item()
        evidence_pass = (
            reliability_value is not None
            and reliability_value > 0.10
            and q_qb.height == 1
            and (q_qb["pearson"].item() or -1) > 0
            and q_team.height == 1
            and (q_team["pearson"].item() or -1) > 0
            and q_placebo.height == 1
            and (q_placebo["empirical_p_value"].item() or 1) <= 0.05
        )
        if role == "play_caller":
            p = reliability.filter((pl.col("role") == role) & (pl.col("signal") == "pcae"))
            evidence_pass = (
                evidence_pass and p.height == 1 and (p["one_season_reliability"].item() or 0) > 0.10
            )
        readiness = "READY FOR SCORE" if evidence_pass else "EXPLORATORY ONLY"
        if role == "play_caller" and not scheme_passed:
            readiness = "EXPLORATORY ONLY"
        rows.append(
            {
                "role": role,
                "readiness": readiness,
                "q_reliability": reliability_value,
                "different_qb_pearson": q_qb["pearson"].item() if q_qb.height else None,
                "different_team_pearson": q_team["pearson"].item() if q_team.height else None,
                "future_placebo_p": (
                    q_placebo["empirical_p_value"].item() if q_placebo.height else None
                ),
                "scheme_component_passed": scheme_passed,
                "production_score_authorized": False,
            }
        )
    return pl.DataFrame(rows).sort("role")


def _input_hashes(project_root: Path, sources: ResearchSources) -> dict[str, str]:
    paths = [
        sources.pae_path,
        sources.qb_games_path,
        sources.environment_path,
        sources.team_statistics_path,
        sources.pcae_path,
        sources.pcae_manifest_path,
        *sorted((project_root / "data/manual").glob("*.csv")),
        *[
            sources.pbp_root / f"season={season}/play_by_play.parquet"
            for season in range(2010, 2026)
        ],
    ]
    return {str(path.relative_to(project_root)): sha256_file(path) for path in paths}


def _identity(project_root: Path, sources: ResearchSources) -> dict[str, Any]:
    code_paths = [Path(__file__), project_root / "research/coach_effect/config.py"]
    return {
        "research_specification": RESEARCH_SPECIFICATION,
        "production_load_id": PRODUCTION_LOAD_ID,
        "historical_version": sources.historical_version,
        "enhancement_version": sources.enhancement_version,
        "pae_data_version": EXPECTED_PAE_DATA_VERSION,
        "pae_model_version": EXPECTED_PAE_MODEL_VERSION,
        "pcae_data_version": EXPECTED_PCAE_DATA_VERSION,
        "pcae_model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "pcae_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "pae_formula": PAE_FORMULA,
        "q_features": Q_FEATURES,
        "environment_features": ENVIRONMENT_FEATURES,
        "core_score_components": CORE_SCORE_COMPONENTS,
        "scheme_features": SCHEME_FEATURES,
        "available_scheme_features": AVAILABLE_SCHEME_FEATURES,
        "random_seed": RANDOM_SEED,
        "permutations": PERMUTATIONS,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "movement_alpha": MOVEMENT_ALPHA,
        "joint_alpha": JOINT_ALPHA,
        "minimum_movement_training_rows": MIN_MOVEMENT_TRAINING_ROWS,
        "minimum_interval_dropbacks": MIN_INTERVAL_DROPBACKS,
        "q_shrinkage_k_values": Q_SHRINKAGE_K_VALUES,
        "p_shrinkage_k_values": P_SHRINKAGE_K_VALUES,
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "input_hashes": _input_hashes(project_root, sources),
        "code_hashes": {
            str(path.relative_to(project_root)): sha256_file(path) for path in code_paths
        },
    }


def _add_version(frame: pl.DataFrame, data_version: str) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    floating = [name for name, dtype in frame.schema.items() if dtype in (pl.Float32, pl.Float64)]
    deterministic = frame.with_columns(pl.col(floating).round(10)) if floating else frame
    ordering = [name for name in deterministic.columns if name not in floating]
    if ordering:
        deterministic = deterministic.sort(ordering, nulls_last=True)
    return deterministic.with_columns(
        pl.lit(data_version).alias("research_data_version"),
        pl.lit(True).alias("research_only"),
        pl.lit(False).alias("production_ranking"),
    )


def run_checkpoint_twelve(project_root: Path, output_root: Path | None = None) -> dict[str, Any]:
    """Run the complete research publication without touching any production output."""

    project_root = project_root.resolve()
    sources = _sources(project_root)
    identity = _identity(project_root, sources)
    data_version = (
        "c12-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    joined, movement_folds, mapped_pcae = build_joined_research_table(project_root, sources)
    sample_sizes = build_sample_sizes(joined)
    q_estimates, p_estimates, shrinkage = build_estimates(joined, mapped_pcae)
    reliability, signal_tables = build_reliability(joined, mapped_pcae)
    qb_holdouts, team_holdouts = build_portability(joined, mapped_pcae)
    placebos = build_placebos(signal_tables, joined, mapped_pcae)
    environment = build_environment_sensitivity(joined)
    assignments = _assignment_frame(project_root)
    pae = _load_pae(sources.pae_path)
    scheme, scheme_passed, scheme_reason = build_scheme_portability(
        assignments, sources, pae, mapped_pcae
    )
    team_statistics = pl.read_parquet(sources.team_statistics_path)
    future, comparisons, weights, joint_folds = build_future_models(
        joined, mapped_pcae, team_statistics
    )
    folds = (
        pl.concat([movement_folds, joint_folds], how="diagonal_relaxed").sort(
            "fold_family", "target_season"
        )
        if not joint_folds.is_empty()
        else movement_folds
    )
    confidence, suppression = build_confidence_and_suppression(q_estimates, p_estimates)
    presentation = build_presentation(suppression)
    readiness = build_role_readiness(
        reliability, qb_holdouts, team_holdouts, placebos, scheme_passed=scheme_passed
    )
    outputs = {
        "joined_research_table.csv": joined,
        "fold_definitions.csv": folds,
        "sample_sizes.csv": sample_sizes,
        "q_estimates.csv": q_estimates,
        "pcae_estimates.csv": p_estimates,
        "reliability.csv": reliability,
        "future_validation.csv": future,
        "qb_holdouts.csv": qb_holdouts,
        "team_holdouts.csv": team_holdouts,
        "placebos.csv": placebos,
        "environment_sensitivity.csv": environment,
        "scheme_portability.csv": scheme,
        "model_comparisons.csv": comparisons,
        "weights.csv": weights,
        "shrinkage.csv": shrinkage,
        "confidence.csv": confidence,
        "suppression.csv": suppression,
        "presentation_0_100.csv": presentation,
        "role_readiness.csv": readiness,
    }
    outputs = {name: _add_version(frame, data_version) for name, frame in outputs.items()}
    root = output_root or project_root / "research/coach_effect/outputs/checkpoint_12"
    destination = root / data_version
    temporary = root / f".{data_version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for name in OUTPUT_NAMES:
        _write_csv(outputs[name], temporary / name)
    checksums = {name: sha256_file(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "research_data_version": data_version,
        "research_only": True,
        "production_coach_effect": False,
        "production_ranking": False,
        "production_load_id": PRODUCTION_LOAD_ID,
        "identity": identity,
        "scheme_component_passed": scheme_passed,
        "scheme_gate_reason": scheme_reason,
        "row_counts": {name.removesuffix(".csv"): outputs[name].height for name in OUTPUT_NAMES},
        "output_checksums": checksums,
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if destination.exists():
        expected = {**checksums, "MANIFEST.json": sha256_file(temporary / "MANIFEST.json")}
        for name, digest in expected.items():
            if sha256_file(destination / name) != digest:
                raise ValueError(f"existing checkpoint-twelve output differs: {name}")
        shutil.rmtree(temporary)
    else:
        temporary.replace(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "LATEST").write_text(data_version + "\n", encoding="utf-8")
    return {
        "research_data_version": data_version,
        "output_path": destination,
        "row_counts": manifest["row_counts"],
        "scheme_component_passed": scheme_passed,
        "scheme_gate_reason": scheme_reason,
    }

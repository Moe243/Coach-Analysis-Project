"""Checkpoint 16: team-independent, historically evaluated QB prediction intervals.

Consumes frozen Player State. Never calls a state builder or a target-team resolver.
Retrospective outcomes and subgroup labels are deliberately separate from predictors.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import platform
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import polars as pl
import scipy
import sklearn
from sklearn.linear_model import Ridge

from . import player_scheme_fit, predictive_foundation
from .player_scheme_fit import FoldPreprocessor, _metrics
from .predictive_foundation import FeatureDefinition, validate_feature_records

C14_VERSION = "c14-43283062e788e686"
C13_VERSION = "c13-5e3d7a34ea4d1af5"
ENH_VERSION = "enh-04254065cafd92ba"
KEY = ["player_id", "target_season"]
# Fixed before inspecting C16 performance. No empirically promoted situation splits,
# conditional PAE/trend, descriptive volatility, or scheme features enter M1.
STATE_FEATURES = (
    "preseason_ability_estimate_epa_per_db",
    "recent_epa_per_dropback",
    "recent_success_rate",
    "recent_cpoe",
    "recent_sack_rate",
    "recent_scramble_rate",
    "recent_average_air_yards",
    "recent_target_depth_short_rate",
    "recent_target_depth_intermediate_rate",
    "recent_target_depth_deep_rate",
    "recent_shotgun_rate",
)
HEADER_FEATURES = (
    "age_at_season_start",
    "seasons_since_rookie_year",
    "seasons_with_qb_activity",
    "prior_starts_log1p",
    "prior_dropbacks_log1p",
    "career_starts_log1p",
    "career_dropbacks_log1p",
    "preseason_ability_standard_error",
)
MODEL_FEATURES = STATE_FEATURES + HEADER_FEATURES
BASELINE_RECORDS = ("recent_observed_pae",)
MODELS = ("B0", "B1", "B2", "M1")
OUTCOMES = ("epa", "pae")


@dataclass(frozen=True)
class ProjectionConfig:
    specification: str = "checkpoint-16-player-state-v1"
    minimum_dropbacks: int = 50
    minimum_train_rows: int = 120
    minimum_train_seasons: int = 3
    minimum_test_rows: int = 20
    minimum_inner_train: int = 100
    minimum_inner_seasons: int = 2
    minimum_feature_values: int = 10
    ridge_alphas: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0, 1000.0)
    default_alpha: float = 100.0
    development_end: int = 2018
    calibration_window: int = 5
    minimum_calibration: int = 100
    interval_levels: tuple[float, ...] = (0.50, 0.80, 0.95)
    minimum_selection_folds: int = 3
    selection_relative_gain: float = 0.02
    selection_minimum_win_rate: float = 0.60
    selection_maximum_rmse_ratio: float = 1.01
    acceptance_minimum_n: int = 200
    acceptance_minimum_folds: int = 5
    acceptance_interval_tolerance: float = 0.06
    acceptance_minimum_correlation: float = 0.10
    acceptance_slope_bounds: tuple[float, float] = (0.50, 1.50)
    acceptance_maximum_intercept: float = 0.05
    acceptance_recent_start: int = 2022
    bootstrap_draws: int = 1000
    seed: int = 16026


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _assert_grain(frame: pl.DataFrame, keys: list[str]) -> None:
    if frame.select(pl.any_horizontal(pl.col(keys).is_null()).any()).item():
        raise ValueError(f"null identifiers: {keys}")
    if frame.unique(keys).height != frame.height:
        raise ValueError(f"duplicate grain: {keys}")


def validate_model_features(features: tuple[str, ...]) -> None:
    if not features or set(features) - set(MODEL_FEATURES):
        raise ValueError("unregistered or forbidden projection predictor")


def build_predictors(
    states: pl.DataFrame, records: pl.DataFrame, registry: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Only this function builds model inputs; it never receives an outcome or team."""
    _assert_grain(states, KEY)
    if states.filter(
        pl.col("as_of_date").is_null()
        | (pl.col("data_version") != C14_VERSION)
        | (pl.col("feature_store_version") != C13_VERSION)
    ).height:
        raise ValueError("invalid frozen Player State identity/date")
    if states.filter(
        (pl.col("maximum_source_season") >= pl.col("target_season"))
        | (pl.col("as_of_date") != pl.col("target_season").cast(pl.String) + "-08-31")
    ).height:
        raise ValueError("Player State source/as-of leakage")
    names = STATE_FEATURES + BASELINE_RECORDS
    lookup = {row["name"]: row for row in registry.to_dicts()}
    if set(names) - set(lookup):
        raise ValueError("unregistered required state feature")
    for name in STATE_FEATURES:
        if lookup[name]["status"] != "PREDICTIVE_CORE":
            raise ValueError(f"non-core feature cannot enter primary model: {name}")
    selected = records.filter(pl.col("feature_name").is_in(names))
    definitions = tuple(FeatureDefinition(**row) for row in registry.to_dicts())
    validate_feature_records(selected, definitions)
    _assert_grain(selected, KEY + ["feature_name"])
    if selected.join(states.select(KEY), on=KEY, how="anti").height:
        raise ValueError("feature record outside frozen Player State universe")
    if selected.filter(
        (pl.col("source_season") >= pl.col("target_season"))
        | (pl.col("observation_end_season") >= pl.col("target_season"))
        | (pl.col("source_available_date") > pl.col("as_of_date"))
        | (pl.col("as_of_date") != pl.col("target_season").cast(pl.String) + "-08-31")
        | (~pl.col("qualified") & pl.col("feature_value").is_not_null())
        | (pl.col("feature_value").is_not_null() & ~pl.col("feature_value").is_finite())
        | pl.col("source_season").is_null()
        | pl.col("source_available_date").is_null()
    ).height:
        raise ValueError("invalid state timing/qualification/value")
    keep = KEY + [
        "as_of_date",
        "maximum_source_season",
        "state_version",
        "data_version",
        "feature_store_version",
        "is_rookie",
        "age_at_season_start",
        "seasons_since_rookie_year",
        "seasons_with_qb_activity",
        "prior_starts",
        "prior_dropbacks",
        "career_starts",
        "career_dropbacks",
        "preseason_ability_standard_error",
        "preseason_ability_reliability",
    ]
    result = states.select(keep).rename({"data_version": "state_data_version"})
    wide = selected.select(*KEY, "feature_name", "feature_value").pivot(
        on="feature_name", index=KEY, values="feature_value"
    )
    result = result.join(wide, on=KEY, how="left", validate="1:1")
    for name in names:
        if name not in result.columns:
            result = result.with_columns(pl.lit(None, dtype=pl.Float64).alias(name))
    raw = selected.filter(pl.col("feature_name") == "recent_epa_per_dropback").select(
        *KEY, pl.when(pl.col("qualified")).then(pl.col("raw_value")).alias("b1_prior_epa")
    )
    result = result.join(raw, on=KEY, how="left", validate="1:1").with_columns(
        *[
            pl.col(name).cast(pl.Float64).log1p().alias(f"{name}_log1p")
            for name in ("prior_starts", "prior_dropbacks", "career_starts", "career_dropbacks")
        ]
    )
    prior_pae = selected.filter(pl.col("feature_name") == "recent_observed_pae").select(
        *KEY, pl.when(pl.col("qualified")).then(pl.col("raw_value")).alias("b1_prior_pae")
    )
    result = result.join(prior_pae, on=KEY, how="left", validate="1:1")
    return result.sort("target_season", "player_id"), selected.sort(
        "target_season", "player_id", "feature_name"
    )


def aggregate_outcomes(performance: pl.DataFrame, pae: pl.DataFrame) -> pl.DataFrame:
    """Aggregate additive EPA across all stints BEFORE applying evaluation volume."""
    grain = ["player_id", "team_id", "season"]
    perf = performance.filter(
        (pl.col("scope") == "analysis") & pl.col("season").is_between(2010, 2025)
    )
    _assert_grain(perf, grain)
    _assert_grain(pae, grain)
    if pae.filter(
        pl.any_horizontal(
            [
                pl.col(name).is_null() | ~pl.col(name).is_finite()
                for name in (
                    "actual_epa_per_dropback",
                    "expected_epa_per_dropback",
                    "performance_above_expectation",
                )
            ]
        )
        | pl.col("is_out_of_sample").is_null()
        | pl.col("training_end_season").is_null()
        | (
            pl.col("feature_source_max_season").is_null()
            & ~pl.col("no_prior_qb_performance").fill_null(False)
        )
    ).height:
        raise ValueError("invalid published baseline values/lineage")
    if perf.filter(
        (pl.col("dropbacks") <= 0)
        | ~pl.col("total_qb_epa").is_finite()
        | pl.col("total_qb_epa").is_null()
    ).height:
        raise ValueError("invalid observed EPA/dropbacks")
    if pae.filter(
        ~pl.col("is_out_of_sample")
        | (pl.col("training_end_season") >= pl.col("season"))
        | (pl.col("feature_source_max_season") >= pl.col("season"))
        | (pl.col("model_name") != "career_performance")
        | (
            (
                pl.col("actual_epa_per_dropback")
                - pl.col("expected_epa_per_dropback")
                - pl.col("performance_above_expectation")
            ).abs()
            > 1e-10
        )
    ).height:
        raise ValueError("published baseline timing/specification/PAE arithmetic invalid")
    joined = perf.join(
        pae.select(
            *grain,
            pl.col("dropbacks").alias("pae_dropbacks"),
            pl.col("actual_epa_per_dropback").alias("pae_actual"),
            "expected_epa_per_dropback",
            "model_version",
        ),
        on=grain,
        how="left",
        validate="1:1",
    )
    if joined.filter(
        pl.col("pae_dropbacks").is_not_null()
        & (
            (pl.col("dropbacks") != pl.col("pae_dropbacks"))
            | ((pl.col("total_qb_epa") / pl.col("dropbacks") - pl.col("pae_actual")).abs() > 1e-10)
        )
    ).height:
        raise ValueError("PAE/full-stint outcome reconciliation failed")
    if (
        joined.group_by("player_id", "season")
        .agg(pl.col("expected_epa_per_dropback").drop_nulls().n_unique().alias("n"))
        .filter(pl.col("n") > 1)
        .height
    ):
        raise ValueError("contradictory multi-team preseason expectations")
    result = (
        joined.sort(grain)
        .group_by("player_id", "season")
        .agg(
            pl.col("dropbacks").sum().alias("outcome_dropbacks"),
            pl.col("total_qb_epa").sum().alias("total_qb_epa"),
            pl.len().alias("outcome_team_count"),
            pl.col("team_id").sort().str.join("|").alias("retrospective_team_ids"),
            pl.when(pl.col("expected_epa_per_dropback").null_count() == 0)
            .then(pl.col("expected_epa_per_dropback").first())
            .alias("b2_expected_epa"),
        )
        .with_columns((pl.col("total_qb_epa") / pl.col("outcome_dropbacks")).alias("outcome_epa"))
    )
    result = result.with_columns(
        (pl.col("outcome_epa") - pl.col("b2_expected_epa")).alias("outcome_pae")
    )
    # Outcome-only change labels, never model inputs or eligibility conditions.
    primary = (
        performance.sort(
            "player_id", "season", "dropbacks", "team_id", descending=[False, False, True, False]
        )
        .unique(["player_id", "season"], keep="first")
        .select("player_id", "season", "team_id")
    )
    prior = primary.with_columns((pl.col("season") + 1).alias("season")).rename(
        {"team_id": "prior_team"}
    )
    change = primary.join(prior, on=["player_id", "season"], how="left", validate="1:1").select(
        "player_id",
        "season",
        (pl.col("team_id") != pl.col("prior_team")).alias("diagnostic_team_change"),
    )
    return (
        result.join(change, on=["player_id", "season"], validate="1:1")
        .rename({"season": "target_season"})
        .sort("target_season", "player_id")
    )


def build_cohort(
    predictors: pl.DataFrame, outcomes: pl.DataFrame, config: ProjectionConfig
) -> pl.DataFrame:
    _assert_grain(outcomes, KEY)
    cohort = outcomes.join(
        predictors.with_columns(pl.lit(True).alias("state_matched")),
        on=KEY,
        how="left",
        validate="1:1",
    )
    return (
        cohort.with_columns(
            pl.col("state_matched").fill_null(False),
            pl.when(pl.col("state_matched").is_null())
            .then(pl.lit("NOT_IN_ASOF_STATE_UNIVERSE"))
            .when(pl.col("outcome_dropbacks") < config.minimum_dropbacks)
            .then(pl.lit("BELOW_OUTCOME_DROPBACK_MINIMUM"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("exclusion_reason"),
        )
        .with_columns(pl.col("exclusion_reason").is_null().alias("eligible"))
        .sort("target_season", "player_id")
    )


def fit_ridge(
    training: pl.DataFrame,
    target: pl.DataFrame,
    outcome: str,
    year: int,
    alpha: float,
    config: ProjectionConfig,
    features: tuple[str, ...] = MODEL_FEATURES,
):
    validate_model_features(features)
    if training.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future row in model training")
    prep = FoldPreprocessor.fit(
        training, features, target_season=year, minimum_values=config.minimum_feature_values
    )
    x, names = prep.transform(training)
    xt, _ = prep.transform(target)
    model = Ridge(alpha=alpha, fit_intercept=True, solver="svd")
    model.fit(x, training[f"outcome_{outcome}"].to_numpy())
    return model.predict(xt), model, prep, names


def tune_alpha(training: pl.DataFrame, outcome: str, year: int, config: ProjectionConfig):
    if training.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future row in hyperparameter history")
    scores = {alpha: [] for alpha in config.ridge_alphas}
    validation_years = []
    for inner in sorted(training["target_season"].unique().to_list()):
        tr = training.filter(pl.col("target_season") < inner)
        te = training.filter(pl.col("target_season") == inner)
        if (
            tr.height < config.minimum_inner_train
            or tr["target_season"].n_unique() < config.minimum_inner_seasons
            or te.height < config.minimum_test_rows
        ):
            continue
        validation_years.append(inner)
        for alpha in config.ridge_alphas:
            prediction, _, _, _ = fit_ridge(tr, te, outcome, inner, alpha, config)
            scores[alpha].append(
                float(np.mean(np.abs(te[f"outcome_{outcome}"].to_numpy() - prediction)))
            )
    if not validation_years:
        return config.default_alpha, [], "PREDECLARED_DEFAULT"
    selected = min(config.ridge_alphas, key=lambda a: (np.mean(scores[a]), -a))
    return selected, validation_years, "INNER_ROLLING_MAE"


def residual_intervals(
    history: pl.DataFrame, year: int, outcome: str, model: str, config: ProjectionConfig
) -> dict:
    if history.height and history.filter(pl.col("target_season") >= year).height:
        raise ValueError("target/future residual in calibration history")
    selected = (
        history.filter(
            (pl.col("outcome") == outcome)
            & (pl.col("model") == model)
            & (pl.col("target_season") >= year - config.calibration_window)
        )
        if history.height
        else history
    )
    errors = (
        np.sort(np.abs(selected["actual"].to_numpy() - selected["prediction"].to_numpy()))
        if selected.height
        else np.array([])
    )
    n = len(errors)
    result = {
        "calibration_n": n,
        "calibration_start_season": int(selected["target_season"].min()) if n else None,
        "calibration_end_season": int(selected["target_season"].max()) if n else None,
        "interval_method": "ROLLING_OOS_ABSOLUTE_RESIDUAL_NO_EXCHANGEABILITY_GUARANTEE",
    }
    for level in config.interval_levels:
        k = math.ceil((n + 1) * level)
        result[f"radius_{round(level * 100)}"] = (
            float(errors[k - 1]) if n >= config.minimum_calibration and 1 <= k <= n else None
        )
    return result


def rolling_predictions(cohort: pl.DataFrame, config: ProjectionConfig):
    cohort = cohort.sort("target_season", "player_id")
    _assert_grain(cohort, KEY)
    predictions, folds, parameters = [], [], []
    for year in sorted(cohort["target_season"].unique().to_list()):
        # Freeze all current-year outputs before adding any of their residuals.
        history = (
            pl.DataFrame(predictions, infer_schema_length=None) if predictions else pl.DataFrame()
        )
        for outcome in OUTCOMES:
            available = cohort.filter(
                pl.col("eligible") & pl.col(f"outcome_{outcome}").is_not_null()
            )
            train = available.filter(pl.col("target_season") < year)
            test = available.filter(pl.col("target_season") == year)
            if (
                train.height < config.minimum_train_rows
                or train["target_season"].n_unique() < config.minimum_train_seasons
                or test.height < config.minimum_test_rows
            ):
                continue
            alpha, inner, tuning = tune_alpha(train, outcome, year, config)
            ridge, model, prep, names = fit_ridge(train, test, outcome, year, alpha, config)
            league = float(
                np.average(
                    train[f"outcome_{outcome}"].to_numpy(),
                    weights=train["outcome_dropbacks"].to_numpy(),
                )
            )
            raw_b1 = test["b1_prior_epa" if outcome == "epa" else "b1_prior_pae"].to_numpy()
            b1 = np.where(np.isfinite(raw_b1), raw_b1, league)
            b2 = test["b2_expected_epa"].to_numpy() if outcome == "epa" else np.zeros(test.height)
            for name, values in {
                "B0": np.full(test.height, league),
                "B1": b1,
                "B2": b2,
                "M1": ridge,
            }.items():
                interval = residual_intervals(history, year, outcome, name, config)
                folds.append(
                    {
                        "target_season": year,
                        "outcome": outcome,
                        "model": name,
                        "train_rows": train.height,
                        "target_rows": test.height,
                        "train_start_season": int(train["target_season"].min()),
                        "train_end_season": int(train["target_season"].max()),
                        "alpha": alpha if name == "M1" else None,
                        "tuning": tuning if name == "M1" else "NOT_APPLICABLE",
                        "inner_validation_seasons": "|".join(map(str, inner))
                        if name == "M1"
                        else "",
                        "tuning_latest_validation_season": max(inner)
                        if inner and name == "M1"
                        else None,
                        **interval,
                    }
                )
                for row, value in zip(test.to_dicts(), values, strict=True):
                    if not math.isfinite(float(value)):
                        continue  # explicit baseline missingness; never substitute target data
                    result = {
                        "player_id": row["player_id"],
                        "target_season": year,
                        "outcome": outcome,
                        "model": name,
                        "prediction": float(value),
                        "actual": row[f"outcome_{outcome}"],
                        "as_of_date": row["as_of_date"],
                        "state_data_version": row["state_data_version"],
                        "state_version": row["state_version"],
                        "train_end_season": int(train["target_season"].max()),
                        **interval,
                    }
                    result["b1_used_league_fallback"] = (
                        name == "B1"
                        and row["b1_prior_epa" if outcome == "epa" else "b1_prior_pae"] is None
                    )
                    for level in config.interval_levels:
                        pct = round(level * 100)
                        radius = interval[f"radius_{pct}"]
                        result[f"lower_{pct}"] = (
                            float(value) - radius if radius is not None else None
                        )
                        result[f"upper_{pct}"] = (
                            float(value) + radius if radius is not None else None
                        )
                    predictions.append(result)
            parameters.append(
                {
                    "target_season": year,
                    "outcome": outcome,
                    "alpha": alpha,
                    "intercept": float(model.intercept_),
                    "coefficients": dict(zip(names, model.coef_.tolist(), strict=True)),
                    "preprocessor": asdict(prep),
                    "inner_validation_seasons": inner,
                }
            )
    if not predictions:
        raise ValueError("no rolling projection folds satisfy the declared sample rules")
    return (
        pl.DataFrame(predictions, infer_schema_length=None).sort(
            "target_season", "outcome", "model", "player_id"
        ),
        pl.DataFrame(folds, infer_schema_length=None).sort("target_season", "outcome", "model"),
        parameters,
    )


def model_metrics(predictions: pl.DataFrame, config: ProjectionConfig) -> pl.DataFrame:
    rows = []
    periods = {
        "ALL_ROLLING": pl.lit(True),
        "DEVELOPMENT": pl.col("target_season") <= config.development_end,
        "LOCKED_VALIDATION": pl.col("target_season") > config.development_end,
        "RECENT": pl.col("target_season") >= config.acceptance_recent_start,
    }
    for period, condition in periods.items():
        for (outcome, model), group in predictions.filter(condition).group_by(
            "outcome", "model", maintain_order=True
        ):
            rows.append(
                {
                    "period": period,
                    "outcome": outcome,
                    "model": model,
                    **_metrics(group["actual"].to_numpy(), group["prediction"].to_numpy(), 0.0),
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None).sort("period", "outcome", "model")


def interval_coverage(predictions: pl.DataFrame, config: ProjectionConfig) -> pl.DataFrame:
    rows = []
    for period, cond in {
        "ALL_ROLLING": pl.lit(True),
        "LOCKED_VALIDATION": pl.col("target_season") > config.development_end,
    }.items():
        for (outcome, model), group in predictions.filter(cond).group_by(
            "outcome", "model", maintain_order=True
        ):
            for level in config.interval_levels:
                pct = round(level * 100)
                eligible = group.filter(pl.col(f"lower_{pct}").is_not_null())
                rows.append(
                    {
                        "period": period,
                        "outcome": outcome,
                        "model": model,
                        "level": level,
                        "n": eligible.height,
                        "unavailable_intervals": group.height - eligible.height,
                        "coverage": float(
                            eligible.select(
                                (
                                    (pl.col("actual") >= pl.col(f"lower_{pct}"))
                                    & (pl.col("actual") <= pl.col(f"upper_{pct}"))
                                ).mean()
                            ).item()
                        )
                        if eligible.height
                        else None,
                        "mean_width": float(
                            eligible.select(
                                (pl.col(f"upper_{pct}") - pl.col(f"lower_{pct}")).mean()
                            ).item()
                        )
                        if eligible.height
                        else None,
                    }
                )
    return pl.DataFrame(rows, infer_schema_length=None).sort("period", "outcome", "model", "level")


def paired_comparison(predictions: pl.DataFrame, config: ProjectionConfig) -> pl.DataFrame:
    rows = []
    for outcome in OUTCOMES:
        base = predictions.filter(
            (pl.col("outcome") == outcome) & (pl.col("model") == "B2")
        ).select(*KEY, "actual", pl.col("prediction").alias("base"))
        for model in MODELS:
            paired = predictions.filter(
                (pl.col("outcome") == outcome) & (pl.col("model") == model)
            ).join(base, on=KEY, validate="1:1", suffix="_base")
            for (year,), g in paired.group_by("target_season", maintain_order=True):
                a, b, p = g["actual"].to_numpy(), g["base"].to_numpy(), g["prediction"].to_numpy()
                rows.append(
                    {
                        "target_season": year,
                        "outcome": outcome,
                        "model": model,
                        "n": g.height,
                        "mae": float(np.mean(abs(a - p))),
                        "b2_mae": float(np.mean(abs(a - b))),
                        "mae_improvement": float(np.mean(abs(a - b) - abs(a - p))),
                        "rmse": float(np.sqrt(np.mean((a - p) ** 2))),
                        "b2_rmse": float(np.sqrt(np.mean((a - b) ** 2))),
                    }
                )
    return pl.DataFrame(rows).sort("target_season", "outcome", "model")


def select_models(
    predictions: pl.DataFrame, comparison: pl.DataFrame, config: ProjectionConfig
) -> dict:
    """Freeze family choice using development outcomes only, never validation outcomes."""
    selected = {}
    for outcome in OUTCOMES:
        candidates = []
        for model in ("B0", "B1", "M1"):
            g = comparison.filter(
                (pl.col("outcome") == outcome)
                & (pl.col("model") == model)
                & (pl.col("target_season") <= config.development_end)
            )
            if g.height < config.minimum_selection_folds:
                continue
            gain = float(g["mae_improvement"].mean())
            se = float(g["mae_improvement"].std(ddof=1) / math.sqrt(g.height))
            win = float((g["mae_improvement"] > 0).mean())
            dev = predictions.filter(
                (pl.col("outcome") == outcome)
                & (pl.col("model") == model)
                & (pl.col("target_season") <= config.development_end)
            )
            corr = _metrics(dev["actual"].to_numpy(), dev["prediction"].to_numpy(), 0.0)["pearson"]
            if (
                gain > max(se, config.selection_relative_gain * float(g["b2_mae"].mean()))
                and win >= config.selection_minimum_win_rate
                and g["rmse"].mean() <= config.selection_maximum_rmse_ratio * g["b2_rmse"].mean()
                and corr is not None
                and corr > 0
            ):
                candidates.append((float(g["mae"].mean()), model))
        selected[outcome] = min(candidates)[1] if candidates else "B2"
    return selected


def bootstrap_comparison(predictions: pl.DataFrame, config: ProjectionConfig) -> pl.DataFrame:
    rows = []
    for outcome in OUTCOMES:
        g = predictions.filter(
            (pl.col("target_season") > config.development_end) & (pl.col("outcome") == outcome)
        )
        base = g.filter(pl.col("model") == "B2").select(*KEY, pl.col("prediction").alias("base"))
        for model in MODELS:
            pairs = (
                g.filter(pl.col("model") == model)
                .join(base, on=KEY, validate="1:1")
                .with_columns(
                    (
                        (pl.col("actual") - pl.col("base")).abs()
                        - (pl.col("actual") - pl.col("prediction")).abs()
                    ).alias("gain")
                )
            )
            clusters = (
                pairs.group_by("player_id")
                .agg(pl.col("gain").sum(), pl.len().alias("n"))
                .sort("player_id")
            )
            rng = np.random.default_rng(config.seed)
            draws = []
            for _ in range(config.bootstrap_draws):
                ix = rng.integers(0, clusters.height, clusters.height)
                draws.append(
                    float(
                        clusters["gain"].to_numpy()[ix].sum() / clusters["n"].to_numpy()[ix].sum()
                    )
                )
            rows.append(
                {
                    "outcome": outcome,
                    "model": model,
                    "n": pairs.height,
                    "qb_clusters": clusters.height,
                    "mae_improvement": float(pairs["gain"].mean()),
                    "bootstrap_draws": len(draws),
                    "lower_95": float(np.quantile(draws, 0.025)),
                    "upper_95": float(np.quantile(draws, 0.975)),
                    "method": "QB_CLUSTER_FIXED_OOS_PREDICTIONS_NOT_REFIT",
                }
            )
    return pl.DataFrame(rows).sort("outcome", "model")


def subgroup_metrics(
    predictions: pl.DataFrame, cohort: pl.DataFrame, config: ProjectionConfig
) -> pl.DataFrame:
    info = cohort.select(
        *KEY,
        "is_rookie",
        "seasons_since_rookie_year",
        "prior_dropbacks",
        "outcome_dropbacks",
        "diagnostic_team_change",
        "preseason_ability_reliability",
    )
    g = predictions.filter(pl.col("target_season") > config.development_end).join(
        info, on=KEY, validate="m:1"
    )
    groups = {
        "returning_veteran": ~pl.col("is_rookie") & (pl.col("prior_dropbacks") > 0),
        "developing_0_to_3_years": pl.col("seasons_since_rookie_year").is_between(0, 3),
        "experienced_4plus_years": pl.col("seasons_since_rookie_year") >= 4,
        "volume_50_to_199": pl.col("outcome_dropbacks").is_between(50, 199),
        "volume_200_to_399": pl.col("outcome_dropbacks").is_between(200, 399),
        "volume_400plus": pl.col("outcome_dropbacks") >= 400,
        "retrospective_team_changer": pl.col("diagnostic_team_change") == True,  # noqa: E712
        "ability_high_reliability": pl.col("preseason_ability_reliability") == "HIGH",
    }
    rows = []
    for name, expr in groups.items():
        for (outcome, model), f in g.filter(expr).group_by("outcome", "model", maintain_order=True):
            rows.append(
                {
                    "subgroup": name,
                    "outcome": outcome,
                    "model": model,
                    **_metrics(f["actual"].to_numpy(), f["prediction"].to_numpy(), 0.0),
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None).sort("subgroup", "outcome", "model")


def assess_models(
    metrics: pl.DataFrame,
    coverage: pl.DataFrame,
    comparison: pl.DataFrame,
    selected: dict,
    config: ProjectionConfig,
) -> list[dict]:
    decisions = []
    for outcome, model in selected.items():
        m = metrics.filter(
            (pl.col("period") == "LOCKED_VALIDATION")
            & (pl.col("outcome") == outcome)
            & (pl.col("model") == model)
        ).row(0, named=True)
        b0 = metrics.filter(
            (pl.col("period") == "LOCKED_VALIDATION")
            & (pl.col("outcome") == outcome)
            & (pl.col("model") == "B0")
        ).row(0, named=True)
        recent = comparison.filter(
            (pl.col("target_season") >= config.acceptance_recent_start)
            & (pl.col("outcome") == outcome)
            & (pl.col("model") == model)
        )
        folds = comparison.filter(
            (pl.col("target_season") > config.development_end)
            & (pl.col("outcome") == outcome)
            & (pl.col("model") == model)
        )
        cov = coverage.filter(
            (pl.col("period") == "LOCKED_VALIDATION")
            & (pl.col("outcome") == outcome)
            & (pl.col("model") == model)
        )
        point_ok = (
            m["n"] >= config.acceptance_minimum_n
            and folds.height >= config.acceptance_minimum_folds
            and m["pearson"] is not None
            and m["pearson"] >= config.acceptance_minimum_correlation
            and m["spearman"] is not None
            and m["spearman"] > 0
            and m["mae"] < b0["mae"]
            and m["calibration_slope"] is not None
            and config.acceptance_slope_bounds[0]
            <= m["calibration_slope"]
            <= config.acceptance_slope_bounds[1]
            and abs(m["calibration_intercept"]) <= config.acceptance_maximum_intercept
            and recent["mae"].mean()
            <= config.selection_maximum_rmse_ratio * recent["b2_mae"].mean()
        )
        interval_ok = all(
            r["n"] >= config.acceptance_minimum_n
            and r["coverage"] is not None
            and abs(r["coverage"] - r["level"]) <= config.acceptance_interval_tolerance
            for r in cov.to_dicts()
        )
        status = (
            "RESEARCH-READY WITH LIMITATIONS"
            if point_ok and interval_ok
            else "EXPLORATORY ONLY"
            if point_ok
            else "NOT SUPPORTED"
        )
        decisions.append(
            {
                "outcome": outcome,
                "selected_model": model,
                "selection_cutoff": config.development_end,
                "point_acceptance": bool(point_ok),
                "interval_acceptance": bool(interval_ok),
                "model_status": status,
                "projection_intervals_supported": bool(point_ok and interval_ok),
                "scheme_interactions_allowed": False,
                "coach_effect_allowed": False,
            }
        )
    return decisions


def content_identity(inputs: dict, config: ProjectionConfig) -> tuple[str, dict]:
    code = {
        p.name: _digest(p.read_bytes())
        for p in (
            Path(__file__),
            Path(player_scheme_fit.__file__),
            Path(predictive_foundation.__file__),
        )
    }
    identity = {
        "inputs": inputs,
        "config": asdict(config),
        "state_features": STATE_FEATURES,
        "header_features": HEADER_FEATURES,
        "baseline_records": BASELINE_RECORDS,
        "models": MODELS,
        "outcomes": OUTCOMES,
        "source_code": code,
        "dependencies": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
        },
        "serialization": {
            "parquet_compression": "zstd",
            "compression_level": 3,
            "statistics": True,
            "row_group_size": 10000,
            "csv_float_precision": 15,
        },
        "grain": KEY,
        "target_seasons": list(range(2010, 2026)),
        "forward_target": 2026,
    }
    identity = json.loads(_json_bytes(identity))
    return "c16-" + _digest(_json_bytes(identity))[:16], identity


def _publish_latest(root: Path, version: str) -> None:
    fd, latest = tempfile.mkstemp(prefix=".LATEST-", dir=root)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(version + "\n")
        os.replace(latest, root / "LATEST")
    finally:
        if Path(latest).exists():
            Path(latest).unlink()


def load_inputs(project_root: Path):
    root = project_root / "data/processed"
    parents = {
        "state": root / f"qb_player_state/{C14_VERSION}",
        "enh": root / f"enhancements/{ENH_VERSION}",
        "foundation": root / f"predictive_foundation/{C13_VERSION}",
    }
    manifest_bytes = {
        key: (path / ("RUN_MANIFEST.json" if key == "enh" else "MANIFEST.json")).read_bytes()
        for key, path in parents.items()
    }
    enhancement_checksums = (parents["enh"] / "OUTPUT_CHECKSUMS.json").read_bytes()
    manifests = {key: json.loads(content) for key, content in manifest_bytes.items()}
    names = {
        "states": ("state", "player_states.parquet"),
        "records": ("state", "qb_state_feature_records.parquet"),
        "registry": ("state", "qb_feature_registry.csv"),
        "evaluation": ("state", "qb_state_evaluation_links.parquet"),
        "performance": ("enh", "canonical_qb_team_season_performance.parquet"),
        "pae": ("enh", "canonical_qb_pae.parquet"),
    }
    inputs, frames = {}, {}
    for key, (parent, name) in names.items():
        content = (parents[parent] / name).read_bytes()
        digest = _digest(content)
        checks = manifests[parent].get("output_checksums", manifests[parent].get("checksums", {}))
        if parent == "enh":
            checks = {
                name: item["sha256"] for name, item in json.loads(enhancement_checksums).items()
            }
        if digest != checks.get(name):
            raise ValueError(f"input checksum mismatch: {key}")
        inputs[key] = digest
        frames[key] = (
            pl.read_parquet(io.BytesIO(content))
            if name.endswith(".parquet")
            else pl.read_csv(io.BytesIO(content))
        )
    inputs.update({f"{key}_manifest": _digest(manifest_bytes[key]) for key in parents})
    inputs["enhancement_checksums"] = _digest(enhancement_checksums)
    return frames, inputs


def forward_readiness(predictors: pl.DataFrame) -> dict:
    forward = predictors.filter(pl.col("target_season") == 2026)
    if (
        forward.height
        and forward.filter(
            (pl.col("maximum_source_season") >= 2026) | (pl.col("as_of_date") != "2026-08-31")
        ).height
    ):
        raise ValueError("invalid forward Player State")
    return {
        "target_season": 2026,
        "approved_state_rows": forward.height,
        "status": "NOT_READY_MISSING_APPROVED_2026_PLAYER_STATE"
        if not forward.height
        else "STATE_AVAILABLE_REQUIRES_ACCEPTED_MODEL",
        "projected_qbs": 0,
    }


def run_checkpoint_sixteen(
    project_root: Path,
    output_root: Path | None = None,
    config: ProjectionConfig | None = None,
) -> dict:
    config = config or ProjectionConfig()
    frames, inputs = load_inputs(project_root)
    version, identity = content_identity(inputs, config)
    root = output_root or project_root / "data/processed/qb_projection"
    destination = root / version
    if destination.exists():
        manifest = json.loads((destination / "MANIFEST.json").read_bytes())
        if manifest["identity"] != identity:
            raise ValueError("published projection identity mismatch")
        for name, digest in manifest["output_checksums"].items():
            if _digest((destination / name).read_bytes()) != digest:
                raise ValueError(f"published projection checksum mismatch: {name}")
        _publish_latest(root, version)
        return manifest
    predictors, lineage = build_predictors(frames["states"], frames["records"], frames["registry"])
    outcomes = aggregate_outcomes(frames["performance"], frames["pae"])
    cohort = build_cohort(predictors, outcomes, config)
    # Reconcile C14's published stint-level universe audit without backfilling states.
    links = frames["evaluation"]
    link_check = links.join(
        predictors.select(
            pl.col("player_id"), pl.col("target_season").alias("season")
        ).with_columns(pl.lit(True).alias("matched")),
        on=["player_id", "season"],
        how="left",
        validate="m:1",
    )
    if link_check.filter(
        pl.col("state_universe_member") != pl.col("matched").fill_null(False)
    ).height:
        raise ValueError("C14 evaluation/state membership disagrees")
    predictions, folds, parameters = rolling_predictions(cohort, config)
    metrics = model_metrics(predictions, config)
    coverage = interval_coverage(predictions, config)
    comparison = paired_comparison(predictions, config)
    selected = select_models(predictions, comparison, config)
    decisions = assess_models(metrics, coverage, comparison, selected, config)
    selected_oos = pl.concat(
        [
            predictions.filter(
                (pl.col("outcome") == o)
                & (pl.col("model") == m)
                & (pl.col("target_season") > config.development_end)
            )
            for o, m in selected.items()
        ]
    ).sort("outcome", "target_season", "player_id")
    selected_oos = selected_oos.with_columns(
        pl.lit(version).alias("data_version"),
        pl.lit(version.replace("c16-", "qb-projection-")).alias("model_version"),
    )
    selected_oos = selected_oos.join(
        pl.DataFrame(decisions).select("outcome", "model_status", "projection_intervals_supported"),
        on="outcome",
        validate="m:1",
    ).with_columns(pl.lit("HISTORICAL_OOS_RESEARCH_NOT_LIVE_FORECAST").alias("use_status"))
    forward = forward_readiness(predictors)
    registry = pl.DataFrame(
        [
            {
                "feature_name": name,
                "source": "C14_FEATURE_RECORD" if name in STATE_FEATURES else "C14_STATE_HEADER",
                "primary_input": True,
                "timing": "AUGUST_31_NO_TARGET_OUTCOMES",
            }
            for name in MODEL_FEATURES
        ]
    )
    missing = (
        cohort.filter(pl.col("eligible"))
        .select(*KEY, *MODEL_FEATURES)
        .unpivot(index=KEY, variable_name="feature_name", value_name="value")
        .group_by("target_season", "feature_name")
        .agg(pl.len().alias("rows"), pl.col("value").is_null().sum().alias("missing_rows"))
        .sort("target_season", "feature_name")
    )
    leakage = pl.DataFrame(
        [
            {
                "gate": "NO_TARGET_SOURCE_OR_TRANSFORMATION",
                "failures": lineage.filter(
                    (pl.col("source_season") >= pl.col("target_season"))
                    | (pl.col("standardization_fit_end_season") >= pl.col("target_season"))
                ).height,
            },
            {
                "gate": "TRAINING_BEFORE_TARGET",
                "failures": folds.filter(
                    pl.col("train_end_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "TUNING_BEFORE_TARGET",
                "failures": folds.filter(
                    pl.col("tuning_latest_validation_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "CALIBRATION_BEFORE_TARGET",
                "failures": predictions.filter(
                    pl.col("calibration_end_season") >= pl.col("target_season")
                ).height,
            },
            {
                "gate": "EXPLICIT_PLAYER_ONLY_FEATURE_ALLOWLIST",
                "failures": len(set(MODEL_FEATURES) - set(STATE_FEATURES + HEADER_FEATURES)),
            },
        ]
    ).with_columns((pl.col("failures") == 0).alias("passed"))
    if leakage.filter(~pl.col("passed")).height:
        raise ValueError("projection leakage gate failed")
    artifacts = {
        "projection_feature_registry.csv": registry,
        "projection_cohort.parquet": cohort,
        "state_predictors.parquet": predictors,
        "state_input_lineage.parquet": lineage,
        "fold_assignments.csv": folds,
        "model_comparison.csv": metrics,
        "baseline_comparison.csv": comparison,
        "oos_predictions.parquet": predictions,
        "selected_oos_projections.parquet": selected_oos,
        "subgroup_diagnostics.csv": subgroup_metrics(predictions, cohort, config),
        "interval_coverage.csv": coverage,
        "bootstrap_comparison.csv": bootstrap_comparison(predictions, config),
        "missingness_coverage.csv": missing,
        "leakage_audit.csv": leakage,
        "checkpoint_decision.csv": pl.DataFrame(decisions),
        "forward_readiness.csv": pl.DataFrame([forward]),
        "cohort_coverage.csv": cohort.group_by("target_season", "exclusion_reason")
        .len()
        .sort("target_season", "exclusion_reason"),
    }
    summary = {
        "state_headers": predictors.height,
        "c14_evaluation_stints": links.height,
        "c14_matched_stints": links.filter(pl.col("state_universe_member")).height,
        "c14_excluded_stints": links.filter(~pl.col("state_universe_member")).height,
        "outcome_player_seasons": outcomes.height,
        "matched_player_seasons": cohort.filter(pl.col("state_matched")).height,
        "eligible_player_seasons": cohort.filter(pl.col("eligible")).height,
        "prediction_rows_all_models_outcomes": predictions.height,
        "selected_models": selected,
        "forward": forward,
    }
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=root))
    try:
        for name, frame in artifacts.items():
            if name.endswith(".parquet"):
                frame.write_parquet(
                    stage / name,
                    compression="zstd",
                    compression_level=3,
                    statistics=True,
                    row_group_size=10000,
                )
            else:
                frame.write_csv(stage / name, float_precision=15)
        (stage / "selected_model_parameters.json").write_bytes(
            _json_bytes(
                {
                    "selection_development_end": config.development_end,
                    "selected": selected,
                    "baseline_definitions": {
                        "B0": "Prior eligible player-seasons: dropback-weighted outcome mean.",
                        "B1": "Qualified prior-season raw observation; missing uses B0 with flag.",
                        "B2_epa": {
                            "source": "canonical_qb_pae.parquet:expected_epa_per_dropback",
                            "model_version": "expected-performance-8fd5d1aba2598c59",
                            "model_name": "career_performance",
                            "historical_shrinkage_dropbacks": 500,
                            "usage": "Frozen OOS comparison baseline, not a Player State feature.",
                        },
                        "B2_pae": "Zero: performance exactly at the frozen preseason expectation.",
                    },
                    "rolling_ridge_parameters": parameters,
                }
            )
        )
        manifest = {
            "data_version": version,
            "model_version": version.replace("c16-", "qb-projection-"),
            "identity": identity,
            "counts": summary,
            "checkpoint_status": "COMPLETE",
            "decisions": decisions,
            "checkpoint_17_readiness": "NOT READY",
            "checkpoint_17_blocker": (
                "Selected projection models have not passed all acceptance gates. "
                "No validated target-environment/scenario contract; approved 2026 Player State "
                "is absent. Historical team-independent validation does not solve C15 fit."
            ),
            "output_checksums": {p.name: _digest(p.read_bytes()) for p in sorted(stage.iterdir())},
        }
        (stage / "MANIFEST.json").write_bytes(_json_bytes(manifest))
        os.replace(stage, destination)
        _publish_latest(root, version)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest

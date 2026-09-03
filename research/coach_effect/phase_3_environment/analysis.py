"""Environment robustness tests for exploratory PCAE."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.coach_effect.config import ENVIRONMENT_FEATURES

OUTCOME = "actual_offensive_epa"


@dataclass(frozen=True)
class ModelResult:
    name: str
    features: tuple[str, ...]
    in_sample_r2: float
    rmse: float


def _require(frame: pl.DataFrame, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"environment frame is missing required columns: {missing}")


def _pipeline() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LinearRegression()),
        ]
    )


def _fit(frame: pl.DataFrame, features: tuple[str, ...], name: str) -> ModelResult:
    _require(frame, {OUTCOME, *features})
    x = frame.select(features).cast(pl.Float64).to_numpy()
    y = frame[OUTCOME].to_numpy()
    prediction = _pipeline().fit(x, y).predict(x)
    return ModelResult(
        name=name,
        features=features,
        in_sample_r2=float(r2_score(y, prediction)),
        rmse=float(mean_squared_error(y, prediction) ** 0.5),
    )


def compare_environment_models(frame: pl.DataFrame) -> tuple[ModelResult, ModelResult]:
    """Compare the final environment control set with and without PCAE."""

    environment = tuple(ENVIRONMENT_FEATURES)
    return (
        _fit(frame, environment, "environment_only"),
        _fit(frame, (*environment, "pcae"), "environment_plus_pcae"),
    )


def staged_environment_models(frame: pl.DataFrame) -> tuple[ModelResult, ...]:
    """Reproduce the chronological in-sample control additions from Phase 3."""

    specifications = (
        ("prior_team", ("prior_team_epa",)),
        ("prior_team_plus_pcae", ("prior_team_epa", "pcae")),
        ("prior_team_plus_expected_qb", ("prior_team_epa", "expected_qb_epa")),
        (
            "prior_team_plus_expected_qb_plus_pcae",
            ("prior_team_epa", "expected_qb_epa", "pcae"),
        ),
        (
            "prior_team_plus_expected_qb_plus_supporting_cast",
            ("prior_team_epa", "expected_qb_epa", "supporting_cast"),
        ),
        (
            "prior_team_plus_expected_qb_plus_supporting_cast_plus_pcae",
            ("prior_team_epa", "expected_qb_epa", "supporting_cast", "pcae"),
        ),
    )
    return tuple(_fit(frame, features, name) for name, features in specifications)


def leave_one_team_out(
    frame: pl.DataFrame,
    features: tuple[str, ...],
) -> tuple[pl.DataFrame, dict[str, float]]:
    """Predict each team using a model fit without any row from that team."""

    _require(frame, {"team_id", OUTCOME, *features})
    teams = sorted(frame["team_id"].unique().to_list())
    predictions: list[pl.DataFrame] = []
    for team_id in teams:
        train = frame.filter(pl.col("team_id") != team_id)
        test = frame.filter(pl.col("team_id") == team_id)
        if train.height <= len(features) or test.is_empty():
            raise ValueError(f"insufficient leave-one-team-out sample for {team_id}")
        model = _pipeline().fit(
            train.select(features).cast(pl.Float64).to_numpy(),
            train[OUTCOME].to_numpy(),
        )
        prediction = model.predict(test.select(features).cast(pl.Float64).to_numpy())
        predictions.append(
            test.select("team_id", OUTCOME).with_columns(pl.Series("prediction", prediction))
        )
    scored = pl.concat(predictions).sort("team_id")
    actual = scored[OUTCOME].to_numpy()
    predicted = scored["prediction"].to_numpy()
    return scored, {
        "r2": float(r2_score(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
    }


def standardized_coefficients(
    frame: pl.DataFrame,
    features: tuple[str, ...] = (*ENVIRONMENT_FEATURES, "pcae"),
) -> dict[str, float]:
    """Return descriptive standardized coefficients, never final Coach Effect weights."""

    _require(frame, {OUTCOME, *features})
    x = frame.select(features).cast(pl.Float64).to_numpy()
    y = frame[OUTCOME].to_numpy()
    y_scale = float(np.std(y, ddof=0))
    if y_scale == 0:
        raise ValueError("outcome variance is required")
    y_standardized = (y - float(np.mean(y))) / y_scale
    model = _pipeline().fit(x, y_standardized)
    coefficients = model.named_steps["model"].coef_
    return {feature: float(value) for feature, value in zip(features, coefficients, strict=True)}

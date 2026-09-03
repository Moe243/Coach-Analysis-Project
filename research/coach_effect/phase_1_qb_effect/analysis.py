"""Leakage-safe Phase 1 PAE and consecutive-QB-transition helpers.

Inputs are research frames derived from the immutable checkpoint-five PAE artifact and
interval-aware coaching assignments. No production table is written by this module.
"""

from __future__ import annotations

import polars as pl
from sklearn.linear_model import Ridge

from research.coach_effect.config import PAE_FORMULA, QB_DEVELOPMENT_SIGNAL_FORMULA


def _require(frame: pl.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def add_pae(frame: pl.DataFrame) -> pl.DataFrame:
    """Calculate the checkpoint-five PAE identity without changing eligibility."""

    _require(frame, {"actual_epa_per_dropback", "expected_epa_per_dropback"}, "PAE input")
    return frame.with_columns(
        (pl.col("actual_epa_per_dropback") - pl.col("expected_epa_per_dropback")).alias(
            "performance_above_expectation"
        )
    )


def build_transitions(qb_role_seasons: pl.DataFrame) -> pl.DataFrame:
    """Build consecutive transitions while preserving QB/team/coach identities.

    The input must already contain one interval-safe, full-season role context per QB season.
    Ambiguous multi-interval seasons must be resolved upstream or excluded explicitly.
    """

    required = {
        "player_id",
        "team_id",
        "season",
        "performance_above_expectation",
        "offensive_coordinator_id",
        "head_coach_id",
    }
    _require(qb_role_seasons, required, "QB role-season input")
    key = ["player_id", "team_id", "season"]
    if qb_role_seasons.select(key).n_unique() != qb_role_seasons.height:
        raise ValueError("QB role-season input must be unique at player/team/season grain")

    current = qb_role_seasons.sort("player_id", "season", "team_id")
    prior = current.select(
        "player_id",
        (pl.col("season") + 1).alias("season"),
        pl.col("team_id").alias("prior_team_id"),
        pl.col("performance_above_expectation").alias("prior_pae"),
        pl.col("offensive_coordinator_id").alias("prior_offensive_coordinator_id"),
        pl.col("head_coach_id").alias("prior_head_coach_id"),
    )
    return (
        current.join(prior, on=["player_id", "season"], how="inner", validate="m:1")
        .with_columns(
            (pl.col("performance_above_expectation") - pl.col("prior_pae")).alias(
                "actual_qb_delta_pae"
            ),
            (pl.col("team_id") == pl.col("prior_team_id")).alias("same_team"),
            (pl.col("head_coach_id") == pl.col("prior_head_coach_id")).alias("same_head_coach"),
            (pl.col("offensive_coordinator_id") != pl.col("prior_offensive_coordinator_id")).alias(
                "changed_offensive_coordinator"
            ),
        )
        .sort("season", "player_id", "team_id")
    )


def fit_expected_movement(
    training_transitions: pl.DataFrame,
    scoring_transitions: pl.DataFrame,
    *,
    alpha: float = 10.0,
) -> tuple[pl.DataFrame, Ridge]:
    """Fit on earlier transitions and score a strictly later holdout.

    Coach identity is never a predictor. Requiring separate, ordered frames prevents a target
    transition from teaching the normal-movement baseline used to score itself.
    """

    required = {"season", "prior_pae", "actual_qb_delta_pae"}
    _require(training_transitions, required, "movement training input")
    _require(scoring_transitions, required, "movement scoring input")
    if training_transitions.height < 2 or scoring_transitions.is_empty():
        raise ValueError(
            "at least two training transitions and one scoring transition are required"
        )
    if training_transitions["season"].max() >= scoring_transitions["season"].min():
        raise ValueError("movement training seasons must be earlier than every scoring season")
    x_train = training_transitions.select("prior_pae").to_numpy()
    y_train = training_transitions["actual_qb_delta_pae"].to_numpy()
    model = Ridge(alpha=alpha).fit(x_train, y_train)
    expected = model.predict(scoring_transitions.select("prior_pae").to_numpy())
    actual = scoring_transitions["actual_qb_delta_pae"].to_numpy()
    scored = scoring_transitions.with_columns(
        pl.Series("expected_qb_delta_pae", expected),
        pl.Series("qb_development_signal", actual - expected),
    )
    return scored, model


def formula_contract() -> dict[str, str]:
    """Expose stable formula identities for tests and research manifests."""

    return {
        "pae": PAE_FORMULA,
        "qb_development_signal": QB_DEVELOPMENT_SIGNAL_FORMULA,
    }

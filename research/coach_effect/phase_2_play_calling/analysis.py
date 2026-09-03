"""Expected play-call and expected-EPA research for exploratory PCAE.

All functions operate on caller-supplied frames and return research frames. No function writes
to a production checkpoint, serving table, API, or frontend contract.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
    PLAY_CALL_TEST_SEASON,
    PLAY_CALL_TRAIN_SEASONS,
    RANDOM_SEED,
)

PLAY_KEY = ("game_id", "play_id")


@dataclass(frozen=True)
class ExpectedPlayModels:
    """The three fitted Phase 2 models and their declared feature contract."""

    call_model: Pipeline
    pass_epa_model: Pipeline
    run_epa_model: Pipeline
    feature_columns: tuple[str, ...] = PLAY_CALL_FEATURES
    train_seasons: tuple[int, ...] = PLAY_CALL_TRAIN_SEASONS
    test_season: int = PLAY_CALL_TEST_SEASON


def _require(frame: pl.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _matrix(frame: pl.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    return frame.select(features).cast(pl.Float64).to_numpy()


def _pipeline(estimator: object) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", estimator),
        ]
    )


def prepare_plays(raw: pl.DataFrame) -> pl.DataFrame:
    """Apply the declared regular-season run/pass and pre-snap feature contract."""

    required = {
        *PLAY_KEY,
        "season",
        "season_type",
        "week",
        "posteam",
        "play_type",
        "epa",
        *PLAY_CALL_FEATURES,
    }
    _require(raw, required, "play-by-play")
    candidate = raw.filter(
        (pl.col("season_type") == "REG") & pl.col("play_type").is_in(["pass", "run"])
    )
    null_keys = candidate.select(
        pl.col("game_id").is_null().sum().alias("null_game_ids"),
        pl.col("play_id").is_null().sum().alias("null_play_ids"),
        pl.col("posteam").is_null().sum().alias("null_teams"),
        pl.col("week").is_null().sum().alias("null_weeks"),
    ).row(0, named=True)
    if any(null_keys.values()):
        raise ValueError(f"eligible run/pass plays contain missing identifiers: {null_keys}")
    if candidate.select(PLAY_KEY).n_unique() != candidate.height:
        raise ValueError("play-by-play contains duplicate (game_id, play_id) keys")
    plays = candidate.filter(pl.col("epa").is_not_null() & pl.col("epa").is_finite())
    return plays.sort("season", "week", "game_id", "play_id")


def fit_expected_play_models(plays: pl.DataFrame) -> ExpectedPlayModels:
    """Fit the 2022–2024 expected-call and separate pass/run EPA models."""

    _require(plays, {"season", "play_type", "epa", *PLAY_CALL_FEATURES}, "prepared plays")
    train = plays.filter(pl.col("season").is_in(PLAY_CALL_TRAIN_SEASONS))
    if train.is_empty():
        raise ValueError("no declared training-season plays are available")
    if (
        train.filter(pl.col("play_type") == "pass").is_empty()
        or train.filter(pl.col("play_type") == "run").is_empty()
    ):
        raise ValueError("training data must contain both pass and run plays")

    x = _matrix(train, PLAY_CALL_FEATURES)
    y_call = (train["play_type"] == "pass").cast(pl.Int8).to_numpy()
    call_model = _pipeline(LogisticRegression(max_iter=2_000, random_state=RANDOM_SEED)).fit(
        x, y_call
    )

    pass_train = train.filter(pl.col("play_type") == "pass")
    run_train = train.filter(pl.col("play_type") == "run")
    pass_epa_model = _pipeline(Ridge(alpha=10.0)).fit(
        _matrix(pass_train, PLAY_CALL_FEATURES), pass_train["epa"].to_numpy()
    )
    run_epa_model = _pipeline(Ridge(alpha=10.0)).fit(
        _matrix(run_train, PLAY_CALL_FEATURES), run_train["epa"].to_numpy()
    )
    return ExpectedPlayModels(call_model, pass_epa_model, run_epa_model)


def score_expected_decisions(
    plays: pl.DataFrame,
    models: ExpectedPlayModels,
) -> pl.DataFrame:
    """Score expected choices without using the individual play's actual EPA result."""

    x = _matrix(plays, models.feature_columns)
    pass_probability = models.call_model.predict_proba(x)[:, 1]
    expected_pass = models.pass_epa_model.predict(x)
    expected_run = models.run_epa_model.predict(x)
    is_pass = (plays["play_type"] == "pass").to_numpy()
    chosen = np.where(is_pass, expected_pass, expected_run)
    alternative = np.where(is_pass, expected_run, expected_pass)
    preferred_pass = expected_pass >= expected_run
    return plays.with_columns(
        pl.Series("expected_pass_probability", pass_probability),
        pl.Series("expected_pass_epa", expected_pass),
        pl.Series("expected_run_epa", expected_run),
        pl.Series("expected_chosen_epa", chosen),
        pl.Series("expected_alternative_epa", alternative),
        pl.Series("call_value", chosen - alternative),
        pl.Series("modeled_advantage", np.abs(expected_pass - expected_run)),
        pl.Series("followed_preferred_call", is_pass == preferred_pass),
    )


def call_model_metrics(scored: pl.DataFrame) -> dict[str, float]:
    """Return held-out call-classification metrics for the declared test season."""

    test = scored.filter(pl.col("season") == PLAY_CALL_TEST_SEASON)
    if test.is_empty():
        raise ValueError(f"no {PLAY_CALL_TEST_SEASON} test plays are available")
    actual = (test["play_type"] == "pass").cast(pl.Int8).to_numpy()
    probability = test["expected_pass_probability"].to_numpy()
    predicted = (probability >= 0.5).astype(int)
    return {
        "actual_pass_rate": float(actual.mean()),
        "average_predicted_pass_probability": float(probability.mean()),
        "accuracy": float(accuracy_score(actual, predicted)),
        "log_loss": float(log_loss(actual, probability)),
        "brier": float(brier_score_loss(actual, probability)),
    }


def preferred_call_validation(scored: pl.DataFrame, threshold: float = 0.0) -> dict[str, float]:
    """Validate choices with aggregate actual EPA; actual EPA never defines Call Value."""

    sample = scored.filter(pl.col("modeled_advantage") >= threshold)
    followed = sample.filter(pl.col("followed_preferred_call"))["epa"].mean()
    ignored = sample.filter(~pl.col("followed_preferred_call"))["epa"].mean()
    return {
        "threshold": threshold,
        "followed_preferred_actual_epa": float(followed),
        "ignored_preferred_actual_epa": float(ignored),
        "difference": float(followed - ignored),
        "plays": sample.height,
    }


def attribute_play_callers(
    scored: pl.DataFrame,
    assignments: pl.DataFrame,
    *,
    evidence_column: str = "primary_source_url",
) -> pl.DataFrame:
    """Join every play to explicit, interval-aware play-caller evidence or fail."""

    assignment_columns = {
        "assignment_key",
        "season",
        "team_id",
        "coach_id",
        "role",
        "start_week",
        "end_week",
        "verification_status",
        "confidence_level",
        "interval_basis",
        "is_shared",
        evidence_column,
    }
    _require(assignments, assignment_columns, "play-caller assignments")
    caller_rows = assignments.filter(pl.col("role") == "play_caller")
    unsupported = caller_rows.filter(
        (pl.col("verification_status") != "verified")
        | (pl.col("interval_basis") == "season_designation")
        | pl.col(evidence_column).is_null()
        | (pl.col(evidence_column).str.strip_chars() == "")
    )
    if unsupported.height:
        keys = unsupported["assignment_key"].head(5).to_list()
        raise ValueError(f"play callers require explicit interval evidence: {keys}")
    if caller_rows["assignment_key"].n_unique() != caller_rows.height:
        raise ValueError("duplicate play-caller assignment keys")

    joined = (
        scored.join(
            caller_rows,
            left_on=["season", "posteam"],
            right_on=["season", "team_id"],
            how="left",
            validate="m:m",
        )
        .filter(pl.col("week").is_between(pl.col("start_week"), pl.col("end_week")))
        .with_columns(pl.len().over(PLAY_KEY).alias("simultaneous_callers"))
    )
    matched = joined.select(PLAY_KEY).unique()
    missing = scored.join(matched, on=PLAY_KEY, how="anti")
    if missing.height:
        sample = missing.select(*PLAY_KEY, "season", "week", "posteam").head(5).to_dicts()
        raise ValueError(f"plays lack explicit weekly play-caller evidence: {sample}")
    illegal = joined.filter(
        (pl.col("simultaneous_callers") > 1) & ~pl.col("is_shared").fill_null(False)
    )
    if illegal.height:
        keys = illegal["assignment_key"].unique().head(5).to_list()
        raise ValueError(f"unsupported simultaneous play callers: {keys}")
    return joined.with_columns(
        (1.0 / pl.col("simultaneous_callers")).alias("attribution_weight")
    ).sort("season", "week", "game_id", "play_id", "coach_id")


def aggregate_pcae(attributed: pl.DataFrame) -> pl.DataFrame:
    """Calculate league-centered coach average decision value by season."""

    _require(
        attributed,
        {"season", "coach_id", "call_value", "attribution_weight"},
        "attributed calls",
    )
    league = attributed.group_by("season").agg(
        (
            (pl.col("call_value") * pl.col("attribution_weight")).sum()
            / pl.col("attribution_weight").sum()
        ).alias("league_average_call_value")
    )
    coaches = attributed.group_by("season", "coach_id", maintain_order=True).agg(
        (
            (pl.col("call_value") * pl.col("attribution_weight")).sum()
            / pl.col("attribution_weight").sum()
        ).alias("coach_average_call_value"),
        pl.col("attribution_weight").sum().alias("effective_plays"),
        pl.len().alias("observed_plays"),
    )
    return (
        coaches.join(league, on="season", validate="m:1")
        .with_columns(
            (pl.col("coach_average_call_value") - pl.col("league_average_call_value")).alias("pcae")
        )
        .sort("season", "coach_id")
    )


def repeatability(
    pcae: pl.DataFrame,
    first_season: int = 2024,
    second_season: int = 2025,
) -> dict[str, float | int]:
    """Compare repeated play callers across two seasons."""

    first = pcae.filter(pl.col("season") == first_season).select(
        "coach_id", pl.col("pcae").alias("first_pcae")
    )
    second = pcae.filter(pl.col("season") == second_season).select(
        "coach_id", pl.col("pcae").alias("second_pcae")
    )
    paired = first.join(second, on="coach_id", how="inner", validate="1:1")
    if paired.height < 2:
        raise ValueError("at least two repeat play callers are required")
    correlation = float(np.corrcoef(paired["first_pcae"], paired["second_pcae"])[0, 1])
    same_direction = float(((paired["first_pcae"] * paired["second_pcae"]) > 0).mean())
    return {
        "repeat_callers": paired.height,
        "correlation": correlation,
        "same_direction_rate": same_direction,
    }


def estimate_repeat_reliability(pcae: pl.DataFrame) -> dict[str, float | int]:
    """Estimate one-season ICC and two-season Spearman-Brown reliability.

    Only coaches with at least two seasons enter the estimate. This is an exploratory empirical
    reliability calculation, not a final ranking weight.
    """

    repeated_ids = pcae.group_by("coach_id").len().filter(pl.col("len") >= 2)["coach_id"].to_list()
    repeated = pcae.filter(pl.col("coach_id").is_in(repeated_ids))
    if len(repeated_ids) < 2:
        raise ValueError("at least two repeated play callers are required")
    groups = [group["pcae"].to_numpy() for _, group in repeated.group_by("coach_id")]
    counts = np.array([len(values) for values in groups], dtype=float)
    grand = float(repeated["pcae"].mean())
    between_ss = sum(len(values) * (float(values.mean()) - grand) ** 2 for values in groups)
    within_ss = sum(float(((values - values.mean()) ** 2).sum()) for values in groups)
    between_ms = between_ss / (len(groups) - 1)
    within_df = int(counts.sum() - len(groups))
    if within_df <= 0:
        raise ValueError("repeat callers need within-coach replication")
    within_ms = within_ss / within_df
    k = float(counts.mean())
    denominator = between_ms + (k - 1.0) * within_ms
    one_season = max(0.0, min(1.0, (between_ms - within_ms) / denominator))
    two_season = (2.0 * one_season) / (1.0 + one_season) if one_season else 0.0
    return {
        "repeat_callers": len(groups),
        "one_season_reliability": one_season,
        "two_season_average_reliability": two_season,
    }


def shrink_pcae(pcae: pl.DataFrame, reliability: float) -> pl.DataFrame:
    """Shrink league-centered PCAE toward zero using an externally estimated reliability."""

    if not 0.0 <= reliability <= 1.0:
        raise ValueError("reliability must be between zero and one")
    return pcae.with_columns((pl.col("pcae") * reliability).alias("shrunk_pcae"))


def formula_contract() -> dict[str, str]:
    return {"call_value": CALL_VALUE_FORMULA, "pcae": PCAE_FORMULA}

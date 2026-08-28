"""Leakage-safe checkpoint-five quarterback expectation and PAE pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .constants import ANALYSIS_SEASONS, WARMUP_SEASONS
from .errors import PipelineError
from .pipeline import (
    _output_checksums,
    _update_latest,
    _validate_existing_version,
    _write_json,
)
from .sources import sha256_file

FEATURE_VERSION = "qb-preseason-v2"
MODEL_PIPELINE_VERSION = "checkpoint-5.1"
MODEL_NAMES = (
    "league_average",
    "recent_performance",
    "career_performance",
    "ridge",
)
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
TRAINING_MIN_DROPBACKS = 50
ELIGIBILITY_DROPBACKS = 200
RECENT_SHRINKAGE_DROPBACKS = 200.0
CAREER_SHRINKAGE_DROPBACKS = 500.0
SENSITIVITY_THRESHOLDS = (50, 100, 200, 300, 400)
SELECTION_INTERCEPT_WEIGHT = 0.25
SELECTION_SLOPE_WEIGHT = 0.02
INTERVAL_MULTIPLIER = 1.96
INTERVAL_FALLBACK_RESIDUALS = 20
RELIABILITY_CAREER_DROPBACKS = 600
MINIMUM_PREDICTION_SIGMA = 0.01
TRAINING_WEIGHT_MINIMUM = 50.0
TRAINING_WEIGHT_MAXIMUM = 600.0
TRAINING_WEIGHT_SCALE = 200.0
FORBIDDEN_FEATURE_TERMS = (
    "coach",
    "current_season",
    "target_season",
    "record",
    "ranking",
    "wins",
    "losses",
)

MODEL_FEATURE_COLUMNS = (
    "age",
    "nfl_experience",
    "is_rookie",
    "prior_qb_seasons",
    "no_prior_qb_performance",
    "prior_starts",
    "prior_dropbacks",
    "prior_epa_per_dropback",
    "prior_cpoe",
    "prior_success_rate",
    "prior_sack_rate",
    "prior_interception_rate",
    "prior_touchdown_rate",
    "career_starts",
    "career_dropbacks",
    "career_epa_per_dropback",
    "career_cpoe",
    "career_success_rate",
    "career_sack_rate",
    "career_interception_rate",
    "career_touchdown_rate",
    "changed_team",
    "changed_team_missing",
    "prior_injury_report_weeks",
    "prior_injury_out_weeks",
    "draft_position",
    "draft_round",
    "college_production",
    "age_missing",
    "nfl_experience_missing",
    "rookie_status_missing",
    "prior_season_missing",
    "prior_cpoe_missing",
    "prior_injury_missing",
    "draft_position_missing",
    "draft_round_missing",
    "college_production_missing",
)


@dataclass(frozen=True)
class ExpectedPerformanceConfig:
    project_root: Path
    historical_dir: Path | None = None
    output_dir: Path | None = None

    @property
    def resolved_historical_dir(self) -> Path:
        return self.historical_dir or self.project_root / "data" / "processed" / "historical"

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "data" / "processed" / "expected_performance"


@dataclass(frozen=True)
class ExpectedPerformanceResult:
    data_version: str
    model_version: str
    selected_model: str
    output_path: Path
    reused_existing: bool
    table_counts: dict[str, int]


@dataclass(frozen=True)
class ExpectedPerformanceTables:
    features: pl.DataFrame
    predictions: pl.DataFrame
    pae: pl.DataFrame
    evaluation: pl.DataFrame
    sensitivity: pl.DataFrame
    experience_evaluation: pl.DataFrame
    metadata: dict[str, object]


def _finite(value: object) -> bool:
    return value is not None and math.isfinite(float(value))


def _safe_rate(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _sum(rows: list[dict[str, object]], column: str) -> float:
    return sum(float(row.get(column) or 0.0) for row in rows)


def _aggregate_history(rows: list[dict[str, object]]) -> dict[str, object]:
    dropbacks = int(_sum(rows, "dropbacks"))
    attempts = int(_sum(rows, "attempts"))
    sacks = int(_sum(rows, "sacks"))
    cpoe_attempts = int(_sum(rows, "cpoe_attempts"))
    total_epa = sum(
        float(row["total_qb_epa"])
        if _finite(row.get("total_qb_epa"))
        else float(row["epa_per_dropback"]) * int(row["dropbacks"])
        for row in rows
    )
    return {
        "starts": int(_sum(rows, "starts")),
        "dropbacks": dropbacks,
        "epa_per_dropback": _safe_rate(total_epa, dropbacks),
        "cpoe": _safe_rate(_sum(rows, "total_cpoe"), cpoe_attempts),
        "success_rate": _safe_rate(_sum(rows, "positive_epa_dropbacks"), dropbacks),
        "sack_rate": _safe_rate(sacks, attempts + sacks),
        "interception_rate": _safe_rate(_sum(rows, "interceptions"), attempts),
        "touchdown_rate": _safe_rate(_sum(rows, "passing_touchdowns"), attempts),
        "teams": sorted({str(row["team_id"]) for row in rows}),
        "seasons": sorted({int(row["season"]) for row in rows}),
    }


def _injury_history(injuries: pl.DataFrame | None) -> dict[tuple[str, int], tuple[int, int]]:
    if injuries is None or injuries.is_empty():
        return {}
    required = {"canonical_player_id", "source_season", "week", "report_status"}
    if not required <= set(injuries.columns):
        raise PipelineError(
            f"injury input lacks required columns: {sorted(required - set(injuries.columns))}"
        )
    weeks: dict[tuple[str, int], set[int]] = defaultdict(set)
    out_weeks: dict[tuple[str, int], set[int]] = defaultdict(set)
    for row in injuries.select(sorted(required)).iter_rows(named=True):
        player_id = row["canonical_player_id"]
        if not player_id or row["source_season"] is None or row["week"] is None:
            continue
        key = (str(player_id), int(row["source_season"]))
        week = int(row["week"])
        weeks[key].add(week)
        if str(row["report_status"] or "").strip().casefold() == "out":
            out_weeks[key].add(week)
    return {key: (len(values), len(out_weeks[key])) for key, values in weeks.items()}


def _age_on_season_start(birth_date: object, season: int) -> float | None:
    if birth_date is None:
        return None
    if isinstance(birth_date, str):
        birth_date = date.fromisoformat(birth_date)
    if not isinstance(birth_date, date):
        return None
    return (date(season, 9, 1) - birth_date).days / 365.2425


def _roster_profile_lookup(
    rosters: pl.DataFrame | None,
) -> dict[tuple[str, int], dict[str, int | None]]:
    if rosters is None or rosters.is_empty():
        return {}
    required = {"gsis_id", "source_season", "years_exp", "entry_year", "rookie_year"}
    if not required <= set(rosters.columns):
        raise PipelineError(
            f"roster input lacks required columns: {sorted(required - set(rosters.columns))}"
        )
    profiles: dict[tuple[str, int], dict[str, int | None]] = {}
    for key, group in (
        rosters.select(sorted(required))
        .drop_nulls("gsis_id")
        .group_by("gsis_id", "source_season", maintain_order=True)
    ):
        player_id, season = str(key[0]), int(key[1])
        values: dict[str, int | None] = {}
        for column in ("years_exp", "entry_year", "rookie_year"):
            distinct = sorted({int(value) for value in group[column].drop_nulls().to_list()})
            values[column] = distinct[0] if len(distinct) == 1 else None
        profiles[(player_id, season)] = values
    return profiles


def _preseason_team_lookup(
    depth_charts: pl.DataFrame | None,
) -> dict[tuple[str, int], tuple[str, ...]]:
    if depth_charts is None or depth_charts.is_empty():
        return {}
    required = {
        "canonical_player_id",
        "canonical_team_id",
        "source_season",
        "week",
        "game_type",
    }
    if not required <= set(depth_charts.columns):
        missing = sorted(required - set(depth_charts.columns))
        raise PipelineError(f"depth-chart input lacks required columns: {missing}")
    preseason = depth_charts.filter(
        (pl.col("week") == 1)
        & (pl.col("game_type") == "REG")
        & pl.col("canonical_player_id").is_not_null()
        & pl.col("canonical_team_id").is_not_null()
    )
    lookup: dict[tuple[str, int], tuple[str, ...]] = {}
    for key, group in preseason.group_by(
        "canonical_player_id", "source_season", maintain_order=True
    ):
        lookup[(str(key[0]), int(key[1]))] = tuple(
            sorted({str(value) for value in group["canonical_team_id"].to_list()})
        )
    return lookup


def validate_feature_frame(features: pl.DataFrame) -> None:
    grain = ("player_id", "team_id", "season")
    if features.select(grain).n_unique() != features.height:
        raise PipelineError("duplicate QB-team-season preseason feature rows")
    if features.filter(pl.col("as_of_season") != pl.col("season") - 1).height:
        raise PipelineError("preseason features must use an exact season-minus-one as-of value")
    leaked = features.filter(
        pl.col("feature_source_max_season").is_not_null()
        & (pl.col("feature_source_max_season") >= pl.col("season"))
    )
    if leaked.height:
        raise PipelineError("target-season or future-season data leaked into preseason features")
    forbidden = [
        column
        for column in MODEL_FEATURE_COLUMNS
        if any(term in column.casefold() for term in FORBIDDEN_FEATURE_TERMS)
    ]
    if forbidden:
        raise PipelineError(f"forbidden expectation-model features: {forbidden}")
    for column in MODEL_FEATURE_COLUMNS:
        if column not in features.columns:
            raise PipelineError(f"missing expectation-model feature column: {column}")
    multi_team = features.group_by("player_id", "season").len().filter(pl.col("len") > 1)
    if not multi_team.is_empty():
        multi_team_features = features.join(
            multi_team.select("player_id", "season"),
            on=["player_id", "season"],
            validate="m:1",
        )
        for column in MODEL_FEATURE_COLUMNS:
            inconsistent = (
                multi_team_features.group_by("player_id", "season")
                .agg(pl.col(column).n_unique().alias("distinct_values"))
                .filter(pl.col("distinct_values") > 1)
            )
            if inconsistent.height:
                raise PipelineError(
                    f"target-season destination changed preseason model feature: {column}"
                )


def build_preseason_features(
    qb_seasons: pl.DataFrame,
    players: pl.DataFrame,
    injuries: pl.DataFrame | None = None,
    rosters: pl.DataFrame | None = None,
    depth_charts: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Build one deterministic row per QB-team-season using seasons strictly before target."""

    required = {
        "season",
        "player_id",
        "team_id",
        "starts",
        "dropbacks",
        "attempts",
        "sacks",
        "interceptions",
        "passing_touchdowns",
        "positive_epa_dropbacks",
        "cpoe_attempts",
        "total_cpoe",
        "total_qb_epa",
        "epa_per_dropback",
    }
    missing = required - set(qb_seasons.columns)
    if missing:
        raise PipelineError(f"QB-season input lacks required columns: {sorted(missing)}")
    input_grain = qb_seasons.select("player_id", "team_id", "season")
    if input_grain.n_unique() != qb_seasons.height:
        raise PipelineError("duplicate QB-team-season rows in historical input")

    player_lookup = {
        str(row["player_id"]): row
        for row in players.select("player_id", "display_name", "birth_date").iter_rows(named=True)
    }
    injury_lookup = _injury_history(injuries)
    roster_lookup = _roster_profile_lookup(rosters)
    preseason_team_lookup = _preseason_team_lookup(depth_charts)
    rows = qb_seasons.sort("season", "player_id", "team_id").to_dicts()
    by_player: dict[str, list[dict[str, object]]] = defaultdict(list)
    records: list[dict[str, object]] = []
    for row in rows:
        season = int(row["season"])
        player_id = str(row["player_id"])
        history = [item for item in by_player[player_id] if int(item["season"]) < season]
        prior_rows = [item for item in history if int(item["season"]) == season - 1]
        prior = _aggregate_history(prior_rows) if prior_rows else None
        career = _aggregate_history(history) if history else None
        player = player_lookup.get(player_id, {})
        injury_value = injury_lookup.get((player_id, season - 1))
        roster_profile = roster_lookup.get((player_id, season))
        nfl_experience = None if roster_profile is None else roster_profile.get("years_exp")
        rookie_year = None if roster_profile is None else roster_profile.get("rookie_year")
        entry_year = None if roster_profile is None else roster_profile.get("entry_year")
        is_rookie: bool | None = None
        if roster_profile is not None:
            is_rookie = rookie_year == season and nfl_experience in (0, None)
            if rookie_year is None and entry_year == season and nfl_experience == 0:
                is_rookie = True
        prior_qb_seasons = len({int(item["season"]) for item in history})
        no_prior_qb_performance = not history
        preseason_teams = preseason_team_lookup.get((player_id, season), ())
        preseason_team_id = preseason_teams[0] if len(preseason_teams) == 1 else None
        actual_epa = row.get("epa_per_dropback")
        if not _finite(actual_epa) or int(row["dropbacks"]) <= 0:
            raise PipelineError(
                f"non-finite actual EPA/dropback for {season}-{player_id}-{row['team_id']}"
            )
        source_max = max((int(item["season"]) for item in history), default=None)
        prior_missing = prior is None
        prior_cpoe = None if prior is None else prior["cpoe"]
        age = _age_on_season_start(player.get("birth_date"), season)
        record = {
            "feature_version": FEATURE_VERSION,
            "as_of_season": season - 1,
            "feature_source_max_season": source_max,
            "season_scope": "warmup" if season in WARMUP_SEASONS else "analysis",
            "season": season,
            "player_id": player_id,
            "quarterback_name": str(player.get("display_name") or player_id),
            "team_id": str(row["team_id"]),
            "actual_epa_per_dropback": float(actual_epa),
            "dropbacks": int(row["dropbacks"]),
            "starts": int(row.get("starts") or 0),
            "age": age,
            "nfl_experience": nfl_experience,
            "is_rookie": is_rookie,
            "prior_qb_seasons": prior_qb_seasons,
            "no_prior_qb_performance": no_prior_qb_performance,
            "experience_group": (
                "rookie"
                if is_rookie is True
                else "one_prior_nfl_season"
                if nfl_experience == 1
                else "veteran"
                if nfl_experience is not None and nfl_experience >= 2
                else "experience_unknown"
            ),
            "performance_history_group": (
                "no_prior_qb_performance"
                if no_prior_qb_performance
                else "one_prior_qb_season"
                if prior_qb_seasons == 1
                else "multiple_prior_qb_seasons"
            ),
            "prior_starts": None if prior is None else prior["starts"],
            "prior_dropbacks": None if prior is None else prior["dropbacks"],
            "prior_epa_per_dropback": None if prior is None else prior["epa_per_dropback"],
            "prior_cpoe": prior_cpoe,
            "prior_success_rate": None if prior is None else prior["success_rate"],
            "prior_sack_rate": None if prior is None else prior["sack_rate"],
            "prior_interception_rate": (None if prior is None else prior["interception_rate"]),
            "prior_touchdown_rate": None if prior is None else prior["touchdown_rate"],
            "career_starts": 0 if career is None else career["starts"],
            "career_dropbacks": 0 if career is None else career["dropbacks"],
            "career_epa_per_dropback": None if career is None else career["epa_per_dropback"],
            "career_cpoe": None if career is None else career["cpoe"],
            "career_success_rate": None if career is None else career["success_rate"],
            "career_sack_rate": None if career is None else career["sack_rate"],
            "career_interception_rate": (None if career is None else career["interception_rate"]),
            "career_touchdown_rate": None if career is None else career["touchdown_rate"],
            "preseason_team_id": preseason_team_id,
            "preseason_team_status": (
                "available"
                if preseason_team_id is not None
                else "unavailable_ambiguous"
                if len(preseason_teams) > 1
                else "unavailable_no_week_1_snapshot"
            ),
            "changed_team": (
                None
                if prior is None or preseason_team_id is None
                else preseason_team_id not in prior["teams"]
            ),
            "changed_team_missing": prior is None or preseason_team_id is None,
            "prior_injury_report_weeks": None if injury_value is None else injury_value[0],
            "prior_injury_out_weeks": None if injury_value is None else injury_value[1],
            "draft_position": None,
            "draft_round": None,
            "college_production": None,
            "age_missing": age is None,
            "nfl_experience_missing": nfl_experience is None,
            "rookie_status_missing": is_rookie is None,
            "prior_season_missing": prior_missing,
            "prior_cpoe_missing": prior_cpoe is None,
            "prior_injury_missing": injury_value is None,
            "draft_position_missing": True,
            "draft_round_missing": True,
            "college_production_missing": True,
        }
        record["missing_feature_count"] = sum(
            bool(record[column])
            for column in (
                "age_missing",
                "nfl_experience_missing",
                "rookie_status_missing",
                "prior_season_missing",
                "changed_team_missing",
                "prior_cpoe_missing",
                "prior_injury_missing",
                "draft_position_missing",
                "draft_round_missing",
                "college_production_missing",
            )
        )
        records.append(record)
        by_player[player_id].append(row)
    features = pl.DataFrame(records, infer_schema_length=None).sort(
        "season", "player_id", "team_id"
    )
    validate_feature_frame(features)
    return features


def _model_matrix(frame: pl.DataFrame) -> np.ndarray:
    return np.asarray(
        [
            [
                np.nan
                if row[column] is None
                else float(row[column])
                if not isinstance(row[column], bool)
                else float(row[column])
                for column in MODEL_FEATURE_COLUMNS
            ]
            for row in frame.select(MODEL_FEATURE_COLUMNS).iter_rows(named=True)
        ],
        dtype=float,
    )


def _ridge(alpha: float) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )


def _training_weights(frame: pl.DataFrame) -> np.ndarray:
    return (
        np.clip(
            np.asarray(frame["dropbacks"], dtype=float),
            TRAINING_WEIGHT_MINIMUM,
            TRAINING_WEIGHT_MAXIMUM,
        )
        / TRAINING_WEIGHT_SCALE
    )


def _tune_ridge_alpha(training: pl.DataFrame) -> float:
    seasons = sorted(set(int(value) for value in training["season"]))
    validation_seasons = seasons[5:]
    scores: dict[float, list[float]] = {alpha: [] for alpha in RIDGE_ALPHAS}
    for season in validation_seasons:
        inner_train = training.filter(pl.col("season") < season)
        validation = training.filter(
            (pl.col("season") == season) & (pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
        )
        if inner_train.height < 20 or validation.is_empty():
            continue
        x_train = _model_matrix(inner_train)
        y_train = np.asarray(inner_train["actual_epa_per_dropback"], dtype=float)
        x_validation = _model_matrix(validation)
        y_validation = np.asarray(validation["actual_epa_per_dropback"], dtype=float)
        for alpha in RIDGE_ALPHAS:
            model = _ridge(alpha)
            model.fit(x_train, y_train, ridge__sample_weight=_training_weights(inner_train))
            scores[alpha].append(float(np.mean(np.abs(y_validation - model.predict(x_validation)))))
    candidates = [(float(np.mean(values)), alpha) for alpha, values in scores.items() if values]
    return min(candidates)[1] if candidates else 10.0


def _metrics(rows: list[dict[str, object]]) -> dict[str, float | int | None]:
    if not rows:
        return {
            "rows": 0,
            "mae": None,
            "rmse": None,
            "r_squared": None,
            "correlation": None,
            "calibration_intercept": None,
            "calibration_slope": None,
            "prediction_interval_coverage": None,
        }
    actual = np.asarray([float(row["actual_epa_per_dropback"]) for row in rows], dtype=float)
    predicted = np.asarray([float(row["expected_epa_per_dropback"]) for row in rows], dtype=float)
    residual = actual - predicted
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(np.square(residual))))
    centered = actual - actual.mean()
    total = float(np.sum(np.square(centered)))
    r_squared = None if total <= 1e-15 else float(1.0 - np.sum(np.square(residual)) / total)
    pred_variance = float(np.var(predicted))
    if pred_variance <= 1e-15:
        slope = 0.0
        intercept = float(actual.mean())
        correlation = None
    else:
        slope = float(np.cov(predicted, actual, ddof=0)[0, 1] / pred_variance)
        intercept = float(actual.mean() - slope * predicted.mean())
        correlation = float(np.corrcoef(predicted, actual)[0, 1])
    coverage = float(
        np.mean(
            [
                float(row["prediction_interval_low"])
                <= float(row["actual_epa_per_dropback"])
                <= float(row["prediction_interval_high"])
                for row in rows
            ]
        )
    )
    return {
        "rows": len(rows),
        "mae": mae,
        "rmse": rmse,
        "r_squared": r_squared,
        "correlation": correlation,
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "prediction_interval_coverage": coverage,
    }


def _prediction_sigma(residual_history: list[float], training: pl.DataFrame) -> float:
    if len(residual_history) >= INTERVAL_FALLBACK_RESIDUALS:
        return max(
            MINIMUM_PREDICTION_SIGMA,
            float(np.sqrt(np.mean(np.square(residual_history)))),
        )
    values = np.asarray(training["actual_epa_per_dropback"], dtype=float)
    return max(MINIMUM_PREDICTION_SIGMA, float(np.std(values)))


def _league_average(training: pl.DataFrame) -> float:
    weights = np.asarray(training["dropbacks"], dtype=float)
    actual = np.asarray(training["actual_epa_per_dropback"], dtype=float)
    return float(np.average(actual, weights=weights))


def _baseline_prediction(row: dict[str, object], league: float, kind: str) -> float:
    if kind == "league_average":
        return league
    if kind == "recent_performance":
        value = row["prior_epa_per_dropback"]
        history = float(row["prior_dropbacks"] or 0)
        shrinkage = RECENT_SHRINKAGE_DROPBACKS
    elif kind == "career_performance":
        value = row["career_epa_per_dropback"]
        history = float(row["career_dropbacks"] or 0)
        shrinkage = CAREER_SHRINKAGE_DROPBACKS
    else:  # pragma: no cover - protected by callers
        raise AssertionError(kind)
    if value is None or history <= 0:
        return league
    weight = history / (history + shrinkage)
    return float(weight * float(value) + (1.0 - weight) * league)


def _selection_score(metrics: dict[str, object]) -> float:
    return (
        float(metrics["mae"])
        + SELECTION_INTERCEPT_WEIGHT * abs(float(metrics["calibration_intercept"]))
        + SELECTION_SLOPE_WEIGHT * abs(float(metrics["calibration_slope"]) - 1.0)
    )


def validate_model_outputs(
    features: pl.DataFrame, predictions: pl.DataFrame, pae: pl.DataFrame
) -> None:
    analysis = features.filter(pl.col("season").is_in(ANALYSIS_SEASONS))
    if predictions.select("model_name", "player_id", "team_id", "season").n_unique() != (
        predictions.height
    ):
        raise PipelineError("duplicate model prediction outputs")
    if predictions.height != analysis.height * len(MODEL_NAMES):
        raise PipelineError("model prediction output cardinality does not reconcile")
    if pae.select("player_id", "team_id", "season").n_unique() != pae.height:
        raise PipelineError("duplicate selected PAE outputs")
    if pae.height != analysis.height:
        raise PipelineError("selected PAE output does not reconcile to analysis QB seasons")
    if pae.filter(pl.col("season").is_in(WARMUP_SEASONS)).height:
        raise PipelineError("warm-up seasons appeared in published PAE output")
    for column in (
        "actual_epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
    ):
        if pae.filter(~pl.col(column).is_finite()).height:
            raise PipelineError(f"non-finite selected PAE output: {column}")
    arithmetic_errors = pae.filter(
        (
            pl.col("actual_epa_per_dropback")
            - pl.col("expected_epa_per_dropback")
            - pl.col("performance_above_expectation")
        ).abs()
        > 1e-12
    )
    if arithmetic_errors.height:
        raise PipelineError("PAE arithmetic does not reconcile")
    expected = analysis.select("player_id", "team_id", "season", "dropbacks").rename(
        {"dropbacks": "source_dropbacks"}
    )
    mismatch = pae.join(expected, on=["player_id", "team_id", "season"], validate="1:1").filter(
        pl.col("dropbacks") != pl.col("source_dropbacks")
    )
    if mismatch.height:
        raise PipelineError("PAE dropbacks do not reconcile to QB-team-season input")


def build_expected_performance_tables(features: pl.DataFrame) -> ExpectedPerformanceTables:
    """Fit expanding-window candidates and return deterministic out-of-sample outputs."""

    validate_feature_frame(features)
    predictions: list[dict[str, object]] = []
    residual_history: dict[str, list[float]] = {name: [] for name in MODEL_NAMES}
    alpha_by_season: dict[str, float] = {}
    for season in ANALYSIS_SEASONS:
        training = features.filter(
            (pl.col("season") < season) & (pl.col("dropbacks") >= TRAINING_MIN_DROPBACKS)
        )
        target = features.filter(pl.col("season") == season)
        if training.height < 20 or target.is_empty():
            raise PipelineError(f"insufficient expanding-window data for season {season}")
        league = _league_average(training)
        alpha = _tune_ridge_alpha(training)
        alpha_by_season[str(season)] = alpha
        ridge = _ridge(alpha)
        ridge.fit(
            _model_matrix(training),
            np.asarray(training["actual_epa_per_dropback"], dtype=float),
            ridge__sample_weight=_training_weights(training),
        )
        ridge_values = ridge.predict(_model_matrix(target))
        target_rows = target.to_dicts()
        for model_name in MODEL_NAMES:
            sigma = _prediction_sigma(residual_history[model_name], training)
            if model_name == "ridge":
                expected_values = [float(value) for value in ridge_values]
            else:
                expected_values = [
                    _baseline_prediction(row, league, model_name) for row in target_rows
                ]
            current_residuals: list[float] = []
            for row, expected in zip(target_rows, expected_values, strict=True):
                actual = float(row["actual_epa_per_dropback"])
                record = dict(row)
                record.update(
                    {
                        "model_name": model_name,
                        "training_start_season": int(training["season"].min()),
                        "training_end_season": season - 1,
                        "expected_epa_per_dropback": expected,
                        "performance_above_expectation": actual - expected,
                        "prediction_std_error": sigma,
                        "prediction_interval_low": expected - INTERVAL_MULTIPLIER * sigma,
                        "prediction_interval_high": expected + INTERVAL_MULTIPLIER * sigma,
                        "is_out_of_sample": True,
                        "ridge_alpha": alpha if model_name == "ridge" else None,
                    }
                )
                predictions.append(record)
                if int(row["dropbacks"]) >= ELIGIBILITY_DROPBACKS:
                    current_residuals.append(actual - expected)
            residual_history[model_name].extend(current_residuals)

    prediction_frame = pl.DataFrame(predictions, infer_schema_length=None).sort(
        "model_name", "season", "player_id", "team_id"
    )
    evaluation_records = []
    evaluation_by_model: dict[str, dict[str, object]] = {}
    for model_name in MODEL_NAMES:
        eligible_rows = prediction_frame.filter(
            (pl.col("model_name") == model_name) & (pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
        ).to_dicts()
        metrics = _metrics(eligible_rows)
        metrics["selection_score"] = _selection_score(metrics)
        evaluation_by_model[model_name] = metrics
        evaluation_records.append(
            {
                "evaluation_scope": "overall_eligible",
                "model_name": model_name,
                "evaluation_start_season": min(ANALYSIS_SEASONS),
                "evaluation_end_season": max(ANALYSIS_SEASONS),
                **metrics,
            }
        )
    selected_model = min(
        MODEL_NAMES,
        key=lambda name: (float(evaluation_by_model[name]["selection_score"]), name),
    )
    selected = prediction_frame.filter(pl.col("model_name") == selected_model).with_columns(
        pl.when(pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
        .then(pl.lit("eligible"))
        .otherwise(pl.lit("below_200_dropbacks"))
        .alias("eligibility_status"),
        pl.when(
            (pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
            & (pl.col("career_dropbacks") >= RELIABILITY_CAREER_DROPBACKS)
        )
        .then(pl.lit("high"))
        .when(pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
        .then(pl.lit("medium"))
        .otherwise(pl.lit("low"))
        .alias("reliability"),
    )

    sensitivity_records = []
    for threshold in SENSITIVITY_THRESHOLDS:
        rows = selected.filter(pl.col("dropbacks") >= threshold).to_dicts()
        sensitivity_records.append({"minimum_dropbacks": threshold, **_metrics(rows)})
    experience_records = []
    for group in ("rookie", "one_prior_nfl_season", "veteran", "experience_unknown"):
        rows = selected.filter(
            (pl.col("experience_group") == group) & (pl.col("dropbacks") >= ELIGIBILITY_DROPBACKS)
        ).to_dicts()
        if rows:
            experience_records.append({"experience_group": group, **_metrics(rows)})

    metadata = {
        "feature_version": FEATURE_VERSION,
        "pipeline_version": MODEL_PIPELINE_VERSION,
        "selected_model": selected_model,
        "selection_rule": (
            "minimum OOS MAE plus calibration-intercept and calibration-slope penalties"
        ),
        "ridge_alpha_by_prediction_season": alpha_by_season,
        "training_minimum_dropbacks": TRAINING_MIN_DROPBACKS,
        "eligibility_dropbacks": ELIGIBILITY_DROPBACKS,
        "model_specification": _model_specification(),
        "college_data_available": False,
        "college_data_note": (
            "Only a profile college-name field exists; no validated college production data "
            "is fitted."
        ),
        "model_features": list(MODEL_FEATURE_COLUMNS),
        "candidate_models": list(MODEL_NAMES),
        "model_results": evaluation_records,
        "threshold_sensitivity": sensitivity_records,
        "experience_results": experience_records,
    }
    tables = ExpectedPerformanceTables(
        features=features,
        predictions=prediction_frame,
        pae=selected.sort("season", "player_id", "team_id"),
        evaluation=pl.DataFrame(evaluation_records).sort("selection_score", "model_name"),
        sensitivity=pl.DataFrame(sensitivity_records).sort("minimum_dropbacks"),
        experience_evaluation=pl.DataFrame(experience_records).sort("experience_group"),
        metadata=metadata,
    )
    validate_model_outputs(tables.features, tables.predictions, tables.pae)
    return tables


def _read_injuries(historical_version: Path) -> pl.DataFrame | None:
    paths = sorted((historical_version / "silver" / "injuries").glob("season=*/data.parquet"))
    frames = []
    required = ["canonical_player_id", "source_season", "week", "report_status"]
    for path in paths:
        frame = pl.read_parquet(path)
        if set(required) <= set(frame.columns):
            frames.append(frame.select(required))
    return pl.concat(frames, how="vertical_relaxed") if frames else None


def _read_roster_profiles(historical_version: Path) -> pl.DataFrame | None:
    paths = sorted((historical_version / "bronze" / "rosters").glob("season=*/roster.parquet"))
    frames = []
    required = ["gsis_id", "years_exp", "entry_year", "rookie_year"]
    for path in paths:
        frame = pl.read_parquet(path)
        if set(required) <= set(frame.columns):
            season = int(path.parent.name.split("=", maxsplit=1)[1])
            frames.append(
                frame.select(required).with_columns(pl.lit(season).alias("source_season"))
            )
    return pl.concat(frames, how="vertical_relaxed") if frames else None


def _read_preseason_depth_charts(historical_version: Path) -> pl.DataFrame | None:
    paths = sorted((historical_version / "silver" / "depth_charts").glob("season=*/data.parquet"))
    frames = []
    required = [
        "canonical_player_id",
        "canonical_team_id",
        "source_season",
        "week",
        "game_type",
    ]
    for path in paths:
        schema = pl.read_parquet_schema(path)
        if set(required) <= set(schema):
            frames.append(pl.read_parquet(path, columns=required))
    return pl.concat(frames, how="vertical_relaxed") if frames else None


def _model_specification() -> dict[str, object]:
    source_files = [
        Path(__file__),
        Path(__file__).with_name("constants.py"),
        Path(__file__).with_name("pipeline.py"),
    ]
    return {
        "feature_version": FEATURE_VERSION,
        "pipeline_version": MODEL_PIPELINE_VERSION,
        "models": list(MODEL_NAMES),
        "ridge_alphas": list(RIDGE_ALPHAS),
        "training_minimum_dropbacks": TRAINING_MIN_DROPBACKS,
        "eligibility_dropbacks": ELIGIBILITY_DROPBACKS,
        "recent_shrinkage_dropbacks": RECENT_SHRINKAGE_DROPBACKS,
        "career_shrinkage_dropbacks": CAREER_SHRINKAGE_DROPBACKS,
        "selection_intercept_weight": SELECTION_INTERCEPT_WEIGHT,
        "selection_slope_weight": SELECTION_SLOPE_WEIGHT,
        "interval_multiplier": INTERVAL_MULTIPLIER,
        "interval_fallback_residuals": INTERVAL_FALLBACK_RESIDUALS,
        "reliability_career_dropbacks": RELIABILITY_CAREER_DROPBACKS,
        "minimum_prediction_sigma": MINIMUM_PREDICTION_SIGMA,
        "sensitivity_thresholds": list(SENSITIVITY_THRESHOLDS),
        "training_weight_minimum": TRAINING_WEIGHT_MINIMUM,
        "training_weight_maximum": TRAINING_WEIGHT_MAXIMUM,
        "training_weight_scale": TRAINING_WEIGHT_SCALE,
        "model_features": list(MODEL_FEATURE_COLUMNS),
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_sha256": {path.name: sha256_file(path) for path in source_files},
    }


def _historical_version_path(root: Path) -> tuple[str, Path]:
    latest = root / "LATEST"
    if not latest.is_file():
        raise PipelineError(f"historical LATEST pointer is missing: {latest}")
    data_version = latest.read_text(encoding="utf-8").strip()
    path = root / data_version
    if not path.is_dir():
        raise PipelineError(f"historical version directory is missing: {path}")
    return data_version, path


def _model_version(source_data_version: str, source_path: Path) -> tuple[str, str]:
    source_paths = [
        source_path / "silver" / "qb_team_season_performance.parquet",
        source_path / "silver" / "players.parquet",
        *sorted((source_path / "silver" / "injuries").glob("season=*/data.parquet")),
        *sorted((source_path / "silver" / "depth_charts").glob("season=*/data.parquet")),
        *sorted((source_path / "bronze" / "rosters").glob("season=*/roster.parquet")),
    ]
    identity = {
        "source_data_version": source_data_version,
        "source_inputs": {
            path.relative_to(source_path).as_posix(): sha256_file(path) for path in source_paths
        },
        "model_specification": _model_specification(),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return f"c5-{digest}", f"expected-performance-{digest}"


def _write_execution_log(
    output_root: Path,
    *,
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


def run_expected_performance_pipeline(
    config: ExpectedPerformanceConfig,
) -> ExpectedPerformanceResult:
    """Build and atomically publish deterministic checkpoint-five analytical outputs."""

    started_at = datetime.now(UTC)
    source_data_version, historical_path = _historical_version_path(config.resolved_historical_dir)
    data_version, model_version = _model_version(source_data_version, historical_path)
    output_root = config.resolved_output_dir
    final_path = output_root / data_version
    if final_path.exists():
        counts = _validate_existing_version(final_path, data_version)
        manifest = json.loads((final_path / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
        _update_latest(output_root, data_version)
        _write_execution_log(
            output_root,
            data_version=data_version,
            model_version=model_version,
            started_at=started_at,
            reused_existing=True,
        )
        return ExpectedPerformanceResult(
            data_version,
            model_version,
            str(manifest["selected_model"]),
            final_path,
            True,
            counts,
        )

    staging = output_root / ".staging" / uuid.uuid4().hex
    try:
        staging.mkdir(parents=True, exist_ok=False)
        qb_seasons = pl.read_parquet(
            historical_path / "silver" / "qb_team_season_performance.parquet"
        )
        players = pl.read_parquet(historical_path / "silver" / "players.parquet")
        features = build_preseason_features(
            qb_seasons,
            players,
            _read_injuries(historical_path),
            _read_roster_profiles(historical_path),
            _read_preseason_depth_charts(historical_path),
        )
        tables = build_expected_performance_tables(features)
        lineage = [
            pl.lit(data_version).alias("data_version"),
            pl.lit(model_version).alias("model_version"),
        ]
        output_tables = {
            "preseason_features": tables.features,
            "model_predictions": tables.predictions,
            "qb_pae": tables.pae,
            "model_evaluation": tables.evaluation,
            "threshold_sensitivity": tables.sensitivity,
            "experience_evaluation": tables.experience_evaluation,
        }
        for name, frame in output_tables.items():
            frame.with_columns(lineage).select(
                "data_version", "model_version", pl.exclude("data_version", "model_version")
            ).write_parquet(staging / f"{name}.parquet", compression="zstd")
        table_counts = {name: frame.height for name, frame in output_tables.items()}
        manifest = {
            "data_version": data_version,
            "model_version": model_version,
            "source_data_version": source_data_version,
            "pipeline_version": MODEL_PIPELINE_VERSION,
            "feature_version": FEATURE_VERSION,
            "selected_model": tables.metadata["selected_model"],
            "table_counts": table_counts,
            "status": "succeeded",
        }
        _write_json(staging / "MODEL_EVALUATION.json", tables.metadata)
        _write_json(staging / "RUN_MANIFEST.json", manifest)
        _write_json(staging / "OUTPUT_CHECKSUMS.json", _output_checksums(staging))
        output_root.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_path)
        _update_latest(output_root, data_version)
        _write_execution_log(
            output_root,
            data_version=data_version,
            model_version=model_version,
            started_at=started_at,
            reused_existing=False,
        )
        return ExpectedPerformanceResult(
            data_version,
            model_version,
            str(tables.metadata["selected_model"]),
            final_path,
            False,
            table_counts,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

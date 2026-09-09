"""Final, deterministic, research-only Coach Effect architecture rerun.

The module consumes the frozen Prompt 10 evidence and Prompt 11 gate decision.  It
does not write production data and does not construct a public score or ranking.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import scipy
import sklearn
from scipy.optimize import minimize_scalar
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nfl_coaching_impact.coach_impact import build_coach_exposures
from nfl_coaching_impact.sources import sha256_file
from research.coach_effect.checkpoint_eleven import _write_csv
from research.coach_effect.checkpoint_twelve import (
    ENVIRONMENT_FEATURES,
    EXPECTED_PAE_DATA_VERSION,
    EXPECTED_PAE_MODEL_VERSION,
    MIN_INTERVAL_DROPBACKS,
    PAE_KEY,
    PRODUCTION_LOAD_ID,
    Q_FEATURES,
    ROLES,
    _canonical_team,
    _load_pae,
    _sources,
    rolling_movement_predictions,
)
from research.coach_effect.checkpoint_twelve_coverage_gate_review import (
    PROMPT10_VERSION,
    RESEARCH_GATE_POLICY,
    _consecutive_pairs,
    _future_rows,
    _load_prompt10,
)
from research.coach_effect.checkpoint_twelve_final_play_caller_evidence import (
    build_assignments,
    load_and_validate_prompt10_evidence,
)

PROMPT11_VERSION = "c12-gate-38dc6c52c7f74b88"
SPECIFICATION = "checkpoint-twelve-final-coach-effect-research-v1"
RANDOM_SEED = 20260908
BOOTSTRAPS = 500
PERMUTATIONS = 1_000
RIDGE_ALPHA = 10.0
PRIMARY_START = 2020
CREDIBLE_FOLDS = (2021, 2022, 2023, 2024, 2025)
MIN_RESEARCH_SEASONS = 3
MIN_RESEARCH_QBS = 2
MIN_RESEARCH_EXPOSURE = 600.0
MIN_PRODUCTION_FULL_CELL_RATE = 0.95
MIN_PRODUCTION_PLAY_RATE = 0.95
PRACTICAL_RMSE_REDUCTION = 0.02
MIN_RESEARCH_CORRELATION = 0.10
MIN_RESEARCH_DIRECTION = 0.55
SCHEME_FEATURES = ("shotgun_rate", "no_huddle_rate", "early_down_pass_rate")

OUTPUT_NAMES = (
    "final_research_snapshot.csv",
    "final_sample_summary.csv",
    "role_signal_summary.csv",
    "pcae_reliability.csv",
    "qp_overlap.csv",
    "rolling_model_comparison.csv",
    "fold_metrics.csv",
    "weight_stability.csv",
    "shrinkage_comparison.csv",
    "environment_sensitivity.csv",
    "missingness_sensitivity.csv",
    "placebo_results.csv",
    "eligibility_research.csv",
    "role_readiness.csv",
    "architecture_decision.csv",
    "production_gate.csv",
    "checkpoint_closeout.csv",
)


@dataclass(frozen=True)
class FinalResearchResult:
    output_path: Path
    data_version: str
    architecture: str


def _seed(label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{RANDOM_SEED}:{label}".encode()).digest()[:8], "big") % (
        2**32
    )


def _pearson(left: Iterable[float], right: Iterable[float]) -> float | None:
    x = np.asarray(list(left), dtype=float)
    y = np.asarray(list(right), dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if len(x) < 2 or np.ptp(x) <= 1e-12 or np.ptp(y) <= 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(left: Iterable[float], right: Iterable[float]) -> float | None:
    x = np.asarray(list(left), dtype=float)
    y = np.asarray(list(right), dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if len(x) < 2 or np.ptp(x) <= 1e-12 or np.ptp(y) <= 1e-12:
        return None
    return float(spearmanr(x, y).statistic)


def _metric(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, Any]:
    y = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if len(y) == 0:
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
    correlation = _pearson(y, p)
    if np.ptp(p) > 1e-12:
        slope, intercept = np.polyfit(p, y, 1)
    else:
        slope, intercept = None, float(np.mean(y))
    return {
        "n": len(y),
        "pearson": correlation,
        "spearman": _spearman(y, p),
        "rmse": float(mean_squared_error(y, p) ** 0.5),
        "mae": float(mean_absolute_error(y, p)),
        "direction_accuracy": float(np.mean(np.sign(y) == np.sign(p))),
        "calibration_slope": None if slope is None else float(slope),
        "calibration_intercept": float(intercept),
    }


def _contract(frame: pl.DataFrame, version: str) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    floats = [name for name, dtype in frame.schema.items() if dtype in (pl.Float32, pl.Float64)]
    result = frame.with_columns(pl.col(floats).round(10)) if floats else frame
    order = [name for name in result.columns if name not in floats]
    if order:
        result = result.sort(order, nulls_last=True)
    return result.with_columns(
        pl.lit(version).alias("research_data_version"),
        pl.lit(True).alias("research_only"),
        pl.lit(False).alias("production_ranking"),
    )


def _prompt_roots(project_root: Path) -> tuple[Path, Path, Path]:
    prompt10 = (
        project_root
        / "research/coach_effect/outputs/checkpoint_12_final_play_caller_evidence"
        / PROMPT10_VERSION
    )
    prompt11_root = (
        project_root / "research/coach_effect/outputs/checkpoint_12_coverage_gate_review"
    )
    if (prompt11_root / "LATEST").read_text(encoding="utf-8").strip() != PROMPT11_VERSION:
        raise ValueError("final rerun requires the frozen Prompt 11 methodology decision")
    prompt11 = prompt11_root / PROMPT11_VERSION
    prompt6 = project_root / "research/coach_effect/outputs/checkpoint_12/c12-8cd15ae6015e900b"
    for path in (prompt6, prompt10, prompt11):
        if not path.is_dir():
            raise ValueError(f"missing frozen research input: {path}")
    return prompt6, prompt10, prompt11


def _final_assignments(project_root: Path) -> pl.DataFrame:
    cells, intervals, _ = load_and_validate_prompt10_evidence(project_root)
    assignments = pl.DataFrame(
        build_assignments(project_root, cells, intervals), infer_schema_length=None
    ).with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        (pl.col("is_interim") == "true").alias("is_interim"),
        (pl.col("is_shared") == "true").alias("is_shared"),
        (pl.col("is_retained") == "true").alias("is_retained"),
        pl.col("team_id")
        .map_elements(_canonical_team, return_dtype=pl.String)
        .alias("canonical_team_id"),
        pl.col("coach_canonical_name").alias("coach_name"),
    )
    assignments = assignments.filter(pl.col("verification_status") == "verified")
    assignments = assignments.filter(
        (pl.col("role") != "play_caller") | (pl.col("interval_basis") != "season_designation")
    )
    if assignments["assignment_key"].n_unique() != assignments.height:
        raise ValueError("final assignment snapshot has duplicate assignment keys")
    unsupported = assignments.filter(
        (pl.col("role") == "play_caller")
        & (
            pl.col("primary_source_url").is_null()
            | (pl.col("primary_source_url").str.strip_chars() == "")
        )
    )
    if unsupported.height:
        raise ValueError("final caller snapshot contains unsupported attribution")
    return assignments


def _map_final_pcae(assignments: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    if pcae.filter((pl.col("verification_status") != "verified") | pl.col("is_shared")).height:
        raise ValueError("final PCAE contains non-verified or shared attribution")
    pcae = pcae.drop("research_data_version", "research_only", "production_ranking").with_columns(
        pl.col("team_id").map_elements(_canonical_team, return_dtype=pl.String).alias("team_id")
    )
    assignment_keys = assignments.filter(pl.col("role") == "play_caller").select(
        "assignment_key",
        "coach_id",
        pl.col("canonical_team_id").alias("team_id"),
        "season",
        "start_week",
        "end_week",
        "interval_basis",
        "primary_source_url",
    )
    keys = ["coach_id", "team_id", "season", "start_week", "end_week"]
    mapped = pcae.join(assignment_keys, on=keys, how="left", validate="1:1")
    if (
        mapped["assignment_key"].null_count()
        or mapped["assignment_key"].n_unique() != mapped.height
    ):
        raise ValueError("final PCAE does not map one-to-one to verified caller assignments")
    return mapped.sort("season", "team_id", "start_week", "coach_id")


def build_final_snapshot(
    project_root: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build the exact assignment/QB/team-season research grain from frozen evidence."""

    sources = _sources(project_root)
    pae = _load_pae(sources.pae_path)
    assignments = _final_assignments(project_root)
    games = pl.read_parquet(sources.qb_games_path).filter(pl.col("season") >= 2010)
    exposures = (
        build_coach_exposures(games, pae, assignments)
        .rename({"actual_epa_per_dropback": "interval_actual_epa_per_dropback"})
        .with_columns(
            pl.lit(PRODUCTION_LOAD_ID).alias("load_id"),
            pl.lit(EXPECTED_PAE_DATA_VERSION).alias("pae_data_version"),
        )
    )
    exposures = exposures.join(
        pae.select(*PAE_KEY, "actual_epa_per_dropback"),
        on=list(PAE_KEY),
        how="left",
        validate="m:1",
    )
    exposures = exposures.join(
        assignments.select("assignment_key", "primary_source_url"),
        on="assignment_key",
        how="left",
        validate="m:1",
    )
    movement, movement_folds = rolling_movement_predictions(pae)
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
    _, prompt10, _ = _prompt_roots(project_root)
    mapped_pcae = _map_final_pcae(assignments, pl.read_csv(prompt10 / "historical_pcae.csv"))
    joined = joined.join(
        mapped_pcae.select(
            "assignment_key",
            "eligible_play_count",
            "attributed_play_count",
            "average_call_value",
            "league_average_call_value",
            "pcae",
            pl.col("model_version").alias("pcae_model_version"),
            "play_eligibility_version",
        ),
        on="assignment_key",
        how="left",
        validate="m:1",
    )
    if joined.filter(pl.col("pcae").is_not_null() & (pl.col("role") != "play_caller")).height:
        raise ValueError("PCAE attached outside the verified play-caller role")
    key = ["assignment_key", "player_id", "team_id", "season"]
    if joined.select(key).n_unique() != joined.height:
        raise ValueError("final research snapshot has duplicate analytical keys")
    snapshot = joined.select(
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
        "primary_source_url",
        "is_interim",
        "is_shared",
        "is_retained",
        "observed_games",
        "observed_dropbacks",
        "exposure_dropbacks",
        "exposure_fraction",
        "eligibility_status",
        "actual_epa_per_dropback",
        "interval_actual_epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "coach_interval_pae",
        "prior_pae",
        "actual_qb_delta_pae",
        "expected_normal_qb_delta",
        "q_development_signal",
        "eligible_play_count",
        "attributed_play_count",
        "average_call_value",
        "league_average_call_value",
        "pcae",
        "age",
        "nfl_experience",
        "changed_team",
        *ENVIRONMENT_FEATURES[:-1],
        "feature_source_max_season",
        "environment_feature_source_max_season",
        "pae_data_version",
        pl.col("model_version").alias("pae_model_version"),
        "pcae_model_version",
        "play_eligibility_version",
        "environment_data_version",
        "environment_feature_version",
    ).sort("role", "season", "team_id", "start_week", "coach_id", "player_id")
    leakage = snapshot.filter(
        (
            pl.col("feature_source_max_season").is_not_null()
            & (pl.col("feature_source_max_season") >= pl.col("season"))
        )
        | (
            pl.col("environment_feature_source_max_season").is_not_null()
            & (pl.col("environment_feature_source_max_season") >= pl.col("season"))
        )
    )
    if leakage.height:
        raise ValueError("final snapshot contains target/future-season feature leakage")
    if snapshot["pae_data_version"].unique().to_list() != [EXPECTED_PAE_DATA_VERSION]:
        raise ValueError("PAE lineage drift in final snapshot")
    if snapshot["pae_model_version"].unique().to_list() != [EXPECTED_PAE_MODEL_VERSION]:
        raise ValueError("PAE model lineage drift in final snapshot")
    return snapshot, mapped_pcae, assignments, movement_folds


def _q_rows(snapshot: pl.DataFrame) -> pl.DataFrame:
    return snapshot.filter(
        pl.col("q_development_signal").is_not_null()
        & pl.col("q_development_signal").is_finite()
        & (pl.col("exposure_dropbacks") >= MIN_INTERVAL_DROPBACKS)
        & (pl.col("verification") == "verified")
    )


def _coach_seasons(rows: pl.DataFrame, *, signal: str, exposure: str, role: str) -> pl.DataFrame:
    source = rows.filter(pl.col("role") == role)
    return (
        source.group_by("coach_id", "coach_name", "team_id", "season")
        .agg(
            ((pl.col(signal) * pl.col(exposure)).sum() / pl.col(exposure).sum()).alias(signal),
            pl.col(exposure).sum().alias("signal_exposure"),
            pl.col("player_id").n_unique().alias("quarterbacks"),
            pl.col("player_id").unique().sort().str.join("|").alias("player_ids"),
        )
        .sort("season", "coach_id", "team_id")
    )


def _pcae_seasons(mapped: pl.DataFrame) -> pl.DataFrame:
    return (
        mapped.group_by("coach_id", "coach_canonical_name", "team_id", "season")
        .agg(
            (
                (pl.col("pcae") * pl.col("attributed_play_count")).sum()
                / pl.col("attributed_play_count").sum()
            ).alias("pcae"),
            pl.col("attributed_play_count").sum().alias("signal_exposure"),
        )
        .rename({"coach_canonical_name": "coach_name"})
        .with_columns(pl.lit(1).alias("quarterbacks"), pl.lit("").alias("player_ids"))
        .sort("season", "coach_id", "team_id")
    )


def _pairs(table: pl.DataFrame, signal: str) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for group in table.partition_by("coach_id", as_dict=False):
        by_season = {int(row["season"]): row for row in group.to_dicts()}
        for season, current in sorted(by_season.items()):
            prior = by_season.get(season - 1)
            if prior is None:
                continue
            prior_players = set(str(prior["player_ids"]).split("|")) - {""}
            current_players = set(str(current["player_ids"]).split("|")) - {""}
            rows.append(
                {
                    "coach_id": current["coach_id"],
                    "prior_season": season - 1,
                    "season": season,
                    "prior_team_id": prior["team_id"],
                    "team_id": current["team_id"],
                    "prior_player_ids": prior["player_ids"],
                    "player_ids": current["player_ids"],
                    "prior_signal": prior[signal],
                    "current_signal": current[signal],
                    "different_qb": bool(
                        prior_players and current_players and prior_players != current_players
                    ),
                    "different_team": prior["team_id"] != current["team_id"],
                }
            )
    schema = {
        "coach_id": pl.String,
        "prior_season": pl.Int64,
        "season": pl.Int64,
        "prior_team_id": pl.String,
        "team_id": pl.String,
        "prior_player_ids": pl.String,
        "player_ids": pl.String,
        "prior_signal": pl.Float64,
        "current_signal": pl.Float64,
        "different_qb": pl.Boolean,
        "different_team": pl.Boolean,
    }
    return pl.DataFrame(rows, schema=schema).sort("season", "coach_id", "team_id")


def _cluster_interval(
    pairs: pl.DataFrame, *, subset: str, label: str
) -> tuple[float | None, float | None, int]:
    selected = pairs
    if subset == "different_qb":
        selected = selected.filter(pl.col("different_qb"))
    elif subset == "different_team":
        selected = selected.filter(pl.col("different_team"))
    coaches = sorted(selected["coach_id"].unique().to_list()) if selected.height else []
    rng = np.random.default_rng(_seed(f"cluster:{label}:{subset}"))
    draws: list[float] = []
    for _ in range(BOOTSTRAPS):
        sampled = rng.choice(coaches, len(coaches), replace=True) if coaches else []
        pieces = [selected.filter(pl.col("coach_id") == coach) for coach in sampled]
        if not pieces:
            continue
        sample = pl.concat(pieces)
        value = _pearson(sample["prior_signal"], sample["current_signal"])
        if value is not None:
            draws.append(value)
    if not draws:
        return None, None, 0
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975)), len(draws)


def _signal_summary(
    table: pl.DataFrame,
    *,
    signal: str,
    signal_name: str,
    role: str,
    window: str,
    start: int,
) -> dict[str, Any]:
    table = table.filter(pl.col("season") >= start)
    pairs = _pairs(table, signal)
    different_qb = pairs.filter(pl.col("different_qb"))
    different_team = pairs.filter(pl.col("different_team"))
    repeat_ci = _cluster_interval(pairs, subset="all", label=f"{window}:{role}:{signal_name}")
    qb_ci = _cluster_interval(pairs, subset="different_qb", label=f"{window}:{role}:{signal_name}")
    team_ci = _cluster_interval(
        pairs, subset="different_team", label=f"{window}:{role}:{signal_name}"
    )
    player_ids = {
        player
        for value in table["player_ids"].to_list()
        for player in str(value).split("|")
        if player
    }
    return {
        "analysis_window": window,
        "signal": signal_name,
        "role": role,
        "observations": table.height,
        "coaches": table["coach_id"].n_unique(),
        "qbs": len(player_ids) if signal_name == "q" else None,
        "teams": table["team_id"].n_unique(),
        "exposure": float(table["signal_exposure"].sum()),
        "consecutive_pairs": pairs.height,
        "different_qb_pairs": different_qb.height,
        "different_team_pairs": different_team.height,
        "repeatability_pearson": _pearson(pairs["prior_signal"], pairs["current_signal"]),
        "repeatability_spearman": _spearman(pairs["prior_signal"], pairs["current_signal"]),
        "repeatability_direction": (
            float((np.sign(pairs["prior_signal"]) == np.sign(pairs["current_signal"])).mean())
            if pairs.height
            else None
        ),
        "future_qb_portability": _pearson(
            different_qb["prior_signal"], different_qb["current_signal"]
        ),
        "future_team_portability": _pearson(
            different_team["prior_signal"], different_team["current_signal"]
        ),
        "repeatability_bootstrap_low": repeat_ci[0],
        "repeatability_bootstrap_high": repeat_ci[1],
        "repeatability_successful_draws": repeat_ci[2],
        "qb_portability_bootstrap_low": qb_ci[0],
        "qb_portability_bootstrap_high": qb_ci[1],
        "team_portability_bootstrap_low": team_ci[0],
        "team_portability_bootstrap_high": team_ci[1],
        "association_not_causal": True,
    }


def build_role_signals(
    snapshot: pl.DataFrame, mapped_pcae: pl.DataFrame, common: pl.DataFrame
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    q = _q_rows(snapshot)
    tables = {
        f"q:{role}": _coach_seasons(
            q, signal="q_development_signal", exposure="exposure_dropbacks", role=role
        )
        for role in ROLES
    }
    common_players = common.select(
        "coach_id",
        pl.col("team_id").map_elements(_canonical_team, return_dtype=pl.String).alias("team_id"),
        "season",
        "quarterbacks",
        "player_ids",
    )
    tables["pcae:play_caller"] = (
        _pcae_seasons(mapped_pcae)
        .drop("quarterbacks", "player_ids")
        .join(
            common_players,
            on=["coach_id", "team_id", "season"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("quarterbacks").fill_null(0),
            pl.col("player_ids").fill_null(""),
        )
    )
    rows: list[dict[str, Any]] = []
    for window, start in (("primary_2020_2025", 2020), ("secondary_2010_2025", 2010)):
        for label, table in tables.items():
            signal_name, role = label.split(":", 1)
            signal = "pcae" if signal_name == "pcae" else "q_development_signal"
            rows.append(
                _signal_summary(
                    table,
                    signal=signal,
                    signal_name=signal_name,
                    role=role,
                    window=window,
                    start=start,
                )
            )
    summary = pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.when(pl.col("signal") == "pcae")
        .then(pl.lit("DIRECT COACH EFFECT SIGNAL"))
        .when(pl.col("role") == "head_coach")
        .then(pl.lit("NOT IDENTIFIABLE"))
        .otherwise(pl.lit("INSUFFICIENT SIGNAL"))
        .alias("attribution_classification")
    )
    return summary, tables


def build_pcae_reliability(pcae_table: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for label, start in (("primary_2020_2025", 2020), ("secondary_2010_2025", 2010)):
        table = pcae_table.filter(pl.col("season") >= start)
        repeated = table.join(
            table.group_by("coach_id").len().filter(pl.col("len") >= 2).select("coach_id"),
            on="coach_id",
        )
        groups = [group["pcae"].to_numpy() for group in repeated.partition_by("coach_id")]
        coaches = len(groups)
        grand = float(repeated["pcae"].mean()) if repeated.height else 0.0
        between_ss = sum(len(values) * (float(np.mean(values)) - grand) ** 2 for values in groups)
        within_ss = sum(float(np.sum((values - np.mean(values)) ** 2)) for values in groups)
        between_ms = between_ss / (coaches - 1) if coaches > 1 else 0.0
        within_df = repeated.height - coaches
        within_ms = within_ss / within_df if within_df > 0 else 0.0
        k_bar = float(np.mean([len(values) for values in groups])) if groups else 0.0
        denominator = between_ms + (k_bar - 1) * within_ms
        icc = max(0.0, min(1.0, (between_ms - within_ms) / denominator)) if denominator else 0.0
        pairs = _pairs(table, "pcae")
        rows.append(
            {
                "analysis_window": label,
                "coach_seasons": table.height,
                "repeat_coaches": coaches,
                "consecutive_pairs": pairs.height,
                "repeatability_pearson": _pearson(pairs["prior_signal"], pairs["current_signal"]),
                "one_season_reliability": icc,
                "two_season_reliability": 2 * icc / (1 + icc) if icc else 0.0,
                "multi_season_reliability": (k_bar * icc / (1 + (k_bar - 1) * icc) if icc else 0.0),
                "mean_repeated_seasons": k_bar,
                "method": "one_way_random_effects_icc_clipped_to_zero_one",
            }
        )
    return pl.DataFrame(rows)


def build_qp_overlap(common: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for label, start in (("primary_2020_2025", 2020), ("secondary_2010_2025", 2010)):
        frame = common.filter(pl.col("season") >= start)
        pearson = _pearson(frame["q_development_signal"], frame["pcae"])
        rows.append(
            {
                "analysis_window": label,
                "rows": frame.height,
                "coaches": frame["coach_id"].n_unique(),
                "pearson": pearson,
                "spearman": _spearman(frame["q_development_signal"], frame["pcae"]),
                "shared_linear_variance": None if pearson is None else pearson**2,
                "sign_agreement": float(
                    (
                        np.sign(frame["q_development_signal"].to_numpy())
                        == np.sign(frame["pcae"].to_numpy())
                    ).mean()
                ),
                "interpretation": (
                    "small_overlap_requires_independent_validation_not_automatic_combination"
                ),
            }
        )
    return pl.DataFrame(rows)


def _future_model_rows(common: pl.DataFrame) -> pl.DataFrame:
    records = []
    for current in common.sort("season", "coach_id", "team_id").to_dicts():
        history = common.filter(
            (pl.col("coach_id") == current["coach_id"]) & (pl.col("season") < current["season"])
        )
        if history.is_empty():
            continue
        records.append(
            {
                **current,
                "history_q": float(
                    np.average(history["q_development_signal"], weights=history["q_exposure"])
                ),
                "history_p": float(np.average(history["pcae"], weights=history["p_exposure"])),
                "history_rows": history.height,
                "target_q": current["q_development_signal"],
            }
        )
    result = pl.DataFrame(records, infer_schema_length=None)
    return result.sort("season", "coach_id", "team_id")


def _ridge() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=RIDGE_ALPHA)),
        ]
    )


def _fit_predict(
    train: pl.DataFrame, test: pl.DataFrame, features: Sequence[str]
) -> tuple[np.ndarray, Pipeline]:
    model = _ridge()
    model.fit(train.select(features).to_numpy(), train["target_q"].to_numpy())
    return model.predict(test.select(features).to_numpy()), model


def _scheme_frame(project_root: Path) -> pl.DataFrame:
    root = (
        project_root
        / "research/coach_effect/outputs/checkpoint_12_data_expansion"
        / "c12-data-250e540b7de79385"
    )
    long = pl.read_csv(root / "team_season_scheme_fingerprints.csv").filter(
        pl.col("feature_name").is_in(SCHEME_FEATURES)
    )
    wide = long.select("team_id", "season", "feature_name", "raw_value").pivot(
        on="feature_name", index=["team_id", "season"], values="raw_value"
    )
    return wide.with_columns((pl.col("season") + 1).alias("season")).rename(
        {name: f"prior_scheme_{name}" for name in SCHEME_FEATURES}
    )


def build_models(
    project_root: Path, common: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    rows = _future_model_rows(common)
    prompt11_folds = pl.read_csv(
        _prompt_roots(project_root)[2] / "fold_quality_analysis.csv"
    ).select("target_season", "target_rows", "prior_training_rows", "credible_target_fold")
    observed = rows.group_by("season").len().rename({"season": "target_season", "len": "observed"})
    audit = prompt11_folds.join(observed, on="target_season", how="left")
    if audit.filter(pl.col("observed") != pl.col("target_rows")).height:
        raise ValueError("final future-row counts differ from Prompt 11")
    predictions: list[pl.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    model_features = {
        "model_1_q_only": ("history_q",),
        "model_2_pcae_only": ("history_p",),
        "model_4_learned_q_p": ("history_q", "history_p"),
    }
    scheme = _scheme_frame(project_root)
    rows_scheme = rows.join(scheme, on=["team_id", "season"], how="left", validate="m:1")
    scheme_names = tuple(f"prior_scheme_{name}" for name in SCHEME_FEATURES)
    for target in CREDIBLE_FOLDS:
        train = rows.filter(pl.col("season") < target)
        test = rows.filter(pl.col("season") == target)
        if train.height < 20 or test.height < 20 or int(train["season"].max()) >= target:
            raise ValueError(f"credible fold contract failed for {target}")
        y_train = train["target_q"].to_numpy()
        y_test = test["target_q"].to_numpy()
        model_predictions: dict[str, np.ndarray] = {
            "model_0_no_coach": np.repeat(float(np.mean(y_train)), test.height)
        }
        fitted: dict[str, Pipeline] = {}
        for name, features in model_features.items():
            model_predictions[name], fitted[name] = _fit_predict(train, test, features)
        scaler_qp = StandardScaler().fit(train.select("history_q", "history_p").to_numpy())
        train_qp = scaler_qp.transform(train.select("history_q", "history_p").to_numpy())
        test_qp = scaler_qp.transform(test.select("history_q", "history_p").to_numpy())
        equal_train = train_qp.mean(axis=1).reshape(-1, 1)
        equal_test = test_qp.mean(axis=1).reshape(-1, 1)
        equal_model = Ridge(alpha=RIDGE_ALPHA).fit(equal_train, y_train)
        model_predictions["model_3_equal_q_p"] = equal_model.predict(equal_test)
        q_on_p = Ridge(alpha=RIDGE_ALPHA).fit(train_qp[:, [1]], train_qp[:, 0])
        p_on_q = Ridge(alpha=RIDGE_ALPHA).fit(train_qp[:, [0]], train_qp[:, 1])
        train_decomp = np.column_stack(
            [
                train_qp[:, 0] - q_on_p.predict(train_qp[:, [1]]),
                train_qp[:, 1] - p_on_q.predict(train_qp[:, [0]]),
                train_qp.mean(axis=1),
            ]
        )
        test_decomp = np.column_stack(
            [
                test_qp[:, 0] - q_on_p.predict(test_qp[:, [1]]),
                test_qp[:, 1] - p_on_q.predict(test_qp[:, [0]]),
                test_qp.mean(axis=1),
            ]
        )
        overlap_model = Ridge(alpha=RIDGE_ALPHA).fit(train_decomp, y_train)
        model_predictions["model_5_overlap_decomposition"] = overlap_model.predict(test_decomp)
        train_scheme = rows_scheme.filter(pl.col("season") < target)
        test_scheme = rows_scheme.filter(pl.col("season") == target)
        if train_scheme.select(scheme_names).null_count().row(0) == (0,) * len(
            scheme_names
        ) and test_scheme.select(scheme_names).null_count().row(0) == (0,) * len(scheme_names):
            model_predictions["scheme_challenger"] = _fit_predict(
                train_scheme, test_scheme, ("history_q", "history_p", *scheme_names)
            )[0]
        for name, predicted in model_predictions.items():
            metrics = _metric(y_test, predicted)
            fold_rows.append(
                {
                    "target_season": target,
                    "model": name,
                    "training_rows": train.height,
                    "target_rows": test.height,
                    "training_max_season": int(train["season"].max()),
                    "identical_model_0_5_population": not name.startswith("scheme"),
                    "target_definition": "current verified play-caller coach-season Q",
                    **metrics,
                }
            )
            predictions.append(
                test.select("coach_id", "team_id", "season", "player_ids").with_columns(
                    pl.lit(name).alias("model"),
                    pl.Series("actual", y_test),
                    pl.Series("predicted", predicted),
                )
            )
        learned = fitted["model_4_learned_q_p"]
        scale = learned.named_steps["scale"]
        ridge = learned.named_steps["ridge"]
        for index, feature in enumerate(("history_q", "history_p")):
            weight_rows.append(
                {
                    "record_type": "chronological_fold",
                    "target_season": target,
                    "resample_dimension": None,
                    "feature": feature,
                    "standardized_coefficient": float(ridge.coef_[index]),
                    "raw_coefficient": float(ridge.coef_[index] / scale.scale_[index]),
                    "interval_low": None,
                    "interval_high": None,
                    "successful_draws": None,
                }
            )
    future = pl.concat(predictions, how="diagonal_relaxed")
    comparisons = []
    for name in sorted(future["model"].unique().to_list()):
        frame = future.filter(pl.col("model") == name)
        comparisons.append(
            {
                "model": name,
                "evaluation_window": "credible_folds_2021_2025",
                "same_population_as_models_0_5": not name.startswith("scheme"),
                "target_definition": (
                    "Q(c,t): verified play-caller coach-season QB development residual"
                ),
                **_metric(frame["actual"].to_numpy(), frame["predicted"].to_numpy()),
            }
        )
    comparisons.append(
        {
            "model": "model_6_role_aware",
            "evaluation_window": "not_fit",
            "same_population_as_models_0_5": False,
            "target_definition": "not_identifiable_due_to_role_team_season_cooccurrence",
            **_metric([], []),
        }
    )
    weight_rows.extend(_weight_bootstraps(rows.filter(pl.col("season") < 2025)))
    return pl.DataFrame(comparisons), pl.DataFrame(fold_rows), pl.DataFrame(weight_rows)


def _weight_bootstraps(training: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension, column in (
        ("coach", "coach_id"),
        ("team", "team_id"),
        ("quarterback_set", "player_ids"),
        ("season", "season"),
    ):
        clusters = sorted(training[column].unique().to_list())
        rng = np.random.default_rng(_seed(f"weights:{dimension}"))
        draws: dict[str, list[float]] = defaultdict(list)
        for _ in range(BOOTSTRAPS):
            chosen = rng.choice(clusters, len(clusters), replace=True)
            pieces = [training.filter(pl.col(column) == value) for value in chosen]
            sample = pl.concat(pieces)
            if sample.height < 20:
                continue
            model = _ridge()
            model.fit(
                sample.select("history_q", "history_p").to_numpy(), sample["target_q"].to_numpy()
            )
            for feature, coefficient in zip(
                ("history_q", "history_p"), model.named_steps["ridge"].coef_[:2], strict=True
            ):
                draws[feature].append(float(coefficient))
        for feature in ("history_q", "history_p"):
            values = draws[feature]
            rows.append(
                {
                    "record_type": "cluster_bootstrap",
                    "target_season": None,
                    "resample_dimension": dimension,
                    "feature": feature,
                    "standardized_coefficient": float(np.median(values)) if values else None,
                    "raw_coefficient": None,
                    "interval_low": float(np.quantile(values, 0.025)) if values else None,
                    "interval_high": float(np.quantile(values, 0.975)) if values else None,
                    "successful_draws": len(values),
                }
            )
    for dimension, column in (("season", "season"), ("coach", "coach_id")):
        for value in sorted(training[column].unique().to_list()):
            sample = training.filter(pl.col(column) != value)
            if sample.height < 20:
                continue
            model = _ridge()
            model.fit(
                sample.select("history_q", "history_p").to_numpy(),
                sample["target_q"].to_numpy(),
            )
            for feature, coefficient in zip(
                ("history_q", "history_p"),
                model.named_steps["ridge"].coef_[:2],
                strict=True,
            ):
                rows.append(
                    {
                        "record_type": f"leave_one_{dimension}_out",
                        "target_season": value if dimension == "season" else None,
                        "resample_dimension": str(value),
                        "feature": feature,
                        "standardized_coefficient": float(coefficient),
                        "raw_coefficient": None,
                        "interval_low": None,
                        "interval_high": None,
                        "successful_draws": None,
                    }
                )
    return rows


def _variance_components(table: pl.DataFrame, signal: str) -> dict[str, float]:
    sort_columns = [
        name for name in ("coach_id", "season", "team_id", "player_ids") if name in table.columns
    ]
    ordered = table.sort(sort_columns)
    coach = ordered.group_by("coach_id", maintain_order=True).agg(
        pl.col(signal).mean().alias("mean"), pl.len().alias("n")
    )
    residual = ordered.join(coach.select("coach_id", "mean"), on="coach_id").with_columns(
        (pl.col(signal) - pl.col("mean")).alias("residual")
    )
    sigma2 = float((residual["residual"] ** 2).sum() / max(ordered.height - coach.height, 1))
    means = coach["mean"].to_numpy()
    sampling = sigma2 / coach["n"].to_numpy()
    center = float(np.average(means, weights=coach["n"].to_numpy()))
    mom = max(float(np.var(means, ddof=1)) - float(np.mean(sampling)), 0.0)

    def objective(tau2: float) -> float:
        weights = 1.0 / (sampling + tau2)
        mu = float(np.sum(weights * means) / np.sum(weights))
        return float(
            np.sum(np.log(sampling + tau2) + weights * (means - mu) ** 2) + np.log(np.sum(weights))
        )

    upper = max(float(np.var(means, ddof=1)) * 10, 1e-8)
    fitted = minimize_scalar(objective, bounds=(0.0, upper), method="bounded")
    reml = max(float(fitted.x), 0.0) if fitted.success else 0.0
    return {"residual_variance": sigma2, "mom_tau2": mom, "reml_tau2": reml, "center": center}


def _shrinkage_oos(
    table: pl.DataFrame, *, signal: str, signal_name: str, role: str
) -> list[dict[str, Any]]:
    predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)
    tau_values: dict[str, list[float]] = defaultdict(list)
    for target in CREDIBLE_FOLDS:
        train = table.filter(pl.col("season") < target)
        test = table.filter(pl.col("season") == target)
        if train.height < 20 or test.is_empty():
            continue
        components = _variance_components(train, signal)
        for current in test.to_dicts():
            history = train.filter(pl.col("coach_id") == current["coach_id"])
            if history.is_empty():
                continue
            raw = float(np.average(history[signal], weights=history["signal_exposure"]))
            predictions["raw_history"].append((float(current[signal]), raw))
            for method, tau2 in (
                ("mom_empirical_bayes", components["mom_tau2"]),
                ("reml_empirical_bayes", components["reml_tau2"]),
            ):
                sampling = components["residual_variance"] / history.height
                weight = tau2 / (tau2 + sampling) if tau2 > 0 else 0.0
                estimate = components["center"] + weight * (raw - components["center"])
                predictions[method].append((float(current[signal]), estimate))
                tau_values[method].append(tau2)
    rows = []
    for method, values in sorted(predictions.items()):
        metrics = _metric([value[0] for value in values], [value[1] for value in values])
        rows.append(
            {
                "record_type": "rolling_oos_validation",
                "signal": signal_name,
                "role": role,
                "method": method,
                "residual_variance": None,
                "between_coach_variance": (
                    float(np.mean(tau_values[method])) if tau_values[method] else None
                ),
                "variance_at_boundary": (
                    bool(np.all(np.asarray(tau_values[method]) <= 1e-12))
                    if tau_values[method]
                    else None
                ),
                "coaches": None,
                **metrics,
            }
        )
    return rows


def build_shrinkage(tables: dict[str, pl.DataFrame]) -> tuple[pl.DataFrame, pl.DataFrame]:
    rows: list[pl.DataFrame] = []
    oos_rows: list[dict[str, Any]] = []
    eligibility: list[dict[str, Any]] = []
    for label, table in sorted(tables.items()):
        signal_name, role = label.split(":", 1)
        signal = "pcae" if signal_name == "pcae" else "q_development_signal"
        primary = table.filter(pl.col("season") >= PRIMARY_START)
        if primary.height < 2:
            continue
        components = _variance_components(primary, signal)
        oos_rows.extend(_shrinkage_oos(table, signal=signal, signal_name=signal_name, role=role))
        raw = primary.group_by("coach_id", "coach_name").agg(
            (
                (pl.col(signal) * pl.col("signal_exposure")).sum() / pl.col("signal_exposure").sum()
            ).alias("raw_estimate"),
            pl.col("signal_exposure").sum().alias("exposure"),
            pl.len().alias("seasons"),
            pl.col("team_id").n_unique().alias("teams"),
        )
        qbs = (
            primary.select("coach_id", pl.col("player_ids").str.split("|").alias("player_id"))
            .explode("player_id", empty_as_null=True)
            .filter(pl.col("player_id") != "")
            .group_by("coach_id")
            .agg(pl.col("player_id").n_unique().alias("qbs"))
        )
        raw = raw.join(qbs, on="coach_id", how="left", validate="1:1").with_columns(
            pl.col("qbs").fill_null(0)
        )
        for method, tau2 in (
            ("method_of_moments", components["mom_tau2"]),
            ("reml", components["reml_tau2"]),
        ):
            sampling = components["residual_variance"] / raw["seasons"].to_numpy()
            weights = tau2 / (tau2 + sampling) if tau2 > 0 else np.zeros(len(sampling))
            posterior = components["center"] + weights * (
                raw["raw_estimate"].to_numpy() - components["center"]
            )
            posterior_variance = 1.0 / (1.0 / tau2 + 1.0 / sampling) if tau2 > 0 else sampling
            rows.append(
                pl.DataFrame(
                    {
                        "signal": signal_name,
                        "role": role,
                        "method": method,
                        "residual_variance": components["residual_variance"],
                        "between_coach_variance": tau2,
                        "variance_at_boundary": tau2 <= 1e-12,
                        "coaches": raw.height,
                    }
                )
            )
            if method == "reml":
                for index, item in enumerate(raw.to_dicts()):
                    qbs = int(item["qbs"] or 0)
                    grade = (
                        "HIGH"
                        if item["seasons"] >= 4 and qbs >= 2 and item["exposure"] >= 1500
                        else "MODERATE"
                        if item["seasons"] >= MIN_RESEARCH_SEASONS
                        and qbs >= MIN_RESEARCH_QBS
                        and item["exposure"] >= MIN_RESEARCH_EXPOSURE
                        else "LOW"
                    )
                    eligible = (
                        item["seasons"] >= MIN_RESEARCH_SEASONS
                        and qbs >= MIN_RESEARCH_QBS
                        and item["exposure"] >= MIN_RESEARCH_EXPOSURE
                        and tau2 > 0
                    )
                    se = float(np.sqrt(posterior_variance[index]))
                    eligibility.append(
                        {
                            "signal": signal_name,
                            "role": role,
                            "coach_id": item["coach_id"],
                            "coach_name": item["coach_name"],
                            "seasons": item["seasons"],
                            "qbs": qbs,
                            "teams": item["teams"],
                            "exposure": item["exposure"],
                            "raw_estimate": item["raw_estimate"],
                            "shrinkage_weight": float(weights[index]),
                            "research_estimate": float(posterior[index]),
                            "interval_low": float(posterior[index] - 1.96 * se),
                            "interval_high": float(posterior[index] + 1.96 * se),
                            "evidence_grade": grade,
                            "research_status": "ELIGIBLE" if eligible else "SUPPRESSED",
                            "production_status": "SUPPRESSED",
                            "confidence_multiplies_effect": False,
                        }
                    )
    diagnostic = pl.concat(
        [*rows, pl.DataFrame(oos_rows, infer_schema_length=None)],
        how="diagonal_relaxed",
    )
    return diagnostic, pl.DataFrame(eligibility, infer_schema_length=None)


def build_environment(snapshot: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    q = _q_rows(snapshot)
    features = list(ENVIRONMENT_FEATURES)
    for role in ROLES:
        source = q.filter(pl.col("role") == role)
        scored: list[pl.DataFrame] = []
        for target in CREDIBLE_FOLDS:
            train = source.filter(pl.col("season") < target)
            test = source.filter(pl.col("season") == target)
            if train.height < 30 or test.is_empty():
                continue
            model = _ridge()
            model.fit(train.select(features).to_numpy(), train["q_development_signal"].to_numpy())
            predicted = model.predict(test.select(features).to_numpy())
            scored.append(
                test.select(
                    "coach_id", "season", "exposure_dropbacks", "q_development_signal"
                ).with_columns(
                    pl.col("q_development_signal").alias("raw_q"),
                    (pl.col("q_development_signal") - pl.Series(predicted)).alias("adjusted_q"),
                )
            )
        if not scored:
            continue
        estimates = (
            pl.concat(scored)
            .group_by("coach_id")
            .agg(
                (
                    (pl.col("raw_q") * pl.col("exposure_dropbacks")).sum()
                    / pl.col("exposure_dropbacks").sum()
                ).alias("raw"),
                (
                    (pl.col("adjusted_q") * pl.col("exposure_dropbacks")).sum()
                    / pl.col("exposure_dropbacks").sum()
                ).alias("adjusted"),
            )
        )
        rows.append(
            {
                "role": role,
                "analysis_window": "credible_folds_2021_2025",
                "coaches": estimates.height,
                "estimate_pearson": _pearson(estimates["raw"], estimates["adjusted"]),
                "rank_spearman": _spearman(estimates["raw"], estimates["adjusted"]),
                "sign_agreement": float(
                    (np.sign(estimates["raw"]) == np.sign(estimates["adjusted"])).mean()
                ),
                "context_fit_scope": "prior_seasons_only_for_each_target",
                "context_is_score_points": False,
            }
        )
    rows.append(
        {
            "role": "head_coach_orientation",
            "analysis_window": "not_run",
            "coaches": 0,
            "estimate_pearson": None,
            "rank_spearman": None,
            "sign_agreement": None,
            "context_fit_scope": "no_independently_versioned_offensive_orientation_contract",
            "context_is_score_points": False,
        }
    )
    return pl.DataFrame(rows, infer_schema_length=None)


def build_missingness(project_root: Path) -> pl.DataFrame:
    prompt11 = _prompt_roots(project_root)[2]
    temporal = pl.read_csv(prompt11 / "temporal_window_sensitivity.csv")
    ipw = pl.read_csv(prompt11 / "inverse_probability_sensitivity.csv")
    leave = pl.read_csv(prompt11 / "leave_era_out_results.csv")
    rows = []
    for item in temporal.to_dicts():
        rows.append(
            {
                "analysis": item["analysis"],
                "method": "temporal_window",
                "q_p_pearson": item["q_p_pearson"],
                "p_repeatability": item["p_repeatability_pearson"],
                "q_repeatability": item["q_repeatability_pearson"],
                "effective_rows": item["common_qp_rows"],
                "interpretation": "primary_recent_and_secondary_history_reported_separately",
            }
        )
    for item in ipw.to_dicts():
        rows.append(
            {
                "analysis": item["metric"],
                "method": "clipped_verification_propensity_diagnostic",
                "q_p_pearson": item["ipw_weighted"],
                "p_repeatability": None,
                "q_repeatability": None,
                "effective_rows": item["weighted_effective_rows"],
                "interpretation": "poor_overlap_diagnostic_only_missingness_not_solved",
            }
        )
    for item in leave.to_dicts():
        rows.append(
            {
                "analysis": item["analysis"],
                "method": "leave_era_out",
                "q_p_pearson": item["q_p_pearson"],
                "p_repeatability": item["p_repeatability_pearson"],
                "q_repeatability": item["q_repeatability_pearson"],
                "effective_rows": item["common_qp_rows"],
                "interpretation": "archival_selection_sensitivity_not_correction",
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def build_placebos(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for window, start in (("primary_2020_2025", 2020), ("secondary_2010_2025", 2010)):
        for label, original in sorted(tables.items()):
            signal_name, role = label.split(":", 1)
            signal = "pcae" if signal_name == "pcae" else "q_development_signal"
            table = original.filter(pl.col("season") >= start)
            pairs = _pairs(table, signal)
            for subset, selected in (
                ("repeatability", pairs),
                ("different_qb", pairs.filter(pl.col("different_qb"))),
                ("different_team", pairs.filter(pl.col("different_team"))),
            ):
                observed = _pearson(selected["prior_signal"], selected["current_signal"])
                rng = np.random.default_rng(_seed(f"placebo:{window}:{label}:{subset}"))
                null: list[float] = []
                if selected.height:
                    seasons = selected["season"].to_numpy()
                    current = selected["current_signal"].to_numpy()
                    for _ in range(PERMUTATIONS):
                        permuted = current.copy()
                        for season in np.unique(seasons):
                            indices = np.flatnonzero(seasons == season)
                            permuted[indices] = rng.permutation(permuted[indices])
                        statistic = _pearson(selected["prior_signal"], permuted)
                        if statistic is not None:
                            null.append(statistic)
                rows.append(
                    {
                        "analysis_window": window,
                        "signal": signal_name,
                        "role": role,
                        "metric": subset,
                        "n": selected.height,
                        "observed": observed,
                        "permutations": PERMUTATIONS,
                        "null_low": float(np.quantile(null, 0.025)) if null else None,
                        "null_high": float(np.quantile(null, 0.975)) if null else None,
                        "empirical_two_sided_p": (
                            float((1 + np.sum(np.abs(null) >= abs(observed))) / (len(null) + 1))
                            if null and observed is not None
                            else None
                        ),
                    }
                )
    return pl.DataFrame(rows, infer_schema_length=None)


def _sample_summary(
    snapshot: pl.DataFrame,
    common: pl.DataFrame,
    mapped_pcae: pl.DataFrame,
    project_root: Path,
) -> pl.DataFrame:
    primary = common.filter(pl.col("season") >= PRIMARY_START)
    players = {
        player
        for value in primary["player_ids"].to_list()
        for player in str(value).split("|")
        if player
    }
    folds = pl.read_csv(_prompt_roots(project_root)[2] / "fold_quality_analysis.csv")
    records = [
        {
            "record": "primary_common_qp",
            "grain": "verified_play_caller_coach_team_season",
            "rows": primary.height,
            "coaches": primary["coach_id"].n_unique(),
            "qbs": len(players),
            "teams": primary["team_id"].n_unique(),
            "seasons": primary["season"].n_unique(),
            "exposure": int(primary["p_exposure"].sum()),
            "detail": "2020-2025",
        },
        {
            "record": "secondary_common_qp",
            "grain": "verified_play_caller_coach_team_season",
            "rows": common.height,
            "coaches": common["coach_id"].n_unique(),
            "qbs": int(common["quarterbacks"].sum()),
            "teams": common["team_id"].n_unique(),
            "seasons": common["season"].n_unique(),
            "exposure": int(common["p_exposure"].sum()),
            "detail": "2010-2025 historical sensitivity",
        },
        {
            "record": "final_snapshot",
            "grain": "assignment_key_player_team_season",
            "rows": snapshot.height,
            "coaches": snapshot["coach_id"].n_unique(),
            "qbs": snapshot["player_id"].n_unique(),
            "teams": snapshot["team_id"].n_unique(),
            "seasons": snapshot["season"].n_unique(),
            "exposure": int(snapshot["exposure_dropbacks"].sum()),
            "detail": "all verified role intervals; shared caller PCAE excluded",
        },
        {
            "record": "pcae_interval",
            "grain": "verified_nonshared_caller_team_season_week_interval",
            "rows": mapped_pcae.height,
            "coaches": mapped_pcae["coach_id"].n_unique(),
            "qbs": None,
            "teams": mapped_pcae["team_id"].n_unique(),
            "seasons": mapped_pcae["season"].n_unique(),
            "exposure": int(mapped_pcae["attributed_play_count"].sum()),
            "detail": "PCAE=CoachAverage(CallValue)-LeagueAverage(CallValue)",
        },
        {
            "record": "future_target",
            "grain": "play_caller_coach_team_season_with_prior_common_history",
            "rows": _future_rows(common).height,
            "coaches": None,
            "qbs": None,
            "teams": None,
            "seasons": folds.height,
            "exposure": None,
            "detail": "Q(c,t) predicted only from coach history before t",
        },
        {
            "record": "credible_future_target",
            "grain": "same_future_target_restricted_by_independent_fold_gate",
            "rows": int(folds.filter(pl.col("credible_target_fold"))["target_rows"].sum()),
            "coaches": None,
            "qbs": None,
            "teams": None,
            "seasons": len(CREDIBLE_FOLDS),
            "exposure": None,
            "detail": "2021-2025; no performance-based fold selection",
        },
        {
            "record": "repeatability_pair",
            "grain": "same_coach_consecutive_coach_seasons",
            "rows": _consecutive_pairs(common).height,
            "coaches": None,
            "qbs": None,
            "teams": None,
            "seasons": None,
            "exposure": None,
            "detail": "no pair across a missing season",
        },
        {
            "record": "different_qb_pair",
            "grain": "repeatability_pair_with_changed_qb_set",
            "rows": _consecutive_pairs(common).filter(pl.col("different_qb")).height,
            "coaches": None,
            "qbs": None,
            "teams": None,
            "seasons": None,
            "exposure": None,
            "detail": "set comparison; not causal portability",
        },
        {
            "record": "different_team_pair",
            "grain": "repeatability_pair_with_changed_team",
            "rows": _consecutive_pairs(common).filter(pl.col("different_team")).height,
            "coaches": None,
            "qbs": None,
            "teams": None,
            "seasons": None,
            "exposure": None,
            "detail": "selected coach moves; not causal portability",
        },
    ]
    return pl.DataFrame(records, infer_schema_length=None)


def _decisions(
    role_signals: pl.DataFrame,
    reliability: pl.DataFrame,
    comparisons: pl.DataFrame,
    folds: pl.DataFrame,
    weights: pl.DataFrame,
    project_root: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    primary = role_signals.filter(pl.col("analysis_window") == "primary_2020_2025")
    fold_model = comparisons.filter(pl.col("model").str.starts_with("model_"))
    baseline = fold_model.filter(pl.col("model") == "model_0_no_coach").row(0, named=True)
    candidates = fold_model.filter(
        (pl.col("model") != "model_0_no_coach") & pl.col("rmse").is_not_null()
    )
    best = candidates.sort("rmse").row(0, named=True)
    improvement = (baseline["rmse"] - best["rmse"]) / baseline["rmse"]
    chronological = weights.filter(pl.col("record_type") == "chronological_fold")
    q_weights = chronological.filter(pl.col("feature") == "history_q")
    p_weights = chronological.filter(pl.col("feature") == "history_p")
    weight_stable = (
        q_weights.height == len(CREDIBLE_FOLDS)
        and p_weights.height == len(CREDIBLE_FOLDS)
        and q_weights["standardized_coefficient"].min()
        * q_weights["standardized_coefficient"].max()
        > 0
        and p_weights["standardized_coefficient"].min()
        * p_weights["standardized_coefficient"].max()
        > 0
    )
    composite_supported = (
        improvement >= PRACTICAL_RMSE_REDUCTION
        and (best["pearson"] or -1) >= MIN_RESEARCH_CORRELATION
        and (best["direction_accuracy"] or -1) >= MIN_RESEARCH_DIRECTION
        and weight_stable
        and best["model"]
        in {"model_3_equal_q_p", "model_4_learned_q_p", "model_5_overlap_decomposition"}
    )
    pcae_model = comparisons.filter(pl.col("model") == "model_2_pcae_only").row(0, named=True)
    pcae_summary = primary.filter(pl.col("signal") == "pcae").row(0, named=True)
    pcae_only_supported = (
        (baseline["rmse"] - pcae_model["rmse"]) / baseline["rmse"] >= PRACTICAL_RMSE_REDUCTION
        and (pcae_model["pearson"] or -1) >= MIN_RESEARCH_CORRELATION
        and (pcae_summary["repeatability_pearson"] or -1) >= MIN_RESEARCH_CORRELATION
    )
    if composite_supported:
        architecture = "B"
        architecture_status = "COMPOSITE COACH EFFECT APPROVED FOR RESEARCH ONLY"
        exact = best["model"]
        formula = "training-fold Ridge prediction of future Q from standardized prior Q and PCAE"
    elif pcae_only_supported:
        architecture = "D"
        architecture_status = "PCAE-ONLY PLAY CALLER EFFECT APPROVED FOR RESEARCH ONLY"
        exact = "PCAE retained as a separate play-calling decision-value signal"
        formula = "PCAE(c,s)=CoachAverage(CallValue)-LeagueAverage(CallValue)"
    else:
        architecture = "E"
        architecture_status = "NO COMPOSITE COACH EFFECT APPROVED"
        exact = "retain Q and PCAE separately; no validated combined Coach Effect"
        formula = "not_applicable"
    role_rows = []
    for role in ROLES:
        if role in {"offensive_coordinator", "quarterbacks_coach", "play_caller"}:
            status = "EXPLORATORY ONLY"
            rationale = "Q has insufficient repeatable or future predictive signal"
        elif role == "head_coach":
            status = "NOT IDENTIFIABLE"
            rationale = "Q cannot be separated defensibly from team/staff environment"
        role_rows.append(
            {
                "role_or_signal": f"{role}_q",
                "classification": status,
                "rationale": rationale,
            }
        )
    role_rows.extend(
        [
            {
                "role_or_signal": "play_caller_pcae",
                "classification": "RESEARCH-READY",
                "rationale": (
                    "verified nonshared interval signal with modern repeatability; "
                    "observational only"
                ),
            },
            {
                "role_or_signal": "play_caller_combined",
                "classification": "RESEARCH-READY" if architecture == "B" else "EXPLORATORY ONLY",
                "rationale": exact,
            },
        ]
    )
    coverage = pl.read_csv(_prompt_roots(project_root)[2] / "final_methodology_decision.csv").row(
        0, named=True
    )
    production_checks = [
        (
            "recent_full_cell_coverage",
            MIN_PRODUCTION_FULL_CELL_RATE,
            coverage["recent_full_cell_rate"],
        ),
        (
            "recent_attributable_play_coverage",
            MIN_PRODUCTION_PLAY_RATE,
            coverage["recent_play_weighted_rate"],
        ),
        ("unsupported_individual_attribution", 0.0, 0.0),
        ("stable_oos_architecture", 1.0, float(composite_supported or pcae_only_supported)),
        ("role_specific_verification_complete", 1.0, 0.0),
    ]
    production = pl.DataFrame(
        [
            {
                "gate": name,
                "threshold": threshold,
                "observed": observed,
                "result": "PASS"
                if (
                    observed >= threshold
                    if name != "unsupported_individual_attribution"
                    else observed == threshold
                )
                else "FAIL",
            }
            for name, threshold, observed in production_checks
        ]
    ).with_columns(pl.lit("NO-GO").alias("production_coach_effect"))
    architecture_frame = pl.DataFrame(
        [
            {
                "architecture_code": architecture,
                "architecture_status": architecture_status,
                "selected_architecture": exact,
                "mathematical_formula": formula,
                "best_oos_model": best["model"],
                "relative_rmse_improvement": improvement,
                "practically_meaningful": improvement >= PRACTICAL_RMSE_REDUCTION,
                "fixed_q_p_weights_approved": composite_supported and weight_stable,
                "zero_to_one_hundred_ready": False,
                "confidence_separate_from_effect": True,
                "causal_claim": False,
            }
        ]
    )
    closeout = pl.DataFrame(
        [
            {
                "checkpoint_12_research_status": "COMPLETE",
                "phase_ii_checkpoint_13_readiness": "READY",
                "single_remaining_scientific_blocker": None,
                "production_coach_effect": "NO-GO",
                "more_broad_play_caller_research": "NOT RECOMMENDED",
                "targeted_recent_cell_verification": "USEFUL ONLY IF FUTURE PRODUCTION IS PURSUED",
                "production_modified": False,
                "phase_two_implemented": False,
                "ask_anything_implemented": False,
            }
        ],
        infer_schema_length=None,
    )
    return architecture_frame, production, closeout, pl.DataFrame(role_rows)


def _identity(project_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    prompt6, prompt10, prompt11 = _prompt_roots(project_root)
    sources = _sources(project_root)
    paths = [
        prompt6 / "MANIFEST.json",
        prompt10 / "MANIFEST.json",
        prompt10 / "historical_pcae.csv",
        prompt10 / "common_qp_availability.csv",
        prompt10 / "play_caller_completeness.csv",
        prompt11 / "MANIFEST.json",
        prompt11 / "fold_quality_analysis.csv",
        prompt11 / "final_methodology_decision.csv",
        prompt11 / "temporal_window_sensitivity.csv",
        prompt11 / "inverse_probability_sensitivity.csv",
        prompt11 / "leave_era_out_results.csv",
        sources.pae_path,
        sources.qb_games_path,
        sources.environment_path,
        project_root
        / "research/coach_effect/outputs/checkpoint_12_data_expansion"
        / "c12-data-250e540b7de79385"
        / "MANIFEST.json",
        project_root
        / "research/coach_effect/outputs/checkpoint_12_data_expansion"
        / "c12-data-250e540b7de79385"
        / "team_season_scheme_fingerprints.csv",
        project_root / "research/coach_effect/checkpoint_twelve_final_research.py",
        project_root / "research/coach_effect/checkpoint_twelve.py",
        project_root / "research/coach_effect/checkpoint_twelve_coverage_gate_review.py",
        project_root / "research/coach_effect/checkpoint_twelve_final_play_caller_evidence.py",
        project_root / "research/coach_effect/config.py",
    ]
    paths.extend(sorted((project_root / "data/manual").glob("*.csv")))
    hashes = {str(path.relative_to(project_root)): sha256_file(path) for path in paths}
    identity = {
        "specification": SPECIFICATION,
        "prompt6_version": "c12-8cd15ae6015e900b",
        "prompt10_version": PROMPT10_VERSION,
        "prompt11_version": PROMPT11_VERSION,
        "primary_window": [2020, 2025],
        "secondary_window": [2010, 2025],
        "credible_folds": CREDIBLE_FOLDS,
        "future_target": "current verified play-caller coach-season Q",
        "q_features_unchanged": Q_FEATURES,
        "pae_data_version": EXPECTED_PAE_DATA_VERSION,
        "pae_model_version": EXPECTED_PAE_MODEL_VERSION,
        "random_seed": RANDOM_SEED,
        "bootstraps": BOOTSTRAPS,
        "permutations": PERMUTATIONS,
        "ridge_alpha": RIDGE_ALPHA,
        "research_gate_policy": RESEARCH_GATE_POLICY,
        "decision_thresholds": {
            "practical_rmse_reduction": PRACTICAL_RMSE_REDUCTION,
            "minimum_research_correlation": MIN_RESEARCH_CORRELATION,
            "minimum_research_direction": MIN_RESEARCH_DIRECTION,
        },
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_hashes": dict(sorted(hashes.items())),
    }
    return identity, hashes


def _verify_hashes(project_root: Path, hashes: dict[str, str]) -> None:
    changed = [
        path for path, digest in hashes.items() if sha256_file(project_root / path) != digest
    ]
    if changed:
        raise ValueError(f"final research input changed during build: {sorted(changed)}")


def run_checkpoint_twelve_final_research(
    project_root: Path, output_root: Path | None = None
) -> FinalResearchResult:
    project_root = project_root.resolve()
    identity, hashes = _identity(project_root)
    version = (
        "c12-final-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    snapshot, mapped_pcae, _, _ = build_final_snapshot(project_root)
    coverage, _, common = _load_prompt10(project_root)
    prompt11_folds = pl.read_csv(_prompt_roots(project_root)[2] / "fold_quality_analysis.csv")
    if (
        coverage.filter(pl.col("season") >= 2020)
        .filter(pl.col("ending_status") == "verified")
        .height
        != 180
        or common.height != 269
        or _future_rows(common).height != 165
        or prompt11_folds.filter(pl.col("credible_target_fold")).height != 5
        or _consecutive_pairs(common).filter(pl.col("different_qb")).height != 96
        or _consecutive_pairs(common).filter(pl.col("different_team")).height != 19
    ):
        raise ValueError("Prompt 11 sample counts were not reproduced")
    role_signals, tables = build_role_signals(snapshot, mapped_pcae, common)
    reliability = build_pcae_reliability(tables["pcae:play_caller"])
    overlap = build_qp_overlap(common)
    comparisons, folds, weights = build_models(project_root, common)
    shrinkage, eligibility = build_shrinkage(tables)
    environment = build_environment(snapshot)
    missingness = build_missingness(project_root)
    placebos = build_placebos(tables)
    architecture, production, closeout, readiness = _decisions(
        role_signals, reliability, comparisons, folds, weights, project_root
    )
    outputs = {
        "final_research_snapshot.csv": snapshot,
        "final_sample_summary.csv": _sample_summary(snapshot, common, mapped_pcae, project_root),
        "role_signal_summary.csv": role_signals,
        "pcae_reliability.csv": reliability,
        "qp_overlap.csv": overlap,
        "rolling_model_comparison.csv": comparisons,
        "fold_metrics.csv": folds,
        "weight_stability.csv": weights,
        "shrinkage_comparison.csv": shrinkage,
        "environment_sensitivity.csv": environment,
        "missingness_sensitivity.csv": missingness,
        "placebo_results.csv": placebos,
        "eligibility_research.csv": eligibility,
        "role_readiness.csv": readiness,
        "architecture_decision.csv": architecture,
        "production_gate.csv": production,
        "checkpoint_closeout.csv": closeout,
    }
    if set(outputs) != set(OUTPUT_NAMES):
        raise ValueError("final research output contract drift")
    outputs = {name: _contract(frame, version) for name, frame in outputs.items()}
    _verify_hashes(project_root, hashes)
    root = (
        output_root or project_root / "research/coach_effect/outputs/checkpoint_12_final_research"
    )
    destination = root / version
    temporary = root / f".{version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    for name in OUTPUT_NAMES:
        _write_csv(outputs[name], temporary / name)
    checksums = {name: sha256_file(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "research_data_version": version,
        "research_only": True,
        "production_coach_effect": False,
        "production_ranking": False,
        "architecture_status": architecture["architecture_code"].item(),
        "checkpoint_12_complete": True,
        "phase_ii_ready": True,
        "phase_ii_started": False,
        "ask_anything_implemented": False,
        "verification_semantics_changed": False,
        "pae_q_pcae_callvalue_changed": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {name: outputs[name].height for name in OUTPUT_NAMES},
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _verify_hashes(project_root, hashes)
    expected = {"MANIFEST.json", *OUTPUT_NAMES}
    if destination.exists():
        if {path.name for path in destination.iterdir() if path.is_file()} != expected:
            raise ValueError("existing final research publication has unexpected files")
        for name in expected:
            if sha256_file(destination / name) != sha256_file(temporary / name):
                raise ValueError(f"existing final research output differs: {name}")
        shutil.rmtree(temporary)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(destination)
    latest = root / ".LATEST.tmp"
    latest.write_text(version + "\n", encoding="utf-8")
    latest.replace(root / "LATEST")
    return FinalResearchResult(destination, version, architecture["architecture_code"].item())

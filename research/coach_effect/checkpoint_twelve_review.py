"""Independent, research-only adversarial review of Checkpoint Twelve Candidate A.

The review rebuilds analytical grains from frozen repository sources, writes only beneath the
ignored research output tree, and never changes production data, models, serving contracts, or
rankings. Candidate A remains an immutable comparison input.
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

import nflreadpy
import numpy as np
import polars as pl
import scipy
import sklearn
from scipy.optimize import minimize_scalar
from scipy.stats import norm, spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from nfl_coaching_impact.coach_impact import build_coach_exposures
from nfl_coaching_impact.constants import TEAM_ALIAS_TO_CANONICAL
from research.coach_effect.checkpoint_eleven import PBP_COLUMNS, prepare_historical_plays
from research.coach_effect.checkpoint_eleven_b import (
    _evidence_assignments,
    build_evidence_coverage,
)

PRODUCTION_LOAD_ID = "22680407-d503-5290-bda2-18f4cbcb622a"
CANDIDATE_VERSION = "c12-8cd15ae6015e900b"
PAE_DATA_VERSION = "c5-8fd5d1aba2598c59"
PAE_MODEL_VERSION = "expected-performance-8fd5d1aba2598c59"
PCAE_DATA_VERSION = "c11b-bbf7d43d0e4c4c05"
REVIEW_SPECIFICATION = "checkpoint-twelve-adversarial-review-v1"
RANDOM_SEED = 20260907
PERMUTATIONS = 1_000
BOOTSTRAPS = 1_000
MIN_Q_EXPOSURE = 25.0
MIN_JOINT_TRAIN = 10
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
BASE_SCHEME_FEATURES = ("shotgun_rate", "no_huddle_rate", "early_down_pass_rate")
PERSONNEL_FEATURES = ("personnel_11_rate", "personnel_12_rate", "personnel_21_rate")
FTN_FEATURES = ("motion_rate", "play_action_rate", "screen_rate", "rpo_rate")
SCHEME_FEATURES = (
    *PERSONNEL_FEATURES,
    "shotgun_rate",
    *FTN_FEATURES,
    "no_huddle_rate",
    "early_down_pass_rate",
)
OUTPUT_NAMES = (
    "grain_audit.csv",
    "qp_overlap_reconciliation.csv",
    "variance_audit.csv",
    "fold_availability_matrix.csv",
    "model_comparison_identical_folds.csv",
    "portability_audit.csv",
    "scheme_feature_availability.csv",
    "play_caller_verification_priority.csv",
    "sample_expansion_simulation.csv",
    "power_analysis.csv",
    "corrected_results.csv",
    "data_expansion_roadmap.csv",
)


@dataclass(frozen=True)
class ReviewSources:
    historical_version: str
    enhancement_version: str
    pae_path: Path
    games_path: Path
    environment_path: Path
    team_statistics_path: Path
    pbp_root: Path
    pcae_path: Path
    candidate_root: Path


def _latest(root: Path) -> str:
    version = (root / "LATEST").read_text(encoding="utf-8").strip()
    if not version or not (root / version).is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return version


def _sources(project_root: Path) -> ReviewSources:
    historical_root = project_root / "data/processed/historical"
    enhancement_root = project_root / "data/processed/enhancements"
    historical_version = _latest(historical_root)
    enhancement_version = _latest(enhancement_root)
    enhancement = enhancement_root / enhancement_version
    pcae_root = project_root / "research/coach_effect/outputs/checkpoint_11b"
    pcae_version = _latest(pcae_root)
    if pcae_version != PCAE_DATA_VERSION:
        raise ValueError(f"expected PCAE {PCAE_DATA_VERSION}, got {pcae_version}")
    candidate_root = (
        project_root / "research/coach_effect/outputs/checkpoint_12" / CANDIDATE_VERSION
    )
    if not candidate_root.is_dir():
        raise ValueError(f"missing Candidate A: {candidate_root}")
    return ReviewSources(
        historical_version=historical_version,
        enhancement_version=enhancement_version,
        pae_path=enhancement / "canonical_qb_pae.parquet",
        games_path=enhancement / "canonical_qb_game_performance.parquet",
        environment_path=enhancement / "inherited_environment_features.parquet",
        team_statistics_path=enhancement / "team_season_statistics.parquet",
        pbp_root=historical_root / historical_version / "bronze/play_by_play",
        pcae_path=pcae_root / pcae_version / "historical_pcae.csv",
        candidate_root=candidate_root,
    )


def _canonical_team(value: str) -> str:
    team = TEAM_ALIAS_TO_CANONICAL.get(value)
    if team is None:
        raise ValueError(f"unresolved team: {value}")
    return f"team_{team.lower()}"


def _seed(label: str) -> int:
    value = hashlib.sha256(f"{RANDOM_SEED}:{label}".encode()).digest()
    return int.from_bytes(value[:8], "big") % (2**32)


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


def _metric_row(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    if not len(actual):
        return {name: None for name in ("pearson", "spearman", "rmse", "mae", "direction")}
    return {
        "pearson": _pearson(actual, predicted),
        "spearman": _spearman(actual, predicted),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "mae": float(mean_absolute_error(actual, predicted)),
        "direction": float(np.mean(np.sign(actual) == np.sign(predicted))),
    }


def _assignments(project_root: Path) -> pl.DataFrame:
    rows = _evidence_assignments(project_root)
    frame = pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        (pl.col("is_interim") == "true").alias("is_interim"),
        (pl.col("is_shared") == "true").alias("is_shared"),
        (pl.col("is_retained") == "true").alias("is_retained"),
        pl.col("team_id")
        .map_elements(_canonical_team, return_dtype=pl.String)
        .alias("canonical_team_id"),
        pl.col("coach_canonical_name").alias("coach_name"),
    )
    verified = frame.filter(pl.col("verification_status") == "verified")
    if verified["assignment_key"].n_unique() != verified.height:
        raise ValueError("duplicate verified assignment keys")
    return verified.filter(
        (pl.col("role") != "play_caller") | (pl.col("interval_basis") != "season_designation")
    ).sort("role", "season", "canonical_team_id", "start_week", "assignment_key")


def _load_pae(path: Path) -> pl.DataFrame:
    frame = pl.read_parquet(path).with_columns(pl.lit(PRODUCTION_LOAD_ID).alias("load_id"))
    if frame.select(PAE_KEY).n_unique() != frame.height:
        raise ValueError("duplicate PAE grain")
    if frame["data_version"].unique().to_list() != [PAE_DATA_VERSION]:
        raise ValueError("unexpected PAE data version")
    if frame["model_version"].unique().to_list() != [PAE_MODEL_VERSION]:
        raise ValueError("unexpected PAE model version")
    bad = frame.filter(
        (
            pl.col("actual_epa_per_dropback")
            - pl.col("expected_epa_per_dropback")
            - pl.col("performance_above_expectation")
        ).abs()
        > 1e-12
    )
    if bad.height:
        raise ValueError("PAE arithmetic mismatch")
    if frame.filter(
        pl.col("feature_source_max_season").is_not_null()
        & (pl.col("feature_source_max_season") >= pl.col("season"))
    ).height:
        raise ValueError("PAE leakage")
    return frame.sort("season", "player_id", "team_id")


def _fit_movement(pae: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    prior = (
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
        )
        .with_columns((pl.col("season") + 1).alias("season"))
    )
    transitions = pae.join(prior, on=["player_id", "season"], validate="m:1").with_columns(
        (pl.col("performance_above_expectation") - pl.col("prior_pae")).alias("qb_delta"),
        pl.col("changed_team").cast(pl.Int8).alias("changed_team_numeric"),
    )
    folds: list[dict[str, Any]] = []
    outputs: list[pl.DataFrame] = []
    for target in sorted(transitions["season"].unique().to_list()):
        train = transitions.filter(pl.col("season") < target)
        test = transitions.filter(pl.col("season") == target)
        if train.height < 30 or test.is_empty():
            continue
        model = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=10.0)),
            ]
        )
        model.fit(
            train.select(Q_FEATURES).cast(pl.Float64).to_numpy(),
            train["qb_delta"].to_numpy(),
            ridge__sample_weight=train["dropbacks"].to_numpy(),
        )
        predicted = model.predict(test.select(Q_FEATURES).cast(pl.Float64).to_numpy())
        outputs.append(
            test.select(*PAE_KEY, "prior_pae", "qb_delta").with_columns(
                pl.Series("expected_normal_qb_delta", predicted)
            )
        )
        folds.append(
            {
                "target_season": target,
                "training_start": int(train["season"].min()),
                "training_end": int(train["season"].max()),
                "training_rows": train.height,
                "target_rows": test.height,
                "preprocessing_scope": "training_only",
            }
        )
    return pl.concat(outputs).sort("season", "player_id", "team_id"), pl.DataFrame(folds)


def _map_pcae(assignments: pl.DataFrame, path: Path) -> pl.DataFrame:
    pcae = pl.read_csv(path, infer_schema_length=None).with_columns(
        pl.col("team_id").map_elements(_canonical_team, return_dtype=pl.String)
    )
    if set(pcae["verification_status"]) != {"verified"}:
        raise ValueError("PCAE attribution is not verified-only")
    callers = assignments.filter(pl.col("role") == "play_caller").select(
        "assignment_key",
        "coach_id",
        pl.col("canonical_team_id").alias("team_id"),
        "season",
        "start_week",
        "end_week",
        "interval_basis",
        "is_shared",
        "primary_source_url",
    )
    keys = ["coach_id", "team_id", "season", "start_week", "end_week"]
    mapped = pcae.join(callers, on=keys, how="left", validate="1:1")
    if mapped["assignment_key"].null_count():
        raise ValueError("PCAE interval failed verified assignment mapping")
    if mapped.filter(pl.col("is_shared")).height:
        raise ValueError("shared play-callers entered individual PCAE")
    if mapped.filter(pl.col("interval_basis") == "season_designation").height:
        raise ValueError("unbounded season designation entered PCAE")
    return mapped.sort("season", "team_id", "start_week", "coach_id")


def build_independent_core(
    project_root: Path, sources: ReviewSources
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """Rebuild PAE, assignment exposure, movement, and PCAE grains from source assets."""

    pae = _load_pae(sources.pae_path)
    assignments = _assignments(project_root)
    games = pl.read_parquet(sources.games_path).filter(pl.col("season") >= 2010)
    exposures = build_coach_exposures(games, pae, assignments).with_columns(
        pl.lit(PRODUCTION_LOAD_ID).alias("load_id")
    )
    movement, movement_folds = _fit_movement(pae)
    joined = exposures.join(movement, on=list(PAE_KEY), how="left", validate="m:1").with_columns(
        (
            pl.col("coach_interval_pae") - pl.col("prior_pae") - pl.col("expected_normal_qb_delta")
        ).alias("q_development_signal")
    )
    environment = (
        pl.read_parquet(sources.environment_path)
        .select("team_id", "season", *ENVIRONMENT_FEATURES[:-1], "feature_source_max_season")
        .rename({"feature_source_max_season": "environment_source_max_season"})
    )
    joined = joined.join(environment, on=["team_id", "season"], how="left", validate="m:1")
    if joined.filter(
        pl.col("environment_source_max_season").is_not_null()
        & (pl.col("environment_source_max_season") >= pl.col("season"))
    ).height:
        raise ValueError("environment leakage")
    pcae = _map_pcae(assignments, sources.pcae_path)
    pcols = pcae.select("assignment_key", "pcae", "attributed_play_count")
    joined = joined.join(pcols, on="assignment_key", how="left", validate="m:1")
    grain = ("assignment_key", "player_id", "team_id", "season")
    if joined.select(grain).n_unique() != joined.height:
        raise ValueError("independent exposure join multiplied rows")
    q = joined.filter(
        pl.col("q_development_signal").is_not_null()
        & (pl.col("exposure_dropbacks") >= MIN_Q_EXPOSURE)
        & (pl.col("verification_status") == "verified")
    )
    return pae, assignments, joined, q, pcae, movement_folds


def _weighted(frame: pl.DataFrame, signal: str, weight: str, group: list[str]) -> pl.DataFrame:
    return (
        frame.filter(pl.col(signal).is_not_null() & (pl.col(weight) > 0))
        .group_by(group)
        .agg(
            ((pl.col(signal) * pl.col(weight)).sum() / pl.col(weight).sum()).alias(signal),
            pl.col(weight).sum().alias("weight"),
        )
        .sort(group)
    )


def build_grain_audit(
    project_root: Path,
    sources: ReviewSources,
    pae: pl.DataFrame,
    assignments: pl.DataFrame,
    joined: pl.DataFrame,
    pcae: pl.DataFrame,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(
        stage: str,
        left: int,
        matched: int,
        unmatched: int,
        final: int,
        duplicates: int,
        grain: str,
        note: str,
    ) -> None:
        rows.append(
            {
                "record_type": "join_summary",
                "stage": stage,
                "input_rows": left,
                "matched_rows": matched,
                "unmatched_rows": unmatched,
                "suppressed_or_missing_rows": max(left - final, 0),
                "final_rows": final,
                "duplicate_multiplication": duplicates,
                "grain": grain,
                "sample_identifier": None,
                "note": note,
            }
        )

    add("pae_source", pae.height, pae.height, 0, pae.height, 0, "|".join(PAE_KEY), "unique")
    add(
        "verified_assignments",
        assignments.height,
        assignments.height,
        0,
        assignments.height,
        assignments.height - assignments["assignment_key"].n_unique(),
        "assignment_key+bounded_role_interval",
        "play-caller season designations excluded",
    )
    add(
        "assignment_qb_exposure",
        joined.height,
        joined.height,
        0,
        joined.height,
        joined.height
        - joined.select("assignment_key", "player_id", "team_id", "season").n_unique(),
        "assignment_key|player_id|team_id|season",
        "interval exposure preserves role duplication by design",
    )
    add(
        "pcae_assignment",
        pcae.height,
        pcae.height,
        0,
        pcae.height,
        pcae.height - pcae["assignment_key"].n_unique(),
        "verified_play_caller_assignment_interval",
        "no provisional, unresolved, shared, or unbounded assignment",
    )

    # Trace fixed source plays without trusting Candidate A's joined CSV.
    for row in pcae.head(3).to_dicts():
        path = sources.pbp_root / f"season={row['season']}/play_by_play.parquet"
        raw = pl.read_parquet(path, columns=list(PBP_COLUMNS))
        eligible, _ = prepare_historical_plays(raw)
        sample = eligible.filter(
            (pl.col("team_id") == row["team_id"].removeprefix("team_").upper())
            & pl.col("week").is_between(row["start_week"], row["end_week"])
        ).head(1)
        identifier = None
        if sample.height:
            item = sample.row(0, named=True)
            identifier = f"{item['game_id']}:{item['play_id']}"
        rows.append(
            {
                "record_type": "pcae_play_trace",
                "stage": "eligible_play_to_assignment",
                "input_rows": eligible.height,
                "matched_rows": 1 if identifier else 0,
                "unmatched_rows": 0 if identifier else 1,
                "suppressed_or_missing_rows": 0,
                "final_rows": 1 if identifier else 0,
                "duplicate_multiplication": 0,
                "grain": "game_id|play_id -> week|team -> assignment_key -> coach",
                "sample_identifier": identifier,
                "note": row["assignment_key"],
            }
        )
    return pl.DataFrame(rows)


def build_overlap(q: pl.DataFrame, pcae: pl.DataFrame, pae: pl.DataFrame) -> pl.DataFrame:
    p_team = _weighted(pcae, "pcae", "attributed_play_count", ["team_id", "season"])
    p_coach = _weighted(
        pcae,
        "pcae",
        "attributed_play_count",
        ["coach_id", "team_id", "season"],
    )
    pae_team = _weighted(pae, "performance_above_expectation", "dropbacks", ["team_id", "season"])
    qb = pae.join(p_team.select("team_id", "season", "pcae"), on=["team_id", "season"])
    team = pae_team.join(p_team, on=["team_id", "season"], suffix="_p")
    q_pc = _weighted(
        q.filter(pl.col("role") == "play_caller"),
        "q_development_signal",
        "exposure_dropbacks",
        ["coach_id", "team_id", "season"],
    )
    coach_pae = _weighted(
        q.filter(pl.col("role") == "play_caller"),
        "performance_above_expectation",
        "exposure_dropbacks",
        ["coach_id", "team_id", "season"],
    ).join(p_coach, on=["coach_id", "team_id", "season"], suffix="_p")
    q_common = q_pc.join(p_coach, on=["coach_id", "team_id", "season"], suffix="_p")
    rows: list[dict[str, Any]] = []

    def record(label: str, frame: pl.DataFrame, left: str, right: str, subset: str) -> None:
        rows.append(
            {
                "grain": label,
                "subset": subset,
                "n": frame.height,
                "pearson": _pearson(frame[left], frame[right]),
                "spearman": _spearman(frame[left], frame[right]),
                "left_signal": left,
                "right_signal": right,
            }
        )

    for subset, predicate in (
        ("full_common_historical", pl.lit(True)),
        ("common_2023_2025", pl.col("season").is_between(2023, 2025)),
    ):
        record(
            "qb_team_season", qb.filter(predicate), "performance_above_expectation", "pcae", subset
        )
        record(
            "team_season", team.filter(predicate), "performance_above_expectation", "pcae", subset
        )
        record(
            "verified_play_caller_coach_season",
            coach_pae.filter(predicate),
            "performance_above_expectation",
            "pcae",
            subset,
        )
        record(
            "prompt6_q_coach_season",
            q_common.filter(predicate),
            "q_development_signal",
            "pcae",
            subset,
        )
    return pl.DataFrame(rows).sort("subset", "grain")


def _reml_tau(group_means: np.ndarray, sampling: np.ndarray) -> float:
    if len(group_means) < 3:
        return 0.0

    def objective(tau2: float) -> float:
        variance = sampling + tau2
        weights = 1.0 / variance
        center = float(np.sum(weights * group_means) / np.sum(weights))
        return float(
            np.sum(np.log(variance) + ((group_means - center) ** 2) / variance)
            + np.log(np.sum(weights))
        )

    upper = max(float(np.var(group_means)) * 10, 1e-6)
    result = minimize_scalar(objective, bounds=(0.0, upper), method="bounded")
    return max(float(result.x), 0.0)


def _variance_row(
    frame: pl.DataFrame, role: str, signal_name: str, signal: str, exposure: str
) -> dict[str, Any]:
    usable = frame.filter(pl.col(signal).is_not_null() & (pl.col(exposure) > 0))
    means = (
        usable.group_by("coach_id")
        .agg(
            ((pl.col(signal) * pl.col(exposure)).sum() / pl.col(exposure).sum()).alias("mean"),
            pl.col(exposure).sum().alias("weight"),
            pl.len().alias("observations"),
        )
        .sort("coach_id")
    )
    joined = usable.join(means.select("coach_id", "mean"), on="coach_id", validate="m:1")
    residual_df = max(usable.height - means.height, 1)
    sigma2 = float(
        joined.select((pl.col(exposure) * (pl.col(signal) - pl.col("mean")) ** 2).sum()).item()
        / residual_df
    )
    values = means["mean"].to_numpy()
    weights = means["weight"].to_numpy()
    center = float(np.average(values, weights=weights))
    sampling = sigma2 / weights
    raw_tau = float(np.average((values - center) ** 2, weights=weights) - np.mean(sampling))
    rng = np.random.default_rng(_seed(f"variance:{signal_name}:{role}"))
    draws: list[float] = []
    for _ in range(BOOTSTRAPS):
        index = rng.integers(0, len(values), len(values))
        selected = values[index]
        selected_weight = weights[index]
        selected_sampling = sampling[index]
        selected_center = float(np.average(selected, weights=selected_weight))
        draws.append(
            float(
                np.average((selected - selected_center) ** 2, weights=selected_weight)
                - np.mean(selected_sampling)
            )
        )
    # Classical one-way ANOVA is a sensitivity analysis that treats intervals equally.
    groups = [g[signal].to_numpy() for _, g in usable.group_by("coach_id")]
    grand = float(usable[signal].mean())
    between = sum(len(g) * (float(np.mean(g)) - grand) ** 2 for g in groups)
    within = sum(float(np.sum((g - np.mean(g)) ** 2)) for g in groups)
    between_ms = between / max(len(groups) - 1, 1)
    within_ms = within / max(usable.height - len(groups), 1)
    k_bar = float(np.mean([len(g) for g in groups]))
    anova_tau = max((between_ms - within_ms) / max(k_bar, 1.0), 0.0)
    return {
        "signal": signal_name,
        "role": role,
        "intervals": usable.height,
        "coaches": means.height,
        "residual_df": residual_df,
        "residual_variance": sigma2,
        "raw_weighted_mom_tau2": raw_tau,
        "truncated_weighted_mom_tau2": max(raw_tau, 0.0),
        "reml_group_mean_tau2": _reml_tau(values, sampling),
        "unweighted_anova_tau2": anova_tau,
        "bootstrap_raw_tau2_low": float(np.quantile(draws, 0.025)),
        "bootstrap_raw_tau2_high": float(np.quantile(draws, 0.975)),
        "classification": "ESTIMATOR_SAMPLE_LIMITATION" if raw_tau <= 0 else "POSITIVE_SENSITIVITY",
    }


def build_variance(q: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    rows = [
        _variance_row(
            q.filter(pl.col("role") == role),
            role,
            "q_development",
            "q_development_signal",
            "exposure_dropbacks",
        )
        for role in ROLES
    ]
    rows.append(_variance_row(pcae, "play_caller", "pcae", "pcae", "attributed_play_count"))
    return pl.DataFrame(rows).sort("signal", "role")


def _common_qp(q: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    q_season = _weighted(
        q.filter(pl.col("role") == "play_caller"),
        "q_development_signal",
        "exposure_dropbacks",
        ["coach_id", "coach_name", "team_id", "season"],
    ).rename({"weight": "q_exposure"})
    p_season = _weighted(
        pcae,
        "pcae",
        "attributed_play_count",
        ["coach_id", "coach_canonical_name", "team_id", "season"],
    ).rename({"coach_canonical_name": "coach_name", "weight": "p_exposure"})
    return q_season.join(
        p_season, on=["coach_id", "coach_name", "team_id", "season"], validate="1:1"
    )


def _history_pairs(common: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in common.sort("season", "coach_id", "team_id").to_dicts():
        history = common.filter(
            (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
        )
        if history.is_empty():
            continue
        rows.append(
            {
                **row,
                "history_q": float(
                    np.average(history["q_development_signal"], weights=history["q_exposure"])
                ),
                "history_p": float(np.average(history["pcae"], weights=history["p_exposure"])),
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def build_fold_matrix(project_root: Path, q: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    common = _common_qp(q, pcae)
    pairs = _history_pairs(common)
    coverage, _ = build_evidence_coverage(project_root)
    pc = coverage.filter(pl.col("role") == "play_caller")
    q_season = _weighted(
        q.filter(pl.col("role") == "play_caller"),
        "q_development_signal",
        "exposure_dropbacks",
        ["coach_id", "team_id", "season"],
    )
    p_season = _weighted(pcae, "pcae", "attributed_play_count", ["coach_id", "team_id", "season"])
    rows: list[dict[str, Any]] = []
    for season in range(2010, 2026):
        q_n = q_season.filter(pl.col("season") == season).height
        p_n = p_season.filter(pl.col("season") == season).height
        common_n = common.filter(pl.col("season") == season).height
        target_n = pairs.filter(pl.col("season") == season).height if not pairs.is_empty() else 0
        train_n = pairs.filter(pl.col("season") < season).height if not pairs.is_empty() else 0
        coverage_counts = {
            row["coverage_status"]: row["len"]
            for row in pc.filter(pl.col("season") == season)
            .group_by("coverage_status")
            .len()
            .to_dicts()
        }
        eligible = target_n >= 2 and train_n >= MIN_JOINT_TRAIN
        if eligible:
            reason = "eligible"
        elif target_n < 2:
            reason = "fewer_than_2_target_history_pairs"
        else:
            reason = f"only_{train_n}_prior_history_pairs_below_{MIN_JOINT_TRAIN}"
        rows.append(
            {
                "season": season,
                "q_available": q_n > 0,
                "q_coach_seasons": q_n,
                "pcae_available": p_n > 0,
                "pcae_coach_seasons": p_n,
                "verified_caller_cells": coverage_counts.get("verified_person", 0),
                "partial_caller_cells": coverage_counts.get("partial", 0),
                "provisional_caller_cells": coverage_counts.get("provisional", 0),
                "unresolved_caller_cells": coverage_counts.get("unresolved", 0),
                "common_qp_rows": common_n,
                "prior_history_target_rows": target_n,
                "prior_training_rows": train_n,
                "eligible_as_training": target_n > 0,
                "eligible_as_target": eligible,
                "reason_excluded": reason,
            }
        )
    return pl.DataFrame(rows)


def _joint_arrays(
    train: pl.DataFrame, score: pl.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Create Candidate A's joint-model arrays using training-only transforms."""

    q_center = float(train["q_development_signal"].mean())
    p_center = float(train["pcae"].mean())
    q_scale = float(train["q_development_signal"].std(ddof=0))
    p_scale = float(train["pcae"].std(ddof=0))
    if q_scale == 0 or p_scale == 0:
        raise ValueError("joint model has a zero-variance training signal")
    train_q = (train["history_q"].to_numpy() - q_center) / q_scale
    train_p = (train["history_p"].to_numpy() - p_center) / p_scale
    score_q = (score["history_q"].to_numpy() - q_center) / q_scale
    score_p = (score["history_p"].to_numpy() - p_center) / p_scale
    y_train = (
        (train["q_development_signal"].to_numpy() - q_center) / q_scale
        + (train["pcae"].to_numpy() - p_center) / p_scale
    ) / 2
    y_score = (
        (score["q_development_signal"].to_numpy() - q_center) / q_scale
        + (score["pcae"].to_numpy() - p_center) / p_scale
    ) / 2
    return train_q, train_p, score_q, score_p, y_train, y_score


def _residual_components(
    train_q: np.ndarray,
    train_p: np.ndarray,
    score_q: np.ndarray,
    score_p: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    q_on_p = LinearRegression().fit(train_p.reshape(-1, 1), train_q)
    p_on_q = LinearRegression().fit(train_q.reshape(-1, 1), train_p)
    train = np.column_stack(
        [
            train_q - q_on_p.predict(train_p.reshape(-1, 1)),
            train_p - p_on_q.predict(train_q.reshape(-1, 1)),
            (train_q + train_p) / 2,
        ]
    )
    score = np.column_stack(
        [
            score_q - q_on_p.predict(score_p.reshape(-1, 1)),
            score_p - p_on_q.predict(score_q.reshape(-1, 1)),
            (score_q + score_p) / 2,
        ]
    )
    return train, score


def _joint_predictions(train: pl.DataFrame, test: pl.DataFrame) -> dict[str, np.ndarray]:
    train_q, train_p, test_q, test_p, y_train, y_test = _joint_arrays(train, test)
    model_1 = Ridge(alpha=10.0).fit(train_q.reshape(-1, 1), y_train)
    model_2 = Ridge(alpha=10.0).fit(train_p.reshape(-1, 1), y_train)
    model_4 = Ridge(alpha=10.0).fit(np.column_stack([train_q, train_p]), y_train)
    train_decomp, test_decomp = _residual_components(train_q, train_p, test_q, test_p)
    model_5 = Ridge(alpha=10.0).fit(train_decomp, y_train)
    return {
        "actual": y_test,
        "model_1_q_only": model_1.predict(test_q.reshape(-1, 1)),
        "model_2_pcae_only": model_2.predict(test_p.reshape(-1, 1)),
        "model_3_equal_q_p": (test_q + test_p) / 2,
        "model_4_learned_joint": model_4.predict(np.column_stack([test_q, test_p])),
        "model_5_overlap_decomposition": model_5.predict(test_decomp),
    }


def build_model_comparison(q: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    """Independently refit Models 1-5 on identical rolling-origin target rows."""

    pairs = _history_pairs(_common_qp(q, pcae))
    prediction_frames: list[pl.DataFrame] = []
    for target in sorted(pairs["season"].unique().to_list()):
        train = pairs.filter(pl.col("season") < target)
        test = pairs.filter(pl.col("season") == target)
        if train.height < MIN_JOINT_TRAIN or test.height < 2:
            continue
        values = _joint_predictions(train, test)
        keys = test.select("coach_id", "team_id", "season").with_columns(
            pl.lit(target).alias("target_season")
        )
        prediction_frames.extend(
            keys.with_columns(
                pl.lit(model).alias("model"),
                pl.Series("actual_future_signal", values["actual"]),
                pl.Series("predicted_future_signal", prediction),
            )
            for model, prediction in values.items()
            if model != "actual"
        )
    future = pl.concat(prediction_frames).sort("model", "target_season", "coach_id", "team_id")
    candidate_models = sorted(future["model"].unique().to_list())
    expected = set(
        future.filter(pl.col("model") == candidate_models[0])
        .select("coach_id", "team_id", "season", "target_season")
        .iter_rows()
    )
    rows: list[dict[str, Any]] = []
    for model in candidate_models:
        frame = future.filter(pl.col("model") == model)
        keys = set(frame.select("coach_id", "team_id", "season", "target_season").iter_rows())
        if keys != expected:
            raise ValueError(f"independent model comparison changes target population: {model}")
        for fold in [*sorted(frame["target_season"].unique().to_list()), None]:
            selected = frame if fold is None else frame.filter(pl.col("target_season") == fold)
            rows.append(
                {
                    "model": model,
                    "fold": "pooled" if fold is None else str(fold),
                    "n": selected.height,
                    "identical_population": True,
                    **_metric_row(
                        selected["actual_future_signal"].to_numpy(),
                        selected["predicted_future_signal"].to_numpy(),
                    ),
                }
            )
    model4 = future.filter(pl.col("model") == "model_4_learned_joint").sort(
        "target_season", "coach_id", "team_id"
    )
    model5 = future.filter(pl.col("model") == "model_5_overlap_decomposition").sort(
        "target_season", "coach_id", "team_id"
    )
    squared4 = (
        model4["actual_future_signal"].to_numpy() - model4["predicted_future_signal"].to_numpy()
    ) ** 2
    squared5 = (
        model5["actual_future_signal"].to_numpy() - model5["predicted_future_signal"].to_numpy()
    ) ** 2
    rng = np.random.default_rng(_seed("model4-v-model5"))
    deltas = []
    for _ in range(BOOTSTRAPS):
        index = rng.integers(0, len(squared4), len(squared4))
        deltas.append(float(np.sqrt(np.mean(squared5[index])) - np.sqrt(np.mean(squared4[index]))))
    rows.append(
        {
            "model": "paired_model5_minus_model4_rmse",
            "fold": "pooled",
            "n": len(squared4),
            "identical_population": True,
            "pearson": None,
            "spearman": None,
            "rmse": float(np.sqrt(np.mean(squared5)) - np.sqrt(np.mean(squared4))),
            "mae": None,
            "direction": None,
            "bootstrap_low": float(np.quantile(deltas, 0.025)),
            "bootstrap_high": float(np.quantile(deltas, 0.975)),
        }
    )
    return pl.DataFrame(rows).sort("model", "fold")


def _fit_joint_weights(frame: pl.DataFrame) -> tuple[float, float]:
    train_q, train_p, _, _, y_train, _ = _joint_arrays(frame, frame)
    model = Ridge(alpha=10.0).fit(np.column_stack([train_q, train_p]), y_train)
    return float(model.coef_[0]), float(model.coef_[1])


def build_weight_stability(
    q: pl.DataFrame, pcae: pl.DataFrame, sources: ReviewSources
) -> list[dict[str, Any]]:
    """Stress-test learned Q/P coefficients without selecting production weights."""

    pairs = _history_pairs(_common_qp(q, pcae))
    qb_membership = (
        q.filter(pl.col("role") == "play_caller")
        .group_by("coach_id", "team_id", "season")
        .agg(pl.col("player_id").unique().sort().alias("player_ids"))
    )
    pairs = pairs.join(
        qb_membership, on=["coach_id", "team_id", "season"], how="left", validate="1:1"
    )
    distributions: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
    target_seasons: list[int] = []
    for target in sorted(pairs["season"].unique().to_list()):
        train = pairs.filter(pl.col("season") < target)
        test = pairs.filter(pl.col("season") == target)
        if train.height >= MIN_JOINT_TRAIN and test.height >= 2:
            distributions["fold"].append(_fit_joint_weights(train))
            target_seasons.append(target)

    reference = pairs.filter(pl.col("season") < max(target_seasons))
    rng = np.random.default_rng(_seed("joint-weight-bootstrap"))
    for _ in range(BOOTSTRAPS):
        index = rng.integers(0, reference.height, reference.height)
        distributions["row_bootstrap"].append(_fit_joint_weights(reference[index]))
    for group_column, label in (("coach_id", "coach_holdout"), ("team_id", "team_holdout")):
        for group in sorted(reference[group_column].unique().to_list()):
            training = reference.filter(pl.col(group_column) != group)
            if training.height >= MIN_JOINT_TRAIN:
                distributions[label].append(_fit_joint_weights(training))
    quarterbacks = sorted(
        {
            player_id
            for player_ids in reference["player_ids"].drop_nulls().to_list()
            for player_id in player_ids
        }
    )
    for player_id in quarterbacks:
        training = reference.filter(
            pl.col("player_ids").is_null() | ~pl.col("player_ids").list.contains(player_id)
        )
        if training.height >= MIN_JOINT_TRAIN:
            distributions["qb_holdout"].append(_fit_joint_weights(training))

    rows: list[dict[str, Any]] = []
    for design, estimates in sorted(distributions.items()):
        array = np.asarray(estimates, dtype=float)
        for index, feature in enumerate(("beta_q", "beta_p")):
            values = array[:, index]
            detail = (
                f"sd={np.std(values, ddof=0):.12f};"
                f"p05={np.quantile(values, 0.05):.12f};"
                f"p95={np.quantile(values, 0.95):.12f};"
                f"negative_share={np.mean(values < 0):.12f}"
            )
            rows.append(
                {
                    "audit": "weight_stability",
                    "role": "play_caller",
                    "metric": f"{design}_{feature}",
                    "n": len(values),
                    "value": float(np.mean(values)),
                    "classification": "insufficient_two_fold_weight_evidence",
                    "detail": detail,
                }
            )
    candidate = pl.read_csv(
        sources.candidate_root / "weights.csv", infer_schema_length=None
    ).filter(pl.col("model") == "model_4_learned_joint")
    independent = {
        (target, feature): coefficient
        for target, estimates in zip(target_seasons, distributions["fold"], strict=True)
        for feature, coefficient in zip(("history_q", "history_p"), estimates, strict=True)
    }
    differences = [
        abs(row["coefficient"] - independent[(row["target_season"], row["feature"])])
        for row in candidate.to_dicts()
    ]
    rows.append(
        {
            "audit": "weight_stability",
            "role": "play_caller",
            "metric": "candidate_a_max_absolute_coefficient_reproduction_error",
            "n": len(differences),
            "value": max(differences),
            "classification": "independently_reproduced",
            "detail": f"eligible_target_seasons={'|'.join(map(str, target_seasons))}",
        }
    )
    return rows


def _group_for_portability(
    frame: pl.DataFrame, signal: str, exposure: str, group: str
) -> pl.DataFrame:
    return _weighted(frame, signal, exposure, ["coach_id", group, "season"])


def _future_portability(
    frame: pl.DataFrame,
    *,
    role: str,
    signal_name: str,
    signal: str,
    exposure: str,
    group: str,
) -> tuple[dict[str, Any], pl.DataFrame]:
    grouped = _group_for_portability(frame, signal, exposure, group)
    records: list[dict[str, Any]] = []
    for row in grouped.to_dicts():
        history = grouped.filter(
            (pl.col("coach_id") == row["coach_id"])
            & (pl.col("season") < row["season"])
            & (pl.col(group) != row[group])
        )
        if history.is_empty():
            continue
        records.append(
            {
                "coach_id": row["coach_id"],
                group: row[group],
                "season": row["season"],
                "actual": row[signal],
                "prediction": float(np.average(history[signal], weights=history["weight"])),
            }
        )
    predictions = pl.DataFrame(records) if records else pl.DataFrame()
    metrics = (
        _metric_row(predictions["actual"].to_numpy(), predictions["prediction"].to_numpy())
        if not predictions.is_empty()
        else _metric_row(np.asarray([]), np.asarray([]))
    )
    boot: list[float] = []
    if not predictions.is_empty():
        coach_ids = sorted(predictions["coach_id"].unique().to_list())
        rng = np.random.default_rng(_seed(f"portability:{signal_name}:{role}:{group}"))
        for _ in range(BOOTSTRAPS):
            selected = rng.choice(coach_ids, len(coach_ids), replace=True)
            left: list[float] = []
            right: list[float] = []
            for coach in selected:
                part = predictions.filter(pl.col("coach_id") == coach)
                left.extend(part["actual"].to_list())
                right.extend(part["prediction"].to_list())
            value = _pearson(left, right)
            if value is not None:
                boot.append(value)
    return (
        {
            "record_type": "chronological_portability",
            "signal": signal_name,
            "role": role,
            "dimension": group,
            "n": predictions.height,
            **metrics,
            "bootstrap_low": float(np.quantile(boot, 0.025)) if boot else None,
            "bootstrap_high": float(np.quantile(boot, 0.975)) if boot else None,
            "chronology": "prior_seasons_other_group_only",
        },
        predictions,
    )


def _all_time_portability(
    frame: pl.DataFrame,
    *,
    role: str,
    signal_name: str,
    signal: str,
    exposure: str,
    group: str,
    aggregate_pair: bool,
) -> dict[str, Any]:
    seasonal = _group_for_portability(frame, signal, exposure, group)
    group_totals = seasonal.group_by("coach_id", group).agg(
        ((pl.col(signal) * pl.col("weight")).sum() / pl.col("weight").sum()).alias("actual"),
        (pl.col(signal) * pl.col("weight")).sum().alias("weighted_total"),
        pl.col("weight").sum().alias("group_weight"),
    )
    coach_totals = seasonal.group_by("coach_id").agg(
        (pl.col(signal) * pl.col("weight")).sum().alias("coach_total"),
        pl.col("weight").sum().alias("coach_weight"),
        pl.col(group).n_unique().alias("distinct_groups"),
    )
    if aggregate_pair:
        scored = (
            group_totals.join(coach_totals, on="coach_id", validate="m:1")
            .filter(pl.col("distinct_groups") >= 2)
            .with_columns(
                (
                    (pl.col("coach_total") - pl.col("weighted_total"))
                    / (pl.col("coach_weight") - pl.col("group_weight"))
                ).alias("prediction")
            )
        )
        record_type = "leave_one_coach_group_pair_out_all_time"
    else:
        scored = (
            seasonal.join(group_totals, on=["coach_id", group], validate="m:1")
            .join(coach_totals, on="coach_id", validate="m:1")
            .filter(pl.col("distinct_groups") >= 2)
            .with_columns(
                (
                    (pl.col("coach_total") - pl.col("weighted_total"))
                    / (pl.col("coach_weight") - pl.col("group_weight"))
                ).alias("prediction"),
                pl.col(signal).alias("actual_season"),
            )
        )
        scored = scored.rename({"actual": "pair_actual", "actual_season": "actual"})
        record_type = "leave_one_group_out_all_time"
    metrics = _metric_row(scored["actual"].to_numpy(), scored["prediction"].to_numpy())
    return {
        "record_type": record_type,
        "signal": signal_name,
        "role": role,
        "dimension": group,
        "n": scored.height,
        **metrics,
        "chronology": "not_chronological_future_rows_can_enter_history",
    }


def _placebo_portability(
    grouped: pl.DataFrame,
    observed: float | None,
    *,
    signal: str,
    group: str,
    label: str,
) -> dict[str, Any]:
    rng = np.random.default_rng(_seed(f"placebo:{label}"))
    ordered = grouped.sort("season", "coach_id", group)
    seasons = ordered["season"].to_numpy()
    coaches = ordered["coach_id"].to_numpy().astype(str)
    groups = ordered[group].to_numpy().astype(str)
    values = ordered[signal].to_numpy().astype(float)
    weights = ordered["weight"].to_numpy().astype(float)

    def chronological_correlation(labels: np.ndarray) -> float | None:
        coach_totals: defaultdict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        group_totals: defaultdict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        actual: list[float] = []
        predicted: list[float] = []
        for season in np.unique(seasons):
            indices = np.flatnonzero(seasons == season)
            for index in indices:
                coach_id = str(labels[index])
                key = (coach_id, str(groups[index]))
                remaining_weight = coach_totals[coach_id][1] - group_totals[key][1]
                if remaining_weight > 0:
                    actual.append(float(values[index]))
                    predicted.append(
                        (coach_totals[coach_id][0] - group_totals[key][0]) / remaining_weight
                    )
            for index in indices:
                coach_id = str(labels[index])
                key = (coach_id, str(groups[index]))
                coach_totals[coach_id][0] += float(values[index] * weights[index])
                coach_totals[coach_id][1] += float(weights[index])
                group_totals[key][0] += float(values[index] * weights[index])
                group_totals[key][1] += float(weights[index])
        return _pearson(actual, predicted)

    nulls: list[float] = []
    for _ in range(PERMUTATIONS):
        permuted = coaches.copy()
        for season in np.unique(seasons):
            index = np.flatnonzero(seasons == season)
            permuted[index] = rng.permutation(permuted[index])
        value = chronological_correlation(permuted)
        if value is not None:
            nulls.append(value)
    return {
        "record_type": "placebo",
        "signal": label.split(":")[0],
        "role": label.split(":")[1],
        "dimension": group,
        "n": len(nulls),
        "pearson": observed,
        "spearman": None,
        "rmse": None,
        "mae": None,
        "direction": None,
        "bootstrap_low": None,
        "bootstrap_high": None,
        "chronology": "within_season_label_permutation_preserves_rows_teams_exposure",
        "observed_percentile": float(np.mean(np.asarray(nulls) <= observed))
        if nulls and observed is not None
        else None,
        "empirical_p_value": float((1 + np.sum(np.asarray(nulls) >= observed)) / (len(nulls) + 1))
        if nulls and observed is not None
        else None,
    }


def build_portability(q: pl.DataFrame, pcae: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for role in ROLES:
        role_q = q.filter(pl.col("role") == role)
        for group in ("player_id", "team_id"):
            summary, _ = _future_portability(
                role_q,
                role=role,
                signal_name="q",
                signal="q_development_signal",
                exposure="exposure_dropbacks",
                group=group,
            )
            rows.append(summary)
            if group == "player_id":
                rows.append(
                    _all_time_portability(
                        role_q,
                        role=role,
                        signal_name="q",
                        signal="q_development_signal",
                        exposure="exposure_dropbacks",
                        group=group,
                        aggregate_pair=False,
                    )
                )
                rows.append(
                    _all_time_portability(
                        role_q,
                        role=role,
                        signal_name="q",
                        signal="q_development_signal",
                        exposure="exposure_dropbacks",
                        group=group,
                        aggregate_pair=True,
                    )
                )
            grouped = _group_for_portability(
                role_q, "q_development_signal", "exposure_dropbacks", group
            )
            rows.append(
                _placebo_portability(
                    grouped,
                    summary["pearson"],
                    signal="q_development_signal",
                    group=group,
                    label=f"q:{role}",
                )
            )
    p_summary, _ = _future_portability(
        pcae,
        role="play_caller",
        signal_name="pcae",
        signal="pcae",
        exposure="attributed_play_count",
        group="team_id",
    )
    rows.append(p_summary)
    rows.append(
        _placebo_portability(
            _group_for_portability(pcae, "pcae", "attributed_play_count", "team_id"),
            p_summary["pearson"],
            signal="pcae",
            group="team_id",
            label="pcae:play_caller",
        )
    )
    common = _common_qp(q, pcae).with_columns(
        ((pl.col("q_development_signal") + pl.col("pcae")) / 2).alias("equal_q_p"),
        pl.min_horizontal("q_exposure", "p_exposure").alias("equal_exposure"),
    )
    equal, _ = _future_portability(
        common,
        role="play_caller",
        signal_name="equal_q_p",
        signal="equal_q_p",
        exposure="equal_exposure",
        group="team_id",
    )
    rows.append(equal)
    return pl.DataFrame(rows).sort("record_type", "signal", "role", "dimension")


def load_scheme_sources() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Capture approved nflverse participation and FTN rows once per review execution."""

    participation = nflreadpy.load_participation(list(range(2016, 2026))).select(
        "nflverse_game_id", "play_id", "offense_personnel"
    )
    ftn = nflreadpy.load_ftn_charting(list(range(2022, 2026))).select(
        "season",
        "nflverse_game_id",
        "nflverse_play_id",
        "is_motion",
        "is_play_action",
        "is_screen_pass",
        "is_rpo",
    )
    return (
        participation.sort("nflverse_game_id", "play_id"),
        ftn.sort("season", "nflverse_game_id", "nflverse_play_id"),
    )


def _scheme_fingerprints(
    sources: ReviewSources,
    participation: pl.DataFrame,
    ftn: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    frames: list[pl.DataFrame] = []
    for season in range(2010, 2026):
        path = sources.pbp_root / f"season={season}/play_by_play.parquet"
        frame = pl.read_parquet(
            path,
            columns=[
                "game_id",
                "play_id",
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
        frames.append(frame)
    plays = pl.concat(frames).with_columns(
        pl.col("play_id").cast(pl.Int64),
        pl.col("posteam").map_elements(_canonical_team, return_dtype=pl.String).alias("team_id"),
    )
    part = participation.rename({"nflverse_game_id": "game_id"}).with_columns(
        pl.col("play_id").cast(pl.Int64),
        pl.col("offense_personnel").str.extract(r"(\d+) RB", 1).cast(pl.Int8).alias("rb"),
        pl.col("offense_personnel").str.extract(r"(\d+) TE", 1).cast(pl.Int8).alias("te"),
    )
    if part.select("game_id", "play_id").n_unique() != part.height:
        raise ValueError("participation source has duplicate play keys")
    chart = ftn.rename({"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"}).with_columns(
        pl.col("play_id").cast(pl.Int64)
    )
    chart = chart.drop("season")
    if chart.select("game_id", "play_id").n_unique() != chart.height:
        raise ValueError("FTN source has duplicate play keys")
    merged = (
        plays.join(part, on=["game_id", "play_id"], how="left", validate="1:1")
        .join(chart, on=["game_id", "play_id"], how="left", validate="1:1")
        .with_columns(
            ((pl.col("rb") == 1) & (pl.col("te") == 1)).cast(pl.Float64).alias("personnel_11"),
            ((pl.col("rb") == 1) & (pl.col("te") == 2)).cast(pl.Float64).alias("personnel_12"),
            ((pl.col("rb") == 2) & (pl.col("te") == 1)).cast(pl.Float64).alias("personnel_21"),
        )
    )
    fingerprints = (
        merged.group_by("team_id", "season")
        .agg(
            pl.col("personnel_11").mean().alias("personnel_11_rate"),
            pl.col("personnel_12").mean().alias("personnel_12_rate"),
            pl.col("personnel_21").mean().alias("personnel_21_rate"),
            pl.col("shotgun").cast(pl.Float64).mean().alias("shotgun_rate"),
            pl.col("is_motion").cast(pl.Float64).mean().alias("motion_rate"),
            pl.col("is_play_action").cast(pl.Float64).mean().alias("play_action_rate"),
            pl.col("is_screen_pass").cast(pl.Float64).mean().alias("screen_rate"),
            pl.col("is_rpo").cast(pl.Float64).mean().alias("rpo_rate"),
            pl.col("no_huddle").cast(pl.Float64).mean().alias("no_huddle_rate"),
            pl.when(pl.col("down").is_in([1, 2]))
            .then((pl.col("play_type") == "pass").cast(pl.Float64))
            .otherwise(None)
            .mean()
            .alias("early_down_pass_rate"),
            pl.len().alias("eligible_scheme_plays"),
        )
        .sort("season", "team_id")
    )
    specs = [
        (
            "personnel_11_rate",
            "participation.offense_personnel",
            "2016-2025",
            "1 RB and 1 TE share of charted plays",
            True,
        ),
        (
            "personnel_12_rate",
            "participation.offense_personnel",
            "2016-2025",
            "1 RB and 2 TE share of charted plays",
            True,
        ),
        (
            "personnel_21_rate",
            "participation.offense_personnel",
            "2016-2025",
            "2 RB and 1 TE share of charted plays",
            True,
        ),
        (
            "shotgun_rate",
            "pbp.shotgun",
            "2010-2025",
            "mean shotgun indicator on regular-season run/pass plays",
            True,
        ),
        ("motion_rate", "ftn.is_motion", "2022-2025", "mean explicit FTN motion indicator", True),
        (
            "play_action_rate",
            "ftn.is_play_action",
            "2022-2025",
            "mean explicit FTN play-action indicator",
            True,
        ),
        (
            "screen_rate",
            "ftn.is_screen_pass",
            "2022-2025",
            "mean explicit FTN screen-pass indicator",
            True,
        ),
        ("rpo_rate", "ftn.is_rpo", "2022-2025", "mean explicit FTN RPO indicator", True),
        (
            "no_huddle_rate",
            "pbp.no_huddle",
            "2010-2025",
            "mean no-huddle indicator on regular-season run/pass plays",
            True,
        ),
        (
            "early_down_pass_rate",
            "pbp.play_type,down",
            "2010-2025",
            "pass share on first and second down",
            True,
        ),
    ]
    availability: list[dict[str, Any]] = []
    for feature, fields, seasons, definition, buildable in specs:
        first, last = map(int, seasons.split("-"))
        eligible = merged.filter(pl.col("season").is_between(first, last))
        source_column = {
            "personnel_11_rate": "personnel_11",
            "personnel_12_rate": "personnel_12",
            "personnel_21_rate": "personnel_21",
            "shotgun_rate": "shotgun",
            "motion_rate": "is_motion",
            "play_action_rate": "is_play_action",
            "screen_rate": "is_screen_pass",
            "rpo_rate": "is_rpo",
            "no_huddle_rate": "no_huddle",
            "early_down_pass_rate": "down",
        }[feature]
        availability.append(
            {
                "feature": feature,
                "source_fields": fields,
                "available_seasons": seasons,
                "coverage_rate": float(eligible[source_column].is_not_null().mean()),
                "definition": definition,
                "deterministically_buildable": buildable,
                "new_in_review": feature not in BASE_SCHEME_FEATURES,
                "limitation": "coverage-window-specific; missing outside listed seasons",
            }
        )
    return fingerprints, pl.DataFrame(availability)


def _role_coach_seasons(assignments: pl.DataFrame, role: str) -> pl.DataFrame:
    if role in ROLES:
        source = assignments.filter(pl.col("role") == role)
    elif role == "oc_and_verified_play_caller":
        left = assignments.filter(pl.col("role") == "offensive_coordinator")
        callers = (
            assignments.filter(pl.col("role") == "play_caller")
            .select("coach_id", "canonical_team_id", "season")
            .unique()
        )
        source = left.join(callers, on=["coach_id", "canonical_team_id", "season"], how="inner")
    elif role == "hc_and_verified_play_caller":
        left = assignments.filter(pl.col("role") == "head_coach")
        callers = (
            assignments.filter(pl.col("role") == "play_caller")
            .select("coach_id", "canonical_team_id", "season")
            .unique()
        )
        source = left.join(callers, on=["coach_id", "canonical_team_id", "season"], how="inner")
    else:
        raise ValueError(role)
    return (
        source.group_by("coach_id", "season")
        .agg(pl.col("canonical_team_id").unique().alias("teams"))
        .filter(pl.col("teams").list.len() == 1)
        .with_columns(pl.col("teams").list.first().alias("team_id"))
        .drop("teams")
    )


def build_scheme_results(assignments: pl.DataFrame, fingerprints: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    role_labels = (
        "head_coach",
        "offensive_coordinator",
        "play_caller",
        "oc_and_verified_play_caller",
        "hc_and_verified_play_caller",
    )
    rng = np.random.default_rng(_seed("scheme-specificity"))
    for role in role_labels:
        coach_seasons = _role_coach_seasons(assignments, role)
        prior = coach_seasons.select(
            "coach_id", (pl.col("season") + 1).alias("season"), pl.col("team_id").alias("from_team")
        )
        moves = coach_seasons.join(prior, on=["coach_id", "season"]).filter(
            pl.col("team_id") != pl.col("from_team")
        )
        adoptions: list[float] = []
        persistences: list[float] = []
        placebo: list[float] = []
        coach_move_counts: defaultdict[str, int] = defaultdict(int)
        feature_values: defaultdict[str, list[float]] = defaultdict(list)
        for move in moves.sort("season", "coach_id").to_dicts():
            season = move["season"]
            old = fingerprints.filter(
                (pl.col("team_id") == move["from_team"]) & (pl.col("season") == season - 1)
            )
            before = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season - 1)
            )
            after = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season)
            )
            if old.height != 1 or before.height != 1 or after.height != 1:
                continue
            usable = [
                feature
                for feature in SCHEME_FEATURES
                if old[feature][0] is not None
                and before[feature][0] is not None
                and after[feature][0] is not None
            ]
            if len(usable) < 3:
                continue
            history = fingerprints.filter(pl.col("season") < season).select(usable)
            center = np.asarray(history.mean().row(0), dtype=float)
            scale = np.asarray(history.std(ddof=0).row(0), dtype=float)
            valid = scale > 0
            if valid.sum() < 3:
                continue
            old_v = (np.asarray(old.select(usable).row(0), dtype=float) - center)[valid] / scale[
                valid
            ]
            before_v = (np.asarray(before.select(usable).row(0), dtype=float) - center)[
                valid
            ] / scale[valid]
            after_v = (np.asarray(after.select(usable).row(0), dtype=float) - center)[
                valid
            ] / scale[valid]
            adoption = float(np.linalg.norm(before_v - old_v) - np.linalg.norm(after_v - old_v))
            adoptions.append(adoption)
            coach_move_counts[move["coach_id"]] += 1
            for feature in usable:
                feature_values[feature].append(
                    abs(float(before[feature][0]) - float(old[feature][0]))
                    - abs(float(after[feature][0]) - float(old[feature][0]))
                )
            next_year = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season + 1)
            )
            retained = coach_seasons.filter(
                (pl.col("coach_id") == move["coach_id"])
                & (pl.col("team_id") == move["team_id"])
                & (pl.col("season") == season + 1)
            ).height
            if (
                retained
                and next_year.height == 1
                and all(next_year[f][0] is not None for f in usable)
            ):
                next_v = (np.asarray(next_year.select(usable).row(0), dtype=float) - center)[
                    valid
                ] / scale[valid]
                persistences.append(
                    float(np.linalg.norm(before_v - old_v) - np.linalg.norm(next_v - old_v))
                )
            candidates = fingerprints.filter(
                (pl.col("season") == season - 1)
                & ~pl.col("team_id").is_in([move["from_team"], move["team_id"]])
            )
            if candidates.height:
                pick = candidates.row(int(rng.integers(0, candidates.height)), named=True)
                values = np.asarray([pick[f] for f in usable], dtype=float)
                if np.isfinite(values).all():
                    random_v = (values - center)[valid] / scale[valid]
                    placebo.append(
                        float(
                            np.linalg.norm(before_v - random_v) - np.linalg.norm(after_v - random_v)
                        )
                    )
        rows.append(
            {
                "record_type": "scheme_role_summary",
                "role": role,
                "feature": "all_available_for_move",
                "moves": len(adoptions),
                "positive_adoption_share": float(np.mean(np.asarray(adoptions) > 0))
                if adoptions
                else None,
                "mean_adoption": float(np.mean(adoptions)) if adoptions else None,
                "same_era_placebo_mean": float(np.mean(placebo)) if placebo else None,
                "specificity_delta": float(np.mean(adoptions) - np.mean(placebo))
                if adoptions and placebo
                else None,
                "persistence_observations": len(persistences),
                "mean_year2_adoption": float(np.mean(persistences)) if persistences else None,
                "retention_percentage": float(np.mean(np.asarray(persistences) > 0))
                if persistences
                else None,
                "coaches_with_multiple_moves": sum(
                    value >= 2 for value in coach_move_counts.values()
                ),
                "multiple_move_coach_ids": "|".join(
                    sorted(key for key, value in coach_move_counts.items() if value >= 2)
                ),
            }
        )
        for feature, values in sorted(feature_values.items()):
            rows.append(
                {
                    "record_type": "scheme_trait_summary",
                    "role": role,
                    "feature": feature,
                    "moves": len(values),
                    "positive_adoption_share": float(np.mean(np.asarray(values) > 0)),
                    "mean_adoption": float(np.mean(values)),
                }
            )
    return pl.DataFrame(rows).sort("record_type", "role", "feature")


def _scheme_distance(left: np.ndarray, right: np.ndarray, method: str) -> float:
    if method == "standardized_euclidean":
        return float(np.linalg.norm(left - right))
    if method == "manhattan":
        return float(np.abs(left - right).sum())
    if method == "cosine":
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return 1.0 - float(np.dot(left, right) / denominator) if denominator else 0.0
    if method == "correlation":
        value = _pearson(left, right)
        return 1.0 - value if value is not None else 1.0
    raise ValueError(method)


def build_expanded_scheme_results(
    assignments: pl.DataFrame, fingerprints: pl.DataFrame
) -> pl.DataFrame:
    """Audit all role-owner moves using every feature available for each move."""

    rows: list[dict[str, Any]] = []
    methods = ("standardized_euclidean", "manhattan", "cosine", "correlation")
    role_labels = (
        "head_coach",
        "offensive_coordinator",
        "play_caller",
        "oc_and_verified_play_caller",
        "hc_and_verified_play_caller",
    )
    rng = np.random.default_rng(_seed("expanded-scheme-specificity"))
    for role in role_labels:
        coach_seasons = _role_coach_seasons(assignments, role)
        prior = coach_seasons.select(
            "coach_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("team_id").alias("from_team"),
        )
        moves = coach_seasons.join(prior, on=["coach_id", "season"]).filter(
            pl.col("team_id") != pl.col("from_team")
        )
        actual: defaultdict[str, list[float]] = defaultdict(list)
        placebo_sums = {method: np.zeros(PERMUTATIONS, dtype=float) for method in methods}
        specificity_actual: defaultdict[str, list[float]] = defaultdict(list)
        persistence: defaultdict[str, list[float]] = defaultdict(list)
        trait: defaultdict[str, list[float]] = defaultdict(list)
        trait_persistence: defaultdict[str, list[float]] = defaultdict(list)
        coach_counts: defaultdict[str, int] = defaultdict(int)
        for move in moves.sort("season", "coach_id").to_dicts():
            season = move["season"]
            old = fingerprints.filter(
                (pl.col("team_id") == move["from_team"]) & (pl.col("season") == season - 1)
            )
            before = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season - 1)
            )
            after = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season)
            )
            if old.height != 1 or before.height != 1 or after.height != 1:
                continue
            usable = [
                feature
                for feature in SCHEME_FEATURES
                if all(frame[feature][0] is not None for frame in (old, before, after))
            ]
            if len(usable) < 3:
                continue
            history = fingerprints.filter(pl.col("season") < season).select(usable)
            center = np.asarray(history.mean().row(0), dtype=float)
            scale = np.asarray(history.std(ddof=0).row(0), dtype=float)
            valid = scale > 0
            if valid.sum() < 3:
                continue

            def vector(
                frame: pl.DataFrame,
                columns: tuple[str, ...] = tuple(usable),
                center_values: np.ndarray = center,
                scale_values: np.ndarray = scale,
                valid_mask: np.ndarray = valid,
            ) -> np.ndarray:
                values = np.asarray(frame.select(columns).row(0), dtype=float)
                return ((values - center_values) / scale_values)[valid_mask]

            old_v, before_v, after_v = vector(old), vector(before), vector(after)
            next_year = fingerprints.filter(
                (pl.col("team_id") == move["team_id"]) & (pl.col("season") == season + 1)
            )
            retained = bool(
                coach_seasons.filter(
                    (pl.col("coach_id") == move["coach_id"])
                    & (pl.col("team_id") == move["team_id"])
                    & (pl.col("season") == season + 1)
                ).height
            )
            move_adoption: dict[str, float] = {}
            for method in methods:
                adoption = _scheme_distance(before_v, old_v, method) - _scheme_distance(
                    after_v, old_v, method
                )
                move_adoption[method] = adoption
                actual[method].append(adoption)
                rows.append(
                    {
                        "record_type": "scheme_move",
                        "role": role,
                        "feature": "all_available_for_move",
                        "method": method,
                        "coach_id": move["coach_id"],
                        "season": season,
                        "from_team_id": move["from_team"],
                        "to_team_id": move["team_id"],
                        "moves": 1,
                        "mean_adoption": adoption,
                        "retained_next_season": retained,
                    }
                )
            for feature in usable:
                trait[feature].append(
                    abs(float(before[feature][0]) - float(old[feature][0]))
                    - abs(float(after[feature][0]) - float(old[feature][0]))
                )
            coach_counts[move["coach_id"]] += 1
            if (
                retained
                and next_year.height == 1
                and all(next_year[feature][0] is not None for feature in usable)
            ):
                next_v = vector(next_year)
                for method in methods:
                    persistence[method].append(
                        _scheme_distance(before_v, old_v, method)
                        - _scheme_distance(next_v, old_v, method)
                    )
                for feature in usable:
                    trait_persistence[feature].append(
                        abs(float(before[feature][0]) - float(old[feature][0]))
                        - abs(float(next_year[feature][0]) - float(old[feature][0]))
                    )
            candidates = fingerprints.filter(
                (pl.col("season") == season - 1)
                & ~pl.col("team_id").is_in([move["from_team"], move["team_id"]])
            ).drop_nulls(usable)
            if candidates.height:
                for draw, index in enumerate(rng.integers(0, candidates.height, PERMUTATIONS)):
                    random_v = vector(candidates.slice(int(index), 1))
                    for method in methods:
                        placebo_sums[method][draw] += _scheme_distance(
                            before_v, random_v, method
                        ) - _scheme_distance(after_v, random_v, method)
                for method in methods:
                    specificity_actual[method].append(move_adoption[method])
        multiple = sorted(coach for coach, count in coach_counts.items() if count >= 2)
        for method in methods:
            observed = actual[method]
            specificity_observed = specificity_actual[method]
            nulls = (
                placebo_sums[method] / len(specificity_observed)
                if specificity_observed
                else np.asarray([], dtype=float)
            )
            observed_specificity_mean = (
                float(np.mean(specificity_observed)) if specificity_observed else None
            )
            rows.append(
                {
                    "record_type": "scheme_role_summary",
                    "role": role,
                    "feature": "all_available_for_move",
                    "method": method,
                    "moves": len(observed),
                    "positive_adoption_share": (
                        float(np.mean(np.asarray(observed) > 0)) if observed else None
                    ),
                    "mean_adoption": float(np.mean(observed)) if observed else None,
                    "specificity_moves": len(specificity_observed),
                    "same_era_placebo_mean": float(np.mean(nulls)) if len(nulls) else None,
                    "specificity_delta": (
                        observed_specificity_mean - float(np.mean(nulls))
                        if observed_specificity_mean is not None and len(nulls)
                        else None
                    ),
                    "specificity_empirical_p": (
                        float((1 + np.sum(nulls >= observed_specificity_mean)) / (len(nulls) + 1))
                        if observed_specificity_mean is not None and len(nulls)
                        else None
                    ),
                    "persistence_observations": len(persistence[method]),
                    "mean_year2_adoption": (
                        float(np.mean(persistence[method])) if persistence[method] else None
                    ),
                    "retention_percentage": (
                        float(np.mean(np.asarray(persistence[method]) > 0))
                        if persistence[method]
                        else None
                    ),
                    "coaches_with_multiple_moves": len(multiple),
                    "multiple_move_coach_ids": "|".join(multiple),
                }
            )
        for feature, values in sorted(trait.items()):
            rows.append(
                {
                    "record_type": "scheme_trait_summary",
                    "role": role,
                    "feature": feature,
                    "method": "absolute_trait_distance",
                    "moves": len(values),
                    "positive_adoption_share": float(np.mean(np.asarray(values) > 0)),
                    "mean_adoption": float(np.mean(values)),
                }
            )
        for feature, values in sorted(trait_persistence.items()):
            rows.append(
                {
                    "record_type": "scheme_trait_persistence",
                    "role": role,
                    "feature": feature,
                    "method": "absolute_trait_distance",
                    "moves": len(values),
                    "positive_adoption_share": float(np.mean(np.asarray(values) > 0)),
                    "mean_adoption": float(np.mean(values)),
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None).sort(
        "record_type", "role", "feature", "method"
    )


def _eligible_play_counts(sources: ReviewSources) -> pl.DataFrame:
    rows: list[pl.DataFrame] = []
    for season in range(2010, 2026):
        raw = pl.read_parquet(
            sources.pbp_root / f"season={season}/play_by_play.parquet", columns=list(PBP_COLUMNS)
        )
        eligible, _ = prepare_historical_plays(raw)
        rows.append(
            eligible.group_by("season", "team_id", "week").len().rename({"len": "eligible_plays"})
        )
    return pl.concat(rows).sort("season", "team_id", "week")


def build_priority_and_simulation(
    project_root: Path,
    sources: ReviewSources,
    pae: pl.DataFrame,
    q: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    coverage, _ = build_evidence_coverage(project_root)
    cells = coverage.filter(
        (pl.col("role") == "play_caller") & (pl.col("coverage_status") != "verified_person")
    )
    reviews = pl.read_csv(
        project_root / "data/manual/coaching_review_queue.csv", infer_schema_length=None
    )
    reviews = (
        reviews.filter((pl.col("role") == "play_caller") & (pl.col("status") == "open"))
        .group_by("season", "team_id")
        .agg(
            pl.col("candidate_names")
            .drop_nulls()
            .unique()
            .sort()
            .str.join("|")
            .alias("existing_candidate"),
            pl.col("source_url")
            .drop_nulls()
            .unique()
            .sort()
            .str.join("|")
            .alias("existing_source"),
            pl.col("issue_type").unique().sort().str.join("|").alias("missing_requirement"),
        )
    )
    eligible_by_week = _eligible_play_counts(sources)
    existing_common_cells = (
        q.filter(pl.col("role") == "play_caller")
        .select(
            "season",
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase().alias("team_id"),
        )
        .unique()
    )
    movement, _ = _fit_movement(pae)
    potential_q_cells = movement.select(
        "season",
        pl.col("team_id").str.strip_prefix("team_").str.to_uppercase().alias("team_id"),
    ).unique()
    verified_callers = _assignments(project_root).filter(pl.col("role") == "play_caller")
    verified_weeks: defaultdict[tuple[int, str], set[int]] = defaultdict(set)
    for row in verified_callers.to_dicts():
        verified_weeks[(row["season"], row["team_id"])].update(
            range(row["start_week"], row["end_week"] + 1)
        )
    verified_names = set(
        _assignments(project_root)
        .filter(pl.col("role") == "play_caller")["coach_name"]
        .str.to_lowercase()
        .to_list()
    )
    priority = (
        cells.join(reviews, on=["season", "team_id"], how="left", validate="1:1")
        .join(
            existing_common_cells.with_columns(pl.lit(True).alias("already_common_qp")),
            on=["season", "team_id"],
            how="left",
            validate="1:1",
        )
        .join(
            potential_q_cells.with_columns(pl.lit(True).alias("potential_q_available")),
            on=["season", "team_id"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("already_common_qp").fill_null(False),
            pl.col("potential_q_available").fill_null(False),
        )
    )

    def recoverability(row: dict[str, Any]) -> str:
        if row["coverage_status"] == "partial":
            return "AMBIGUOUS / SHARED"
        if row["coverage_status"] == "provisional":
            return "LIKELY ARCHIVAL VERIFICATION"
        if row.get("existing_candidate") and row.get("existing_source"):
            return "EASY WEB VERIFICATION"
        if row.get("existing_candidate") or row.get("existing_source"):
            return "LIKELY ARCHIVAL VERIFICATION"
        return "NO EXPLICIT EVIDENCE FOUND"

    records: list[dict[str, Any]] = []
    season_verified = {
        row["season"]: row["len"]
        for row in coverage.filter(
            (pl.col("role") == "play_caller") & (pl.col("coverage_status") == "verified_person")
        )
        .group_by("season")
        .len()
        .to_dicts()
    }
    for row in priority.to_dicts():
        candidates = [
            item.strip().lower()
            for item in (row.get("existing_candidate") or "").split("|")
            if item.strip()
        ]
        repeat_unlock = any(item in verified_names for item in candidates)
        missing_plays = eligible_by_week.filter(
            (pl.col("season") == row["season"])
            & (pl.col("team_id") == row["team_id"])
            & ~pl.col("week").is_in(sorted(verified_weeks[(row["season"], row["team_id"])]))
        )["eligible_plays"].sum()
        unlocks_common = row["potential_q_available"] and not row["already_common_qp"]
        early_fold = int(row["season"] <= 2023)
        score = (
            (800 if unlocks_common else 0)
            + (400 if repeat_unlock else 0)
            + (300 if early_fold else 0)
            + (200 if season_verified.get(row["season"], 0) < 10 else 0)
            + min(int(missing_plays or 0) // 10, 199)
        )
        records.append(
            {
                "season": row["season"],
                "team_id": row["team_id"],
                "current_status": row["coverage_status"],
                "existing_candidate": row.get("existing_candidate"),
                "existing_source": row.get("existing_source") or row.get("source_urls"),
                "missing_requirement": row.get("missing_requirement")
                or "explicit_week_bounded_play_caller_evidence",
                "estimated_recoverability": recoverability(row),
                "eligible_plays": int(missing_plays or 0),
                "already_common_qp": row["already_common_qp"],
                "potential_q_available": row["potential_q_available"],
                "unlocks_common_qp": unlocks_common,
                "repeat_caller_unlock": repeat_unlock,
                "priority_score": score,
                "statistical_reason": "|".join(
                    value
                    for value, enabled in (
                        ("unlocks_common_qp_coach_season", unlocks_common),
                        ("extends_verified_interval", row["already_common_qp"]),
                        ("extends_repeat_caller", repeat_unlock),
                        ("adds_earlier_training_history", bool(early_fold)),
                        ("high_play_volume", (row.get("eligible_plays") or 0) >= 900),
                    )
                    if enabled
                ),
            }
        )
    ranked = (
        pl.DataFrame(records)
        .sort(
            "priority_score",
            "eligible_plays",
            "season",
            "team_id",
            descending=[True, True, False, False],
        )
        .with_row_index("priority_rank", offset=1)
    )
    verified_current = coverage.filter(
        (pl.col("role") == "play_caller") & (pl.col("coverage_status") == "verified_person")
    ).height
    total = 512
    simulation: list[dict[str, Any]] = []
    for target_percent in (40, 50, 60, 75, 90):
        target = math.ceil(total * target_percent / 100)
        needed = max(target - verified_current, 0)
        selected = ranked.head(needed)
        known = selected.filter(pl.col("existing_candidate").is_not_null())
        simulation.append(
            {
                "target_verification_percent": target_percent,
                "target_verified_cells": target,
                "additional_cells_selected": needed,
                "estimated_additional_eligible_plays": int(
                    selected["eligible_plays"].fill_null(0).sum()
                ),
                "known_candidate_cells": known.height,
                "estimated_repeat_caller_cells": selected.filter(
                    pl.col("repeat_caller_unlock")
                ).height,
                "estimated_common_qp_candidate_cells": selected.filter(
                    pl.col("unlocks_common_qp")
                ).height,
                "estimated_new_target_seasons": selected.filter(pl.col("unlocks_common_qp"))
                .select("season")
                .n_unique(),
                "pcae_values_fabricated": False,
                "note": (
                    "availability upper bound; PCAE is computed only after evidence "
                    "verification and play attribution"
                ),
            }
        )
    return ranked, pl.DataFrame(simulation)


def build_power() -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    z_alpha = float(norm.ppf(0.975))
    z_power = float(norm.ppf(0.8))
    for correlation in (0.2, 0.3, 0.4):
        n = math.ceil(((z_alpha + z_power) / np.arctanh(correlation)) ** 2 + 3)
        rows.append(
            {
                "analysis": "correlation_power",
                "target_correlation": correlation,
                "alpha": 0.05,
                "power": 0.8,
                "approximate_independent_n": n,
                "minimum_target_folds": None,
                "minimum_target_rows": None,
                "limitation": (
                    "Fisher-z assumes independent observations; clustered coach/QB/team "
                    "rows require more data"
                ),
            }
        )
    rows.append(
        {
            "analysis": "learned_weight_stability_rule",
            "target_correlation": None,
            "alpha": None,
            "power": None,
            "approximate_independent_n": None,
            "minimum_target_folds": 5,
            "minimum_target_rows": 150,
            "limitation": (
                "design threshold, not a formal power guarantee; require stable signs "
                "under coach/team/QB resampling"
            ),
        }
    )
    return pl.DataFrame(rows)


def build_corrected_results(
    q: pl.DataFrame,
    pcae: pl.DataFrame,
    joined: pl.DataFrame,
    scheme_results: pl.DataFrame,
    model_comparison: pl.DataFrame,
    pae: pl.DataFrame,
    team_statistics: pl.DataFrame,
    weight_stability: list[dict[str, Any]],
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = list(weight_stability)
    for role in ROLES:
        role_rows = q.filter(pl.col("role") == role)
        base = _weighted(
            role_rows, "q_development_signal", "exposure_dropbacks", ["coach_id", "season"]
        )
        prior = base.select(
            "coach_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("q_development_signal").alias("prior"),
        )
        pairs = base.join(prior, on=["coach_id", "season"])
        rows.append(
            {
                "audit": "q_aggregation_sensitivity",
                "role": role,
                "metric": "weighted_transition_residual_repeatability",
                "n": pairs.height,
                "value": _pearson(pairs["prior"], pairs["q_development_signal"]),
                "classification": "aggregation_sensitive_not_production_ready",
            }
        )
        shrunken = base.with_columns(
            (pl.col("q_development_signal") * pl.col("weight") / (pl.col("weight") + 400.0)).alias(
                "shrunken_q"
            )
        )
        prior_s = shrunken.select(
            "coach_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("shrunken_q").alias("prior"),
        )
        pairs_s = shrunken.join(prior_s, on=["coach_id", "season"])
        rows.append(
            {
                "audit": "q_aggregation_sensitivity",
                "role": role,
                "metric": "shrinkage_aware_q_k400_repeatability",
                "n": pairs_s.height,
                "value": _pearson(pairs_s["prior"], pairs_s["shrunken_q"]),
                "classification": "aggregation_sensitive_not_production_ready",
            }
        )
        raw = role_rows.with_columns(
            (pl.col("coach_interval_pae") - pl.col("prior_pae")).alias("raw_pae_delta")
        )
        raw = _weighted(raw, "raw_pae_delta", "exposure_dropbacks", ["coach_id", "season"])
        prior_raw = raw.select(
            "coach_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("raw_pae_delta").alias("prior"),
        )
        pairs_raw = raw.join(prior_raw, on=["coach_id", "season"])
        rows.append(
            {
                "audit": "q_aggregation_sensitivity",
                "role": role,
                "metric": "dropback_weighted_raw_pae_delta_repeatability",
                "n": pairs_raw.height,
                "value": _pearson(pairs_raw["prior"], pairs_raw["raw_pae_delta"]),
                "classification": "aggregation_sensitive_not_production_ready",
            }
        )
        unweighted = role_rows.group_by("coach_id", "season").agg(
            pl.col("q_development_signal").mean()
        )
        prior_u = unweighted.select(
            "coach_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("q_development_signal").alias("prior"),
        )
        pairs_u = unweighted.join(prior_u, on=["coach_id", "season"])
        rows.append(
            {
                "audit": "q_aggregation_sensitivity",
                "role": role,
                "metric": "unweighted_transition_residual_repeatability",
                "n": pairs_u.height,
                "value": _pearson(pairs_u["prior"], pairs_u["q_development_signal"]),
                "classification": "aggregation_sensitive_not_production_ready",
            }
        )
    # Reinterpret environment as stability of the estimated signal, not predictive improvement.
    for role in ROLES:
        role_rows = q.filter(pl.col("role") == role)
        records: list[dict[str, Any]] = []
        for row in role_rows.sort("season", "coach_id", "player_id").to_dicts():
            history = role_rows.filter(
                (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
            )
            if history.height:
                records.append(
                    {
                        **row,
                        "coach_history": float(
                            np.average(
                                history["q_development_signal"],
                                weights=history["exposure_dropbacks"],
                            )
                        ),
                    }
                )
        frame = pl.DataFrame(records) if records else pl.DataFrame()
        predictions: list[tuple[float, float]] = []
        if not frame.is_empty():
            for target in sorted(frame["season"].unique().to_list()):
                train = frame.filter(pl.col("season") < target)
                test = frame.filter(pl.col("season") == target)
                if train.height < 30 or test.is_empty():
                    continue
                values: list[np.ndarray] = []
                for features in (("coach_history",), ("coach_history", *ENVIRONMENT_FEATURES)):
                    model = Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                            ("scale", StandardScaler()),
                            ("ridge", Ridge(alpha=10.0)),
                        ]
                    )
                    model.fit(
                        train.select(features).cast(pl.Float64).to_numpy(),
                        train["q_development_signal"].to_numpy(),
                        ridge__sample_weight=train["exposure_dropbacks"].to_numpy(),
                    )
                    values.append(model.predict(test.select(features).cast(pl.Float64).to_numpy()))
                predictions.extend(zip(values[0], values[1], strict=True))
        if predictions:
            plain = np.asarray([x[0] for x in predictions])
            context = np.asarray([x[1] for x in predictions])
            rows.extend(
                [
                    {
                        "audit": "environment_stability",
                        "role": role,
                        "metric": "pearson_effect_stability",
                        "n": len(plain),
                        "value": _pearson(plain, context),
                        "classification": "robustness_not_prediction_gate",
                    },
                    {
                        "audit": "environment_stability",
                        "role": role,
                        "metric": "spearman_rank_stability",
                        "n": len(plain),
                        "value": _spearman(plain, context),
                        "classification": "robustness_not_prediction_gate",
                    },
                    {
                        "audit": "environment_stability",
                        "role": role,
                        "metric": "sign_stability",
                        "n": len(plain),
                        "value": float(np.mean(np.sign(plain) == np.sign(context))),
                        "classification": "robustness_not_prediction_gate",
                    },
                ]
            )
    delta = model_comparison.filter(pl.col("model") == "paired_model5_minus_model4_rmse").row(
        0, named=True
    )
    rows.append(
        {
            "audit": "model_4_vs_5",
            "role": "play_caller",
            "metric": "paired_rmse_difference",
            "n": delta["n"],
            "value": delta["rmse"],
            "classification": "practically_negligible_two_fold_difference",
        }
    )
    summaries = scheme_results.filter(pl.col("record_type") == "scheme_role_summary")
    for item in summaries.to_dicts():
        method = item["method"]
        common = {
            "audit": "scheme_portability",
            "role": item["role"],
            "classification": "exploratory_partial_coverage",
        }
        for metric, n, value in (
            (f"mean_adoption_{method}", item["moves"], item["mean_adoption"]),
            (
                f"specificity_delta_{method}",
                item["specificity_moves"],
                item["specificity_delta"],
            ),
            (
                f"specificity_empirical_p_{method}",
                item["specificity_moves"],
                item["specificity_empirical_p"],
            ),
            (
                f"year2_mean_adoption_{method}",
                item["persistence_observations"],
                item["mean_year2_adoption"],
            ),
            (
                f"year2_positive_share_{method}",
                item["persistence_observations"],
                item["retention_percentage"],
            ),
        ):
            rows.append({**common, "metric": metric, "n": n, "value": value})
        if method == "standardized_euclidean":
            rows.append(
                {
                    **common,
                    "metric": "coaches_with_multiple_moves",
                    "n": item["moves"],
                    "value": item["coaches_with_multiple_moves"],
                    "detail": item["multiple_move_coach_ids"],
                }
            )

    for item in scheme_results.filter(
        pl.col("record_type").is_in(["scheme_trait_summary", "scheme_trait_persistence"])
    ).to_dicts():
        period = "year1" if item["record_type"] == "scheme_trait_summary" else "year2"
        rows.append(
            {
                "audit": "scheme_portability",
                "role": item["role"],
                "metric": f"trait_{item['feature']}_{period}_mean_adoption",
                "n": item["moves"],
                "value": item["mean_adoption"],
                "classification": "exploratory_partial_coverage",
            }
        )

    # A retained coach's move-season scheme adoption is compared with the destination
    # team's following-season result. These are exploratory associations, not causal
    # effects or production score inputs.
    future_team_pae = _weighted(
        pae,
        "performance_above_expectation",
        "dropbacks",
        ["team_id", "season"],
    ).select(
        "team_id",
        "season",
        pl.col("performance_above_expectation").alias("future_pae"),
    )
    future_q = _weighted(
        q,
        "q_development_signal",
        "exposure_dropbacks",
        ["role", "coach_id", "team_id", "season"],
    ).select(
        "role",
        "coach_id",
        "team_id",
        "season",
        pl.col("q_development_signal").alias("future_q"),
    )
    future_pcae = _weighted(
        pcae,
        "pcae",
        "attributed_play_count",
        ["coach_id", "team_id", "season"],
    ).select(
        "coach_id",
        "team_id",
        "season",
        pl.col("pcae").alias("future_pcae"),
    )
    future_offense = team_statistics.select(
        "team_id", "season", pl.col("team_offensive_epa_per_play").alias("future_offensive_epa")
    )
    moves = (
        scheme_results.filter(
            (pl.col("record_type") == "scheme_move") & pl.col("retained_next_season")
        )
        .select(
            "role",
            "method",
            "coach_id",
            pl.col("to_team_id").alias("team_id"),
            (pl.col("season") + 1).alias("season"),
            pl.col("mean_adoption").alias("scheme_adoption"),
        )
        .with_columns(
            pl.when(
                pl.col("role").is_in(["oc_and_verified_play_caller", "hc_and_verified_play_caller"])
            )
            .then(pl.lit("play_caller"))
            .otherwise(pl.col("role"))
            .alias("q_role")
        )
    )
    for (role, method), move_rows in moves.group_by("role", "method"):
        base = (
            move_rows.join(future_team_pae, on=["team_id", "season"], how="left", validate="m:1")
            .join(future_offense, on=["team_id", "season"], how="left", validate="m:1")
            .join(
                future_q,
                left_on=["q_role", "coach_id", "team_id", "season"],
                right_on=["role", "coach_id", "team_id", "season"],
                how="left",
                validate="m:1",
            )
            .join(
                future_pcae,
                on=["coach_id", "team_id", "season"],
                how="left",
                validate="m:1",
            )
        )
        for outcome in ("future_pae", "future_q", "future_pcae", "future_offensive_epa"):
            available = base.drop_nulls(["scheme_adoption", outcome])
            enough_rows = available.height >= 3
            for correlation_name, value in (
                ("pearson", _pearson(available["scheme_adoption"], available[outcome])),
                ("spearman", _spearman(available["scheme_adoption"], available[outcome])),
            ):
                rows.append(
                    {
                        "audit": "scheme_future_association",
                        "role": role,
                        "metric": f"{outcome}_{method}_{correlation_name}",
                        "n": available.height,
                        "value": value if enough_rows else None,
                        "classification": (
                            "exploratory_retained_coach_next_season_association"
                            if enough_rows
                            else "suppressed_fewer_than_3_moves"
                        ),
                    }
                )
    return pl.DataFrame(rows, infer_schema_length=None).sort("audit", "role", "metric")


def build_roadmap() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "priority": 1,
                "workstream": "play_caller_verification",
                "action": (
                    "Verify the ranked top-25 cells first with explicit weekly/in-season "
                    "evidence; preserve shared and unresolved intervals."
                ),
                "rerun_gate": (
                    "at least 50% verified cells, five target folds, and 150 common future rows"
                ),
            },
            {
                "priority": 2,
                "workstream": "scheme_features",
                "action": (
                    "Materialize approved participation personnel for 2016-2025 and FTN "
                    "motion/play-action/screen/RPO for 2022-2025 with source hashes."
                ),
                "rerun_gate": (
                    "coverage audits pass and role-owner samples are large enough for "
                    "caller-specific moves"
                ),
            },
            {
                "priority": 3,
                "workstream": "pae_q_development",
                "action": (
                    "Retain leakage-safe PAE and interval Q; add history only through "
                    "newly verified assignments, never same-season/future context."
                ),
                "rerun_gate": (
                    "chronological different-QB and different-team intervals exclude zero"
                ),
            },
            {
                "priority": 4,
                "workstream": "model",
                "action": (
                    "Do not revisit final weights, shrinkage, 0-100 mapping, or rankings "
                    "before the evidence gates above pass."
                ),
                "rerun_gate": "stable coefficient signs under fold, coach, team, and QB resampling",
            },
        ]
    )


def _frame_digest(frame: pl.DataFrame, sort_by: list[str]) -> str:
    ordered = frame.sort(sort_by)
    payload = ordered.write_csv(line_terminator="\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(
    project_root: Path,
    sources: ReviewSources,
    participation: pl.DataFrame,
    ftn: pl.DataFrame,
) -> dict[str, Any]:
    manual = {
        str(path.relative_to(project_root)): _file_digest(path)
        for path in sorted((project_root / "data/manual").glob("*.csv"))
    }
    source_files = {
        str(path.relative_to(project_root)): _file_digest(path)
        for path in (
            sources.pae_path,
            sources.games_path,
            sources.environment_path,
            sources.team_statistics_path,
            sources.pcae_path,
            sources.candidate_root / "future_validation.csv",
            project_root / "research/coach_effect/checkpoint_twelve_review.py",
        )
    }
    source_files["nflverse:participation:2016-2025"] = _frame_digest(
        participation, ["nflverse_game_id", "play_id"]
    )
    source_files["nflverse:ftn:2022-2025"] = _frame_digest(
        ftn, ["season", "nflverse_game_id", "nflverse_play_id"]
    )
    return {
        "specification": REVIEW_SPECIFICATION,
        "candidate_version": CANDIDATE_VERSION,
        "production_load_id": PRODUCTION_LOAD_ID,
        "parameters": {
            "random_seed": RANDOM_SEED,
            "permutations": PERMUTATIONS,
            "bootstraps": BOOTSTRAPS,
            "min_q_exposure": MIN_Q_EXPOSURE,
            "min_joint_train": MIN_JOINT_TRAIN,
        },
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
            "nflreadpy": nflreadpy.__version__,
        },
        "manual_inputs": manual,
        "source_inputs": source_files,
    }


def _write_csv(frame: pl.DataFrame, path: Path, version: str) -> None:
    if "review_version" not in frame.columns:
        frame = frame.with_columns(pl.lit(version).alias("review_version"))
    float_columns = [
        name for name, dtype in frame.schema.items() if dtype in (pl.Float32, pl.Float64)
    ]
    if float_columns:
        frame = frame.with_columns(pl.col(float_columns).round(12))
    frame.write_csv(path, line_terminator="\n", float_scientific=False)


def run_checkpoint_twelve_review(
    project_root: Path,
    output_root: Path | None = None,
    *,
    scheme_sources: tuple[pl.DataFrame, pl.DataFrame] | None = None,
) -> dict[str, Any]:
    """Build the independent review into a content-addressed, research-only directory."""

    sources = _sources(project_root)
    participation, ftn = scheme_sources or load_scheme_sources()
    identity = _identity(project_root, sources, participation, ftn)
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    version = f"c12-review-{digest}"
    root = output_root or project_root / "research/coach_effect/outputs/checkpoint_12_review"
    target = root / version
    staging = root / f".{version}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    pae, assignments, joined, q, pcae, movement_folds = build_independent_core(
        project_root, sources
    )
    fingerprints, scheme_availability = _scheme_fingerprints(sources, participation, ftn)
    scheme_results = build_expanded_scheme_results(assignments, fingerprints)
    model_comparison = build_model_comparison(q, pcae)
    weight_stability = build_weight_stability(q, pcae, sources)
    priority, simulation = build_priority_and_simulation(project_root, sources, pae, q)
    outputs = {
        "grain_audit.csv": build_grain_audit(project_root, sources, pae, assignments, joined, pcae),
        "qp_overlap_reconciliation.csv": build_overlap(q, pcae, pae),
        "variance_audit.csv": build_variance(q, pcae),
        "fold_availability_matrix.csv": build_fold_matrix(project_root, q, pcae),
        "model_comparison_identical_folds.csv": model_comparison,
        "portability_audit.csv": build_portability(q, pcae),
        "scheme_feature_availability.csv": scheme_availability,
        "play_caller_verification_priority.csv": priority,
        "sample_expansion_simulation.csv": simulation,
        "power_analysis.csv": build_power(),
        "corrected_results.csv": build_corrected_results(
            q,
            pcae,
            joined,
            scheme_results,
            model_comparison,
            pae,
            pl.read_parquet(sources.team_statistics_path),
            weight_stability,
        ),
        "data_expansion_roadmap.csv": build_roadmap(),
    }
    for name in OUTPUT_NAMES:
        _write_csv(outputs[name], staging / name, version)
    manifest = {
        "review_version": version,
        "identity": identity,
        "candidate_a_preserved": True,
        "production_changed": False,
        "outputs": {name: _file_digest(staging / name) for name in OUTPUT_NAMES},
        "movement_fold_count": movement_folds.height,
    }
    (staging / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if target.exists():
        existing = {path.name: _file_digest(path) for path in target.iterdir() if path.is_file()}
        candidate = {path.name: _file_digest(path) for path in staging.iterdir() if path.is_file()}
        if existing != candidate:
            raise ValueError(f"existing review version differs: {version}")
        shutil.rmtree(staging)
    else:
        staging.replace(target)
    if output_root is None:
        (root / "LATEST").write_text(version + "\n", encoding="utf-8")
    return {"review_version": version, "output_path": str(target), "outputs": OUTPUT_NAMES}

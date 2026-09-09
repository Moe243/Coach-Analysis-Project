"""Prompt 11 research-only review of the play-caller coverage gate.

This module evaluates whether the historical 50% full-cell rule is an appropriate
prerequisite for another Coach Effect architecture research run. It consumes the frozen
Prompt 10 evidence state, performs no evidence promotion, and fits no final equation.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import scipy
import sklearn
from scipy.stats import rankdata, spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from research.coach_effect.checkpoint_eleven import (
    PBP_COLUMNS,
    _sha256,
    _write_csv,
    prepare_historical_plays,
)
from research.coach_effect.checkpoint_twelve_data_expansion import _add_research_contract
from research.coach_effect.checkpoint_twelve_final_play_caller_evidence import (
    PROMPT9_VERSION,
    build_assignments,
    load_and_validate_prompt10_evidence,
)
from research.coach_effect.checkpoint_twelve_play_caller_verification import build_q_availability

PROMPT10_VERSION = "c12-pc-final-cac923f086757e5b"
PROMPT11_SPECIFICATION = "checkpoint-twelve-coverage-gate-methodology-review-v1"
RANDOM_SEED = 20260908
BOOTSTRAPS = 500

# Design requirements are declared independently of the observed correlations. They concern
# coverage, temporal validation, replication, and resampling feasibility, not desired signs.
RESEARCH_GATE_POLICY = {
    "recent_start_season": 2020,
    "minimum_recent_full_cell_rate": 0.90,
    "minimum_recent_play_rate": 0.90,
    "minimum_credible_folds": 5,
    "minimum_target_rows_per_fold": 20,
    "minimum_prior_training_rows_per_fold": 20,
    "minimum_target_play_rate": 0.80,
    "minimum_total_future_rows": 150,
    "minimum_credible_target_rows": 125,
    "minimum_recent_common_rows": 150,
    "minimum_recent_consecutive_pairs": 75,
    "minimum_recent_different_qb_pairs": 60,
    "minimum_recent_different_team_pairs": 15,
    "minimum_repeat_callers": 50,
    "minimum_successful_bootstraps": 475,
}
PRODUCTION_GATE_POLICY = {
    "minimum_claimed_window_full_cell_rate": 0.95,
    "minimum_claimed_window_play_rate": 0.95,
    "provisional_or_shared_individual_attribution_allowed": False,
}

OUTPUT_NAMES = (
    "coverage_denominator_comparison.csv",
    "verified_interval_coverage.csv",
    "play_weighted_coverage.csv",
    "era_coverage.csv",
    "missingness_diagnostics.csv",
    "selection_bias_diagnostics.csv",
    "inverse_probability_sensitivity.csv",
    "missing_data_stress_test.csv",
    "temporal_window_sensitivity.csv",
    "leave_era_out_results.csv",
    "fold_quality_analysis.csv",
    "cluster_aware_precision.csv",
    "candidate_gate_comparison.csv",
    "final_methodology_decision.csv",
)


@dataclass(frozen=True)
class Prompt11Result:
    output_path: Path
    data_version: str
    decision: pl.DataFrame


def _prompt10_root(project_root: Path) -> Path:
    root = project_root / "research/coach_effect/outputs/checkpoint_12_final_play_caller_evidence"
    if (root / "LATEST").read_text(encoding="utf-8").strip() != PROMPT10_VERSION:
        raise ValueError("Prompt 11 requires the frozen Prompt 10 research baseline")
    version = root / PROMPT10_VERSION
    if not version.is_dir():
        raise ValueError("Prompt 10 output directory is missing")
    return version


def _era(season: int) -> str:
    if season <= 2014:
        return "2010-2014"
    if season <= 2019:
        return "2015-2019"
    if season <= 2022:
        return "2020-2022"
    return "2023-2025"


def _pearson(left: Any, right: Any, weights: Any | None = None) -> float | None:
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if len(x) < 2:
        return None
    if weights is None:
        if np.std(x) == 0 or np.std(y) == 0:
            return None
        return float(np.corrcoef(x, y)[0, 1])
    w = np.asarray(weights, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[keep], y[keep], w[keep]
    if len(x) < 2 or w.sum() <= 0:
        return None
    mx = float(np.average(x, weights=w))
    my = float(np.average(y, weights=w))
    vx = float(np.average((x - mx) ** 2, weights=w))
    vy = float(np.average((y - my) ** 2, weights=w))
    if vx <= 0 or vy <= 0:
        return None
    covariance = float(np.average((x - mx) * (y - my), weights=w))
    return covariance / math.sqrt(vx * vy)


def _spearman(left: Any, right: Any, weights: Any | None = None) -> float | None:
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return None
    if weights is None:
        return float(spearmanr(x, y).statistic)
    return _pearson(rankdata(x), rankdata(y), weights)


def _direction(left: Any, right: Any, weights: Any | None = None) -> float | None:
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if not len(x):
        return None
    match = (np.sign(x) == np.sign(y)).astype(float)
    return float(match.mean()) if weights is None else float(np.average(match, weights=weights))


def _load_prompt10(project_root: Path) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    root = _prompt10_root(project_root)
    coverage = pl.read_csv(root / "play_caller_completeness.csv").drop(
        "research_data_version", "research_only", "production_ranking"
    )
    pcae = pl.read_csv(root / "historical_pcae.csv").drop(
        "research_data_version", "research_only", "production_ranking"
    )
    common = pl.read_csv(root / "common_qp_availability.csv").drop(
        "research_data_version", "research_only", "production_ranking"
    )
    if coverage.height != 512 or coverage.select("season", "team_id").n_unique() != 512:
        raise ValueError("Prompt 10 coverage is not the complete 512-cell matrix")
    if pcae.filter((pl.col("verification_status") != "verified") | pl.col("is_shared")).height:
        raise ValueError("Prompt 10 PCAE includes provisional, unresolved, or shared attribution")
    if common.select("coach_id", "team_id", "season").n_unique() != common.height:
        raise ValueError("Prompt 10 common Q/P grain is not unique")
    return coverage, pcae, common


def _assignment_frame(project_root: Path) -> pl.DataFrame:
    cells, intervals, _ = load_and_validate_prompt10_evidence(project_root)
    return pl.DataFrame(
        build_assignments(project_root, cells, intervals), infer_schema_length=None
    ).with_columns(
        pl.col("season", "start_week", "end_week").cast(pl.Int64),
        (pl.col("is_shared") == "true").alias("shared"),
    )


def build_verified_interval_coverage(
    coverage: pl.DataFrame, pcae: pl.DataFrame, assignments: pl.DataFrame
) -> pl.DataFrame:
    """Separate full-cell status from usable source-bounded interval evidence."""

    bounded = assignments.filter(
        (pl.col("role") == "play_caller")
        & (pl.col("verification_status") == "verified")
        & (pl.col("interval_basis") != "season_designation")
    )
    individually_usable = bounded.filter(~pl.col("shared"))
    pcae_keys = pcae.select("coach_id", "team_id", "season", "start_week", "end_week").unique()
    assignment_keys = individually_usable.select(
        "coach_id", "team_id", "season", "start_week", "end_week"
    ).unique()
    if pcae_keys.join(
        assignment_keys,
        on=["coach_id", "team_id", "season", "start_week", "end_week"],
        how="anti",
    ).height:
        raise ValueError("PCAE attribution lacks a matching usable verified interval")
    cells_with_attribution = (
        pcae.select("season", "team_id")
        .unique()
        .join(
            coverage.select("season", "team_id", "ending_status"),
            on=["season", "team_id"],
            validate="1:1",
        )
    )
    if cells_with_attribution.filter(
        pl.col("ending_status").is_in(["provisional", "unresolved"])
    ).height:
        raise ValueError("provisional or unresolved cells were attributed")
    grouped = (
        pcae.join(
            coverage.select("season", "team_id", "ending_status"),
            on=["season", "team_id"],
            validate="m:1",
        )
        .group_by("ending_status")
        .agg(
            pl.struct("season", "team_id").n_unique().alias("cells_with_usable_intervals"),
            pl.len().alias("individually_attributable_intervals"),
            pl.col("attributed_play_count").sum().alias("attributed_plays"),
        )
        .sort("ending_status")
    )
    totals = pl.DataFrame(
        [
            {
                "ending_status": "ALL_USABLE",
                "cells_with_usable_intervals": cells_with_attribution.height,
                "individually_attributable_intervals": individually_usable.height,
                "attributed_plays": int(pcae["attributed_play_count"].sum()),
            },
            {
                "ending_status": "ALL_SOURCE_BACKED_INCLUDING_SHARED",
                "cells_with_usable_intervals": bounded.select("season", "team_id").n_unique(),
                "individually_attributable_intervals": bounded.height,
                "attributed_plays": int(pcae["attributed_play_count"].sum()),
            },
        ]
    )
    return pl.concat([grouped, totals], how="vertical_relaxed")


def _eligible_play_counts(project_root: Path) -> tuple[pl.DataFrame, dict[str, str]]:
    historical = project_root / "data/processed/historical"
    version = (historical / "LATEST").read_text(encoding="utf-8").strip()
    pbp_root = historical / version / "bronze/play_by_play"
    rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for season in range(2010, 2026):
        path = pbp_root / f"season={season}" / "play_by_play.parquet"
        prepared, audit = prepare_historical_plays(pl.read_parquet(path, columns=PBP_COLUMNS))
        hashes[str(path.relative_to(project_root))] = _sha256(path)
        for row in prepared.group_by("team_id").len(name="eligible_plays").to_dicts():
            rows.append({"season": season, **row})
        if (
            sum(row["eligible_plays"] for row in rows if row["season"] == season)
            != audit["eligible_plays"]
        ):
            raise ValueError(f"eligible-play reconciliation failed for {season}")
    return pl.DataFrame(rows).sort("season", "team_id"), hashes


def build_play_weighted_coverage(
    eligible: pl.DataFrame, pcae: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    attributed = pcae.group_by("season", "team_id").agg(
        pl.col("attributed_play_count").sum().alias("verified_attributable_plays")
    )
    season = (
        eligible.join(attributed, on=["season", "team_id"], how="left")
        .with_columns(pl.col("verified_attributable_plays").fill_null(0))
        .group_by("season")
        .agg(
            pl.col("eligible_plays").sum(),
            pl.col("verified_attributable_plays").sum(),
        )
        .with_columns(
            (pl.col("verified_attributable_plays") / pl.col("eligible_plays")).alias(
                "verified_attributable_play_rate"
            ),
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era"),
        )
        .sort("season")
    )
    era = (
        season.group_by("era")
        .agg(
            pl.col("eligible_plays").sum(),
            pl.col("verified_attributable_plays").sum(),
        )
        .with_columns(
            (pl.col("verified_attributable_plays") / pl.col("eligible_plays")).alias(
                "verified_attributable_play_rate"
            )
        )
        .sort("era")
    )
    overall = pl.DataFrame(
        [
            {
                "era": "2010-2025",
                "eligible_plays": int(season["eligible_plays"].sum()),
                "verified_attributable_plays": int(season["verified_attributable_plays"].sum()),
                "verified_attributable_play_rate": float(
                    season["verified_attributable_plays"].sum() / season["eligible_plays"].sum()
                ),
            },
            {
                "era": "2020-2025",
                "eligible_plays": int(
                    season.filter(pl.col("season") >= 2020)["eligible_plays"].sum()
                ),
                "verified_attributable_plays": int(
                    season.filter(pl.col("season") >= 2020)["verified_attributable_plays"].sum()
                ),
                "verified_attributable_play_rate": float(
                    season.filter(pl.col("season") >= 2020)["verified_attributable_plays"].sum()
                    / season.filter(pl.col("season") >= 2020)["eligible_plays"].sum()
                ),
            },
        ]
    )
    return season, pl.concat([era, overall], how="vertical_relaxed")


def _consecutive_pairs(common: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for group in common.partition_by("coach_id", as_dict=False):
        by_season = {int(row["season"]): row for row in group.to_dicts()}
        for season, current in sorted(by_season.items()):
            prior = by_season.get(season - 1)
            if prior is None:
                continue
            prior_players = set(str(prior["player_ids"]).split("|"))
            current_players = set(str(current["player_ids"]).split("|"))
            rows.append(
                {
                    "coach_id": current["coach_id"],
                    "prior_season": season - 1,
                    "season": season,
                    "prior_team_id": prior["team_id"],
                    "team_id": current["team_id"],
                    "prior_player_ids": prior["player_ids"],
                    "player_ids": current["player_ids"],
                    "prior_q": prior["q_development_signal"],
                    "current_q": current["q_development_signal"],
                    "prior_p": prior["pcae"],
                    "current_p": current["pcae"],
                    "different_qb": prior_players != current_players,
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
        "prior_q": pl.Float64,
        "current_q": pl.Float64,
        "prior_p": pl.Float64,
        "current_p": pl.Float64,
        "different_qb": pl.Boolean,
        "different_team": pl.Boolean,
    }
    return pl.DataFrame(rows, schema=schema).sort("season", "coach_id", "team_id")


def _core_summary(label: str, common: pl.DataFrame) -> dict[str, Any]:
    common = common.sort("season", "coach_id", "team_id")
    pairs = _consecutive_pairs(common)
    different_qb = pairs.filter(pl.col("different_qb"))
    different_team = pairs.filter(pl.col("different_team"))
    return {
        "analysis": label,
        "common_qp_rows": common.height,
        "seasons": common["season"].n_unique(),
        "coaches": common["coach_id"].n_unique(),
        "teams": common["team_id"].n_unique(),
        "quarterback_observations": int(common["quarterbacks"].sum()),
        "repeat_callers": common.group_by("coach_id").len().filter(pl.col("len") >= 2).height,
        "consecutive_pairs": pairs.height,
        "different_qb_pairs": different_qb.height,
        "different_team_pairs": different_team.height,
        "q_p_pearson": _pearson(common["q_development_signal"], common["pcae"]),
        "q_p_spearman": _spearman(common["q_development_signal"], common["pcae"]),
        "q_repeatability_pearson": _pearson(pairs["prior_q"], pairs["current_q"]),
        "q_repeatability_direction": _direction(pairs["prior_q"], pairs["current_q"]),
        "p_repeatability_pearson": _pearson(pairs["prior_p"], pairs["current_p"]),
        "p_repeatability_direction": _direction(pairs["prior_p"], pairs["current_p"]),
        "q_different_qb_pearson": _pearson(different_qb["prior_q"], different_qb["current_q"]),
        "p_different_qb_pearson": _pearson(different_qb["prior_p"], different_qb["current_p"]),
        "q_different_team_pearson": _pearson(
            different_team["prior_q"], different_team["current_q"]
        ),
        "p_different_team_pearson": _pearson(
            different_team["prior_p"], different_team["current_p"]
        ),
    }


def build_temporal_sensitivity(common: pl.DataFrame) -> pl.DataFrame:
    return pl.DataFrame(
        [
            _core_summary(f"{start}-2025", common.filter(pl.col("season") >= start))
            for start in (2010, 2016, 2020, 2021)
        ],
        infer_schema_length=None,
    )


def build_leave_era_out(common: pl.DataFrame) -> pl.DataFrame:
    policies = (
        ("leave_2010_2014_out", ~pl.col("season").is_between(2010, 2014)),
        ("leave_2015_2019_out", ~pl.col("season").is_between(2015, 2019)),
        ("leave_2010_2019_out", pl.col("season") >= 2020),
    )
    return pl.DataFrame(
        [_core_summary(label, common.filter(predicate)) for label, predicate in policies],
        infer_schema_length=None,
    )


def _cell_structure(
    project_root: Path, coverage: pl.DataFrame, assignments: pl.DataFrame
) -> pl.DataFrame:
    supporting = assignments.filter(pl.col("role") != "play_caller")
    structure = supporting.group_by("season", "team_id").agg(
        (pl.col("verification_status") == "verified")
        .sum()
        .alias("verified_supporting_assignments"),
        pl.col("assignment_key").len().alias("supporting_assignment_count"),
    )
    caller = assignments.filter(pl.col("role") == "play_caller")
    repeated_ids = set(
        caller.select("coach_id", "season", "team_id")
        .unique()
        .group_by("coach_id")
        .len()
        .filter(pl.col("len") >= 2)["coach_id"]
        .to_list()
    )
    caller_counts = caller.group_by("season", "team_id").agg(
        pl.len().alias("named_caller_intervals"),
        pl.col("coach_id").n_unique().alias("named_caller_identities"),
        pl.col("coach_id").is_in(repeated_ids).any().cast(pl.Int8).alias("repeated_named_caller"),
    )
    primary: dict[str, pl.DataFrame] = {}
    for role, prefix in (("head_coach", "hc"), ("offensive_coordinator", "oc")):
        primary[prefix] = (
            supporting.filter(
                (pl.col("role") == role) & (pl.col("verification_status") == "verified")
            )
            .group_by("season", "team_id")
            .agg(pl.col("coach_id").unique().sort().str.join("|").alias(f"{prefix}_ids"))
        )
    frame = (
        coverage.select("season", "team_id", "ending_status")
        .join(structure, on=["season", "team_id"], how="left")
        .join(caller_counts, on=["season", "team_id"], how="left")
        .join(primary["hc"], on=["season", "team_id"], how="left")
        .join(primary["oc"], on=["season", "team_id"], how="left")
        .with_columns(
            pl.col(
                "verified_supporting_assignments",
                "supporting_assignment_count",
                "named_caller_intervals",
                "named_caller_identities",
                "repeated_named_caller",
            ).fill_null(0),
            pl.col("hc_ids", "oc_ids").fill_null(""),
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era"),
            (pl.col("season") >= 2020).cast(pl.Int8).alias("modern_era"),
            (pl.col("ending_status") == "verified").cast(pl.Int8).alias("is_verified"),
        )
    )
    prior = frame.select(
        (pl.col("season") + 1).alias("season"),
        "team_id",
        pl.col("hc_ids").alias("prior_hc_ids"),
        pl.col("oc_ids").alias("prior_oc_ids"),
    )
    return (
        frame.join(prior, on=["season", "team_id"], how="left")
        .with_columns(
            (
                (pl.col("hc_ids") != "")
                & (pl.col("hc_ids") == pl.col("prior_hc_ids").fill_null("__missing__"))
            )
            .cast(pl.Int8)
            .alias("head_coach_continuity"),
            (
                (pl.col("oc_ids") != "")
                & (pl.col("oc_ids") == pl.col("prior_oc_ids").fill_null("__missing__"))
            )
            .cast(pl.Int8)
            .alias("oc_continuity"),
            (pl.col("named_caller_identities") > 0).cast(pl.Int8).alias("named_caller_known"),
            (pl.col("named_caller_intervals") > 1).cast(pl.Int8).alias("multi_interval_structure"),
        )
        .sort("season", "team_id")
    )


def _propensity(structure: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    teams = sorted(structure["team_id"].unique().to_list())
    eras = sorted(structure["era"].unique().to_list())
    rows = structure.to_dicts()
    matrix: list[list[float]] = []
    for row in rows:
        values = [
            (float(row["season"]) - 2017.5) / 5.0,
            float(row["verified_supporting_assignments"]),
            float(row["supporting_assignment_count"]),
            float(row["head_coach_continuity"]),
            float(row["oc_continuity"]),
        ]
        values.extend(float(row["team_id"] == value) for value in teams[1:])
        values.extend(float(row["era"] == value) for value in eras[1:])
        matrix.append(values)
    x = np.asarray(matrix, dtype=float)
    y = structure["is_verified"].to_numpy()
    model = LogisticRegression(C=1.0, max_iter=5_000, solver="lbfgs").fit(x, y)
    predicted = model.predict_proba(x)[:, 1]
    prevalence = float(y.mean())
    raw_weight = prevalence / np.maximum(predicted, 1e-9)
    clipped = np.clip(raw_weight, 0.1, 10.0)
    diagnostics = pl.DataFrame(
        [
            {
                "model": "verification_propensity_non_outcome_v1",
                "observations": len(y),
                "verified_prevalence": prevalence,
                "auc": float(roc_auc_score(y, predicted)),
                "minimum_propensity": float(predicted.min()),
                "maximum_propensity": float(predicted.max()),
                "maximum_unclipped_weight": float(raw_weight.max()),
                "weights_clipped_at": 10.0,
                "feature_contract": (
                    "season+team+era+supporting-role-counts+HC/OC-continuity;no outcomes"
                ),
            }
        ]
    )
    return structure.with_columns(
        pl.Series("verification_propensity", predicted),
        pl.Series("stabilized_ipw", clipped),
    ), diagnostics


def _standardized_difference(reference: np.ndarray, group: np.ndarray) -> float | None:
    if not len(reference) or not len(group):
        return None
    pooled = math.sqrt((float(np.var(reference)) + float(np.var(group))) / 2)
    return None if pooled == 0 else float((np.mean(reference) - np.mean(group)) / pooled)


def build_selection_diagnostics(
    project_root: Path, structure: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    enhancement = project_root / "data/processed/enhancements"
    version = (enhancement / "LATEST").read_text(encoding="utf-8").strip()
    source = enhancement / version
    team = pl.read_parquet(source / "team_season_statistics.parquet").select(
        "season",
        pl.col("team_id").str.strip_prefix("team_").str.to_uppercase().alias("team_id"),
        "team_win_percentage",
        "team_offensive_epa_per_play",
        "team_passing_epa_per_dropback",
    )
    pae = (
        pl.read_parquet(source / "canonical_qb_pae.parquet")
        .filter((pl.col("season") >= 2010) & pl.col("is_out_of_sample"))
        .group_by("season", "team_id")
        .agg(
            (
                (pl.col("performance_above_expectation") * pl.col("dropbacks")).sum()
                / pl.col("dropbacks").sum()
            ).alias("team_qb_pae"),
            pl.col("dropbacks").sum().alias("team_qb_dropbacks"),
        )
        .with_columns(pl.col("team_id").str.strip_prefix("team_").str.to_uppercase())
    )
    enriched = structure.join(team, on=["season", "team_id"], validate="1:1").join(
        pae, on=["season", "team_id"], how="left", validate="1:1"
    )
    non_outcomes = (
        "season",
        "verified_supporting_assignments",
        "supporting_assignment_count",
        "head_coach_continuity",
        "oc_continuity",
        "named_caller_known",
        "repeated_named_caller",
        "multi_interval_structure",
    )
    outcomes = (
        "team_win_percentage",
        "team_offensive_epa_per_play",
        "team_passing_epa_per_dropback",
        "team_qb_pae",
    )
    rows: list[dict[str, Any]] = []
    reference_frame = enriched.filter(pl.col("ending_status") == "verified")
    for feature_class, fields in (("non_outcome", non_outcomes), ("outcome_diagnostic", outcomes)):
        for field in fields:
            reference = reference_frame[field].drop_nulls().to_numpy().astype(float)
            for status in ("verified", "partial", "provisional", "unresolved"):
                values = (
                    enriched.filter(pl.col("ending_status") == status)[field]
                    .drop_nulls()
                    .to_numpy()
                    .astype(float)
                )
                rows.append(
                    {
                        "feature_class": feature_class,
                        "feature": field,
                        "status": status,
                        "n": len(values),
                        "mean": float(np.mean(values)) if len(values) else None,
                        "verified_mean": float(np.mean(reference)) if len(reference) else None,
                        "standardized_difference_vs_verified": (
                            0.0
                            if status == "verified"
                            else _standardized_difference(reference, values)
                        ),
                        "used_to_assign_verification": False,
                    }
                )
    propensity, propensity_diagnostics = _propensity(structure)
    missingness_rows: list[dict[str, Any]] = []
    for dimension in ("era", "team_id", "ending_status"):
        for row in (
            structure.group_by(dimension)
            .agg(pl.len().alias("cells"), pl.col("is_verified").sum().alias("verified"))
            .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
            .sort(dimension)
            .to_dicts()
        ):
            missingness_rows.append(
                {
                    "dimension": dimension,
                    "group": str(row[dimension]),
                    "cells": row["cells"],
                    "verified": row["verified"],
                    "verified_rate": row["verified_rate"],
                }
            )
    for dimension in (
        "head_coach_continuity",
        "oc_continuity",
        "named_caller_known",
        "repeated_named_caller",
        "multi_interval_structure",
    ):
        for row in (
            structure.group_by(dimension)
            .agg(pl.len().alias("cells"), pl.col("is_verified").sum().alias("verified"))
            .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
            .sort(dimension)
            .to_dicts()
        ):
            missingness_rows.append(
                {
                    "dimension": dimension,
                    "group": str(row[dimension]),
                    "cells": row["cells"],
                    "verified": row["verified"],
                    "verified_rate": row["verified_rate"],
                }
            )
    prompt10 = _prompt10_root(project_root)
    source_cells = (
        pl.read_csv(prompt10 / "source_lineage.csv")
        .select("season", "team_id", "source_family")
        .unique()
        .join(structure.select("season", "team_id", "is_verified"), on=["season", "team_id"])
    )
    for row in (
        source_cells.group_by("source_family")
        .agg(
            pl.struct("season", "team_id").n_unique().alias("cells"),
            pl.col("is_verified").sum().alias("verified"),
        )
        .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
        .sort("source_family")
        .to_dicts()
    ):
        missingness_rows.append(
            {
                "dimension": "prompt10_source_family",
                "group": row["source_family"],
                "cells": row["cells"],
                "verified": row["verified"],
                "verified_rate": row["verified_rate"],
            }
        )
    researched = pl.read_csv(prompt10 / "researched_cells.csv")
    for row in (
        researched.group_by("tier")
        .agg(
            pl.len().alias("cells"), (pl.col("ending_status") == "verified").sum().alias("verified")
        )
        .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
        .sort("tier")
        .to_dicts()
    ):
        missingness_rows.append(
            {
                "dimension": "prompt10_research_tier",
                "group": row["tier"],
                "cells": row["cells"],
                "verified": row["verified"],
                "verified_rate": row["verified_rate"],
            }
        )
    return (
        pl.DataFrame(missingness_rows),
        pl.DataFrame(rows, infer_schema_length=None),
        propensity.join(propensity_diagnostics, how="cross"),
    )


def build_ipw_sensitivity(common: pl.DataFrame, propensity: pl.DataFrame) -> pl.DataFrame:
    weighted = common.join(
        propensity.select("season", "team_id", "verification_propensity", "stabilized_ipw"),
        on=["season", "team_id"],
        validate="m:1",
    )
    weights = weighted["stabilized_ipw"].to_numpy()
    ess = float(weights.sum() ** 2 / np.square(weights).sum())
    pairs = _consecutive_pairs(weighted)
    pair_weights = pairs.join(
        propensity.select("season", "team_id", "stabilized_ipw"),
        on=["season", "team_id"],
        validate="m:1",
    )["stabilized_ipw"].to_numpy()
    metrics = (
        (
            "common_q_p_pearson",
            weighted["q_development_signal"],
            weighted["pcae"],
            weights,
        ),
        (
            "common_q_p_spearman",
            weighted["q_development_signal"],
            weighted["pcae"],
            weights,
        ),
        ("q_repeatability", pairs["prior_q"], pairs["current_q"], pair_weights),
        ("p_repeatability", pairs["prior_p"], pairs["current_p"], pair_weights),
    )
    rows: list[dict[str, Any]] = []
    for metric, left, right, metric_weights in metrics:
        function = _spearman if metric.endswith("spearman") else _pearson
        raw = function(left, right)
        adjusted = function(left, right, metric_weights)
        rows.append(
            {
                "metric": metric,
                "unweighted": raw,
                "ipw_weighted": adjusted,
                "absolute_change": (
                    abs(float(adjusted) - float(raw))
                    if raw is not None and adjusted is not None
                    else None
                ),
                "weighted_effective_rows": ess if metric.startswith("common") else None,
                "minimum_propensity": float(weighted["verification_propensity"].min()),
                "maximum_weight": float(weights.max()),
                "reliability": (
                    "limited_overlap_clipped_sensitivity_only"
                    if float(weighted["verification_propensity"].min()) < 0.05
                    or float(weights.max()) >= 10.0
                    else "diagnostically_usable_not_causal"
                ),
            }
        )
    return pl.DataFrame(rows)


def build_missing_data_stress(common: pl.DataFrame) -> pl.DataFrame:
    pairs = _consecutive_pairs(common)
    rows: list[dict[str, Any]] = []
    for signal, left, right in (
        ("q_repeatability", "prior_q", "current_q"),
        ("p_repeatability", "prior_p", "current_p"),
    ):
        for subset, frame in (
            ("all_consecutive", pairs),
            ("different_qb", pairs.filter(pl.col("different_qb"))),
            ("different_team", pairs.filter(pl.col("different_team"))),
        ):
            correlation = _pearson(frame[left], frame[right])
            direction = _direction(frame[left], frame[right])
            adversarial_products = (
                0
                if correlation is None or correlation <= 0
                else math.ceil(frame.height * correlation)
            )
            direction_failures = (
                0
                if direction is None or direction <= 0.5
                else math.ceil(frame.height * (2 * direction - 1))
            )
            rows.append(
                {
                    "signal": signal,
                    "subset": subset,
                    "observed_pairs": frame.height,
                    "observed_pearson": correlation,
                    "observed_same_direction": direction,
                    "minimum_unit_negative_standardized_products_to_nonpositive": (
                        adversarial_products
                    ),
                    "minimum_all_mismatch_pairs_to_direction_at_or_below_half": (
                        direction_failures
                    ),
                    "interpretation": (
                        "mathematical stress bound; no caller identity or PCAE was imputed"
                    ),
                }
            )
    return pl.DataFrame(rows)


def _future_rows(common: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for row in common.to_dicts():
        prior = common.filter(
            (pl.col("coach_id") == row["coach_id"]) & (pl.col("season") < row["season"])
        )
        if prior.height:
            rows.append({**row, "prior_common_coach_seasons": prior.height})
    return pl.DataFrame(rows, schema={**common.schema, "prior_common_coach_seasons": pl.Int64})


def build_fold_quality(
    common: pl.DataFrame, play_coverage: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    future = _future_rows(common)
    rows: list[dict[str, Any]] = []
    for season in range(2020, 2026):
        target = future.filter(pl.col("season") == season)
        training = future.filter(pl.col("season") < season)
        rate = play_coverage.filter(pl.col("season") == season)[
            "verified_attributable_play_rate"
        ].item()
        row = {
            "target_season": season,
            "target_rows": target.height,
            "prior_training_rows": training.height,
            "target_callers": target["coach_id"].n_unique(),
            "target_teams": target["team_id"].n_unique(),
            "target_quarterback_observations": int(target["quarterbacks"].sum()),
            "target_verified_attributable_play_rate": rate,
            "training_2010_2014": training.filter(pl.col("season") <= 2014).height,
            "training_2015_2019": training.filter(pl.col("season").is_between(2015, 2019)).height,
            "training_2020_2025": training.filter(pl.col("season") >= 2020).height,
        }
        row["credible_target_fold"] = (
            row["target_rows"] >= RESEARCH_GATE_POLICY["minimum_target_rows_per_fold"]
            and row["prior_training_rows"]
            >= RESEARCH_GATE_POLICY["minimum_prior_training_rows_per_fold"]
            and row["target_verified_attributable_play_rate"]
            >= RESEARCH_GATE_POLICY["minimum_target_play_rate"]
        )
        failures = []
        if row["target_rows"] < RESEARCH_GATE_POLICY["minimum_target_rows_per_fold"]:
            failures.append("target_rows")
        if (
            row["prior_training_rows"]
            < RESEARCH_GATE_POLICY["minimum_prior_training_rows_per_fold"]
        ):
            failures.append("prior_training_rows")
        if (
            row["target_verified_attributable_play_rate"]
            < RESEARCH_GATE_POLICY["minimum_target_play_rate"]
        ):
            failures.append("target_play_coverage")
        row["credibility_note"] = "credible" if not failures else "below:" + "|".join(failures)
        rows.append(row)
    return pl.DataFrame(rows), future


def _cluster_members(frame: pl.DataFrame, dimension: str, paired: bool) -> list[list[str]]:
    rows = frame.to_dicts()
    members: list[list[str]] = []
    for row in rows:
        if dimension == "coach":
            values = [row["coach_id"]]
        elif dimension == "team":
            values = [row["team_id"]]
            if paired:
                values.append(row["prior_team_id"])
        elif dimension == "season":
            values = [str(row["season"])]
            if paired:
                values.append(str(row["prior_season"]))
        elif dimension == "quarterback":
            values = str(row["player_ids"]).split("|")
            if paired:
                values.extend(str(row["prior_player_ids"]).split("|"))
        else:
            raise ValueError(f"unsupported cluster dimension: {dimension}")
        members.append(sorted(set(values)))
    return members


def cluster_bootstrap(
    frame: pl.DataFrame,
    left: str,
    right: str,
    *,
    dimension: str,
    label: str,
    paired: bool,
    bootstraps: int = BOOTSTRAPS,
) -> dict[str, Any]:
    """Resample dependence clusters and retain multi-QB/team membership as row weights."""

    frame = frame.sort("season", "coach_id", "team_id")
    members = _cluster_members(frame, dimension, paired)
    clusters = sorted({member for row in members for member in row})
    rng = np.random.default_rng(
        int.from_bytes(
            hashlib.sha256(f"{RANDOM_SEED}:{label}:{dimension}".encode()).digest()[:8],
            "big",
        )
    )
    x = frame[left].to_numpy().astype(float)
    y = frame[right].to_numpy().astype(float)
    draws: list[float] = []
    for _ in range(bootstraps):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        counts = {cluster: int(np.sum(sampled == cluster)) for cluster in clusters}
        weights = np.asarray(
            [sum(counts[value] for value in row) / len(row) for row in members], dtype=float
        )
        estimate = _pearson(x, y, weights)
        if estimate is not None and np.isfinite(estimate):
            draws.append(float(estimate))
    estimate = _pearson(x, y)
    return {
        "record_type": "cluster_bootstrap",
        "metric": label,
        "cluster_dimension": dimension,
        "rows": frame.height,
        "clusters": len(clusters),
        "estimate": estimate,
        "bootstrap_low": float(np.quantile(draws, 0.025)) if draws else None,
        "bootstrap_median": float(np.median(draws)) if draws else None,
        "bootstrap_high": float(np.quantile(draws, 0.975)) if draws else None,
        "positive_draw_rate": float(np.mean(np.asarray(draws) > 0)) if draws else None,
        "successful_draws": len(draws),
        "requested_draws": bootstraps,
        "multi_membership_weighting": dimension in {"team", "season", "quarterback"} and paired,
    }


def _icc_and_effective_n(frame: pl.DataFrame, value: str, cluster: str) -> tuple[float, float]:
    groups = [group[value].to_numpy().astype(float) for group in frame.partition_by(cluster)]
    groups = [group for group in groups if len(group)]
    n = sum(len(group) for group in groups)
    k = len(groups)
    if k < 2 or n <= k:
        return 0.0, float(n)
    grand = float(np.mean(np.concatenate(groups)))
    ss_between = sum(len(group) * (float(np.mean(group)) - grand) ** 2 for group in groups)
    ss_within = sum(float(np.square(group - np.mean(group)).sum()) for group in groups)
    ms_between = ss_between / (k - 1)
    ms_within = ss_within / (n - k)
    n0 = (n - sum(len(group) ** 2 for group in groups) / n) / (k - 1)
    denominator = ms_between + (n0 - 1) * ms_within
    icc = max(0.0, (ms_between - ms_within) / denominator) if denominator > 0 else 0.0
    mean_size = n / k
    effective = n / (1 + (mean_size - 1) * icc)
    return float(icc), float(effective)


def build_cluster_precision(common: pl.DataFrame, future: pl.DataFrame) -> pl.DataFrame:
    recent = common.filter(pl.col("season") >= 2020)
    recent_pairs = _consecutive_pairs(recent)
    specifications = (
        ("common_q_p", recent, "q_development_signal", "pcae", False),
        ("q_repeatability", recent_pairs, "prior_q", "current_q", True),
        ("p_repeatability", recent_pairs, "prior_p", "current_p", True),
        (
            "p_different_qb",
            recent_pairs.filter(pl.col("different_qb")),
            "prior_p",
            "current_p",
            True,
        ),
        (
            "p_different_team",
            recent_pairs.filter(pl.col("different_team")),
            "prior_p",
            "current_p",
            True,
        ),
    )
    rows: list[dict[str, Any]] = []
    for label, frame, left, right, paired in specifications:
        for dimension in ("coach", "team", "season", "quarterback"):
            rows.append(
                cluster_bootstrap(
                    frame,
                    left,
                    right,
                    dimension=dimension,
                    label=label,
                    paired=paired,
                )
            )
    for signal in ("q_development_signal", "pcae"):
        for cluster in ("coach_id", "team_id", "season"):
            icc, effective = _icc_and_effective_n(future, signal, cluster)
            rows.append(
                {
                    "record_type": "effective_sample",
                    "metric": signal,
                    "cluster_dimension": cluster,
                    "rows": future.height,
                    "clusters": future[cluster].n_unique(),
                    "estimate": icc,
                    "bootstrap_low": None,
                    "bootstrap_median": None,
                    "bootstrap_high": None,
                    "positive_draw_rate": None,
                    "successful_draws": None,
                    "requested_draws": None,
                    "multi_membership_weighting": False,
                    "effective_rows": effective,
                }
            )
        quarterback = future.with_columns(
            pl.col("player_ids").str.split("|").alias("quarterback_id")
        ).explode("quarterback_id", empty_as_null=True)
        icc, effective_expanded = _icc_and_effective_n(quarterback, signal, "quarterback_id")
        mean_memberships = quarterback.height / future.height
        rows.append(
            {
                "record_type": "effective_sample",
                "metric": signal,
                "cluster_dimension": "quarterback_multi_membership",
                "rows": future.height,
                "clusters": quarterback["quarterback_id"].n_unique(),
                "estimate": icc,
                "bootstrap_low": None,
                "bootstrap_median": None,
                "bootstrap_high": None,
                "positive_draw_rate": None,
                "successful_draws": None,
                "requested_draws": None,
                "multi_membership_weighting": True,
                "effective_rows": min(future.height, effective_expanded / mean_memberships),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort(
        "record_type", "metric", "cluster_dimension"
    )


def _criterion(
    system: str, criterion: str, threshold: str, observed: Any, passed: bool
) -> dict[str, Any]:
    return {
        "gate_system": system,
        "criterion": criterion,
        "threshold": threshold,
        "observed": str(observed),
        "result": "PASS" if passed else "FAIL",
    }


def build_gate_comparison(
    coverage: pl.DataFrame,
    play_era: pl.DataFrame,
    temporal: pl.DataFrame,
    folds: pl.DataFrame,
    cluster_precision: pl.DataFrame,
    future: pl.DataFrame,
) -> pl.DataFrame:
    recent_cells = coverage.filter(pl.col("season") >= 2020)
    recent_full_rate = (
        recent_cells.filter(pl.col("ending_status") == "verified").height / recent_cells.height
    )
    recent_play_rate = play_era.filter(pl.col("era") == "2020-2025")[
        "verified_attributable_play_rate"
    ].item()
    recent = temporal.filter(pl.col("analysis") == "2020-2025").row(0, named=True)
    credible = folds.filter(pl.col("credible_target_fold"))
    successful = cluster_precision.filter(pl.col("record_type") == "cluster_bootstrap")
    minimum_success = int(successful["successful_draws"].min())
    rows = [
        _criterion(
            "A_original",
            "all_512_full_cells",
            ">=256",
            coverage.filter(pl.col("ending_status") == "verified").height,
            coverage.filter(pl.col("ending_status") == "verified").height >= 256,
        ),
        _criterion(
            "B_effective_sample",
            "recent_full_cell_rate",
            ">=0.90",
            recent_full_rate,
            recent_full_rate >= RESEARCH_GATE_POLICY["minimum_recent_full_cell_rate"],
        ),
        _criterion(
            "B_effective_sample",
            "recent_play_rate",
            ">=0.90",
            recent_play_rate,
            recent_play_rate >= RESEARCH_GATE_POLICY["minimum_recent_play_rate"],
        ),
        _criterion(
            "B_effective_sample",
            "credible_folds",
            ">=5",
            credible.height,
            credible.height >= RESEARCH_GATE_POLICY["minimum_credible_folds"],
        ),
        _criterion(
            "B_effective_sample",
            "total_future_rows",
            ">=150",
            future.height,
            future.height >= RESEARCH_GATE_POLICY["minimum_total_future_rows"],
        ),
        _criterion(
            "B_effective_sample",
            "credible_target_rows",
            ">=125",
            int(credible["target_rows"].sum()),
            int(credible["target_rows"].sum())
            >= RESEARCH_GATE_POLICY["minimum_credible_target_rows"],
        ),
        _criterion(
            "B_effective_sample",
            "repeat_callers",
            ">=50",
            recent["repeat_callers"],
            recent["repeat_callers"] >= RESEARCH_GATE_POLICY["minimum_repeat_callers"],
        ),
        _criterion(
            "B_effective_sample",
            "successful_cluster_bootstraps",
            ">=475/500 each",
            minimum_success,
            minimum_success >= RESEARCH_GATE_POLICY["minimum_successful_bootstraps"],
        ),
        _criterion(
            "C_model_specific",
            "recent_common_qp_rows",
            ">=150",
            recent["common_qp_rows"],
            recent["common_qp_rows"] >= RESEARCH_GATE_POLICY["minimum_recent_common_rows"],
        ),
        _criterion(
            "C_model_specific",
            "recent_consecutive_pairs",
            ">=75",
            recent["consecutive_pairs"],
            recent["consecutive_pairs"] >= RESEARCH_GATE_POLICY["minimum_recent_consecutive_pairs"],
        ),
        _criterion(
            "C_model_specific",
            "recent_different_qb_pairs",
            ">=60",
            recent["different_qb_pairs"],
            recent["different_qb_pairs"]
            >= RESEARCH_GATE_POLICY["minimum_recent_different_qb_pairs"],
        ),
        _criterion(
            "C_model_specific",
            "recent_different_team_pairs",
            ">=15",
            recent["different_team_pairs"],
            recent["different_team_pairs"]
            >= RESEARCH_GATE_POLICY["minimum_recent_different_team_pairs"],
        ),
        _criterion(
            "C_model_specific",
            "credible_folds",
            ">=5",
            credible.height,
            credible.height >= RESEARCH_GATE_POLICY["minimum_credible_folds"],
        ),
        _criterion(
            "C_model_specific",
            "credible_target_rows",
            ">=125",
            int(credible["target_rows"].sum()),
            int(credible["target_rows"].sum())
            >= RESEARCH_GATE_POLICY["minimum_credible_target_rows"],
        ),
        _criterion(
            "C_model_specific",
            "successful_cluster_bootstraps",
            ">=475/500 each",
            minimum_success,
            minimum_success >= RESEARCH_GATE_POLICY["minimum_successful_bootstraps"],
        ),
        _criterion(
            "production_separate",
            "claimed_window_full_cell_rate",
            ">=0.95",
            recent_full_rate,
            recent_full_rate >= PRODUCTION_GATE_POLICY["minimum_claimed_window_full_cell_rate"],
        ),
        _criterion(
            "production_separate",
            "claimed_window_play_rate",
            ">=0.95",
            recent_play_rate,
            recent_play_rate >= PRODUCTION_GATE_POLICY["minimum_claimed_window_play_rate"],
        ),
    ]
    frame = pl.DataFrame(rows)
    summaries = []
    for system in ("A_original", "B_effective_sample", "C_model_specific", "production_separate"):
        subset = frame.filter(pl.col("gate_system") == system)
        summaries.append(
            {
                "gate_system": system,
                "criterion": "OVERALL",
                "threshold": "all system criteria",
                "observed": f"{subset.filter(pl.col('result') == 'PASS').height}/{subset.height}",
                "result": "PASS" if (subset["result"] == "PASS").all() else "FAIL",
            }
        )
    return pl.concat([frame, pl.DataFrame(summaries)], how="vertical_relaxed")


def build_denominator_comparison(
    coverage: pl.DataFrame,
    intervals: pl.DataFrame,
    play_era: pl.DataFrame,
    common: pl.DataFrame,
    future: pl.DataFrame,
    folds: pl.DataFrame,
) -> pl.DataFrame:
    recent_cells = coverage.filter(pl.col("season") >= 2020)
    values = [
        (
            "all_team_season_cells",
            coverage.height,
            512,
            "inventory completeness, not direct identifiability",
        ),
        (
            "fully_verified_cells",
            coverage.filter(pl.col("ending_status") == "verified").height,
            512,
            "complete cell continuity",
        ),
        (
            "partial_cells_with_usable_intervals",
            int(
                intervals.filter(pl.col("ending_status") == "partial")[
                    "cells_with_usable_intervals"
                ].sum()
            ),
            512,
            "bounded evidence without full-cell promotion",
        ),
        (
            "individually_attributable_intervals",
            int(
                intervals.filter(pl.col("ending_status") == "ALL_USABLE")[
                    "individually_attributable_intervals"
                ].item()
            ),
            None,
            "direct PCAE attribution units",
        ),
        (
            "verified_attributable_plays",
            int(
                play_era.filter(pl.col("era") == "2010-2025")["verified_attributable_plays"].item()
            ),
            int(play_era.filter(pl.col("era") == "2010-2025")["eligible_plays"].item()),
            "play-weighted PCAE support",
        ),
        (
            "recent_fully_verified_cells",
            recent_cells.filter(pl.col("ending_status") == "verified").height,
            recent_cells.height,
            "primary-window completeness",
        ),
        (
            "recent_verified_attributable_plays",
            int(
                play_era.filter(pl.col("era") == "2020-2025")["verified_attributable_plays"].item()
            ),
            int(play_era.filter(pl.col("era") == "2020-2025")["eligible_plays"].item()),
            "primary-window play support",
        ),
        ("common_qp_coach_seasons", common.height, None, "direct joint Q/P estimation rows"),
        (
            "common_future_qp_rows",
            future.height,
            None,
            "chronological validation rows with caller history",
        ),
        (
            "credible_target_folds",
            folds.filter(pl.col("credible_target_fold")).height,
            6,
            "independent temporal replication",
        ),
    ]
    return pl.DataFrame(
        [
            {
                "denominator": name,
                "numerator": numerator,
                "denominator_value": denominator,
                "rate": numerator / denominator if denominator else None,
                "identifiability_relevance": relevance,
            }
            for name, numerator, denominator, relevance in values
        ],
        infer_schema_length=None,
    )


def build_era_coverage(
    coverage: pl.DataFrame,
    pcae: pl.DataFrame,
    play_era: pl.DataFrame,
    common: pl.DataFrame,
    future: pl.DataFrame,
    q_availability: pl.DataFrame,
) -> pl.DataFrame:
    base = coverage.with_columns(
        pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era")
    )
    full = base.group_by("era").agg(
        pl.len().alias("cells"),
        (pl.col("ending_status") == "verified").sum().alias("fully_verified_cells"),
        (pl.col("ending_status") == "partial").sum().alias("partial_cells"),
    )
    usable_cells = (
        pcae.join(base.select("season", "team_id", "era"), on=["season", "team_id"])
        .group_by("era")
        .agg(
            pl.struct("season", "team_id").n_unique().alias("cells_with_usable_intervals"),
            pl.len().alias("usable_intervals"),
        )
    )
    common_era = (
        common.with_columns(
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era")
        )
        .group_by("era")
        .agg(
            pl.len().alias("common_qp_rows"),
            pl.col("coach_id").n_unique().alias("common_qp_coaches"),
            pl.col("quarterbacks").sum().alias("quarterback_observations"),
        )
    )
    future_era = (
        future.with_columns(
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era")
        )
        .group_by("era")
        .agg(pl.len().alias("common_future_rows"))
    )
    q_era = (
        q_availability.with_columns(
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era")
        )
        .group_by("era")
        .agg(
            pl.len().alias("q_available_coach_seasons"),
            pl.col("quarterbacks").sum().alias("q_available_quarterback_observations"),
        )
    )
    repeat_by_era = (
        common.with_columns(
            pl.col("season").map_elements(_era, return_dtype=pl.String).alias("era")
        )
        .group_by("era", "coach_id")
        .len()
        .filter(pl.col("len") >= 2)
        .group_by("era")
        .len(name="repeat_callers_within_era")
    )
    return (
        full.join(usable_cells, on="era", how="left")
        .join(
            play_era.filter(
                pl.col("era").is_in(["2010-2014", "2015-2019", "2020-2022", "2023-2025"])
            ),
            on="era",
            validate="1:1",
        )
        .join(common_era, on="era", how="left")
        .join(future_era, on="era", how="left")
        .join(q_era, on="era", how="left")
        .join(repeat_by_era, on="era", how="left")
        .with_columns((pl.col("fully_verified_cells") / pl.col("cells")).alias("full_cell_rate"))
        .fill_null(0)
        .sort("era")
    )


def build_final_decision(
    coverage: pl.DataFrame,
    era: pl.DataFrame,
    play_era: pl.DataFrame,
    common: pl.DataFrame,
    future: pl.DataFrame,
    folds: pl.DataFrame,
    gates: pl.DataFrame,
) -> pl.DataFrame:
    systems = dict(
        gates.filter(pl.col("criterion") == "OVERALL").select("gate_system", "result").rows()
    )
    recent_full = (
        coverage.filter((pl.col("season") >= 2020) & (pl.col("ending_status") == "verified")).height
        / coverage.filter(pl.col("season") >= 2020).height
    )
    recent_play = play_era.filter(pl.col("era") == "2020-2025")[
        "verified_attributable_play_rate"
    ].item()
    credible = folds.filter(pl.col("credible_target_fold"))
    return pl.DataFrame(
        [
            {
                "decision": "REPLACE 50% GATE",
                "final_equation_research_rerun": "GO",
                "recommended_gate_system": "C_model_specific_with_recent_primary_window",
                "original_gate_classification": "heuristic_conservative_rerun_safeguard",
                "original_gate_statistically_derived": False,
                "all_history_full_cell_rate": coverage.filter(
                    pl.col("ending_status") == "verified"
                ).height
                / 512,
                "recent_full_cell_rate": recent_full,
                "recent_play_weighted_rate": recent_play,
                "common_qp_rows": common.height,
                "common_future_rows": future.height,
                "credible_folds": credible.height,
                "credible_target_rows": int(credible["target_rows"].sum()),
                "system_a": systems["A_original"],
                "system_b": systems["B_effective_sample"],
                "system_c": systems["C_model_specific"],
                "production_gate": systems["production_separate"],
                "primary_analysis_window": "2020-2025",
                "historical_role": "secondary robustness and training-history evidence",
                "research_rationale": (
                    "joint-row, repeated-caller, fold, play-coverage, and cluster-resampling "
                    "requirements measure estimability more directly than 256 inventory cells"
                ),
                "production_rationale": (
                    "research sufficiency does not authorize rankings; publication needs stricter "
                    "claimed-window coverage and model-specific validation"
                ),
                "more_broad_play_caller_collection": False,
                "targeted_recent_collection_if_production_pursued": True,
                "verification_semantics_changed": False,
                "final_equation_fitted": False,
            }
        ]
    )


def _verify_sources(project_root: Path, hashes: dict[str, str]) -> None:
    changed = [path for path, digest in hashes.items() if _sha256(project_root / path) != digest]
    if changed:
        raise ValueError(f"Prompt 11 input bytes changed during build: {sorted(changed)}")


def run_checkpoint_twelve_coverage_gate_review(
    project_root: Path, output_root: Path | None = None
) -> Prompt11Result:
    """Build the deterministic Prompt 11 methodology review."""

    prompt10 = _prompt10_root(project_root)
    coverage, pcae, common = _load_prompt10(project_root)
    assignments = _assignment_frame(project_root)
    q_availability = build_q_availability(project_root, assignments.to_dicts())
    interval_coverage = build_verified_interval_coverage(coverage, pcae, assignments)
    eligible, pbp_hashes = _eligible_play_counts(project_root)
    play_season, play_era = build_play_weighted_coverage(eligible, pcae)
    temporal = build_temporal_sensitivity(common)
    leave_out = build_leave_era_out(common)
    structure = _cell_structure(project_root, coverage, assignments)
    missingness, selection, propensity = build_selection_diagnostics(project_root, structure)
    propensity_summary_columns = (
        "model",
        "observations",
        "verified_prevalence",
        "auc",
        "minimum_propensity",
        "maximum_propensity",
        "maximum_unclipped_weight",
        "weights_clipped_at",
        "feature_contract",
    )
    propensity_summary = propensity.select(propensity_summary_columns).unique()
    ipw = build_ipw_sensitivity(common, propensity)
    ipw = ipw.join(propensity_summary, how="cross")
    stress = build_missing_data_stress(common)
    folds, future = build_fold_quality(common, play_season)
    cluster_precision = build_cluster_precision(common, future)
    gates = build_gate_comparison(coverage, play_era, temporal, folds, cluster_precision, future)
    denominator = build_denominator_comparison(
        coverage, interval_coverage, play_era, common, future, folds
    )
    era = build_era_coverage(coverage, pcae, play_era, common, future, q_availability)
    decision = build_final_decision(coverage, era, play_era, common, future, folds, gates)

    input_paths = [
        prompt10 / "MANIFEST.json",
        prompt10 / "play_caller_completeness.csv",
        prompt10 / "historical_pcae.csv",
        prompt10 / "common_qp_availability.csv",
        project_root / "research/coach_effect/checkpoint_twelve_coverage_gate_review.py",
        project_root / "research/coach_effect/checkpoint_twelve_final_play_caller_evidence.py",
        project_root / "research/coach_effect/checkpoint_twelve_review.py",
        project_root / "docs/CHECKPOINT_12_ADVERSARIAL_REVIEW.md",
    ]
    enhancement = project_root / "data/processed/enhancements"
    enhancement_version = (enhancement / "LATEST").read_text(encoding="utf-8").strip()
    input_paths.extend(
        [
            enhancement / enhancement_version / "team_season_statistics.parquet",
            enhancement / enhancement_version / "canonical_qb_pae.parquet",
        ]
    )
    input_hashes = {str(path.relative_to(project_root)): _sha256(path) for path in input_paths}
    input_hashes.update(pbp_hashes)
    identity = {
        "specification": PROMPT11_SPECIFICATION,
        "prompt10_version": PROMPT10_VERSION,
        "prompt9_version": PROMPT9_VERSION,
        "random_seed": RANDOM_SEED,
        "bootstraps": BOOTSTRAPS,
        "research_gate_policy": RESEARCH_GATE_POLICY,
        "production_gate_policy": PRODUCTION_GATE_POLICY,
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_hashes": dict(sorted(input_hashes.items())),
    }
    data_version = (
        "c12-gate-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    outputs = {
        "coverage_denominator_comparison.csv": denominator,
        "verified_interval_coverage.csv": interval_coverage,
        "play_weighted_coverage.csv": play_season,
        "era_coverage.csv": era,
        "missingness_diagnostics.csv": missingness,
        "selection_bias_diagnostics.csv": selection,
        "inverse_probability_sensitivity.csv": ipw,
        "missing_data_stress_test.csv": stress,
        "temporal_window_sensitivity.csv": temporal,
        "leave_era_out_results.csv": leave_out,
        "fold_quality_analysis.csv": folds,
        "cluster_aware_precision.csv": cluster_precision,
        "candidate_gate_comparison.csv": gates,
        "final_methodology_decision.csv": decision,
    }
    if set(outputs) != set(OUTPUT_NAMES):
        raise ValueError("Prompt 11 output contract drift")
    outputs = {name: _add_research_contract(frame, data_version) for name, frame in outputs.items()}
    _verify_sources(project_root, input_hashes)

    root = output_root or (
        project_root / "research/coach_effect/outputs/checkpoint_12_coverage_gate_review"
    )
    destination = root / data_version
    temporary = root / f".{data_version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    for name in OUTPUT_NAMES:
        _write_csv(outputs[name], temporary / name)
    checksums = {name: _sha256(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "data_version": data_version,
        "research_only": True,
        "production_model": False,
        "production_ranking": False,
        "final_equation_fitted": False,
        "verification_semantics_changed": False,
        "pae_q_pcae_callvalue_changed": False,
        "phase_two_started": False,
        "ask_anything_implemented": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {name: outputs[name].height for name in OUTPUT_NAMES},
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _verify_sources(project_root, input_hashes)
    expected = {"MANIFEST.json", *OUTPUT_NAMES}
    if destination.exists():
        if {path.name for path in destination.iterdir() if path.is_file()} != expected:
            raise ValueError("existing Prompt 11 publication has unexpected files")
        for name in expected:
            if _sha256(destination / name) != _sha256(temporary / name):
                raise ValueError("existing Prompt 11 output differs from deterministic rebuild")
        shutil.rmtree(temporary)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(destination)
    latest = root / ".LATEST.tmp"
    latest.write_text(data_version + "\n", encoding="utf-8")
    latest.replace(root / "LATEST")
    return Prompt11Result(destination, data_version, outputs["final_methodology_decision.csv"])

"""Prompt 9 research-only historical play-caller evidence sprint.

The pipeline preserves the frozen Prompt 8 outputs, changes no analytical definition, and writes
only ignored content-addressed research artifacts.  Verified individual PCAE attribution is
limited to explicit, non-shared weekly intervals.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import polars as pl
import scipy
import sklearn

from nfl_coaching_impact.coaching import normalize_coach_name
from research.coach_effect.checkpoint_eleven import _sha256, _write_csv
from research.coach_effect.checkpoint_twelve_data_expansion import (
    COMMON_FUTURE_GATE,
    PLAY_CALLER_GATE,
    PROMPT6_VERSION,
    TARGET_FOLD_GATE,
    _add_research_contract,
    _latest,
    _sources,
    build_common_qp_availability,
    build_prompt8_assignments,
    load_and_validate_play_caller_evidence,
    rebuild_new_pcae_attribution,
)
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
)

PROMPT9_SPECIFICATION = "checkpoint-twelve-play-caller-verification-v1"
PROMPT8_VERSION = "c12-data-250e540b7de79385"
EVIDENCE_FILE = "research/coach_effect/play_caller_evidence_prompt9.csv"
SOURCE_ACCESS_DATE = "2026-09-08"
EXPECTED_STARTING_COUNTS = {
    "verified": 144,
    "partial": 2,
    "provisional": 98,
    "unresolved": 268,
}
MANDATORY_TOP_TEN = (
    (2021, "CHI", "Matt Nagy"),
    (2020, "ARI", "Kliff Kingsbury"),
    (2020, "ATL", "Dirk Koetter"),
    (2022, "JAX", "Doug Pederson"),
    (2021, "WAS", "Scott Turner"),
    (2020, "PHI", "Doug Pederson"),
    (2022, "LV", "Josh McDaniels"),
    (2021, "GB", "Matt LaFleur"),
    (2021, "LA", "Sean McVay"),
    (2022, "GB", "Matt LaFleur"),
)
OUTPUT_NAMES = (
    "researched_cells.csv",
    "accepted_evidence.csv",
    "rejected_evidence.csv",
    "newly_verified_intervals.csv",
    "partial_intervals.csv",
    "shared_intervals.csv",
    "source_lineage.csv",
    "play_caller_completeness.csv",
    "remaining_unresolved_queue.csv",
    "priority_ranking.csv",
    "historical_pcae.csv",
    "pcae_attribution_by_season.csv",
    "common_qp_availability.csv",
    "future_fold_matrix.csv",
    "repeat_play_callers.csv",
    "consecutive_play_caller_pairs.csv",
    "different_qb_samples.csv",
    "different_team_samples.csv",
    "caller_team_transitions.csv",
    "caller_qb_transitions.csv",
    "season_readiness_matrix.csv",
    "batch_snapshots.csv",
    "readiness_gate_status.csv",
)


@dataclass(frozen=True)
class Prompt9Result:
    output_path: Path
    data_version: str
    coverage: pl.DataFrame
    readiness: pl.DataFrame


def _prompt8_root(project_root: Path) -> Path:
    root = project_root / "research/coach_effect/outputs/checkpoint_12_data_expansion"
    if _latest(root) != PROMPT8_VERSION:
        raise ValueError("Prompt 9 requires the frozen Prompt 8 research baseline")
    return root / PROMPT8_VERSION


def _bool_columns() -> tuple[str, ...]:
    return (
        "is_shared",
        "proves_identity",
        "proves_initial_designation",
        "proves_continuity",
        "proves_transition",
        "proves_shared_duties",
    )


def load_and_validate_prompt9_evidence(project_root: Path) -> pl.DataFrame:
    """Read the fixed 50-cell audit and enforce evidence, status, and interval semantics."""

    frame = pl.read_csv(
        project_root / EVIDENCE_FILE,
        infer_schema_length=None,
        null_values=[],
    ).with_columns(
        pl.col("research_order", "source_priority_rank", "season", "start_week", "end_week").cast(
            pl.Int64
        ),
        *((pl.col(name) == "true").alias(name) for name in _bool_columns()),
    )
    required_text = (
        "batch",
        "team_id",
        "candidate_coach_name",
        "starting_status",
        "ending_status",
        "coach_id",
        "coach_canonical_name",
        "interval_status",
        "source_url",
        "source_title",
        "source_publisher",
        "source_family",
        "evidence_locator",
        "evidence_summary",
        "research_notes",
        "recoverability",
        "disposition",
    )
    for name in required_text:
        if frame.filter(pl.col(name).is_null() | (pl.col(name).str.strip_chars() == "")).height:
            raise ValueError(f"Prompt 9 evidence has a blank required field: {name}")
    if set(frame["interval_status"]) - {"verified", "provisional", "unresolved"}:
        raise ValueError("Prompt 9 evidence has an invalid interval status")
    if set(frame["ending_status"]) - {"verified", "partial", "provisional", "unresolved"}:
        raise ValueError("Prompt 9 evidence has an invalid cell status")
    if frame.select("research_order", "season", "team_id").unique().height != 50:
        raise ValueError("Prompt 9 must preserve exactly 50 researched cells")
    orders = frame["research_order"].unique().sort().to_list()
    if orders != list(range(1, 51)):
        raise ValueError(f"Prompt 9 research order is not complete: {orders}")
    batch_counts = dict(
        frame.select("batch", "research_order").unique().group_by("batch").len().iter_rows()
    )
    if batch_counts != {"mandatory_top10": 10, "dynamic_batch_1": 20, "dynamic_batch_2": 20}:
        raise ValueError(f"Prompt 9 batch sizes drifted: {batch_counts}")
    top = (
        frame.filter(pl.col("batch") == "mandatory_top10")
        .select("research_order", "season", "team_id", "candidate_coach_name")
        .unique()
        .sort("research_order")
    )
    observed_top = tuple(
        (row["season"], row["team_id"], row["candidate_coach_name"]) for row in top.to_dicts()
    )
    if observed_top != MANDATORY_TOP_TEN:
        raise ValueError("Prompt 9 did not begin with the mandatory top-ten queue")

    prompt8_coverage = pl.read_csv(_prompt8_root(project_root) / "play_caller_completeness.csv")
    cell_starts = (
        frame.select("season", "team_id", "starting_status")
        .unique()
        .join(
            prompt8_coverage.select(
                "season", "team_id", pl.col("ending_status").alias("expected_starting_status")
            ),
            on=["season", "team_id"],
            validate="1:1",
        )
    )
    if cell_starts.filter(pl.col("starting_status") != pl.col("expected_starting_status")).height:
        raise ValueError("Prompt 9 starting status differs from the frozen Prompt 8 baseline")

    for row in frame.to_dicts():
        last_week = 18 if row["season"] >= 2021 else 17
        if not 1 <= row["start_week"] <= row["end_week"] <= last_week:
            raise ValueError(f"invalid Prompt 9 interval: {row['season']}-{row['team_id']}")
        expected_id = f"coach-{normalize_coach_name(row['coach_canonical_name'])}"
        if row["coach_id"] != expected_id:
            raise ValueError(f"canonical coach mismatch: {row['coach_id']} != {expected_id}")
        for field in ("source_url", "corroborating_source_url"):
            value = row[field]
            if value and urlparse(value).scheme != "https":
                raise ValueError(f"non-HTTPS Prompt 9 evidence source: {value}")
        if row["interval_status"] == "verified":
            evidence_text = (
                f"{row['source_title']} {row['evidence_locator']} {row['evidence_summary']}"
            ).casefold()
            if not row["proves_identity"] or not any(
                term in evidence_text
                for term in ("caller", "calling", "called", "calls", "call sheet", "call the")
            ):
                raise ValueError("verified status requires explicit caller evidence")
            if row["is_shared"] != row["proves_shared_duties"]:
                raise ValueError("shared status must be explicitly proved")
        if (
            row["disposition"] == "rejected_full_verification"
            and row["interval_status"] == "verified"
        ):
            raise ValueError("rejected evidence cannot create a verified interval")

    for cell in frame.partition_by(["research_order", "season", "team_id"], as_dict=False):
        if cell["ending_status"].n_unique() != 1 or cell["starting_status"].n_unique() != 1:
            raise ValueError("one researched cell has contradictory status metadata")
        status = cell["ending_status"][0]
        verified = cell.filter(pl.col("interval_status") == "verified").sort(
            "start_week", "end_week", "coach_id"
        )
        rows = verified.to_dicts()
        for index, left in enumerate(rows):
            for right in rows[index + 1 :]:
                overlaps = right["start_week"] <= left["end_week"]
                if overlaps and not (left["is_shared"] and right["is_shared"]):
                    raise ValueError("overlapping non-shared Prompt 9 caller intervals")
        last_week = 18 if cell["season"][0] >= 2021 else 17
        individually_covered = {
            week
            for row in rows
            if not row["is_shared"]
            for week in range(row["start_week"], row["end_week"] + 1)
        }
        full_individual = individually_covered == set(range(1, last_week + 1))
        if status == "verified" and (not full_individual or not rows):
            raise ValueError("verified cell lacks complete non-shared weekly evidence")
        if status == "partial" and (not rows or full_individual):
            raise ValueError(
                "partial cell must retain useful but incomplete/shared verified evidence"
            )
        if status in {"provisional", "unresolved"} and rows:
            raise ValueError("non-verified cell unexpectedly contains a verified interval")
    return frame.sort("research_order", "start_week", "coach_id")


def build_coverage(project_root: Path, evidence: pl.DataFrame) -> pl.DataFrame:
    base = (
        pl.read_csv(_prompt8_root(project_root) / "play_caller_completeness.csv")
        .select("season", "team_id", pl.col("ending_status").alias("starting_status"))
        .sort("season", "team_id")
    )
    actual = dict(base.group_by("starting_status").len().iter_rows())
    if actual != EXPECTED_STARTING_COUNTS:
        raise ValueError(f"Prompt 9 starting matrix drift: {actual}")
    review = evidence.group_by("research_order", "season", "team_id").agg(
        pl.first("batch").alias("batch"),
        pl.first("source_priority_rank").alias("source_priority_rank"),
        pl.first("ending_status").alias("reviewed_status"),
        pl.first("candidate_coach_name").alias("candidate_coach_name"),
    )
    coverage = (
        base.join(review, on=["season", "team_id"], how="left", validate="1:1")
        .with_columns(
            pl.coalesce("reviewed_status", "starting_status").alias("ending_status"),
            pl.col("reviewed_status").is_not_null().alias("researched"),
        )
        .sort("season", "team_id")
    )
    if coverage.height != 512 or coverage.select("season", "team_id").n_unique() != 512:
        raise ValueError("Prompt 9 must preserve the exact 512-cell matrix")
    return coverage


def _prompt8_compatible(evidence: pl.DataFrame) -> pl.DataFrame:
    return evidence.select(
        pl.col("source_priority_rank").alias("priority_rank"),
        "batch",
        "season",
        "team_id",
        "coach_id",
        "coach_canonical_name",
        "start_week",
        "end_week",
        "interval_status",
        pl.col("ending_status").alias("cell_status"),
        "is_shared",
        "source_family",
        pl.col("source_url").alias("primary_source_url"),
        pl.col("corroborating_source_url").alias("secondary_source_url"),
        "evidence_summary",
        pl.when(pl.col("proves_continuity"))
        .then(pl.lit("source_backed_continuity"))
        .otherwise(pl.lit("bounded_or_unresolved"))
        .alias("continuity_basis"),
    )


def build_assignments(project_root: Path, evidence: pl.DataFrame) -> list[dict[str, str]]:
    prompt8_evidence = load_and_validate_play_caller_evidence(project_root)
    base = build_prompt8_assignments(project_root, prompt8_evidence)
    replacement = {
        (row["season"], row["team_id"])
        for row in evidence.filter(pl.col("ending_status").is_in(["verified", "partial"]))
        .select("season", "team_id")
        .unique()
        .to_dicts()
    }
    assignments = [
        row
        for row in base
        if not (
            row["role"] == "play_caller" and (int(row["season"]), row["team_id"]) in replacement
        )
    ]
    for row in evidence.filter(
        pl.col("ending_status").is_in(["verified", "partial"])
        & pl.col("interval_status").is_in(["verified", "provisional"])
    ).to_dicts():
        status = row["interval_status"]
        slug = row["coach_id"].removeprefix("coach-")
        assignments.append(
            {
                "assignment_key": (
                    f"p9-{row['season']}-{row['team_id']}-play_caller-"
                    f"{row['start_week']:02d}-{row['end_week']:02d}-{slug}"
                ),
                "season": str(row["season"]),
                "team_id": row["team_id"],
                "coach_id": row["coach_id"],
                "coach_canonical_name": row["coach_canonical_name"],
                "role": "play_caller",
                "start_week": str(row["start_week"]),
                "end_week": str(row["end_week"]),
                "start_date": "",
                "end_date": "",
                "is_interim": "false",
                "is_shared": str(row["is_shared"]).lower(),
                "is_retained": "false",
                "verification_status": status,
                "confidence_level": "high" if status == "verified" else "medium",
                "interval_basis": (
                    "source_verified_weeks"
                    if status == "verified"
                    else "research_provisional_weeks"
                ),
                "primary_source_url": row["source_url"],
                "notes": row["evidence_summary"],
            }
        )
    keys = [row["assignment_key"] for row in assignments]
    if len(keys) != len(set(keys)):
        raise ValueError("Prompt 9 assignment keys are not unique")
    return assignments


def build_priority_ranking(project_root: Path, evidence: pl.DataFrame) -> pl.DataFrame:
    """Re-rank after the mandatory ten with a documented lexicographic policy."""

    base = pl.read_csv(_prompt8_root(project_root) / "remaining_play_caller_priority.csv").drop(
        "research_data_version", "research_only", "production_ranking"
    )
    top = evidence.filter(pl.col("research_order") <= 10).select("season", "team_id").unique()
    candidates = base.join(top, on=["season", "team_id"], how="anti")
    existing_common = pl.read_csv(_prompt8_root(project_root) / "common_qp_availability.csv")
    caller_history = {
        row["coach_canonical_name"]: {
            "seasons": set(row["season"]),
            "teams": set(row["team_id"]),
        }
        for row in existing_common.group_by("coach_canonical_name")
        .agg(pl.col("season"), pl.col("team_id"))
        .to_dicts()
    }
    rows: list[dict[str, Any]] = []
    selected = {
        (row["season"], row["team_id"]): (row["research_order"], row["batch"])
        for row in evidence.filter(pl.col("research_order") > 10)
        .select("research_order", "batch", "season", "team_id")
        .unique()
        .to_dicts()
    }
    for row in candidates.to_dicts():
        names = str(row["existing_candidate"] or "").split("|")
        histories = [caller_history[name] for name in names if name in caller_history]
        adds_history = any(
            any(season > row["season"] for season in item["seasons"]) for item in histories
        )
        creates_repeat = bool(histories) or bool(row["repeat_caller_unlock"])
        consecutive = any(
            row["season"] - 1 in item["seasons"] or row["season"] + 1 in item["seasons"]
            for item in histories
        )
        different_team = any(row["team_id"] not in item["teams"] for item in histories)
        tier = (
            1
            if row["unlocks_common_qp"] or adds_history
            else 2
            if creates_repeat or consecutive or different_team
            else 3
            if int(row["eligible_plays"] or 0) >= 750
            else 4
        )
        key = (row["season"], row["team_id"])
        order, batch = selected.get(key, (None, None))
        rows.append(
            {
                **row,
                "priority_tier": tier,
                "estimated_added_common_qp_rows": int(bool(row["unlocks_common_qp"])),
                "adds_prior_history_before_future_target": adds_history,
                "creates_repeat_caller": creates_repeat,
                "creates_consecutive_pair": consecutive,
                "creates_different_team_transition": different_team,
                "eligible_play_volume": int(row["eligible_plays"] or 0),
                "existing_candidate_available": bool(str(row["existing_candidate"] or "").strip()),
                "pre_research_evidence_quality": str(row["existing_source"] or "missing"),
                "pre_research_recoverability": row["estimated_recoverability"],
                "selected_research_order": order,
                "selected_batch": batch,
                "priority_basis": (
                    "lexicographic: common/future history; repeat/transition; PCAE volume; coverage"
                ),
            }
        )
    return (
        pl.DataFrame(rows)
        .sort(
            "priority_tier",
            "existing_candidate_available",
            "priority_score",
            "adds_prior_history_before_future_target",
            "creates_repeat_caller",
            "creates_consecutive_pair",
            "eligible_play_volume",
            "season",
            "team_id",
            descending=[False, True, True, True, True, True, True, True, False],
        )
        .with_row_index("prompt9_priority_rank", offset=1)
    )


def build_remaining_queue(
    project_root: Path, coverage: pl.DataFrame, priority: pl.DataFrame, evidence: pl.DataFrame
) -> pl.DataFrame:
    remaining = coverage.filter(pl.col("ending_status") != "verified").join(
        priority.drop("current_status"), on=["season", "team_id"], how="left"
    )
    shared = {
        (row["season"], row["team_id"])
        for row in evidence.filter(
            pl.col("is_shared") | pl.col("contradictory_evidence").str.contains("split was unclear")
        )
        .select("season", "team_id")
        .unique()
        .to_dicts()
    }
    return remaining.with_columns(
        pl.struct("season", "team_id", "ending_status", "prompt9_priority_rank")
        .map_elements(
            lambda row: (
                "KNOWN SHARED / AMBIGUOUS"
                if (row["season"], row["team_id"]) in shared or row["ending_status"] == "partial"
                else "HIGHLY RECOVERABLE"
                if row["ending_status"] == "provisional"
                and row["prompt9_priority_rank"] is not None
                and row["prompt9_priority_rank"] <= 100
                else "POSSIBLY RECOVERABLE"
                if row["ending_status"] == "provisional"
                else "ARCHIVAL / EXPENSIVE"
                if row["prompt9_priority_rank"] is not None and row["prompt9_priority_rank"] <= 250
                else "LIKELY UNRESOLVABLE"
            ),
            return_dtype=pl.String,
        )
        .alias("evidence_ceiling_class"),
        pl.when(pl.col("researched"))
        .then(pl.lit("research completed; retained below verified standard"))
        .otherwise(pl.lit("not researched in bounded Prompt 9 sprint"))
        .alias("queue_note"),
    ).sort("prompt9_priority_rank", "season", "team_id", nulls_last=True)


def _source_lineage(evidence: pl.DataFrame) -> pl.DataFrame:
    return evidence.select(
        "research_order",
        "season",
        "team_id",
        "coach_id",
        "start_week",
        "end_week",
        "interval_status",
        "ending_status",
        "source_url",
        "corroborating_source_url",
        "source_family",
        pl.lit(SOURCE_ACCESS_DATE).alias("access_date"),
        "source_title",
        "source_publisher",
        "publication_date",
        "evidence_locator",
        "evidence_summary",
        "proves_identity",
        "proves_initial_designation",
        "proves_continuity",
        "proves_transition",
        "proves_shared_duties",
        "contradictory_evidence",
        "research_notes",
    ).sort("research_order", "start_week", "coach_id")


def _strip_contract(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.drop("research_data_version", "research_only", "production_ranking", strict=False)


def rebuild_prompt9_pcae(
    project_root: Path, evidence: pl.DataFrame, coverage: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, str], pl.DataFrame]:
    """Append only new verified non-shared intervals to frozen Prompt 8 PCAE."""

    compatible = _prompt8_compatible(evidence)
    trial, _, source_hashes = rebuild_new_pcae_attribution(project_root, compatible, coverage)
    prior = _strip_contract(pl.read_csv(_prompt8_root(project_root) / "historical_pcae.csv"))
    key = ["coach_id", "team_id", "season", "start_week", "end_week"]
    additions = _strip_contract(trial).join(prior.select(key), on=key, how="anti")
    additions = additions.join(
        evidence.select("research_order", "season", "team_id").unique(),
        on=["season", "team_id"],
        validate="m:1",
    )
    if additions.filter(pl.col("is_shared")).height:
        raise ValueError("shared Prompt 9 play-calling was individually attributed")
    combined = pl.concat(
        [prior, additions.drop("research_order").select(prior.columns)], how="vertical_relaxed"
    ).sort("season", "team_id", "coach_id", "start_week")
    if combined.select(key).n_unique() != combined.height:
        raise ValueError("Prompt 9 PCAE contains duplicate interval keys")
    by_season = (
        combined.group_by("season")
        .agg(
            pl.col("attributed_play_count").sum().alias("attributed_plays"),
            pl.col("coach_id").n_unique().alias("attributed_callers"),
            pl.len().alias("caller_intervals"),
        )
        .sort("season")
    )
    return combined, by_season, source_hashes, additions.sort("research_order", "start_week")


def _consecutive_pairs(common: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for group in common.partition_by("coach_id", as_dict=False):
        ordered = group.sort("season", "team_id").to_dicts()
        for prior, current in zip(ordered, ordered[1:], strict=False):
            if current["season"] != prior["season"] + 1:
                continue
            rows.append(
                {
                    "coach_id": current["coach_id"],
                    "coach_canonical_name": current["coach_canonical_name"],
                    "prior_season": prior["season"],
                    "season": current["season"],
                    "prior_team_id": prior["team_id"],
                    "team_id": current["team_id"],
                    "prior_player_ids": prior["player_ids"],
                    "player_ids": current["player_ids"],
                    "different_team": prior["team_id"] != current["team_id"],
                    "different_qb_set": prior["player_ids"] != current["player_ids"],
                }
            )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("coach_id", "season", "team_id")


def build_q_availability(project_root: Path, assignments: list[dict[str, str]]) -> pl.DataFrame:
    """Return all verified non-shared play-caller Q observations before the P intersection."""

    caller = (
        pl.DataFrame(assignments, infer_schema_length=None)
        .with_columns(
            pl.col("season", "start_week", "end_week").cast(pl.Int64),
            (pl.col("is_shared") == "true").alias("is_shared"),
        )
        .filter(
            (pl.col("role") == "play_caller")
            & (pl.col("verification_status") == "verified")
            & (pl.col("interval_basis") != "season_designation")
            & ~pl.col("is_shared")
        )
    )
    sources = _sources(project_root)
    games = (
        pl.read_parquet(sources.pae_path.parent / "canonical_qb_game_performance.parquet")
        .select("season", "week", "player_id", "team_id", "dropbacks")
        .with_columns(
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase(),
            pl.col("dropbacks").cast(pl.Float64),
        )
    )
    q_signal = (
        pl.read_csv(
            project_root
            / "research/coach_effect/outputs/checkpoint_12"
            / PROMPT6_VERSION
            / "joined_research_table.csv"
        )
        .select(
            "player_id",
            "team_id",
            "season",
            "quarterback_name",
            "full_season_q_development_signal",
        )
        .unique()
        .with_columns(
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase(),
            pl.col("full_season_q_development_signal").cast(pl.Float64, strict=False),
        )
    )
    return (
        games.join(caller, on=["season", "team_id"], how="inner", validate="m:m")
        .filter(pl.col("week").is_between(pl.col("start_week"), pl.col("end_week")))
        .group_by("coach_id", "coach_canonical_name", "team_id", "season", "player_id")
        .agg(pl.col("dropbacks").sum().alias("q_exposure"))
        .join(q_signal, on=["player_id", "team_id", "season"], how="left", validate="m:1")
        .filter(pl.col("full_season_q_development_signal").is_not_null())
        .group_by("coach_id", "coach_canonical_name", "team_id", "season")
        .agg(
            (
                (pl.col("full_season_q_development_signal") * pl.col("q_exposure")).sum()
                / pl.col("q_exposure").sum()
            ).alias("q_development_signal"),
            pl.col("q_exposure").sum(),
            pl.col("player_id").n_unique().alias("quarterbacks"),
        )
        .sort("season", "coach_id", "team_id")
    )


def _season_matrix(
    coverage: pl.DataFrame,
    pcae_by_season: pl.DataFrame,
    q_availability: pl.DataFrame,
    common: pl.DataFrame,
    folds: pl.DataFrame,
) -> pl.DataFrame:
    counts = coverage.group_by("season").agg(
        (pl.col("ending_status") == "verified").sum().alias("verified_caller_cells")
    )
    q_counts = q_availability.group_by("season").agg(pl.len().alias("q_observations"))
    return (
        pl.DataFrame({"season": list(range(2010, 2026))})
        .join(counts, on="season", how="left", validate="1:1")
        .join(pcae_by_season.select("season", "attributed_plays"), on="season", how="left")
        .join(q_counts, on="season", how="left")
        .join(
            folds.select(
                "season",
                "common_qp_rows",
                "future_target_rows",
                "prior_training_rows",
                "eligible_as_target",
                "reason",
            ),
            on="season",
            validate="1:1",
        )
        .with_columns(
            pl.col(
                "attributed_plays", "q_observations", "common_qp_rows", "future_target_rows"
            ).fill_null(0)
        )
        .sort("season")
    )


def _readiness(coverage: pl.DataFrame, common: pl.DataFrame, folds: pl.DataFrame) -> pl.DataFrame:
    counts = dict(coverage.group_by("ending_status").len().iter_rows())
    fold_count = folds.filter(pl.col("eligible_as_target")).height
    future = int(folds["future_target_rows"].sum())
    units = {
        "seasons": common["season"].n_unique() if common.height else 0,
        "coaches": common["coach_id"].n_unique() if common.height else 0,
        "teams": common["team_id"].n_unique() if common.height else 0,
        "quarterbacks": int(common["quarterbacks"].sum()) if common.height else 0,
    }
    gate_results = (
        counts.get("verified", 0) >= PLAY_CALLER_GATE,
        fold_count >= TARGET_FOLD_GATE,
        future >= COMMON_FUTURE_GATE,
        units["seasons"] >= 5
        and units["coaches"] >= 20
        and units["teams"] >= 20
        and units["quarterbacks"] >= 30,
    )
    rows = (
        (
            "A_verified_play_caller_coverage",
            ">=256 verified cells",
            str(counts.get("verified", 0)),
            gate_results[0],
        ),
        (
            "B_chronological_target_folds",
            ">=5 eligible target seasons",
            str(fold_count),
            gate_results[1],
        ),
        ("C_common_future_qp_rows", ">=150 future target rows", str(future), gate_results[2]),
        (
            "D_resampling_feasibility",
            ">=5 seasons; >=20 coaches/teams; >=30 QB observations",
            json.dumps(units, sort_keys=True),
            gate_results[3],
        ),
    )
    output = [
        {
            "gate": gate,
            "threshold": threshold,
            "observed": observed,
            "result": "PASS" if passed else "FAIL",
        }
        for gate, threshold, observed, passed in rows
    ]
    output.append(
        {
            "gate": "FINAL_COACH_EFFECT_RERUN_READINESS",
            "threshold": "all four gates pass",
            "observed": "all_pass" if all(gate_results) else "one_or_more_failed",
            "result": "READY" if all(gate_results) else "NOT READY",
        }
    )
    return pl.DataFrame(output)


def _snapshot(
    project_root: Path,
    evidence: pl.DataFrame,
    coverage: pl.DataFrame,
    prior_pcae: pl.DataFrame,
    additions: pl.DataFrame,
    cutoff: int,
    label: str,
) -> dict[str, Any]:
    subset = evidence.filter(pl.col("research_order") <= cutoff)
    subset_coverage = coverage.with_columns(
        pl.when(pl.col("research_order").is_not_null() & (pl.col("research_order") > cutoff))
        .then(pl.col("starting_status"))
        .otherwise(pl.col("ending_status"))
        .alias("ending_status"),
        (pl.col("research_order").is_not_null() & (pl.col("research_order") <= cutoff)).alias(
            "researched"
        ),
    )
    assignments = build_assignments(project_root, subset)
    stage_additions = additions.filter(pl.col("research_order") <= cutoff).drop("research_order")
    pcae = pl.concat(
        [prior_pcae, stage_additions.select(prior_pcae.columns)], how="vertical_relaxed"
    )
    common, folds, repeat, different_qb, different_team = build_common_qp_availability(
        project_root, assignments, pcae, subset_coverage
    )
    counts = dict(subset_coverage.group_by("ending_status").len().iter_rows())
    pairs = _consecutive_pairs(common)
    return {
        "batch": label,
        "researched_cells": cutoff,
        "verified_cells": counts.get("verified", 0),
        "partial_cells": counts.get("partial", 0),
        "provisional_cells": counts.get("provisional", 0),
        "unresolved_cells": counts.get("unresolved", 0),
        "common_qp_coach_seasons": common.height,
        "common_future_qp_rows": int(folds["future_target_rows"].sum()),
        "eligible_target_folds": folds.filter(pl.col("eligible_as_target")).height,
        "repeat_play_callers": repeat.height,
        "consecutive_play_caller_pairs": pairs.height,
        "different_qb_samples": different_qb.height,
        "different_team_samples": different_team.height,
    }


def _verify_sources(project_root: Path, hashes: dict[str, str]) -> None:
    changed = [path for path, digest in hashes.items() if _sha256(project_root / path) != digest]
    if changed:
        raise ValueError(f"Prompt 9 source bytes changed during build: {sorted(changed)}")


def run_checkpoint_twelve_play_caller_verification(
    project_root: Path, output_root: Path | None = None
) -> Prompt9Result:
    """Create deterministic Prompt 9 evidence and readiness artifacts.

    This research-only step does not fit Coach Effect.
    """

    evidence = load_and_validate_prompt9_evidence(project_root)
    coverage = build_coverage(project_root, evidence)
    priority = build_priority_ranking(project_root, evidence)
    assignments = build_assignments(project_root, evidence)
    historical_pcae, pcae_by_season, pcae_hashes, additions = rebuild_prompt9_pcae(
        project_root, evidence, coverage
    )
    common, folds, repeat, different_qb, different_team = build_common_qp_availability(
        project_root, assignments, historical_pcae, coverage
    )
    q_availability = build_q_availability(project_root, assignments)
    pairs = _consecutive_pairs(common)
    season_matrix = _season_matrix(coverage, pcae_by_season, q_availability, common, folds)
    readiness = _readiness(coverage, common, folds)
    prompt8_pcae = _strip_contract(pl.read_csv(_prompt8_root(project_root) / "historical_pcae.csv"))
    snapshots = pl.DataFrame(
        [
            _snapshot(
                project_root, evidence, coverage, prompt8_pcae, additions, 10, "mandatory_top10"
            ),
            _snapshot(
                project_root, evidence, coverage, prompt8_pcae, additions, 30, "dynamic_batch_1"
            ),
            _snapshot(
                project_root, evidence, coverage, prompt8_pcae, additions, 50, "dynamic_batch_2"
            ),
        ]
    )
    reviewed = (
        evidence.group_by("research_order", "batch", "source_priority_rank", "season", "team_id")
        .agg(
            pl.first("candidate_coach_name").alias("candidate_coach_name"),
            pl.first("starting_status").alias("starting_status"),
            pl.first("ending_status").alias("ending_status"),
            pl.col("coach_id").unique().sort().str.join("|").alias("researched_coach_ids"),
            pl.col("source_url").n_unique().alias("primary_sources"),
            pl.col("corroborating_source_url")
            .filter(pl.col("corroborating_source_url") != "")
            .n_unique()
            .alias("corroborating_sources"),
            pl.col("research_notes").unique().sort().str.join(" | ").alias("research_notes"),
        )
        .sort("research_order")
    )
    accepted = evidence.filter(pl.col("disposition") != "rejected_full_verification")
    rejected = evidence.filter(pl.col("disposition") == "rejected_full_verification")
    verified_intervals = evidence.filter(pl.col("interval_status") == "verified").with_columns(
        (
            pl.lit("p9-")
            + pl.col("season").cast(pl.String)
            + "-"
            + pl.col("team_id")
            + "-play_caller-"
            + pl.col("start_week").cast(pl.String).str.pad_start(2, "0")
            + "-"
            + pl.col("end_week").cast(pl.String).str.pad_start(2, "0")
            + "-"
            + pl.col("coach_id").str.strip_prefix("coach-")
        ).alias("assignment_key")
    )
    remaining = build_remaining_queue(project_root, coverage, priority, evidence)
    lineage = _source_lineage(evidence)

    input_paths = [
        project_root / EVIDENCE_FILE,
        project_root / "research/coach_effect/checkpoint_twelve_play_caller_verification.py",
        project_root / "research/coach_effect/checkpoint_twelve_data_expansion.py",
        _prompt8_root(project_root) / "MANIFEST.json",
        _prompt8_root(project_root) / "play_caller_completeness.csv",
        _prompt8_root(project_root) / "remaining_play_caller_priority.csv",
        _prompt8_root(project_root) / "historical_pcae.csv",
        _prompt8_root(project_root) / "common_qp_availability.csv",
        project_root
        / "research/coach_effect/outputs/checkpoint_12"
        / PROMPT6_VERSION
        / "joined_research_table.csv",
    ]
    input_hashes = {str(path.relative_to(project_root)): _sha256(path) for path in input_paths}
    input_hashes.update(pcae_hashes)
    identity = {
        "specification": PROMPT9_SPECIFICATION,
        "prompt8_version": PROMPT8_VERSION,
        "pcae_model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "pcae_play_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "call_value_formula": CALL_VALUE_FORMULA,
        "pcae_formula": PCAE_FORMULA,
        "play_call_features": PLAY_CALL_FEATURES,
        "selection_policy": "lexicographic-common-history-repeat-transition-volume-coverage-v1",
        "batch_cutoffs": [10, 30, 50],
        "gates": {
            "verified": PLAY_CALLER_GATE,
            "folds": TARGET_FOLD_GATE,
            "future_common": COMMON_FUTURE_GATE,
        },
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "source_hashes": dict(sorted(input_hashes.items())),
    }
    data_version = (
        "c12-pc-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    historical_pcae = historical_pcae.with_columns(pl.lit(data_version).alias("data_version"))
    outputs = {
        "researched_cells.csv": reviewed,
        "accepted_evidence.csv": accepted,
        "rejected_evidence.csv": rejected,
        "newly_verified_intervals.csv": verified_intervals,
        "partial_intervals.csv": evidence.filter(pl.col("ending_status") == "partial"),
        "shared_intervals.csv": evidence.filter(pl.col("is_shared")),
        "source_lineage.csv": lineage,
        "play_caller_completeness.csv": coverage,
        "remaining_unresolved_queue.csv": remaining,
        "priority_ranking.csv": priority,
        "historical_pcae.csv": historical_pcae,
        "pcae_attribution_by_season.csv": pcae_by_season,
        "common_qp_availability.csv": common,
        "future_fold_matrix.csv": folds,
        "repeat_play_callers.csv": repeat,
        "consecutive_play_caller_pairs.csv": pairs,
        "different_qb_samples.csv": different_qb,
        "different_team_samples.csv": different_team,
        "caller_team_transitions.csv": different_team,
        "caller_qb_transitions.csv": different_qb,
        "season_readiness_matrix.csv": season_matrix,
        "batch_snapshots.csv": snapshots,
        "readiness_gate_status.csv": readiness,
    }
    if set(outputs) != set(OUTPUT_NAMES):
        raise ValueError("Prompt 9 output contract drift")
    outputs = {name: _add_research_contract(frame, data_version) for name, frame in outputs.items()}
    _verify_sources(project_root, input_hashes)

    root = (
        output_root
        or project_root / "research/coach_effect/outputs/checkpoint_12_play_caller_verification"
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
        "scheme_methodology_changed": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {name: outputs[name].height for name in OUTPUT_NAMES},
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    _verify_sources(project_root, input_hashes)
    if destination.exists():
        expected = {"MANIFEST.json", *OUTPUT_NAMES}
        actual = {path.name for path in destination.iterdir() if path.is_file()}
        if actual != expected:
            raise ValueError("existing Prompt 9 publication has unexpected files")
        for name in expected:
            if _sha256(destination / name) != _sha256(temporary / name):
                raise ValueError(f"existing Prompt 9 deterministic output differs: {name}")
        shutil.rmtree(temporary)
    else:
        temporary.replace(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "LATEST").write_text(data_version + "\n", encoding="utf-8")
    return Prompt9Result(
        output_path=destination,
        data_version=data_version,
        coverage=outputs["play_caller_completeness.csv"],
        readiness=outputs["readiness_gate_status.csv"],
    )

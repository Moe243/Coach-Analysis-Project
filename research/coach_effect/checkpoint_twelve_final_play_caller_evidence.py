"""Prompt 10 research-only final play-caller evidence closing sprint.

This module overlays only explicitly sourced play-caller intervals on the frozen Prompt 9
research state. It refreshes availability diagnostics with the unchanged PCAE and Q contracts;
it does not fit Coach Effect or write to any production surface.
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
    build_common_qp_availability,
    rebuild_new_pcae_attribution,
)
from research.coach_effect.checkpoint_twelve_play_caller_verification import (
    PROMPT8_VERSION,
    _consecutive_pairs,
    _readiness,
    _strip_contract,
    build_q_availability,
    load_and_validate_prompt9_evidence,
)
from research.coach_effect.checkpoint_twelve_play_caller_verification import (
    build_assignments as build_prompt9_assignments,
)
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
)

PROMPT10_SPECIFICATION = "checkpoint-twelve-final-play-caller-evidence-v1"
PROMPT9_VERSION = "c12-pc-2cf75b19b3c42914"
EVIDENCE_FILE = "research/coach_effect/play_caller_evidence_prompt10.csv"
SOURCE_FILE = "research/coach_effect/play_caller_sources_prompt10.csv"
SOURCE_ACCESS_DATE = "2026-09-08"
EXPECTED_STARTING_COUNTS = {
    "verified": 184,
    "partial": 4,
    "provisional": 56,
    "unresolved": 268,
}
EXPECTED_RESEARCH_COUNTS = {
    "highly_recoverable": 28,
    "possibly_recoverable": 27,
    "known_shared_ambiguous": 5,
    "archival_expensive": 15,
}
REQUIRED_OPENING_QUEUE = (
    (2021, "IND"),
    (2021, "DEN"),
    (2022, "NO"),
    (2020, "IND"),
    (2022, "TEN"),
)
SNAPSHOT_CUTOFFS = (5, 15, 28, 40, 55, 65, 75)
OUTPUT_NAMES = (
    "researched_cells.csv",
    "newly_verified_evidence.csv",
    "provisional_conversions.csv",
    "partial_cell_updates.csv",
    "rejected_evidence.csv",
    "archival_source_records.csv",
    "source_lineage.csv",
    "play_caller_completeness.csv",
    "remaining_evidence_queue.csv",
    "coverage_by_season.csv",
    "coverage_by_era.csv",
    "coverage_missingness_diagnostics.csv",
    "historical_pcae.csv",
    "pcae_attribution_by_season.csv",
    "common_qp_availability.csv",
    "future_fold_matrix.csv",
    "repeat_play_callers.csv",
    "consecutive_play_caller_pairs.csv",
    "different_qb_samples.csv",
    "different_team_samples.csv",
    "season_readiness_matrix.csv",
    "batch_snapshots.csv",
    "evidence_ceiling.csv",
    "readiness_gate_status.csv",
)


@dataclass(frozen=True)
class Prompt10Result:
    output_path: Path
    data_version: str
    coverage: pl.DataFrame
    readiness: pl.DataFrame


def _prompt9_root(project_root: Path) -> Path:
    root = project_root / "research/coach_effect/outputs/checkpoint_12_play_caller_verification"
    if (root / "LATEST").read_text(encoding="utf-8").strip() != PROMPT9_VERSION:
        raise ValueError("Prompt 10 requires the frozen Prompt 9 research baseline")
    version = root / PROMPT9_VERSION
    if not version.is_dir():
        raise ValueError("Prompt 9 output directory is missing")
    return version


def _read_sources(project_root: Path) -> pl.DataFrame:
    sources = pl.read_csv(
        project_root / SOURCE_FILE, infer_schema_length=None, null_values=[]
    ).fill_null("")
    required = (
        "source_code",
        "url",
        "title",
        "publisher",
        "publication_date",
        "source_family",
        "evidence_locator",
        "evidence_summary",
    )
    for field in required:
        if sources.filter(pl.col(field).str.strip_chars() == "").height:
            raise ValueError(f"Prompt 10 source catalog has a blank required field: {field}")
    if sources["source_code"].n_unique() != sources.height:
        raise ValueError("Prompt 10 source codes must be unique")
    for row in sources.to_dicts():
        for field in ("url", "secondary_url", "archive_url"):
            value = row[field].strip()
            if value and urlparse(value).scheme != "https":
                raise ValueError(f"Prompt 10 source is not HTTPS: {value}")
        if bool(row["archive_url"]) != bool(row["archive_date"]):
            raise ValueError("archive URL and archive date must be populated together")
    return sources.sort("source_code")


def _parse_intervals(value: str) -> list[dict[str, Any]]:
    if not value.strip():
        return []
    rows: list[dict[str, Any]] = []
    for token in value.split(";"):
        parts = token.split("~")
        if len(parts) != 6:
            raise ValueError(f"invalid Prompt 10 interval token: {token}")
        coach_id, name, start, end, status, shared = parts
        rows.append(
            {
                "coach_id": coach_id,
                "coach_canonical_name": name,
                "start_week": int(start),
                "end_week": int(end),
                "interval_status": status,
                "is_shared": shared == "true",
            }
        )
    return rows


def load_and_validate_prompt10_evidence(
    project_root: Path,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Validate the fixed sprint order and turn compact interval records into a ledger."""

    cells = pl.read_csv(
        project_root / EVIDENCE_FILE, infer_schema_length=None, null_values=[]
    ).fill_null("")
    cells = cells.with_columns(pl.col("research_order", "season").cast(pl.Int64))
    sources = _read_sources(project_root)
    if cells.height != 75 or cells["research_order"].sort().to_list() != list(range(1, 76)):
        raise ValueError("Prompt 10 must preserve exactly 75 ordered research reviews")
    actual_tiers = dict(cells.group_by("tier").len().iter_rows())
    if actual_tiers != EXPECTED_RESEARCH_COUNTS:
        raise ValueError(f"Prompt 10 research tiers drifted: {actual_tiers}")
    opening = tuple(cells.sort("research_order").head(5).select("season", "team_id").rows())
    if opening != REQUIRED_OPENING_QUEUE:
        raise ValueError("Prompt 10 did not begin with the required five-cell queue")
    for field in (
        "team_id",
        "starting_status",
        "ending_status",
        "provisional_gap",
        "statistical_value",
        "disposition",
        "research_notes",
    ):
        if cells.filter(pl.col(field).str.strip_chars() == "").height:
            raise ValueError(f"Prompt 10 cell ledger has a blank required field: {field}")
    valid_status = {"verified", "partial", "provisional", "unresolved"}
    if set(cells["starting_status"]) - valid_status or set(cells["ending_status"]) - valid_status:
        raise ValueError("Prompt 10 cell ledger contains an invalid status")

    starting = pl.read_csv(_prompt9_root(project_root) / "play_caller_completeness.csv")
    starting_counts = dict(starting.group_by("ending_status").len().iter_rows())
    if starting_counts != EXPECTED_STARTING_COUNTS:
        raise ValueError(f"Prompt 10 starting matrix drifted: {starting_counts}")
    expected = starting.select(
        "season", "team_id", pl.col("ending_status").alias("expected_starting_status")
    )
    joined = cells.join(expected, on=["season", "team_id"], validate="m:1")
    if (
        joined.height != cells.height
        or joined.filter(pl.col("starting_status") != pl.col("expected_starting_status")).height
    ):
        raise ValueError("Prompt 10 starting status differs from frozen Prompt 9")

    source_codes = set(sources["source_code"])
    source_lookup = {row["source_code"]: row for row in sources.to_dicts()}
    interval_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    for cell in cells.sort("research_order").to_dicts():
        codes = [code.strip() for code in cell["evidence_codes"].split(";") if code.strip()]
        missing = sorted(set(codes) - source_codes)
        if missing:
            raise ValueError(f"unknown Prompt 10 source codes: {missing}")
        if not codes and cell["disposition"] not in {"no_accessible_evidence", "retained_prior"}:
            raise ValueError("researched evidence row lacks a source record")
        for code in codes:
            source = source_lookup[code]
            lineage_rows.append(
                {
                    "research_order": cell["research_order"],
                    "tier": cell["tier"],
                    "season": cell["season"],
                    "team_id": cell["team_id"],
                    "source_code": code,
                    "access_date": SOURCE_ACCESS_DATE,
                    **source,
                }
            )
        intervals = _parse_intervals(cell["intervals"])
        if intervals and not codes:
            raise ValueError("an interval cannot be accepted without a source")
        primary = source_lookup[codes[0]] if codes else None
        for interval in intervals:
            last_week = 18 if cell["season"] >= 2021 else 17
            if not 1 <= interval["start_week"] <= interval["end_week"] <= last_week:
                raise ValueError(f"invalid interval in {cell['season']}-{cell['team_id']}")
            expected_id = f"coach-{normalize_coach_name(interval['coach_canonical_name'])}"
            if interval["coach_id"] != expected_id:
                raise ValueError(f"canonical coach mismatch: {interval['coach_id']}")
            if interval["interval_status"] not in {"verified", "provisional"}:
                raise ValueError("Prompt 10 intervals must be verified or provisional")
            interval_rows.append(
                {
                    "research_order": cell["research_order"],
                    "tier": cell["tier"],
                    "season": cell["season"],
                    "team_id": cell["team_id"],
                    "ending_status": cell["ending_status"],
                    **interval,
                    "source_code": codes[0],
                    "primary_source_url": primary["url"],
                    "secondary_source_url": primary["secondary_url"],
                    "source_family": primary["source_family"],
                    "evidence_summary": primary["evidence_summary"],
                }
            )

        verified = [row for row in intervals if row["interval_status"] == "verified"]
        for index, left in enumerate(verified):
            for right in verified[index + 1 :]:
                overlaps = right["start_week"] <= left["end_week"] and (
                    right["end_week"] >= left["start_week"]
                )
                if overlaps and not (left["is_shared"] and right["is_shared"]):
                    raise ValueError("overlapping non-shared Prompt 10 intervals")
        last_week = 18 if cell["season"] >= 2021 else 17
        individual_weeks = {
            week
            for row in verified
            if not row["is_shared"]
            for week in range(row["start_week"], row["end_week"] + 1)
        }
        full = individual_weeks == set(range(1, last_week + 1))
        if cell["ending_status"] == "verified" and not full:
            raise ValueError("verified cell lacks complete non-shared weekly coverage")
        if cell["ending_status"] == "partial" and cell["intervals"] and (not verified or full):
            raise ValueError("updated partial cell must have useful incomplete verified evidence")
        if cell["ending_status"] in {"provisional", "unresolved"} and verified:
            raise ValueError("non-verified cell contains a verified interval")
        if any(row["is_shared"] for row in verified) and cell["ending_status"] == "verified":
            raise ValueError("shared evidence cannot produce individual full-cell verification")

    interval_schema = {
        "research_order": pl.Int64,
        "tier": pl.String,
        "season": pl.Int64,
        "team_id": pl.String,
        "ending_status": pl.String,
        "coach_id": pl.String,
        "coach_canonical_name": pl.String,
        "start_week": pl.Int64,
        "end_week": pl.Int64,
        "interval_status": pl.String,
        "is_shared": pl.Boolean,
        "source_code": pl.String,
        "primary_source_url": pl.String,
        "secondary_source_url": pl.String,
        "source_family": pl.String,
        "evidence_summary": pl.String,
    }
    intervals = pl.DataFrame(interval_rows, schema=interval_schema).sort(
        "research_order", "start_week", "coach_id"
    )
    lineage = pl.DataFrame(lineage_rows).sort("research_order", "source_code")
    return cells.sort("research_order"), intervals, lineage


def build_coverage(project_root: Path, cells: pl.DataFrame) -> pl.DataFrame:
    starting = (
        pl.read_csv(_prompt9_root(project_root) / "play_caller_completeness.csv")
        .drop("research_data_version", "research_only", "production_ranking", strict=False)
        .select(
            "season",
            "team_id",
            pl.col("ending_status").alias("starting_status"),
        )
    )
    reviews = cells.select(
        "research_order",
        "tier",
        "season",
        "team_id",
        pl.col("ending_status").alias("reviewed_status"),
        "provisional_gap",
        "disposition",
    )
    coverage = (
        starting.join(reviews, on=["season", "team_id"], how="left", validate="1:1")
        .with_columns(
            pl.coalesce("reviewed_status", "starting_status").alias("ending_status"),
            pl.col("reviewed_status").is_not_null().alias("researched_prompt10"),
            pl.col("reviewed_status").is_not_null().alias("researched"),
        )
        .sort("season", "team_id")
    )
    if coverage.height != 512 or coverage.select("season", "team_id").n_unique() != 512:
        raise ValueError("Prompt 10 must preserve the 512-cell matrix")
    return coverage


def build_assignments(
    project_root: Path, cells: pl.DataFrame, intervals: pl.DataFrame
) -> list[dict[str, str]]:
    base = build_prompt9_assignments(project_root, load_and_validate_prompt9_evidence(project_root))
    replacement = set(intervals.select("season", "team_id").unique().rows())
    assignments = [
        row
        for row in base
        if not (
            row["role"] == "play_caller" and (int(row["season"]), row["team_id"]) in replacement
        )
    ]
    for row in intervals.to_dicts():
        slug = row["coach_id"].removeprefix("coach-")
        assignments.append(
            {
                "assignment_key": (
                    f"p10-{row['season']}-{row['team_id']}-play_caller-"
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
                "verification_status": row["interval_status"],
                "confidence_level": "high" if row["interval_status"] == "verified" else "medium",
                "interval_basis": (
                    "source_verified_weeks"
                    if row["interval_status"] == "verified"
                    else "research_provisional_weeks"
                ),
                "primary_source_url": row["primary_source_url"],
                "notes": row["evidence_summary"],
            }
        )
    keys = [row["assignment_key"] for row in assignments]
    if len(keys) != len(set(keys)):
        raise ValueError("Prompt 10 assignment keys are not unique")
    return assignments


def _compatible_intervals(intervals: pl.DataFrame) -> pl.DataFrame:
    return intervals.select(
        pl.col("research_order").alias("priority_rank"),
        pl.col("tier").alias("batch"),
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
        "primary_source_url",
        "secondary_source_url",
        "evidence_summary",
        pl.when(pl.col("ending_status") == "verified")
        .then(pl.lit("cumulative_source_backed_continuity"))
        .otherwise(pl.lit("bounded_or_unresolved"))
        .alias("continuity_basis"),
    )


def rebuild_prompt10_pcae(
    project_root: Path,
    cells: pl.DataFrame,
    intervals: pl.DataFrame,
    coverage: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, str], pl.DataFrame]:
    prior = _strip_contract(pl.read_csv(_prompt9_root(project_root) / "historical_pcae.csv"))
    key = ["coach_id", "team_id", "season", "start_week", "end_week"]
    candidate_intervals = intervals.filter(
        (pl.col("interval_status") == "verified") & ~pl.col("is_shared")
    ).join(prior.select(key), on=key, how="anti")
    trial, _, source_hashes = rebuild_new_pcae_attribution(
        project_root, _compatible_intervals(candidate_intervals), coverage
    )
    additions = _strip_contract(trial).join(prior.select(key), on=key, how="anti")
    additions = additions.join(
        cells.select("research_order", "season", "team_id"),
        on=["season", "team_id"],
        validate="m:1",
    )
    if additions.filter(pl.col("is_shared") | (pl.col("verification_status") != "verified")).height:
        raise ValueError("shared or provisional Prompt 10 play calling was attributed")
    combined = pl.concat(
        [prior, additions.drop("research_order").select(prior.columns)], how="vertical_relaxed"
    ).sort("season", "team_id", "coach_id", "start_week")
    if combined.select(key).n_unique() != combined.height:
        raise ValueError("Prompt 10 PCAE interval grain is not unique")
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


def _coverage_by_season(coverage: pl.DataFrame) -> pl.DataFrame:
    return (
        coverage.group_by("season")
        .agg(
            pl.len().alias("cells"),
            (pl.col("ending_status") == "verified").sum().alias("verified"),
            (pl.col("ending_status") == "partial").sum().alias("partial"),
            (pl.col("ending_status") == "provisional").sum().alias("provisional"),
            (pl.col("ending_status") == "unresolved").sum().alias("unresolved"),
        )
        .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
        .sort("season")
    )


def _era_name(season: int) -> str:
    if season <= 2014:
        return "2010-2014"
    if season <= 2019:
        return "2015-2019"
    if season <= 2022:
        return "2020-2022"
    return "2023-2025"


def build_missingness(
    project_root: Path, coverage: pl.DataFrame, common: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    enriched = coverage.with_columns(
        pl.col("season").map_elements(_era_name, return_dtype=pl.String).alias("era"),
        (pl.col("season") >= 2020).alias("modern_era"),
    )
    eras = (
        enriched.group_by("era")
        .agg(
            pl.len().alias("cells"),
            (pl.col("ending_status") == "verified").sum().alias("verified"),
            (pl.col("ending_status") != "verified").sum().alias("missing_verified_identity"),
        )
        .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
        .sort("era")
    )
    diagnostic_rows: list[dict[str, Any]] = []
    for row in eras.to_dicts():
        diagnostic_rows.append(
            {
                "dimension": "era",
                "group": row["era"],
                "cells": row["cells"],
                "verified": row["verified"],
                "verified_rate": row["verified_rate"],
                "interpretation": "later official archives are materially more complete",
            }
        )
    for row in (
        enriched.group_by("team_id")
        .agg(
            pl.len().alias("cells"),
            (pl.col("ending_status") == "verified").sum().alias("verified"),
        )
        .with_columns((pl.col("verified") / pl.col("cells")).alias("verified_rate"))
        .sort("verified_rate", "team_id")
        .to_dicts()
    ):
        diagnostic_rows.append(
            {
                "dimension": "team",
                "group": row["team_id"],
                "cells": row["cells"],
                "verified": row["verified"],
                "verified_rate": row["verified_rate"],
                "interpretation": "team archive availability varies materially",
            }
        )
    repeated = set(
        common.group_by("coach_id").len().filter(pl.col("len") >= 2)["coach_id"].to_list()
    )
    assignment_path = _prompt9_root(project_root) / "common_qp_availability.csv"
    prior_common = pl.read_csv(assignment_path)
    prior_repeated = set(
        prior_common.group_by("coach_id").len().filter(pl.col("len") >= 2)["coach_id"].to_list()
    )
    diagnostic_rows.extend(
        [
            {
                "dimension": "coaching_role",
                "group": "play_caller",
                "cells": coverage.height,
                "verified": coverage.filter(pl.col("ending_status") == "verified").height,
                "verified_rate": coverage.filter(pl.col("ending_status") == "verified").height
                / coverage.height,
                "interpretation": "this sprint evaluates only explicit in-game offensive callers",
            },
            {
                "dimension": "repeat_caller_proxy",
                "group": "repeat_callers_in_common_qp",
                "cells": len(repeated),
                "verified": len(repeated),
                "verified_rate": 1.0 if repeated else 0.0,
                "interpretation": "prominent repeated callers are easier to corroborate",
            },
            {
                "dimension": "repeat_caller_proxy",
                "group": "repeat_callers_before_prompt10",
                "cells": len(prior_repeated),
                "verified": len(prior_repeated),
                "verified_rate": 1.0 if prior_repeated else 0.0,
                "interpretation": "comparison baseline for prominence bias",
            },
            {
                "dimension": "offensive_quality_proxy",
                "group": "not_used_for_verification",
                "cells": 0,
                "verified": 0,
                "verified_rate": None,
                "interpretation": "evidence acceptance never used offensive outcomes or quality",
            },
        ]
    )
    return eras, pl.DataFrame(diagnostic_rows).sort("dimension", "group")


def _season_matrix(
    coverage: pl.DataFrame,
    pcae_by_season: pl.DataFrame,
    q_availability: pl.DataFrame,
    folds: pl.DataFrame,
) -> pl.DataFrame:
    season = _coverage_by_season(coverage)
    q_counts = q_availability.group_by("season").agg(pl.len().alias("q_observations"))
    return (
        season.join(pcae_by_season.select("season", "attributed_plays"), on="season", how="left")
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
        .with_columns(pl.col("attributed_plays", "q_observations").fill_null(0))
        .sort("season")
    )


def _remaining_queue(
    project_root: Path, coverage: pl.DataFrame, cells: pl.DataFrame
) -> pl.DataFrame:
    prior = pl.read_csv(_prompt9_root(project_root) / "remaining_unresolved_queue.csv").drop(
        "research_data_version", "research_only", "production_ranking", strict=False
    )
    reviewed = cells.select("season", "team_id", "tier", "research_order", "provisional_gap")
    return (
        coverage.filter(pl.col("ending_status") != "verified")
        .join(
            prior.drop("ending_status", "starting_status", strict=False),
            on=["season", "team_id"],
            how="left",
        )
        .join(reviewed, on=["season", "team_id"], how="left", suffix="_prompt10")
        .with_columns(
            pl.when(pl.col("tier").is_in(["highly_recoverable", "possibly_recoverable"]))
            .then(pl.lit("researched_and_exhausted"))
            .when(pl.col("tier") == "archival_expensive")
            .then(pl.lit("researched_archival"))
            .when(pl.col("tier") == "known_shared_ambiguous")
            .then(pl.lit("known_shared_or_ambiguous"))
            .otherwise(pl.col("evidence_ceiling_class"))
            .alias("prompt10_remaining_class")
        )
        .sort("prompt9_priority_rank", "season", "team_id", nulls_last=True)
    )


def _snapshot(
    project_root: Path,
    cells: pl.DataFrame,
    intervals: pl.DataFrame,
    coverage: pl.DataFrame,
    prior_pcae: pl.DataFrame,
    additions: pl.DataFrame,
    cutoff: int,
) -> dict[str, Any]:
    subset_cells = cells.filter(pl.col("research_order") <= cutoff)
    subset_intervals = intervals.filter(pl.col("research_order") <= cutoff)
    stage_coverage = coverage.with_columns(
        pl.when(pl.col("research_order").is_not_null() & (pl.col("research_order") > cutoff))
        .then(pl.col("starting_status"))
        .otherwise(pl.col("ending_status"))
        .alias("ending_status"),
        (pl.col("research_order").is_not_null() & (pl.col("research_order") <= cutoff)).alias(
            "researched_prompt10"
        ),
        (pl.col("research_order").is_not_null() & (pl.col("research_order") <= cutoff)).alias(
            "researched"
        ),
    )
    assignments = build_assignments(project_root, subset_cells, subset_intervals)
    stage_additions = additions.filter(pl.col("research_order") <= cutoff).drop("research_order")
    pcae = pl.concat(
        [prior_pcae, stage_additions.select(prior_pcae.columns)], how="vertical_relaxed"
    )
    common, folds, repeat, different_qb, different_team = build_common_qp_availability(
        project_root, assignments, pcae, stage_coverage
    )
    counts = dict(stage_coverage.group_by("ending_status").len().iter_rows())
    return {
        "research_cutoff": cutoff,
        "verified_cells": counts.get("verified", 0),
        "partial_cells": counts.get("partial", 0),
        "provisional_cells": counts.get("provisional", 0),
        "unresolved_cells": counts.get("unresolved", 0),
        "verified_percentage": counts.get("verified", 0) / 512,
        "pcae_attributed_plays": int(pcae["attributed_play_count"].sum()),
        "common_qp_coach_seasons": common.height,
        "common_future_qp_rows": int(folds["future_target_rows"].sum()),
        "target_folds": folds.filter(pl.col("eligible_as_target")).height,
        "repeat_callers": repeat.height,
        "consecutive_pairs": _consecutive_pairs(common).height,
        "different_qb_samples": different_qb.height,
        "different_team_samples": different_team.height,
        "all_gates_pass": (
            counts.get("verified", 0) >= PLAY_CALLER_GATE
            and int(folds["future_target_rows"].sum()) >= COMMON_FUTURE_GATE
            and folds.filter(pl.col("eligible_as_target")).height >= TARGET_FOLD_GATE
        ),
    }


def _verify_sources(project_root: Path, hashes: dict[str, str]) -> None:
    changed = [path for path, digest in hashes.items() if _sha256(project_root / path) != digest]
    if changed:
        raise ValueError(f"Prompt 10 input bytes changed during build: {sorted(changed)}")


def run_checkpoint_twelve_final_play_caller_evidence(
    project_root: Path, output_root: Path | None = None
) -> Prompt10Result:
    """Build deterministic closing-sprint evidence and readiness artifacts."""

    cells, intervals, lineage = load_and_validate_prompt10_evidence(project_root)
    coverage = build_coverage(project_root, cells)
    assignments = build_assignments(project_root, cells, intervals)
    historical_pcae, pcae_by_season, pcae_hashes, additions = rebuild_prompt10_pcae(
        project_root, cells, intervals, coverage
    )
    common, folds, repeat, different_qb, different_team = build_common_qp_availability(
        project_root, assignments, historical_pcae, coverage
    )
    q_availability = build_q_availability(project_root, assignments)
    consecutive = _consecutive_pairs(common)
    readiness = _readiness(coverage, common, folds)
    by_season = _coverage_by_season(coverage)
    by_era, missingness = build_missingness(project_root, coverage, common)
    season_matrix = _season_matrix(coverage, pcae_by_season, q_availability, folds)
    remaining = _remaining_queue(project_root, coverage, cells)
    prior_pcae = _strip_contract(pl.read_csv(_prompt9_root(project_root) / "historical_pcae.csv"))
    snapshots = pl.DataFrame(
        [
            _snapshot(
                project_root,
                cells,
                intervals,
                coverage,
                prior_pcae,
                additions,
                cutoff,
            )
            for cutoff in SNAPSHOT_CUTOFFS
        ]
    )
    archive_reviewed = cells.filter(pl.col("tier") == "archival_expensive").height
    archive_verified = cells.filter(
        (pl.col("tier") == "archival_expensive") & (pl.col("ending_status") == "verified")
    ).height
    archive_remaining = 188 - archive_reviewed
    reasonable_increment = round(archive_remaining * (archive_verified / archive_reviewed) * 0.70)
    current_verified = coverage.filter(pl.col("ending_status") == "verified").height
    estimated_ceiling = current_verified + reasonable_increment
    evidence_ceiling = pl.DataFrame(
        [
            {
                "current_defensible_verified_cells": current_verified,
                "archival_cells_researched": archive_reviewed,
                "archival_verified_yield": archive_verified,
                "remaining_archival_cells": archive_remaining,
                "discount_for_declining_source_access": 0.70,
                "estimated_additional_reasonable_cells": reasonable_increment,
                "estimated_defensible_ceiling": estimated_ceiling,
                "coverage_gate": PLAY_CALLER_GATE,
                "gate_attainable_with_reasonable_public_effort": estimated_ceiling
                >= PLAY_CALLER_GATE,
                "recommendation": "STOP HISTORICAL VERIFICATION — EVIDENCE CEILING REACHED",
            }
        ]
    )

    input_paths = [
        project_root / EVIDENCE_FILE,
        project_root / SOURCE_FILE,
        project_root / "research/coach_effect/checkpoint_twelve_final_play_caller_evidence.py",
        project_root / "research/coach_effect/checkpoint_twelve_play_caller_verification.py",
        project_root / "research/coach_effect/checkpoint_twelve_data_expansion.py",
        _prompt9_root(project_root) / "MANIFEST.json",
        _prompt9_root(project_root) / "play_caller_completeness.csv",
        _prompt9_root(project_root) / "historical_pcae.csv",
        _prompt9_root(project_root) / "common_qp_availability.csv",
        project_root
        / "research/coach_effect/outputs/checkpoint_12"
        / PROMPT6_VERSION
        / "joined_research_table.csv",
    ]
    input_hashes = {str(path.relative_to(project_root)): _sha256(path) for path in input_paths}
    input_hashes.update(pcae_hashes)
    identity = {
        "specification": PROMPT10_SPECIFICATION,
        "prompt9_version": PROMPT9_VERSION,
        "prompt8_version": PROMPT8_VERSION,
        "pcae_model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "pcae_play_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "call_value_formula": CALL_VALUE_FORMULA,
        "pcae_formula": PCAE_FORMULA,
        "play_call_features": PLAY_CALL_FEATURES,
        "selection_policy": "future-qp-then-recoverability-then-archival-ceiling-v1",
        "snapshot_cutoffs": SNAPSHOT_CUTOFFS,
        "evidence_ceiling_method": "observed_top-archive-yield-times-0.70-v1",
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
        "c12-pc-final-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    historical_pcae = historical_pcae.with_columns(pl.lit(data_version).alias("data_version"))
    source_families = (
        lineage.select("source_code", "source_family")
        .unique()
        .group_by("source_family")
        .len()
        .sort("source_family")
    )
    outputs = {
        "researched_cells.csv": cells,
        "newly_verified_evidence.csv": cells.filter(
            (pl.col("starting_status") != "verified") & (pl.col("ending_status") == "verified")
        ),
        "provisional_conversions.csv": cells.filter(
            (pl.col("starting_status") == "provisional") & (pl.col("ending_status") == "verified")
        ),
        "partial_cell_updates.csv": cells.filter(
            (pl.col("ending_status") == "partial")
            & (pl.col("starting_status") != pl.col("ending_status"))
        ),
        "rejected_evidence.csv": cells.filter(
            pl.col("disposition").is_in(["rejected_full_verification", "no_accessible_evidence"])
        ),
        "archival_source_records.csv": lineage.filter(pl.col("tier") == "archival_expensive"),
        "source_lineage.csv": lineage,
        "play_caller_completeness.csv": coverage,
        "remaining_evidence_queue.csv": remaining,
        "coverage_by_season.csv": by_season,
        "coverage_by_era.csv": by_era,
        "coverage_missingness_diagnostics.csv": missingness,
        "historical_pcae.csv": historical_pcae,
        "pcae_attribution_by_season.csv": pcae_by_season,
        "common_qp_availability.csv": common,
        "future_fold_matrix.csv": folds,
        "repeat_play_callers.csv": repeat,
        "consecutive_play_caller_pairs.csv": consecutive,
        "different_qb_samples.csv": different_qb,
        "different_team_samples.csv": different_team,
        "season_readiness_matrix.csv": season_matrix,
        "batch_snapshots.csv": snapshots,
        "evidence_ceiling.csv": evidence_ceiling,
        "readiness_gate_status.csv": readiness,
    }
    if set(outputs) != set(OUTPUT_NAMES):
        raise ValueError("Prompt 10 output contract drift")
    outputs = {name: _add_research_contract(frame, data_version) for name, frame in outputs.items()}
    _verify_sources(project_root, input_hashes)

    root = output_root or (
        project_root / "research/coach_effect/outputs/checkpoint_12_final_play_caller_evidence"
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
        "source_family_distribution": dict(source_families.iter_rows()),
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
        actual = {path.name for path in destination.iterdir() if path.is_file()}
        if actual != expected:
            raise ValueError("existing Prompt 10 publication has unexpected files")
        for name in expected:
            if _sha256(destination / name) != _sha256(temporary / name):
                raise ValueError(
                    "existing Prompt 10 publication differs from deterministic rebuild"
                )
        shutil.rmtree(temporary)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(destination)
    latest_temp = root / ".LATEST.tmp"
    latest_temp.write_text(data_version + "\n", encoding="utf-8")
    latest_temp.replace(root / "LATEST")
    return Prompt10Result(
        destination,
        data_version,
        outputs["play_caller_completeness.csv"],
        outputs["readiness_gate_status.csv"],
    )

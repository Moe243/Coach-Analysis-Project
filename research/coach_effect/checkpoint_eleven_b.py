"""Deterministic Checkpoint Eleven-B evidence and PCAE-readiness research.

Outputs are research-only, ignored by Git, and never loaded into serving tables.
The PAE, Call Value, and PCAE definitions are imported unchanged.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import polars as pl
import scipy
import sklearn

from nfl_coaching_impact.coaching import normalize_coach_name
from research.coach_effect.checkpoint_eleven import (
    PBP_COLUMNS,
    PLAY_KEY,
    _read_csv,
    _sha256,
    _verify_source_hashes,
    _write_csv,
    aggregate_historical_pcae,
    attribute_verified_calls,
    build_coaching_coverage,
    fit_historical_models,
    prepare_historical_plays,
)
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_ANALYSIS_SEASONS,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    HISTORICAL_PCAE_WARMUP_SEASONS,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
    RANDOM_SEED,
)

OUTPUT_NAMES = (
    "coaching_coverage.csv",
    "unresolved_play_callers.csv",
    "eligibility_reconciliation.csv",
    "season_attribution.csv",
    "historical_pcae.csv",
    "pae_joinability.csv",
    "repeatability_readiness.csv",
)
PAE_KEY = ("data_version", "player_id", "team_id", "season")
FORMAL_ROLES = {"offensive_coordinator", "quarterbacks_coach"}
NO_ROLE_STATUS = "verified_no_designated_role"


def _pae_path(project_root: Path) -> Path:
    root = project_root / "data" / "processed" / "expected_performance"
    version = (root / "LATEST").read_text(encoding="utf-8").strip()
    return root / version / "qb_pae.parquet"


def _analysis_pae(project_root: Path) -> pl.DataFrame:
    return (
        pl.read_parquet(_pae_path(project_root))
        .filter((pl.col("season_scope") == "analysis") & pl.col("is_out_of_sample"))
        .with_columns(
            pl.col("team_id").str.strip_prefix("team_").str.to_uppercase().alias("coaching_team_id")
        )
    )


def _evidence_assignments(project_root: Path) -> list[dict[str, str]]:
    manual = project_root / "data" / "manual"
    committed = _read_csv(manual / "coaching_assignments.csv")
    overlay = _read_csv(manual / "coaching_evidence_11b.csv")
    rows = [row for row in committed if row["role"] not in FORMAL_ROLES]
    for evidence in overlay:
        row = dict(evidence)
        row.update(
            {
                "start_date": "",
                "end_date": "",
                "is_retained": "false",
                "primary_source_url": evidence["source_url"],
                "notes": evidence["evidence_note"],
            }
        )
        rows.append(row)
    keys = [row["assignment_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Eleven-B evidence assignments contain duplicate keys")
    return rows


def _no_role_evidence(project_root: Path) -> list[dict[str, str]]:
    return _read_csv(project_root / "data/manual/coaching_no_role_evidence_11b.csv")


def validate_checkpoint_eleven_b_evidence(project_root: Path) -> int:
    """Validate the research overlay without changing serving-data contracts."""

    rows = _read_csv(project_root / "data/manual/coaching_evidence_11b.csv")
    keys = [row["assignment_key"] for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Eleven-B evidence overlay contains duplicate assignment keys")

    intervals: dict[tuple[int, str, str], list[tuple[int, int, bool, str]]] = defaultdict(list)
    for row in rows:
        key = row["assignment_key"]
        role = row["role"]
        if role not in FORMAL_ROLES or row["verification_status"] != "verified":
            raise ValueError(f"Eleven-B overlay has invalid role/status: {key}")
        season = int(row["season"])
        start = int(row["start_week"])
        end = int(row["end_week"])
        final_week = 18 if season >= 2021 else 17
        if not 1 <= start <= end <= final_week:
            raise ValueError(f"Eleven-B overlay has invalid week interval: {key}")
        expected_coach_id = f"coach-{normalize_coach_name(row['coach_canonical_name'])}"
        if row["coach_id"] != expected_coach_id:
            raise ValueError(f"Eleven-B overlay has invalid canonical coach identity: {key}")
        parsed = urlparse(row["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"Eleven-B overlay lacks an HTTPS source: {key}")

        evidence = " ".join((row["evidence_note"], row["required_terms"])).casefold()
        evidence = " ".join(evidence.replace("-", " ").split())
        role_term = "offensive coordinator" if role == "offensive_coordinator" else "quarterback"
        if role_term not in evidence:
            raise ValueError(f"verified {role} lacks explicit title evidence: {key}")

        is_designation = row["interval_basis"] == "season_designation"
        if (row["weekly_review_required"] == "true") != is_designation:
            raise ValueError(f"Eleven-B overlay has inconsistent interval certainty: {key}")
        intervals[(season, row["team_id"], role)].append(
            (start, end, row["is_shared"] == "true", key)
        )

    for group in intervals.values():
        ordered = sorted(group)
        for left, right in zip(ordered, ordered[1:], strict=False):
            if right[0] <= left[1] and not (left[2] and right[2]):
                raise ValueError(
                    "Eleven-B overlay has overlapping non-shared assignments: "
                    f"{left[3]} and {right[3]}"
                )
    no_role_rows = _no_role_evidence(project_root)
    no_role_keys = [row["evidence_key"] for row in no_role_rows]
    if len(no_role_keys) != len(set(no_role_keys)):
        raise ValueError("Eleven-B no-role evidence contains duplicate evidence keys")

    assignment_weeks = {
        (int(row["season"]), row["team_id"], row["role"], week)
        for row in rows
        for week in range(int(row["start_week"]), int(row["end_week"]) + 1)
    }
    for row in no_role_rows:
        key = row["evidence_key"]
        role = row["role"]
        season = int(row["season"])
        start = int(row["start_week"])
        end = int(row["end_week"])
        final_week = 18 if season >= 2021 else 17
        if role not in FORMAL_ROLES or row["resolution_status"] != NO_ROLE_STATUS:
            raise ValueError(f"Eleven-B no-role evidence has invalid role/status: {key}")
        if not 1 <= start <= end <= final_week:
            raise ValueError(f"Eleven-B no-role evidence has invalid week interval: {key}")
        parsed = urlparse(row["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"Eleven-B no-role evidence lacks an HTTPS source: {key}")
        note = " ".join(row["evidence_note"].casefold().replace("-", " ").split())
        if "no separately designated" not in note:
            raise ValueError(f"Eleven-B no-role evidence lacks explicit absence evidence: {key}")
        overlap = [
            week
            for week in range(start, end + 1)
            if (season, row["team_id"], role, week) in assignment_weeks
        ]
        if overlap:
            detail = f"{key}; weeks={overlap[:3]}"
            raise ValueError(f"Eleven-B no-role evidence overlaps a person assignment: {detail}")
    return len(rows) + len(no_role_rows)


def build_evidence_coverage(project_root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build coverage using the research overlay without mutating serving assignments."""

    return build_coaching_coverage(
        project_root,
        _evidence_assignments(project_root),
        _no_role_evidence(project_root),
    )


def build_pae_joinability(
    project_root: Path, assignments: pl.DataFrame, pcae: pl.DataFrame
) -> pl.DataFrame:
    """Summarize unique leakage-safe PAE observations joinable to verified evidence."""

    pae = _analysis_pae(project_root)
    if pae.select(PAE_KEY).n_unique() != pae.height:
        raise ValueError("published analysis PAE contains duplicate lineage keys")

    records: list[dict[str, Any]] = []
    for role in (
        "head_coach",
        "offensive_coordinator",
        "quarterbacks_coach",
        "play_caller",
    ):
        evidence = assignments.filter(
            (pl.col("role") == role) & (pl.col("verification_status") == "verified")
        ).select(pl.col("team_id").alias("coaching_team_id"), "season", "coach_id")
        linked = pae.join(evidence, on=["coaching_team_id", "season"], how="inner", validate="m:m")
        records.append(
            {
                "component": role,
                "pae_observations": linked.select(PAE_KEY).n_unique(),
                "unique_qbs": linked["player_id"].n_unique(),
                "unique_coaches": linked["coach_id"].n_unique(),
                "unique_teams": linked["team_id"].n_unique(),
                "seasons": linked["season"].n_unique(),
                "join_key": "data_version|player_id|team_id|season then team_id|season evidence",
            }
        )

    if pcae.is_empty():
        pcae_linked = pl.DataFrame()
    else:
        pcae_evidence = pcae.select(
            pl.col("team_id").alias("coaching_team_id"), "season", "coach_id"
        ).unique()
        pcae_linked = pae.join(
            pcae_evidence,
            on=["coaching_team_id", "season"],
            how="inner",
            validate="m:m",
        )
    records.append(
        {
            "component": "pcae",
            "pae_observations": (
                pcae_linked.select(PAE_KEY).n_unique() if not pcae_linked.is_empty() else 0
            ),
            "unique_qbs": pcae_linked["player_id"].n_unique() if not pcae_linked.is_empty() else 0,
            "unique_coaches": (
                pcae_linked["coach_id"].n_unique() if not pcae_linked.is_empty() else 0
            ),
            "unique_teams": pcae_linked["team_id"].n_unique() if not pcae_linked.is_empty() else 0,
            "seasons": pcae_linked["season"].n_unique() if not pcae_linked.is_empty() else 0,
            "join_key": "data_version|player_id|team_id|season then verified PCAE team_id|season",
        }
    )
    return pl.DataFrame(records).sort("component")


def build_repeatability_readiness(project_root: Path, pcae: pl.DataFrame) -> pl.DataFrame:
    """Report sample breadth only; do not estimate Coach Effect or weights."""

    coach_seasons = {
        (row["coach_id"], row["team_id"], int(row["season"])) for row in pcae.to_dicts()
    }
    seasons_by_coach: dict[str, set[int]] = {}
    teams_by_coach: dict[str, set[str]] = {}
    for coach_id, team_id, season in coach_seasons:
        seasons_by_coach.setdefault(coach_id, set()).add(season)
        teams_by_coach.setdefault(coach_id, set()).add(team_id)
    repeat_callers = {coach for coach, seasons in seasons_by_coach.items() if len(seasons) >= 2}
    consecutive_pairs = sum(
        sum(1 for season in seasons if season + 1 in seasons)
        for seasons in seasons_by_coach.values()
    )
    multi_team = {coach for coach, teams in teams_by_coach.items() if len(teams) >= 2}
    team_switches = 0
    for coach in seasons_by_coach:
        observations = sorted(
            (season, team) for candidate, team, season in coach_seasons if candidate == coach
        )
        team_switches += sum(
            1
            for left, right in zip(observations, observations[1:], strict=False)
            if left[1] != right[1]
        )

    pae = _analysis_pae(project_root)
    coach_season_frame = pl.DataFrame(
        [
            {"coach_id": coach, "coaching_team_id": team, "season": season}
            for coach, team, season in sorted(coach_seasons)
        ],
        schema={"coach_id": pl.String, "coaching_team_id": pl.String, "season": pl.Int64},
    )
    if coach_season_frame.is_empty():
        multi_qb = 0
    else:
        qbs_by_coach = (
            pae.join(
                coach_season_frame,
                on=["coaching_team_id", "season"],
                how="inner",
                validate="m:m",
            )
            .group_by("coach_id")
            .agg(pl.col("player_id").n_unique().alias("qbs"))
        )
        multi_qb = qbs_by_coach.filter(pl.col("qbs") >= 2).height

    season_counts = list(map(len, seasons_by_coach.values()))
    return pl.DataFrame(
        [
            {
                "coach_season_pcae_observations": len(coach_seasons),
                "unique_verified_play_callers": len(seasons_by_coach),
                "repeat_play_callers": len(repeat_callers),
                "consecutive_season_pairs": consecutive_pairs,
                "multi_qb_play_callers": multi_qb,
                "multi_team_play_callers": len(multi_team),
                "team_switch_observations": team_switches,
                "callers_with_1_season": sum(value == 1 for value in season_counts),
                "callers_with_2_seasons": sum(value == 2 for value in season_counts),
                "callers_with_3_seasons": sum(value == 3 for value in season_counts),
                "callers_with_4_plus_seasons": sum(value >= 4 for value in season_counts),
                "coach_effect_estimated": False,
                "weights_estimated": False,
            }
        ]
    )


def run_checkpoint_eleven_b(project_root: Path, output_root: Path | None = None) -> dict[str, Any]:
    """Build the ignored content-addressed Eleven-B research publication."""

    validate_checkpoint_eleven_b_evidence(project_root)
    historical_root = project_root / "data" / "processed" / "historical"
    historical_version = (historical_root / "LATEST").read_text(encoding="utf-8").strip()
    bronze = historical_root / historical_version / "bronze" / "play_by_play"
    manual = project_root / "data" / "manual"
    manual_hashes = {
        str(path.relative_to(project_root)): _sha256(path) for path in sorted(manual.glob("*.csv"))
    }
    serving_assignments = pl.read_csv(manual / "coaching_assignments.csv", infer_schema_length=None)
    evidence_rows = _evidence_assignments(project_root)
    assignments = pl.DataFrame(evidence_rows, infer_schema_length=None).with_columns(
        pl.col("season").cast(pl.Int64)
    )
    target_seasons = sorted(
        serving_assignments.filter(
            (pl.col("role") == "play_caller")
            & (pl.col("verification_status") == "verified")
            & (pl.col("interval_basis") != "season_designation")
        )["season"]
        .unique()
        .to_list()
    )

    frames: dict[int, pl.DataFrame] = {}
    eligibility_records: list[dict[str, Any]] = []
    pbp_hashes: dict[str, str] = {}
    for season in (*HISTORICAL_PCAE_WARMUP_SEASONS, *HISTORICAL_PCAE_ANALYSIS_SEASONS):
        path = bronze / f"season={season}" / "play_by_play.parquet"
        pbp_hashes[str(path.relative_to(project_root))] = _sha256(path)
        prepared, audit = prepare_historical_plays(pl.read_parquet(path, columns=PBP_COLUMNS))
        frames[season] = prepared
        eligibility_records.append({"season": season, **audit})

    coverage, unresolved_callers = build_evidence_coverage(project_root)
    scored_targets: list[pl.DataFrame] = []
    for season in target_seasons:
        training = pl.concat(
            [frames[value] for value in frames if value < season], how="diagonal_relaxed"
        )
        _, scored = fit_historical_models(training, frames[season], season)
        scored_targets.append(scored)
    scored = pl.concat(scored_targets, how="diagonal_relaxed") if scored_targets else pl.DataFrame()
    attributed, unresolved_plays = attribute_verified_calls(scored, serving_assignments)
    pcae = aggregate_historical_pcae(attributed)

    attribution_records: list[dict[str, Any]] = []
    caller_coverage = coverage.filter(pl.col("role") == "play_caller")
    for season in HISTORICAL_PCAE_ANALYSIS_SEASONS:
        eligible = frames[season].height
        season_attributed = (
            attributed.filter(pl.col("season") == season)
            if not attributed.is_empty()
            else attributed
        )
        attributed_count = (
            season_attributed.select(PLAY_KEY).n_unique() if not season_attributed.is_empty() else 0
        )
        if season in target_seasons:
            season_unresolved = unresolved_plays.filter(pl.col("season") == season)
            ambiguous = season_unresolved.filter(
                pl.col("reason") == "shared_or_ambiguous_interval"
            ).height
            unresolved = season_unresolved.filter(pl.col("reason") == "no_verified_interval").height
        else:
            ambiguous = 0
            unresolved = eligible
        unattributed = ambiguous + unresolved
        if attributed_count + unattributed != eligible:
            raise ValueError(f"season {season} PCAE attribution does not reconcile")
        statuses = caller_coverage.filter(pl.col("season") == season)["coverage_status"]
        attribution_records.append(
            {
                "season": season,
                "eligible_plays": eligible,
                "attributed_plays": attributed_count,
                "ambiguous_shared_plays": ambiguous,
                "unresolved_unattributed_plays": unresolved,
                "unattributed_plays": unattributed,
                "attribution_rate": attributed_count / eligible if eligible else 0.0,
                "unique_verified_play_callers": (
                    season_attributed["coach_id"].n_unique()
                    if not season_attributed.is_empty()
                    else 0
                ),
                "full_coverage_teams": statuses.filter(statuses == "verified_person").len(),
                "partial_coverage_teams": statuses.filter(statuses == "partial").len(),
                "unresolved_teams": statuses.filter(
                    ~statuses.is_in(["verified_person", "partial"])
                ).len(),
                "model_available": season in target_seasons,
            }
        )
    season_attribution = pl.DataFrame(attribution_records).sort("season")
    eligibility = pl.DataFrame(eligibility_records).sort("season")

    pae_path = _pae_path(project_root)
    source_hashes = {
        **manual_hashes,
        **pbp_hashes,
        str(pae_path.relative_to(project_root)): _sha256(pae_path),
    }
    _verify_source_hashes(project_root, source_hashes)
    code_paths = (
        Path(__file__),
        project_root / "research/coach_effect/checkpoint_eleven.py",
        project_root / "research/coach_effect/config.py",
        project_root / "research/coach_effect/phase_2_play_calling/analysis.py",
    )
    identity = {
        "checkpoint": "eleven-b",
        "historical_data_version": historical_version,
        "pae_data_version": pae_path.parent.name,
        "model_version": HISTORICAL_PCAE_MODEL_VERSION,
        "play_eligibility_version": HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
        "call_value_formula": CALL_VALUE_FORMULA,
        "pcae_formula": PCAE_FORMULA,
        "features": PLAY_CALL_FEATURES,
        "random_seed": RANDOM_SEED,
        "dependencies": {
            "numpy": np.__version__,
            "polars": pl.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "code_hashes": {str(path.relative_to(project_root)): _sha256(path) for path in code_paths},
        "input_hashes": source_hashes,
        "target_seasons": target_seasons,
    }
    data_version = (
        "c11b-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
    )
    if not pcae.is_empty():
        pcae = pcae.with_columns(
            pl.lit(data_version).alias("data_version"),
            pl.lit(True).alias("shared_or_ambiguous_plays_excluded"),
        )
    joinability = build_pae_joinability(project_root, assignments, pcae)
    readiness = build_repeatability_readiness(project_root, pcae)

    outputs = {
        "coaching_coverage.csv": coverage,
        "unresolved_play_callers.csv": unresolved_callers,
        "eligibility_reconciliation.csv": eligibility,
        "season_attribution.csv": season_attribution,
        "historical_pcae.csv": pcae,
        "pae_joinability.csv": joinability,
        "repeatability_readiness.csv": readiness,
    }
    root = output_root or project_root / "research/coach_effect/outputs/checkpoint_11b"
    destination = root / data_version
    temporary = root / f".{data_version}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    for name, frame in outputs.items():
        _write_csv(frame, temporary / name)
    checksums = {name: _sha256(temporary / name) for name in OUTPUT_NAMES}
    manifest = {
        "data_version": data_version,
        "research_only": True,
        "production_coach_effect": False,
        "identity": identity,
        "output_checksums": checksums,
        "row_counts": {name.removesuffix(".csv"): frame.height for name, frame in outputs.items()},
    }
    (temporary / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _verify_source_hashes(project_root, source_hashes)
    if destination.exists():
        for name, expected in {
            **checksums,
            "MANIFEST.json": _sha256(temporary / "MANIFEST.json"),
        }.items():
            if _sha256(destination / name) != expected:
                raise ValueError(f"existing Eleven-B research output differs: {name}")
        shutil.rmtree(temporary)
    else:
        temporary.replace(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "LATEST").write_text(data_version + "\n", encoding="utf-8")
    return {
        "output_path": destination,
        "data_version": data_version,
        "season_attribution": season_attribution,
        "pcae": pcae,
        "pae_joinability": joinability,
        "repeatability_readiness": readiness,
    }

"""Offline contracts for the source-backed checkpoint-four coaching dataset."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .constants import ANALYSIS_SEASONS, CANONICAL_TEAM_IDS

ROLES = frozenset(
    {"head_coach", "offensive_coordinator", "play_caller", "quarterbacks_coach"}
)
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
INTERVAL_BASES = frozenset({"observed_game_weeks", "season_designation"})
VERIFICATION_STATUSES = frozenset({"unverified", "provisional", "verified", "conflicting"})


class CoachingDataError(ValueError):
    """Raised when a committed coaching-data contract is violated."""


@dataclass(frozen=True)
class CoachingValidationResult:
    assignments: int
    citations: int
    coaches: int
    open_reviews: int
    covered_team_seasons: int
    role_counts: dict[str, int]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_coaching_data(project_root: Path) -> CoachingValidationResult:
    """Validate identities, intervals, citations, role coverage, and review routing."""

    manual = project_root / "data" / "manual"
    assignments = _read(manual / "coaching_assignments.csv")
    citations = _read(manual / "coach_assignment_sources.csv")
    coaches = _read(manual / "coaches.csv")
    reviews = _read(manual / "coaching_review_queue.csv")
    definitions = _read(manual / "coaching_role_definitions.csv")
    registry = _read(manual / "coaching_source_registry.csv")

    assignment_keys = [row["assignment_key"] for row in assignments]
    if len(assignment_keys) != len(set(assignment_keys)):
        raise CoachingDataError("assignment_key values must be unique")
    coach_ids = {row["coach_id"] for row in coaches}
    if len(coach_ids) != len(coaches):
        raise CoachingDataError("coach_id values must be unique")
    citation_keys = {row["assignment_key"] for row in citations}
    if any(not _valid_url(row["source_url"]) for row in citations):
        raise CoachingDataError("every citation must contain an HTTPS source URL")
    if {row["role"] for row in definitions} != ROLES:
        raise CoachingDataError("role definitions must cover exactly the four checkpoint roles")
    if {int(row["season"]) for row in registry} != set(ANALYSIS_SEASONS):
        raise CoachingDataError("source registry must cover every 2010-2025 season")
    if any(row["local_raw_committed"] != "false" for row in registry):
        raise CoachingDataError("raw source books must not be committed")

    intervals: dict[tuple[int, str, str], list[tuple[int, int, bool, str]]] = defaultdict(list)
    covered: set[tuple[int, str]] = set()
    role_counts = {role: 0 for role in sorted(ROLES)}
    for row in assignments:
        season = int(row["season"])
        team = row["team_id"]
        role = row["role"]
        start, end = int(row["start_week"]), int(row["end_week"])
        if season not in ANALYSIS_SEASONS or team not in CANONICAL_TEAM_IDS:
            raise CoachingDataError(f"invalid season/team for {row['assignment_key']}")
        if role not in ROLES or row["confidence_level"] not in CONFIDENCE_LEVELS:
            raise CoachingDataError(f"invalid role/confidence for {row['assignment_key']}")
        if row["interval_basis"] not in INTERVAL_BASES:
            raise CoachingDataError(f"invalid interval basis for {row['assignment_key']}")
        if row["verification_status"] not in VERIFICATION_STATUSES:
            raise CoachingDataError(f"invalid verification status for {row['assignment_key']}")
        if not 1 <= start <= end <= 25:
            raise CoachingDataError(f"invalid week interval for {row['assignment_key']}")
        if row["coach_id"] not in coach_ids or not row["coach_canonical_name"].strip():
            raise CoachingDataError(f"unresolved coach identity for {row['assignment_key']}")
        if row["verification_status"] == "verified" and row["assignment_key"] not in citation_keys:
            raise CoachingDataError(f"verified assignment lacks citation: {row['assignment_key']}")
        if not _valid_url(row["primary_source_url"]):
            raise CoachingDataError(f"assignment lacks primary HTTPS URL: {row['assignment_key']}")
        shared = row["is_shared"] == "true"
        intervals[(season, team, role)].append((start, end, shared, row["assignment_key"]))
        covered.add((season, team))
        role_counts[role] += 1

    for grain, values in intervals.items():
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                overlaps = left[0] <= right[1] and right[0] <= left[1]
                if overlaps and not (left[2] and right[2]):
                    raise CoachingDataError(
                        f"overlapping non-shared assignment at {grain}: {left[3]}, {right[3]}"
                    )

    review_ids = [row["review_id"] for row in reviews]
    if len(review_ids) != len(set(review_ids)):
        raise CoachingDataError("review_id values must be unique")
    review_grains = set()
    for row in reviews:
        season, team, role = int(row["season"]), row["team_id"], row["role"]
        if season not in ANALYSIS_SEASONS or team not in CANONICAL_TEAM_IDS or role not in ROLES:
            raise CoachingDataError(f"invalid review queue grain: {row['review_id']}")
        if row["status"] not in {"open", "resolved", "rejected"}:
            raise CoachingDataError(f"invalid review status: {row['review_id']}")
        review_grains.add((season, team, role))
        covered.add((season, team))

    expected_team_seasons = {
        (season, team) for season in ANALYSIS_SEASONS for team in CANONICAL_TEAM_IDS
    }
    if covered != expected_team_seasons:
        missing = sorted(expected_team_seasons - covered)[:10]
        raise CoachingDataError(f"team-season review coverage is incomplete; sample={missing}")
    for season, team in expected_team_seasons:
        for role in ROLES:
            if (season, team, role) not in intervals and (season, team, role) not in review_grains:
                raise CoachingDataError(
                    f"role is neither assigned nor queued: {season}-{team}-{role}"
                )
    if role_counts["play_caller"]:
        raise CoachingDataError(
            "checkpoint four must not infer play callers without explicit evidence"
        )

    return CoachingValidationResult(
        assignments=len(assignments),
        citations=len(citations),
        coaches=len(coaches),
        open_reviews=sum(row["status"] == "open" for row in reviews),
        covered_team_seasons=len(covered),
        role_counts=role_counts,
    )

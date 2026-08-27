"""Offline contracts for the source-backed checkpoint-four coaching dataset."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .constants import ANALYSIS_SEASONS, CANONICAL_TEAM_IDS

ROLES = frozenset({"head_coach", "offensive_coordinator", "play_caller", "quarterbacks_coach"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
INTERVAL_BASES = frozenset({"observed_game_weeks", "season_designation", "dated_source_weeks"})
VERIFICATION_STATUSES = frozenset({"unverified", "provisional", "verified", "conflicting"})
REVIEW_ISSUE_TYPES = frozenset(
    {
        "explicit_play_caller_evidence_required",
        "missing_formal_role",
        "partial_interval_unresolved",
        "season_interval_verification_required",
        "shared_duty_verification_required",
    }
)


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


def normalize_coach_name(value: str) -> str:
    """Return the stable identity key used by the committed manual dataset."""

    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def validate_source_content(content: str, required_terms: str, evidence_id: str) -> None:
    """Require every pipe-delimited evidence term in fetched source content."""

    normalized = " ".join(content.casefold().split())
    missing = [term for term in required_terms.split("|") if term.casefold() not in normalized]
    if missing:
        raise CoachingDataError(
            f"source content check {evidence_id} is missing required terms: {missing}"
        )


def validate_coaching_data(project_root: Path) -> CoachingValidationResult:
    """Validate identities, intervals, citations, role coverage, and review routing."""

    manual = project_root / "data" / "manual"
    assignments = _read(manual / "coaching_assignments.csv")
    citations = _read(manual / "coach_assignment_sources.csv")
    coaches = _read(manual / "coaches.csv")
    aliases = _read(manual / "coach_aliases.csv")
    reviews = _read(manual / "coaching_review_queue.csv")
    definitions = _read(manual / "coaching_role_definitions.csv")
    registry = _read(manual / "coaching_source_registry.csv")
    content_checks = _read(manual / "coaching_source_content_checks.csv")

    assignment_keys = [row["assignment_key"] for row in assignments]
    if len(assignment_keys) != len(set(assignment_keys)):
        raise CoachingDataError("assignment_key values must be unique")
    coach_ids = {row["coach_id"] for row in coaches}
    if len(coach_ids) != len(coaches):
        raise CoachingDataError("coach_id values must be unique")
    normalized_names = [row["normalized_name"] for row in coaches]
    if len(normalized_names) != len(set(normalized_names)):
        raise CoachingDataError("canonical coach identities must have unique normalized names")
    for row in coaches:
        expected = normalize_coach_name(row["canonical_name"])
        if row["normalized_name"] != expected or row["coach_id"] != f"coach-{expected}":
            raise CoachingDataError(f"noncanonical coach identity: {row['coach_id']}")
    alias_names = [row["normalized_alias"] for row in aliases]
    if len(alias_names) != len(set(alias_names)):
        raise CoachingDataError("coach aliases must have unique normalized values")
    coach_names_by_id = {row["coach_id"]: row["canonical_name"] for row in coaches}
    if any(
        row["coach_id"] not in coach_ids
        or row["canonical_name"] != coach_names_by_id[row["coach_id"]]
        for row in aliases
    ):
        raise CoachingDataError("coach alias references an unresolved canonical identity")
    citation_keys = {row["assignment_key"] for row in citations}
    unknown_citation_keys = citation_keys - set(assignment_keys)
    if unknown_citation_keys:
        raise CoachingDataError(
            f"citation references unknown assignment: {sorted(unknown_citation_keys)[:3]}"
        )
    if any(not _valid_url(row["source_url"]) for row in citations):
        raise CoachingDataError("every citation must contain an HTTPS source URL")
    if {row["role"] for row in definitions} != ROLES:
        raise CoachingDataError("role definitions must cover exactly the four checkpoint roles")
    if {int(row["season"]) for row in registry} != set(ANALYSIS_SEASONS):
        raise CoachingDataError("source registry must cover every 2010-2025 season")
    if any(row["local_raw_committed"] != "false" for row in registry):
        raise CoachingDataError("raw source books must not be committed")
    for row in content_checks:
        if not _valid_url(row["source_url"]):
            raise CoachingDataError(f"invalid content-check URL: {row['evidence_id']}")
        referenced = set(row["assignment_keys"].split("|"))
        if not referenced <= set(assignment_keys):
            raise CoachingDataError(
                f"content check references unknown assignment: {row['evidence_id']}"
            )
        if not all(term.strip() for term in row["required_terms"].split("|")):
            raise CoachingDataError(f"content check has empty evidence terms: {row['evidence_id']}")
    content_checked_keys = {
        key for row in content_checks for key in row["assignment_keys"].split("|")
    }

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
        boolean_fields = ("is_interim", "is_shared", "is_retained")
        if any(row[field] not in {"true", "false"} for field in boolean_fields):
            raise CoachingDataError(f"invalid boolean flag for {row['assignment_key']}")
        if not 1 <= start <= end <= 25:
            raise CoachingDataError(f"invalid week interval for {row['assignment_key']}")
        if row["coach_id"] not in coach_ids or not row["coach_canonical_name"].strip():
            raise CoachingDataError(f"unresolved coach identity for {row['assignment_key']}")
        if row["coach_id"] != f"coach-{normalize_coach_name(row['coach_canonical_name'])}":
            raise CoachingDataError(
                f"assignment uses a noncanonical coach identity: {row['assignment_key']}"
            )
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
    review_issues = set()
    for row in reviews:
        season, team, role = int(row["season"]), row["team_id"], row["role"]
        if season not in ANALYSIS_SEASONS or team not in CANONICAL_TEAM_IDS or role not in ROLES:
            raise CoachingDataError(f"invalid review queue grain: {row['review_id']}")
        if row["status"] not in {"open", "resolved", "rejected"}:
            raise CoachingDataError(f"invalid review status: {row['review_id']}")
        if (
            row["issue_type"] not in REVIEW_ISSUE_TYPES
            or row["priority"] not in CONFIDENCE_LEVELS
            or not _valid_url(row["source_url"])
            or not row["notes"].strip()
        ):
            raise CoachingDataError(f"invalid review metadata: {row['review_id']}")
        review_grains.add((season, team, role))
        review_issues.add((season, team, role, row["issue_type"]))
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
    for row in assignments:
        grain = (int(row["season"]), row["team_id"], row["role"])
        if row["verification_status"] == "provisional" and row["interval_basis"] == (
            "season_designation"
        ):
            expected_issue = (
                "shared_duty_verification_required"
                if row["role"] == "play_caller"
                else "season_interval_verification_required"
            )
            if (*grain, expected_issue) not in review_issues:
                raise CoachingDataError(
                    f"provisional season interval is not queued: {row['assignment_key']}"
                )
        if row["role"] == "play_caller":
            evidence = " ".join(
                citation["evidence_note"]
                for citation in citations
                if citation["assignment_key"] == row["assignment_key"]
            ).casefold()
            evidence = " ".join(evidence.replace("-", " ").split())
            verified = row["verification_status"] == "verified"
            allowed_provisional = (
                row["verification_status"] == "provisional"
                and row["confidence_level"] in {"medium", "low"}
                and (*grain, "shared_duty_verification_required") in review_issues
            )
            if not (verified or allowed_provisional) or "play call" not in evidence:
                raise CoachingDataError(
                    f"play-caller assignment lacks explicit evidence or review routing: "
                    f"{row['assignment_key']}"
                )
            if verified and (
                row["confidence_level"] != "high"
                or row["assignment_key"] not in content_checked_keys
            ):
                raise CoachingDataError(
                    f"verified play-caller lacks high-confidence content check: "
                    f"{row['assignment_key']}"
                )
        if row["is_interim"] == "true":
            if row["role"] == "head_coach":
                has_predecessor = any(
                    other["season"] == row["season"]
                    and other["team_id"] == row["team_id"]
                    and other["role"] == "head_coach"
                    and int(other["end_week"]) < int(row["start_week"])
                    for other in assignments
                )
                if int(row["start_week"]) == 1 or not has_predecessor:
                    raise CoachingDataError(
                        "interim head coach is not a temporary replacement: "
                        f"{row['assignment_key']}"
                    )
            else:
                interim_evidence = " ".join(
                    f"{citation['source_title']} {citation['evidence_note']}"
                    for citation in citations
                    if citation["assignment_key"] == row["assignment_key"]
                ).casefold()
                if not any(
                    phrase in interim_evidence
                    for phrase in ("interim", "remainder of season", "remainder of the season")
                ):
                    raise CoachingDataError(f"unsupported interim label: {row['assignment_key']}")
        if row["interval_basis"] == "dated_source_weeks" and (
            row["verification_status"] != "verified" or row["confidence_level"] != "high"
        ):
            raise CoachingDataError(
                f"dated interval is not high-confidence verified: {row['assignment_key']}"
            )

    # Compound formal titles must expand into each checkpoint role they name.
    assignment_grains = {
        (int(row["season"]), row["team_id"], row["coach_id"], row["role"]) for row in assignments
    }
    for citation in citations:
        note = citation["evidence_note"].casefold()
        if "offensive coordinator/quarterbacks" not in note:
            continue
        assignment = next(
            row for row in assignments if row["assignment_key"] == citation["assignment_key"]
        )
        required = {
            (int(assignment["season"]), assignment["team_id"], assignment["coach_id"], role)
            for role in ("offensive_coordinator", "quarterbacks_coach")
        }
        if not required <= assignment_grains:
            raise CoachingDataError(
                f"compound title was not expanded for {assignment['coach_canonical_name']}"
            )

    return CoachingValidationResult(
        assignments=len(assignments),
        citations=len(citations),
        coaches=len(coaches),
        open_reviews=sum(row["status"] == "open" for row in reviews),
        covered_team_seasons=len(covered),
        role_counts=role_counts,
    )

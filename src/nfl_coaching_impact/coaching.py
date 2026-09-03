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

HOUSTON_2020_PLAY_CALLER_INTERVALS = {
    "2020-HOU-play_caller-01-03-tim-kelly": (1, 3, False, "verified"),
    "2020-HOU-play_caller-04-04-bill-o-brien": (4, 4, True, "verified"),
    "2020-HOU-play_caller-04-04-tim-kelly": (4, 4, True, "verified"),
    "2020-HOU-play_caller-05-17-tim-kelly": (5, 17, False, "provisional"),
}

HOUSTON_2020_CONTENT_CHECK_CONTRACTS = {
    "tim-kelly-2020-opening": {
        "assignment_keys": {"2020-HOU-play_caller-01-03-tim-kelly"},
        "required_terms": {
            "with an 0-3 start",
            "attempting to take a step back from both to begin the season",
        },
    },
    "tim-kelly-2020-week4-shared": {
        "assignment_keys": {
            "2020-HOU-play_caller-04-04-bill-o-brien",
            "2020-HOU-play_caller-04-04-tim-kelly",
        },
        "required_terms": {
            "far more involved in game-planning and play-calling",
            "tim kelly will still physically relay the plays",
            "o'brien will take a heavy hand in which plays are called",
        },
    },
    "tim-kelly-2020-provisional-designation": {
        "assignment_keys": {"2020-HOU-play_caller-05-17-tim-kelly"},
        "required_terms": {
            "kelly would take over play-calling duties for the upcoming season",
        },
    },
    "tim-kelly-2020-post-week4-boundary": {
        "assignment_keys": {"2020-HOU-play_caller-05-17-tim-kelly"},
        "required_terms": {
            "fired coach and general manager bill o'brien",
            "after more than six seasons",
            "0-4 start",
        },
    },
}

AFFIRMATIVE_TEMPORARY_TERMS = (
    "interim coach",
    "interim head coach",
    "interim offensive coordinator",
    "interim play-caller",
    "temporary coach",
    "temporary head coach",
    "temporary replacement",
    "remainder of season",
    "remainder of the season",
)
NEGATED_TEMPORARY_TERMS = (
    "not interim",
    "not an interim",
    "without an interim",
    "does not designate interim",
    "does not designate the coach interim",
    "rather than an interim",
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

    normalized = " ".join(content.casefold().replace("’", "'").split())
    missing = [term for term in required_terms.split("|") if term.casefold() not in normalized]
    if missing:
        raise CoachingDataError(
            f"source content check {evidence_id} is missing required terms: {missing}"
        )


def _normalized_terms(required_terms: str) -> set[str]:
    return {" ".join(term.casefold().split()) for term in required_terms.split("|")}


def _has_direct_temporary_evidence(
    assignment_key: str,
    content_checks_by_assignment: dict[str, list[dict[str, str]]],
) -> bool:
    checked_terms = " ".join(
        term
        for row in content_checks_by_assignment.get(assignment_key, [])
        for term in _normalized_terms(row["required_terms"])
    )
    if any(phrase in checked_terms for phrase in NEGATED_TEMPORARY_TERMS):
        return False
    return any(phrase in checked_terms for phrase in AFFIRMATIVE_TEMPORARY_TERMS)


def _is_structurally_temporary_head_coach(
    row: dict[str, str], assignments: list[dict[str, str]]
) -> bool:
    """Return whether observed seasons prove a temporary replacement boundary."""

    season = int(row["season"])
    team = row["team_id"]
    start_week = int(row["start_week"])
    end_week = int(row["end_week"])
    same_season = [
        other
        for other in assignments
        if int(other["season"]) == season
        and other["team_id"] == team
        and other["role"] == "head_coach"
    ]
    has_predecessor = any(int(other["end_week"]) < start_week for other in same_season)
    finishes_team_season = end_week == max(int(other["end_week"]) for other in same_season)

    next_season = [
        other
        for other in assignments
        if int(other["season"]) == season + 1
        and other["team_id"] == team
        and other["role"] == "head_coach"
    ]
    if not next_season:
        return False
    first_next_week = min(int(other["start_week"]) for other in next_season)
    next_appointments = [
        other for other in next_season if int(other["start_week"]) == first_next_week
    ]
    later_permanent_appointment = any(
        other["coach_id"] != row["coach_id"]
        and other["is_interim"] == "false"
        and other["verification_status"] == "verified"
        and other["interval_basis"] == "observed_game_weeks"
        for other in next_appointments
    )
    return (
        row["interval_basis"] == "observed_game_weeks"
        and row["verification_status"] == "verified"
        and start_week > 1
        and has_predecessor
        and finishes_team_season
        and later_permanent_appointment
    )


def _validate_houston_2020_contracts(
    assignments: list[dict[str, str]], content_checks: list[dict[str, str]]
) -> None:
    houston_rows = {
        row["assignment_key"]: (
            int(row["start_week"]),
            int(row["end_week"]),
            row["is_shared"] == "true",
            row["verification_status"],
        )
        for row in assignments
        if row["season"] == "2020" and row["team_id"] == "HOU" and row["role"] == "play_caller"
    }
    if houston_rows != HOUSTON_2020_PLAY_CALLER_INTERVALS:
        raise CoachingDataError("Houston 2020 play-caller intervals do not match the audited split")

    checks_by_id = {row["evidence_id"]: row for row in content_checks}
    for evidence_id, contract in HOUSTON_2020_CONTENT_CHECK_CONTRACTS.items():
        row = checks_by_id.get(evidence_id)
        if row is None:
            raise CoachingDataError(f"missing Houston 2020 content check: {evidence_id}")
        if set(row["assignment_keys"].split("|")) != contract["assignment_keys"]:
            raise CoachingDataError(f"incorrect Houston assignment scope: {evidence_id}")
        if not contract["required_terms"] <= _normalized_terms(row["required_terms"]):
            raise CoachingDataError(f"insufficient Houston boundary terms: {evidence_id}")


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
    citation_urls_by_key: dict[str, set[str]] = defaultdict(set)
    for row in citations:
        citation_urls_by_key[row["assignment_key"]].add(row["source_url"])
    content_checks_by_assignment: dict[str, list[dict[str, str]]] = defaultdict(list)
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
        for assignment_key in referenced:
            if row["source_url"] not in citation_urls_by_key[assignment_key]:
                raise CoachingDataError(
                    f"content check URL is not cited by assignment: {row['evidence_id']}"
                )
            content_checks_by_assignment[assignment_key].append(row)
    _validate_houston_2020_contracts(assignments, content_checks)
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
            expected_issues = (
                {
                    "season_interval_verification_required",
                    "partial_interval_unresolved",
                    "shared_duty_verification_required",
                }
                if row["role"] == "play_caller"
                else {"season_interval_verification_required"}
            )
            if not any((*grain, issue) in review_issues for issue in expected_issues):
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
                and any(
                    (*grain, issue) in review_issues
                    for issue in (
                        "season_interval_verification_required",
                        "partial_interval_unresolved",
                        "shared_duty_verification_required",
                    )
                )
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
            directly_sourced = _has_direct_temporary_evidence(
                row["assignment_key"], content_checks_by_assignment
            )
            structurally_temporary = row["role"] == "head_coach" and (
                _is_structurally_temporary_head_coach(row, assignments)
            )
            if not directly_sourced and not structurally_temporary:
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

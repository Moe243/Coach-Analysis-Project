"""Deterministic serving projection for final Eleven-B coaching evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlparse

import polars as pl

from .coaching import ROLES
from .constants import ANALYSIS_SEASONS, CANONICAL_TEAM_IDS
from .errors import PipelineError

EVIDENCE_VERSION = "c11b-bbf7d43d0e4c4c05"
FORMAL_ROLES = frozenset({"offensive_coordinator", "quarterbacks_coach"})
NO_ROLE_STATUS = "verified_no_designated_role"
EXPECTED_STATUS_COUNTS = {
    "head_coach": {"verified": 512},
    "offensive_coordinator": {"verified": 488, NO_ROLE_STATUS: 24},
    "quarterbacks_coach": {"verified": 496, NO_ROLE_STATUS: 16},
    "play_caller": {
        "verified": 119,
        "partial": 1,
        "provisional": 125,
        "unresolved": 267,
    },
}


def _week_range(row: dict[str, str]) -> range:
    return range(int(row["start_week"]), int(row["end_week"]) + 1)


def _require_https(value: str, evidence_key: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise PipelineError(f"Eleven-B evidence lacks an HTTPS source: {evidence_key}")


def build_serving_coaching_completeness(
    manual_rows: dict[str, list[dict[str, str]]],
) -> pl.DataFrame:
    """Build the final 2,048-cell publication from the captured manual bytes.

    Formal OC/QB-coach truth comes from the Eleven-B evidence overlay. Head-coach
    and play-caller truth stays on the existing assignment dataset. No-role
    evidence resolves completeness only and never creates a person assignment.
    """

    base = manual_rows["coaching_assignments.csv"]
    overlay = manual_rows["coaching_evidence_11b.csv"]
    no_role_rows = manual_rows["coaching_no_role_evidence_11b.csv"]
    reviews = manual_rows["coaching_review_queue.csv"]
    citations = manual_rows["coach_assignment_sources.csv"]

    assignments = [row for row in base if row["role"] not in FORMAL_ROLES]
    for row in overlay:
        if row["role"] not in FORMAL_ROLES or row["verification_status"] != "verified":
            raise PipelineError(f"invalid Eleven-B named evidence state: {row['assignment_key']}")
        _require_https(row["source_url"], row["assignment_key"])
        assignments.append(row)
    keys = [row["assignment_key"] for row in assignments]
    if len(keys) != len(set(keys)):
        raise PipelineError("final Eleven-B completeness inputs contain duplicate assignment keys")

    assignments_by_grain: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in assignments:
        assignments_by_grain[(int(row["season"]), row["team_id"], row["role"])].append(row)

    no_roles_by_grain: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    seen_no_role_keys: set[str] = set()
    for row in no_role_rows:
        key = row["evidence_key"]
        if key in seen_no_role_keys:
            raise PipelineError(f"duplicate Eleven-B no-role evidence key: {key}")
        seen_no_role_keys.add(key)
        if row["role"] not in FORMAL_ROLES or row["resolution_status"] != NO_ROLE_STATUS:
            raise PipelineError(f"invalid Eleven-B no-role evidence state: {key}")
        final_week = 18 if int(row["season"]) >= 2021 else 17
        if not 1 <= int(row["start_week"]) <= int(row["end_week"]) <= final_week:
            raise PipelineError(f"invalid Eleven-B no-role evidence interval: {key}")
        _require_https(row["source_url"], key)
        no_roles_by_grain[(int(row["season"]), row["team_id"], row["role"])].append(row)

    season_weeks_by_team: dict[tuple[int, str], set[int]] = defaultdict(set)
    for row in base:
        if row["role"] == "head_coach":
            season_weeks_by_team[(int(row["season"]), row["team_id"])].update(_week_range(row))

    reviews_by_grain: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in reviews:
        if row["status"] == "open":
            reviews_by_grain[(int(row["season"]), row["team_id"], row["role"])].append(row)

    citations_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in citations:
        citations_by_key[row["assignment_key"]].append(row)

    records: list[dict[str, Any]] = []
    for season in sorted(ANALYSIS_SEASONS):
        for team in sorted(CANONICAL_TEAM_IDS):
            expected_weeks = season_weeks_by_team[(season, team)]
            if not expected_weeks:
                raise PipelineError(f"missing head-coach season boundary: {season}-{team}")
            for role in sorted(ROLES):
                grain = (season, team, role)
                role_assignments = sorted(
                    assignments_by_grain[grain],
                    key=lambda row: (
                        int(row["start_week"]),
                        int(row["end_week"]),
                        row["assignment_key"],
                    ),
                )
                role_no_roles = sorted(
                    no_roles_by_grain[grain],
                    key=lambda row: (
                        int(row["start_week"]),
                        int(row["end_week"]),
                        row["evidence_key"],
                    ),
                )
                role_reviews = sorted(reviews_by_grain[grain], key=lambda row: row["review_id"])
                statuses = {row["verification_status"] for row in role_assignments}
                verified_weeks = {
                    week
                    for row in role_assignments
                    if row["verification_status"] == "verified"
                    for week in _week_range(row)
                }
                supported_weeks = {
                    week
                    for row in role_assignments
                    if row["verification_status"] in {"verified", "provisional"}
                    for week in _week_range(row)
                }
                no_role_weeks = {week for row in role_no_roles for week in _week_range(row)}
                overlap = verified_weeks & no_role_weeks
                if overlap:
                    raise PipelineError(
                        f"no-role evidence overlaps a verified person: {season}-{team}-{role}; "
                        f"weeks={sorted(overlap)[:3]}"
                    )
                resolved_weeks = verified_weeks | no_role_weeks
                if "conflicting" in statuses:
                    status = "conflicting"
                elif expected_weeks <= verified_weeks:
                    status = "verified"
                elif expected_weeks <= resolved_weeks and role_assignments:
                    status = "verified"
                elif expected_weeks <= no_role_weeks:
                    status = NO_ROLE_STATUS
                elif expected_weeks <= supported_weeks and "provisional" in statuses:
                    status = "provisional"
                elif "verified" in statuses or role_no_roles:
                    status = "partial"
                elif "provisional" in statuses:
                    status = "provisional"
                else:
                    status = "unresolved"

                source_records: dict[str, dict[str, str]] = {}
                person_intervals: list[dict[str, Any]] = []
                for row in role_assignments:
                    embedded_sources = []
                    if row.get("source_url"):
                        embedded_sources.append(
                            {
                                "source_url": row["source_url"],
                                "source_type": row.get("source_type", ""),
                                "source_accessed_at": row.get("source_accessed_at", ""),
                                "evidence_locator": row.get("evidence_locator", ""),
                                "evidence_note": row.get("evidence_note", ""),
                            }
                        )
                    for source in [*citations_by_key[row["assignment_key"]], *embedded_sources]:
                        _require_https(source["source_url"], row["assignment_key"])
                        source_records[source["source_url"]] = source
                    person_intervals.append(
                        {
                            "evidence_type": "person_assignment",
                            "evidence_key": row["assignment_key"],
                            "coach_id": row["coach_id"],
                            "coach_name": row["coach_canonical_name"],
                            "start_week": int(row["start_week"]),
                            "end_week": int(row["end_week"]),
                            "interval_basis": row["interval_basis"],
                            "verification_status": row["verification_status"],
                            "confidence_level": row["confidence_level"],
                            "is_interim": row["is_interim"] == "true",
                            "is_shared": row["is_shared"] == "true",
                        }
                    )
                no_role_intervals: list[dict[str, Any]] = []
                for row in role_no_roles:
                    source_records[row["source_url"]] = {
                        "source_url": row["source_url"],
                        "source_type": row["source_type"],
                        "source_accessed_at": row["source_accessed_at"],
                        "evidence_locator": row["evidence_locator"],
                        "evidence_note": row["evidence_note"],
                    }
                    no_role_intervals.append(
                        {
                            "evidence_type": "verified_no_designated_role",
                            "evidence_key": row["evidence_key"],
                            "coach_id": None,
                            "coach_name": None,
                            "start_week": int(row["start_week"]),
                            "end_week": int(row["end_week"]),
                            "interval_basis": row["interval_basis"],
                            "verification_status": NO_ROLE_STATUS,
                            "confidence_level": row["confidence_level"],
                            "source_url": row["source_url"],
                            "evidence_locator": row["evidence_locator"],
                        }
                    )
                for review in role_reviews:
                    if review.get("source_url"):
                        source_records.setdefault(
                            review["source_url"],
                            {
                                "source_url": review["source_url"],
                                "source_type": "review_queue",
                                "source_accessed_at": "",
                                "evidence_locator": "",
                                "evidence_note": review.get("notes", ""),
                            },
                        )

                resolved = status in {"verified", NO_ROLE_STATUS}
                records.append(
                    {
                        "season": season,
                        "team_id": team,
                        "role": role,
                        "assignment_status": status,
                        "review_status": "manual_review"
                        if role_reviews or not resolved
                        else "complete",
                        "requires_manual_review": bool(role_reviews) or not resolved,
                        "assignment_count": len(role_assignments),
                        "verified_assignment_count": sum(
                            row["verification_status"] == "verified" for row in role_assignments
                        ),
                        "citation_count": len(source_records),
                        "has_in_season_change": len(person_intervals) + len(no_role_intervals) > 1,
                        "has_interim": any(row["is_interim"] == "true" for row in role_assignments),
                        "has_shared_duty": any(
                            row["is_shared"] == "true" for row in role_assignments
                        ),
                        "has_unclear_interval": any(
                            row["interval_basis"] == "season_designation"
                            or row["verification_status"] != "verified"
                            for row in role_assignments
                        )
                        or any(
                            row["interval_basis"] == "season_designation" for row in role_no_roles
                        ),
                        "evidence_version": EVIDENCE_VERSION,
                        "source_urls": sorted(source_records),
                        "evidence_intervals": [*person_intervals, *no_role_intervals],
                        "payload": {
                            "evidence_version": EVIDENCE_VERSION,
                            "review_ids": [row["review_id"] for row in role_reviews],
                            "review_issue_types": sorted(
                                {row["issue_type"] for row in role_reviews}
                            ),
                            "sources": [source_records[url] for url in sorted(source_records)],
                            "evidence_intervals": [*person_intervals, *no_role_intervals],
                        },
                    }
                )

    result = pl.DataFrame(records).sort("season", "team_id", "role")
    expected_rows = len(ANALYSIS_SEASONS) * len(CANONICAL_TEAM_IDS) * len(ROLES)
    if (
        result.height != expected_rows
        or result.select("season", "team_id", "role").n_unique() != expected_rows
    ):
        raise PipelineError("serving coaching completeness must contain 2,048 unique cells")
    actual_counts = {
        role: dict(Counter(result.filter(pl.col("role") == role)["assignment_status"].to_list()))
        for role in sorted(ROLES)
    }
    if actual_counts != EXPECTED_STATUS_COUNTS:
        raise PipelineError(f"Eleven-B serving completeness status mismatch: {actual_counts}")
    no_role = result.filter(pl.col("assignment_status") == NO_ROLE_STATUS)
    if no_role.height != 40 or no_role.filter(pl.col("assignment_count") != 0).height:
        raise PipelineError("verified no-designated-role cells must be 40 person-free rows")
    if any(not urls for urls in no_role["source_urls"].to_list()):
        raise PipelineError("verified no-designated-role cells must retain source provenance")
    return result

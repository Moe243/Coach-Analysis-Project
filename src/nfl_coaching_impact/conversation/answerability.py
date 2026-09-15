"""Deterministic answerability over authorized tasks, evidence, and frozen policy."""

from __future__ import annotations

from .authorization import AuthorizationResult
from .contracts import EntityResolution, EvidencePackage
from .enums import Answerability, QuestionType, ResolutionStatus
from .policy import SCIENTIFIC_POLICIES


def determine_answerability(
    question_type: QuestionType,
    resolutions: tuple[EntityResolution, ...],
    authorization: AuthorizationResult,
    package: EvidencePackage,
    requested_metric: str | None = None,
) -> Answerability:
    if any(item.status is ResolutionStatus.AMBIGUOUS for item in resolutions):
        return Answerability.CLARIFICATION_REQUIRED
    if (
        question_type is QuestionType.ROOKIE_PROJECTION
        and SCIENTIFIC_POLICIES["C20_ROOKIE_PROJECTION"].status == "NOT ESTIMABLE / DATA-LIMITED"
    ):
        return Answerability.NOT_SUPPORTED
    if (
        question_type is QuestionType.QB_PROJECTION
        and requested_metric == "performance_above_expectation"
    ):
        return Answerability.NOT_SUPPORTED
    if question_type is QuestionType.UNKNOWN:
        return Answerability.CLARIFICATION_REQUIRED
    if not package.evidence:
        return Answerability.DATA_UNAVAILABLE if resolutions else Answerability.NOT_SUPPORTED
    if (
        (
            question_type is QuestionType.PLAYER_TEAM_SCENARIO
            and SCIENTIFIC_POLICIES["C17_SCENARIO"].status == "NOT SUPPORTED"
        )
        or (
            question_type is QuestionType.CAREER_COUNTERFACTUAL
            and SCIENTIFIC_POLICIES["C18_COUNTERFACTUAL"].status == "NOT READY / NOT IMPLEMENTED"
        )
        or (
            question_type is QuestionType.COACH_EFFECT
            and SCIENTIFIC_POLICIES["C12_COACH_EFFECT"].status == "NO_COMPOSITE_COACH_EFFECT"
        )
    ):
        return Answerability.PARTIALLY_SUPPORTED
    if question_type is QuestionType.COMPARISON and any(
        entity.kind.value == "coach" for entity in package.resolved_entities
    ):
        return Answerability.PARTIALLY_SUPPORTED
    if authorization.rejected or package.answerability is Answerability.PARTIALLY_SUPPORTED:
        return Answerability.PARTIALLY_SUPPORTED
    return Answerability.SUPPORTED

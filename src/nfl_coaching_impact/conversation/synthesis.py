"""Deterministic answer-first rendering from already-approved propositions."""

from __future__ import annotations

from dataclasses import dataclass

from .conclusions import ConclusionResult
from .contracts import (
    EvidencePackage,
    PublicEvidencePoint,
    SupportedFollowUp,
    UnsupportedRequestedPortion,
)
from .enums import Answerability, QuestionType, ReasonCode


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    answer: str
    evidence: tuple[PublicEvidencePoint, ...]
    unsupported: tuple[UnsupportedRequestedPortion, ...]
    limitations: tuple[str, ...]
    follow_ups: tuple[SupportedFollowUp, ...]
    reason_code: ReasonCode | None


class DeterministicSynthesizer:
    """Organize permitted claims without deciding scientific support."""

    def compose(
        self,
        *,
        question_type: QuestionType,
        answerability: Answerability,
        conclusions: ConclusionResult,
        package: EvidencePackage,
        requested_metric: str | None,
        young_only: bool,
        unsupported_season: bool = False,
        best_seasons: bool = False,
    ) -> SynthesisResult:
        propositions = conclusions.propositions
        unsupported, reason = self._unsupported(
            question_type, requested_metric, conclusions.propositions
        )
        if unsupported_season:
            answer = (
                "Use one explicit supported season from 2010 through 2026. Relative-season "
                "and multi-season wording is not mapped to a frozen analytical season."
            )
        elif answerability is Answerability.CLARIFICATION_REQUIRED:
            answer = "I need a more specific player, coach, or team name before I look up evidence."
        elif question_type is QuestionType.ROOKIE_PROJECTION:
            answer = (
                "The approved college-data foundation cannot estimate an NFL rookie "
                "performance forecast, so no numerical projection is available."
            )
        elif answerability is Answerability.NOT_SUPPORTED and unsupported:
            answer = unsupported[0].explanation
        elif answerability is Answerability.DATA_UNAVAILABLE:
            answer = (
                "No approved record is available for that entity, season, and analytical task. "
                "No fallback estimate was created."
            )
        elif question_type is QuestionType.PLAYER_TEAM_SCENARIO:
            answer = self._scenario(propositions)
        elif question_type is QuestionType.CAREER_COUNTERFACTUAL:
            answer = self._counterfactual(propositions)
        elif question_type is QuestionType.COACH_EFFECT:
            answer = (
                "The project does not support a causal or universal Coach Effect. It can "
                "describe verified roles, same-team-season QB context, and separately labeled "
                "observational PCAE evidence without treating those as QB-development impact."
            )
        elif question_type is QuestionType.COMPARISON:
            answer = self._comparison(
                propositions,
                young_only,
                tuple(entity.display_name for entity in package.resolved_entities),
            )
        elif question_type is QuestionType.QB_PROFILE:
            answer = self._profile(propositions)
        elif question_type is QuestionType.TEAM_SCHEME:
            answer = self._team_scheme(propositions)
        elif question_type is QuestionType.COACH_QB_CONTEXT:
            answer = self._coach_qb_context(propositions)
        elif question_type is QuestionType.QB_COACHING_CONTEXT:
            history = sorted(
                (item for item in propositions if item.predicate == "historical_qb_performance"),
                key=lambda item: (
                    -(item.value or 0) if best_seasons else -(item.season or 0),
                    item.proposition_id,
                ),
            )
            # Keep both quarterbacks represented in a contextual comparison.
            shown = []
            for entity in package.resolved_entities:
                first = next(
                    (item for item in history if item.subject == entity.display_name), None
                )
                if first and first not in shown:
                    shown.append(first)
            shown.extend(item for item in history if item not in shown)
            roles = [item for item in propositions if item.predicate == "verified_role_attribution"]
            head_coaches = [item for item in roles if item.value == "head_coach"]
            # Every role sentence is an already-permitted source-backed proposition.
            answer = "\n\n".join(
                [
                    " ".join(item.statement for item in (head_coaches or roles)[:3])
                    or (
                        "No verified coaching assignment is available for these "
                        "recorded team-seasons."
                    ),
                    " ".join(item.statement for item in shown[:3]),
                    (
                        "These are the strongest recorded QB-team-seasons by EPA/dropback "
                        "with at least 200 dropbacks, within 2010–2025. "
                        if best_seasons
                        else "These are the recorded QB-team-seasons in the requested scope. "
                    )
                    + "Recorded staff context is not proof that one coach "
                    "caused the quarterback's performance.",
                ]
            )
        elif propositions:
            answer = propositions[0].statement
        else:
            answer = (
                "The request does not map to an approved analytical answer with available evidence."
            )
        by_id = {record.evidence_id: record for record in package.evidence}
        evidence_ids = []
        for proposition in propositions:
            for evidence_id in proposition.evidence_ids:
                if evidence_id in by_id and evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        public = tuple(
            PublicEvidencePoint(
                rank=index,
                evidence_id=evidence_id,
                summary=by_id[evidence_id].summary,
            )
            for index, evidence_id in enumerate(evidence_ids[:5], start=1)
        )
        limitations = list(package.limitations[:6])
        if young_only:
            limitations.insert(
                0,
                "Young quarterback is defined as age under 25 at season start; "
                "observations with missing age are excluded.",
            )
        return SynthesisResult(
            answer=answer,
            evidence=public,
            unsupported=unsupported,
            limitations=tuple(dict.fromkeys(limitations))[:8],
            follow_ups=self._follow_ups(question_type),
            reason_code=reason,
        )

    @staticmethod
    def _scenario(propositions) -> str:
        alignments = [
            proposition
            for proposition in propositions
            if proposition.predicate == "descriptive_player_scheme_alignment"
        ]
        preferred = {
            "scramble_rate": 0,
            "shotgun_rate": 1,
            "target_depth_deep_rate": 2,
            "target_depth_intermediate_rate": 3,
            "average_air_yards": 4,
            "target_depth_short_rate": 5,
        }
        alignments.sort(key=lambda item: (preferred.get(item.metric or "", 10), item.metric or ""))
        lead = (
            "The project can compare the quarterback's measured profile with the team's "
            "historical scheme, but it cannot estimate a destination-team EPA change."
        )
        return " ".join([lead, *(item.statement for item in alignments[:2])])

    @staticmethod
    def _counterfactual(propositions) -> str:
        qb_history = [
            proposition
            for proposition in propositions
            if proposition.predicate == "historical_qb_performance"
        ]
        team_scheme = [
            proposition
            for proposition in propositions
            if proposition.predicate == "historical_team_scheme"
        ]
        qb_history.sort(key=lambda item: (-(item.season or 0), item.proposition_id))
        scheme_preference = {
            "pass_rate": 0,
            "shotgun_rate": 1,
            "expected_pass_rate": 2,
            "average_air_yards": 3,
        }
        team_scheme.sort(
            key=lambda item: (
                scheme_preference.get(item.metric or "", 10),
                item.metric or "",
            )
        )
        lead = (
            "The project can show the player's actual history and the team's observed "
            "historical context, but it cannot simulate an alternate career."
        )
        selected = [*qb_history[:1], *team_scheme[:1]]
        return " ".join([lead, *(item.statement for item in selected)])

    @staticmethod
    def _profile(propositions) -> str:
        profile = [
            proposition
            for proposition in propositions
            if proposition.predicate == "entering_season_profile"
        ]
        if not profile:
            return "No supported entering-season profile measurement is available."
        lead = profile[0].statement
        category = (profile[0].qualifier or "").lower()
        if "usage" in category:
            return (
                lead + " This describes how often the style appeared, not its efficiency or a "
                "player grade."
            )
        return lead + " This is a measured profile component, not an overall player grade."

    @staticmethod
    def _team_scheme(propositions) -> str:
        scheme = [
            proposition
            for proposition in propositions
            if proposition.predicate == "historical_team_scheme"
        ]
        if not scheme:
            return "No supported historical scheme measurement is available for that scope."
        preferred = {
            "pass_rate": 0,
            "shotgun_rate": 1,
            "expected_pass_rate": 2,
            "average_air_yards": 3,
        }
        scheme.sort(key=lambda item: (preferred.get(item.metric or "", 10), item.metric or ""))
        lead = "The measured offense is best described by its observed tendencies: " + " ".join(
            item.statement for item in scheme[:3]
        )
        return lead + " These are team-season tendencies, not a subjective scheme grade."

    @staticmethod
    def _coach_qb_context(propositions) -> str:
        summary = next(
            (
                proposition
                for proposition in propositions
                if proposition.predicate == "qb_context_summary"
            ),
            None,
        )
        contexts = [
            proposition
            for proposition in propositions
            if proposition.predicate == "same_team_season_context"
        ]
        contexts.sort(
            key=lambda item: (
                -(item.season or 0),
                item.subject or "",
                item.proposition_id,
            )
        )
        selected = [*([] if summary is None else [summary]), *contexts[:4]]
        if not selected:
            return "No verified same-team-season quarterback context is available."
        return " ".join(item.statement for item in selected)

    @staticmethod
    def _comparison(propositions, young_only: bool, entity_order: tuple[str, ...]) -> str:
        if young_only:
            summaries = [
                proposition
                for proposition in propositions
                if proposition.predicate == "young_qb_context_summary"
            ]
            order = {name: index for index, name in enumerate(entity_order)}
            summaries.sort(key=lambda item: order.get(item.subject or "", len(order)))
            lead = (
                "The under-25 same-team-season evidence does not identify a better QB "
                "developer, so no development winner is selected."
            )
            return " ".join([lead, *(item.statement for item in summaries[:2])])
        direct = next(
            (
                proposition
                for proposition in propositions
                if proposition.predicate
                in {
                    "verified_role_evidence_comparison",
                    "same_metric_descriptive_comparison",
                }
            ),
            None,
        )
        if direct is None:
            answer = (
                "The available evidence is mixed or insufficient for a direct comparison, "
                "so no overall winner is selected."
            )
        else:
            answer = direct.statement
            if direct.predicate == "same_metric_descriptive_comparison":
                answer += " This is a same-season comparison, not a career ranking."
        return answer

    @staticmethod
    def _unsupported(
        question_type: QuestionType, requested_metric: str | None, propositions
    ) -> tuple[tuple[UnsupportedRequestedPortion, ...], ReasonCode | None]:
        if question_type is QuestionType.PLAYER_TEAM_SCENARIO:
            code = ReasonCode.C17_SCENARIO_NOT_SUPPORTED
            return (
                (
                    UnsupportedRequestedPortion(
                        description="Destination-team numerical performance or improvement",
                        reason_code=code,
                        explanation=(
                            "The destination-team model did not improve prediction on unseen "
                            "seasons, so the project does not estimate a team-specific performance "
                            "change. Historical profile and scheme evidence may still be compared."
                        ),
                    ),
                ),
                code,
            )
        if question_type is QuestionType.CAREER_COUNTERFACTUAL:
            code = ReasonCode.C18_COUNTERFACTUAL_NOT_IMPLEMENTED
            return (
                (
                    UnsupportedRequestedPortion(
                        description="Alternate-career numerical simulation",
                        reason_code=code,
                        explanation=(
                            "The project cannot simulate alternate careers because it has no "
                            "validated destination-team response model."
                        ),
                    ),
                ),
                code,
            )
        if question_type is QuestionType.ROOKIE_PROJECTION:
            code = ReasonCode.C20_ROOKIE_MODEL_NOT_ESTIMABLE
            return (
                (
                    UnsupportedRequestedPortion(
                        description="College-to-NFL rookie performance projection",
                        reason_code=code,
                        explanation=(
                            "The available college data cannot support a reliable NFL rookie "
                            "performance projection."
                        ),
                    ),
                ),
                code,
            )
        if question_type is QuestionType.COACH_EFFECT:
            code = ReasonCode.CAUSAL_CONCLUSION_NOT_PERMITTED
            return (
                (
                    UnsupportedRequestedPortion(
                        description="Causal or universal Coach Effect conclusion",
                        reason_code=code,
                        explanation=(
                            "There is no composite or causal Coach Effect estimate in the "
                            "available observational evidence."
                        ),
                    ),
                ),
                code,
            )
        if question_type is QuestionType.COMPARISON and any(
            proposition.predicate == "verified_role_evidence_comparison"
            for proposition in propositions
        ):
            code = ReasonCode.DEVELOPMENT_CONCLUSION_NOT_PERMITTED
            return (
                (
                    UnsupportedRequestedPortion(
                        description="Universal or causal QB-development winner",
                        reason_code=code,
                        explanation=(
                            "Verified roles and QB contexts do not identify comparative "
                            "development quality."
                        ),
                    ),
                ),
                code,
            )
        if question_type is QuestionType.QB_PROJECTION and requested_metric not in {
            None,
            "epa_per_dropback",
        }:
            pae = requested_metric == "performance_above_expectation"
            code = (
                ReasonCode.FORWARD_PAE_NOT_SUPPORTED
                if pae
                else ReasonCode.SCIENTIFICALLY_UNSUPPORTED
            )
            return (
                (
                    UnsupportedRequestedPortion(
                        description=(
                            "Forward PAE projection"
                            if pae
                            else "Unsupported projection output or context"
                        ),
                        reason_code=code,
                        explanation=(
                            "The approved research forecast supports only team-independent "
                            "EPA/dropback for 2026; it does not support touchdowns, yards, "
                            "probabilities, coach-specific effects, or other requested outputs."
                        ),
                    ),
                ),
                code,
            )
        return (), None

    @staticmethod
    def _follow_ups(question_type: QuestionType) -> tuple[SupportedFollowUp, ...]:
        labels = {
            QuestionType.QB_HISTORY: (
                "Show the quarterback's entering-season profile",
                "Compare with another quarterback",
            ),
            QuestionType.QB_PROFILE: (
                "Show historical performance",
                "Explain the profile reliability",
                "Show deep and short usage",
            ),
            QuestionType.QB_PROJECTION: (
                "Show historical performance",
                "Show the entering-season profile",
            ),
            QuestionType.COACH_QB_CONTEXT: (
                "Show verified offensive roles",
                "Show available PCAE evidence",
                "Limit to a specific season",
            ),
            QuestionType.COMPARISON: (
                "Show their QB histories",
                "Compare their verified offensive roles",
                "Show available PCAE evidence",
                "Limit to a specific season",
            ),
            QuestionType.PLAYER_TEAM_SCENARIO: (
                "Show the scheme differences",
                "Show the quarterback's historical profile",
                "Show the team-independent projection",
            ),
        }.get(question_type, ())
        return tuple(SupportedFollowUp(label=label, question=label) for label in labels[:4])

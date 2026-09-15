"""Backend-owned deterministic Ask v2 orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from .answerability import determine_answerability
from .authorization import AuthorizationResult, TaskAuthorizer
from .conclusions import ConclusionEngine, ConclusionResult
from .contracts import (
    ASK_V2_CONTRACT_VERSION,
    STAGE_C_IMPLEMENTATION_VERSION,
    AskV2Request,
    AskV2Response,
    EvidencePackage,
    PublicVersionMetadata,
    contract_schema_sha256,
)
from .enums import (
    AnalyticalTask,
    Answerability,
    AnswerMode,
    QuestionType,
    ReasonCode,
    ResolutionStatus,
)
from .evidence import EvidenceService, ReducerResult
from .planner import DeterministicPlan, DeterministicPlanner
from .policy import SCIENTIFIC_POLICY_VERSION
from .registries import EVIDENCE_REDUCER_VERSION, SCHEME_FEATURE_UNITS
from .synthesis import DeterministicSynthesizer


@dataclass(frozen=True, slots=True)
class AuthoritativeResult:
    """Backend-authorized analytical state before optional presentation."""

    plan: DeterministicPlan
    package: EvidencePackage
    conclusions: ConclusionResult
    response: AskV2Response


class AskV2Orchestrator:
    """Execute only authorized registry tasks and render permitted propositions."""

    def __init__(self, evidence: EvidenceService):
        self.evidence = evidence
        self.planner = DeterministicPlanner(evidence.resolver, evidence.analytical.entities)
        self.authorizer = TaskAuthorizer()
        self.conclusions = ConclusionEngine()
        self.synthesizer = DeterministicSynthesizer()

    def answer(self, request: AskV2Request) -> AskV2Response:
        return self.analyze(request).response

    def analyze(
        self, request: AskV2Request, plan: DeterministicPlan | None = None
    ) -> AuthoritativeResult:
        plan = plan or self.planner.plan(request)
        exact_entities = tuple(
            resolution.resolved[0]
            for resolution in plan.resolutions
            if resolution.lookup_authorized
        )
        candidates = tuple(
            candidate
            for resolution in plan.resolutions
            if resolution.status is ResolutionStatus.AMBIGUOUS
            for candidate in resolution.candidates
        )[:5]
        authorization = self.authorizer.authorize(plan.proposal, plan.resolved_by_index)
        result = self._execute(plan, authorization)
        package = self._package(plan, authorization, result, exact_entities)
        answerability = determine_answerability(
            plan.proposal.question_type,
            plan.resolutions,
            authorization,
            package,
            plan.requested_metric,
        )
        conclusions = self.conclusions.derive(
            plan.proposal.question_type,
            package,
            plan.requested_metric,
        )
        synthesis = self.synthesizer.compose(
            question_type=plan.proposal.question_type,
            answerability=answerability,
            conclusions=conclusions,
            package=package,
            requested_metric=plan.requested_metric,
            young_only=plan.young_only,
        )
        reason = synthesis.reason_code
        if answerability is Answerability.CLARIFICATION_REQUIRED:
            reason = ReasonCode.ENTITY_AMBIGUOUS if candidates else ReasonCode.ENTITY_UNRESOLVED
        elif answerability is Answerability.DATA_UNAVAILABLE:
            reason = (
                ReasonCode.SEASON_UNSUPPORTED
                if plan.unsupported_season
                else ReasonCode.DATA_NOT_AVAILABLE
            )
        versions = package.versions.model_copy(
            update={
                "planner_implementation_version": STAGE_C_IMPLEMENTATION_VERSION,
                "deterministic_planner_version": STAGE_C_IMPLEMENTATION_VERSION,
                "synthesizer_implementation_version": STAGE_C_IMPLEMENTATION_VERSION,
            }
        )
        proposition_uncertainty = {
            proposition.uncertainty_id
            for proposition in conclusions.propositions
            if proposition.uncertainty_id
        }
        uncertainty = tuple(
            item for item in package.uncertainty if item.uncertainty_id in proposition_uncertainty
        )[:12]
        response = AskV2Response(
            answerability=answerability,
            answer_mode=AnswerMode.DETERMINISTIC,
            reason_code=reason,
            answer=synthesis.answer,
            entities=exact_entities,
            clarification_candidates=candidates,
            evidence=synthesis.evidence,
            propositions=conclusions.propositions,
            conclusion_permissions=conclusions.permissions,
            uncertainty=uncertainty,
            unsupported_portions=synthesis.unsupported,
            limitations=synthesis.limitations,
            follow_ups=synthesis.follow_ups,
            versions=versions,
        )
        return AuthoritativeResult(
            plan=plan,
            package=package,
            conclusions=conclusions,
            response=response,
        )

    def _execute(
        self, plan: DeterministicPlan, authorization: AuthorizationResult
    ) -> ReducerResult:
        results = []
        if (
            plan.proposal.question_type is QuestionType.QB_PROJECTION
            and plan.requested_metric == "performance_above_expectation"
        ):
            return ReducerResult()
        for approved in authorization.approved:
            entities = approved.entities
            season = (
                approved.seasons.start_season
                if approved.seasons and approved.seasons.start_season == approved.seasons.end_season
                else None
            )
            task = approved.task
            if task is AnalyticalTask.GET_QB_HISTORY:
                result = self.evidence.qb_history(entities[0].id, season)
            elif task is AnalyticalTask.GET_QB_PROFILE:
                features = self._profile_features(plan.requested_metric)
                result = self.evidence.qb_profile(entities[0].id, season, features)
            elif task is AnalyticalTask.GET_QB_PROJECTION:
                result = self.evidence.projection(entities[0].id, season or 2026)
            elif task is AnalyticalTask.GET_COACH_ASSIGNMENTS:
                result = self.evidence.coach_assignments(entities[0].id, season)
            elif task is AnalyticalTask.GET_COACH_QB_CONTEXT:
                result = self.evidence.coach_qb_context(
                    entities[0].id,
                    season,
                    young_only=plan.young_only,
                )
            elif task is AnalyticalTask.GET_TEAM_SCHEME:
                features = self._scheme_features(plan.requested_metric)
                result = self.evidence.team_scheme(entities[0].id, season, features)
            elif task is AnalyticalTask.GET_PLAYCALLER_PCAE:
                result = self.evidence.pcae(entities[0].id, season)
            elif task is AnalyticalTask.COMPARE_QB_MEASUREMENTS:
                result = self.evidence.compare_qbs(
                    entities[0].id,
                    entities[1].id,
                    season or 2025,
                )
            elif task is AnalyticalTask.COMPARE_TEAM_SCHEME:
                result = self.evidence.compare_teams_scheme(
                    entities[0].id,
                    entities[1].id,
                    season or 2025,
                )
            elif task is AnalyticalTask.COMPARE_COACH_EVIDENCE:
                result = self.evidence.compare_coaches(
                    entities[0].id,
                    entities[1].id,
                    season,
                    young_only=plan.young_only,
                )
            elif task is AnalyticalTask.DESCRIBE_PLAYER_SCHEME_ALIGNMENT:
                target_season = season or 2025
                result = self.evidence.player_team_alignment(
                    entities[0].id,
                    entities[1].id,
                    target_season,
                    max(2010, target_season - 1),
                )
            else:  # pragma: no cover - closed enum is exhaustively handled
                raise ValueError("authorized analytical task has no registered executor")
            results.append(result)
        return ReducerResult.combine(*results)

    def _package(
        self,
        plan: DeterministicPlan,
        authorization: AuthorizationResult,
        result: ReducerResult,
        entities,
    ) -> EvidencePackage:
        if authorization.approved:
            package = self.evidence.package(
                authorization.approved[0].task,
                result,
                entities,
                plan.proposal.tasks[0].seasons if plan.proposal.tasks else None,
            )
            return package.model_copy(
                update={
                    "approved_tasks": authorization.approved,
                    "rejected_tasks": authorization.rejected,
                }
            )
        return EvidencePackage(
            answerability=Answerability.DATA_UNAVAILABLE,
            resolved_entities=entities,
            rejected_tasks=authorization.rejected,
            versions=PublicVersionMetadata(
                ask_contract_version=ASK_V2_CONTRACT_VERSION,
                contract_schema_sha256=contract_schema_sha256(),
                scientific_policy_version=SCIENTIFIC_POLICY_VERSION,
                analytical_data_version=self.evidence.analytical.version,
                evidence_reducer_version=EVIDENCE_REDUCER_VERSION,
                deterministic_planner_version=STAGE_C_IMPLEMENTATION_VERSION,
                planner_implementation_version=STAGE_C_IMPLEMENTATION_VERSION,
                synthesizer_implementation_version=STAGE_C_IMPLEMENTATION_VERSION,
                answer_mode=AnswerMode.DETERMINISTIC,
            ),
        )

    @staticmethod
    def _profile_features(metric: str | None) -> tuple[str, ...] | None:
        if metric is None:
            return None
        feature = metric if metric.startswith("recent_") else "recent_" + metric
        return (feature,)

    @staticmethod
    def _scheme_features(metric: str | None) -> tuple[str, ...] | None:
        return (metric,) if metric in SCHEME_FEATURE_UNITS else None

"""Backend-owned task authorization for deterministic Ask v2 execution."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ApprovedTask, PlannerProposal, RejectedTask, ResolvedEntity
from .enums import AnalyticalTask, EntityKind, QuestionType, ReasonCode


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    approved: tuple[ApprovedTask, ...]
    rejected: tuple[RejectedTask, ...]


_REQUIRED_KINDS = {
    AnalyticalTask.GET_QB_HISTORY: (EntityKind.QB,),
    AnalyticalTask.GET_QB_PROFILE: (EntityKind.QB,),
    AnalyticalTask.GET_QB_PROJECTION: (EntityKind.QB,),
    AnalyticalTask.GET_COACH_ASSIGNMENTS: (EntityKind.COACH,),
    AnalyticalTask.GET_COACH_QB_CONTEXT: (EntityKind.COACH,),
    AnalyticalTask.GET_TEAM_SCHEME: (EntityKind.TEAM,),
    AnalyticalTask.GET_PLAYCALLER_PCAE: (EntityKind.COACH,),
    AnalyticalTask.COMPARE_QB_MEASUREMENTS: (EntityKind.QB, EntityKind.QB),
    AnalyticalTask.COMPARE_TEAM_SCHEME: (EntityKind.TEAM, EntityKind.TEAM),
    AnalyticalTask.COMPARE_COACH_EVIDENCE: (EntityKind.COACH, EntityKind.COACH),
    AnalyticalTask.DESCRIBE_PLAYER_SCHEME_ALIGNMENT: (EntityKind.QB, EntityKind.TEAM),
}

_QUESTION_TASKS = {
    QuestionType.QB_HISTORY: {AnalyticalTask.GET_QB_HISTORY},
    QuestionType.QB_PROFILE: {AnalyticalTask.GET_QB_PROFILE},
    QuestionType.QB_PROJECTION: {AnalyticalTask.GET_QB_PROJECTION},
    QuestionType.COACH_HISTORY: {AnalyticalTask.GET_COACH_ASSIGNMENTS},
    QuestionType.COACH_QB_CONTEXT: {AnalyticalTask.GET_COACH_QB_CONTEXT},
    QuestionType.TEAM_SCHEME: {
        AnalyticalTask.GET_TEAM_SCHEME,
        AnalyticalTask.COMPARE_TEAM_SCHEME,
    },
    QuestionType.PCAE_RESEARCH: {AnalyticalTask.GET_PLAYCALLER_PCAE},
    QuestionType.PLAYER_SCHEME_ALIGNMENT: {
        AnalyticalTask.GET_QB_PROFILE,
        AnalyticalTask.GET_TEAM_SCHEME,
        AnalyticalTask.GET_QB_PROJECTION,
        AnalyticalTask.DESCRIBE_PLAYER_SCHEME_ALIGNMENT,
    },
    QuestionType.COMPARISON: {
        AnalyticalTask.COMPARE_QB_MEASUREMENTS,
        AnalyticalTask.COMPARE_TEAM_SCHEME,
        AnalyticalTask.COMPARE_COACH_EVIDENCE,
    },
    QuestionType.PLAYER_TEAM_SCENARIO: {
        AnalyticalTask.GET_QB_PROFILE,
        AnalyticalTask.GET_TEAM_SCHEME,
        AnalyticalTask.GET_QB_PROJECTION,
        AnalyticalTask.DESCRIBE_PLAYER_SCHEME_ALIGNMENT,
    },
    QuestionType.CAREER_COUNTERFACTUAL: {
        AnalyticalTask.GET_QB_HISTORY,
        AnalyticalTask.GET_TEAM_SCHEME,
    },
    QuestionType.COACH_EFFECT: {
        AnalyticalTask.GET_COACH_ASSIGNMENTS,
        AnalyticalTask.GET_COACH_QB_CONTEXT,
        AnalyticalTask.GET_PLAYCALLER_PCAE,
        AnalyticalTask.COMPARE_COACH_EVIDENCE,
    },
    QuestionType.ROOKIE_PROJECTION: set(),
    QuestionType.UNKNOWN: set(),
}


class TaskAuthorizer:
    """Treat planner output as untrusted and approve only registered operations."""

    def authorize(
        self,
        proposal: PlannerProposal,
        resolved_by_index: dict[int, ResolvedEntity],
    ) -> AuthorizationResult:
        approved: list[ApprovedTask] = []
        rejected: list[RejectedTask] = []
        permitted = _QUESTION_TASKS[proposal.question_type]
        for position, proposed in enumerate(proposal.tasks, start=1):
            task_id = f"task_{position}"
            if proposed.task not in permitted:
                rejected.append(
                    RejectedTask(
                        task_id=task_id,
                        task=proposed.task,
                        reason_code=ReasonCode.TASK_NOT_ALLOWED,
                        explanation="The proposed task is not allowed for this question type.",
                    )
                )
                continue
            entities = tuple(
                resolved_by_index[index]
                for index in proposed.entity_indexes
                if index in resolved_by_index
            )
            required = _REQUIRED_KINDS[proposed.task]
            if tuple(entity.kind for entity in entities) != required:
                rejected.append(
                    RejectedTask(
                        task_id=task_id,
                        task=proposed.task,
                        reason_code=ReasonCode.ENTITY_UNRESOLVED,
                        explanation="The task does not have the required canonical entities.",
                    )
                )
                continue
            approved.append(
                ApprovedTask(
                    task_id=task_id,
                    task=proposed.task,
                    entities=entities,
                    seasons=proposed.seasons,
                    authorization_reason=ReasonCode.SUPPORTED_ANALYTICAL_TASK.value,
                )
            )
        return AuthorizationResult(tuple(approved), tuple(rejected))

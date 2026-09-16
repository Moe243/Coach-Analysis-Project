"""Untrusted language drafts and backend-owned translation; no analytical authority."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from .contracts import (
    AskV2Request,
    ContractModel,
    PlannerEntityProposal,
    PlannerProposal,
    ResolvedEntity,
)
from .enums import ContextDependency, ConversationRole, EntityKind, QuestionType, RequestedOutput
from .planner import DeterministicPlan, DeterministicPlanner
from .providers import ProviderError, ProviderFailureCategory
from .resolution import normalize


class RequestedCapability(StrEnum):
    QB_HISTORY = "QB_HISTORY"
    QB_PROFILE = "QB_PROFILE"
    QB_PROJECTION = "QB_PROJECTION"
    COACH_HISTORY = "COACH_HISTORY"
    COACH_QB_CONTEXT = "COACH_QB_CONTEXT"
    COACH_COMPARISON = "COACH_COMPARISON"
    QB_COMPARISON = "QB_COMPARISON"
    TEAM_SCHEME = "TEAM_SCHEME"
    PLAYER_TEAM_DESCRIPTIVE_COMPARISON = "PLAYER_TEAM_DESCRIPTIVE_COMPARISON"
    CAREER_COUNTERFACTUAL_REQUEST = "CAREER_COUNTERFACTUAL_REQUEST"
    ROOKIE_PROJECTION_REQUEST = "ROOKIE_PROJECTION_REQUEST"
    COACH_EFFECT_REQUEST = "COACH_EFFECT_REQUEST"
    PCAE_RESEARCH = "PCAE_RESEARCH"
    EXPLANATION = "EXPLANATION"


class FollowupKind(StrEnum):
    NONE = "NONE"
    EXPLANATION = "EXPLANATION"
    REFINE_SCOPE = "REFINE_SCOPE"
    COMPARISON = "COMPARISON"


class ProviderEntityMention(ContractModel):
    text: str = Field(min_length=1, max_length=100)
    kind_hint: EntityKind

    @model_validator(mode="after")
    def validate_literal(self):
        # Reuse existing syntax controls, but never accept canonical-ID hints or text.
        PlannerEntityProposal(kind=self.kind_hint, mention=self.text)
        if re.search(r"(?:coach-|team_|00-\d|[A-Z]{3}\d{6})", self.text):
            raise ValueError("provider mentions must be names, not canonical identifiers")
        return self


class ProviderPlanDraft(ContractModel):
    question_type: QuestionType
    entity_mentions: tuple[ProviderEntityMention, ...] = Field(max_length=8)
    season_mentions: tuple[StrictInt, ...] = Field(max_length=8)
    requested_capabilities: tuple[RequestedCapability, ...] = Field(min_length=1, max_length=8)
    comparison_requested: StrictBool
    followup_kind: FollowupKind

    @field_validator("season_mentions", "requested_capabilities")
    @classmethod
    def reject_duplicates(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("duplicate provider draft value")
        return tuple(sorted(values))


class ProviderDraftInput(ContractModel):
    question: str = Field(min_length=3, max_length=1_000)
    prior_user_questions: tuple[str, ...] = Field(max_length=8)
    context_mentions: tuple[ProviderEntityMention, ...] = Field(max_length=8)
    context_seasons: tuple[int, ...] = Field(max_length=8)


class DraftRejected(ProviderError):
    category = ProviderFailureCategory.GROUNDING_REJECTED


class DraftEntityResolutionRejected(DraftRejected):
    category = ProviderFailureCategory.ENTITY_RESOLUTION_ERROR


class DraftTaskTranslationRejected(DraftRejected):
    category = ProviderFailureCategory.TASK_TRANSLATION_ERROR


_CAPABILITY_TYPES = {
    RequestedCapability.QB_HISTORY: QuestionType.QB_HISTORY,
    RequestedCapability.QB_PROFILE: QuestionType.QB_PROFILE,
    RequestedCapability.QB_PROJECTION: QuestionType.QB_PROJECTION,
    RequestedCapability.COACH_HISTORY: QuestionType.COACH_HISTORY,
    RequestedCapability.COACH_QB_CONTEXT: QuestionType.COACH_QB_CONTEXT,
    RequestedCapability.COACH_COMPARISON: QuestionType.COMPARISON,
    RequestedCapability.QB_COMPARISON: QuestionType.COMPARISON,
    RequestedCapability.TEAM_SCHEME: QuestionType.TEAM_SCHEME,
    RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON: QuestionType.PLAYER_SCHEME_ALIGNMENT,
    RequestedCapability.CAREER_COUNTERFACTUAL_REQUEST: QuestionType.CAREER_COUNTERFACTUAL,
    RequestedCapability.ROOKIE_PROJECTION_REQUEST: QuestionType.ROOKIE_PROJECTION,
    RequestedCapability.COACH_EFFECT_REQUEST: QuestionType.COACH_EFFECT,
    RequestedCapability.PCAE_RESEARCH: QuestionType.PCAE_RESEARCH,
}
_RESTRICTED = {
    QuestionType.CAREER_COUNTERFACTUAL,
    QuestionType.PLAYER_TEAM_SCENARIO,
    QuestionType.ROOKIE_PROJECTION,
    QuestionType.COACH_EFFECT,
}


class ProviderDraftTranslator:
    """Bind only source-resolved, literal-grounded intent using existing planner rules."""

    def __init__(self, planner: DeterministicPlanner):
        self.planner = planner

    def provider_input(self, request: AskV2Request) -> ProviderDraftInput:
        legacy = self.planner.provider_input(request)
        # Revalidate canonical context on the backend, and send labels rather than IDs.
        context = self.planner.resolver.revalidate_context(request.context.entities)
        seasons = request.context.seasons
        return ProviderDraftInput(
            question=request.question,
            prior_user_questions=legacy.prior_user_questions,
            context_mentions=tuple(
                ProviderEntityMention(text=e.display_name, kind_hint=e.kind) for e in context
            ),
            context_seasons=(
                tuple(sorted({seasons.start_season, seasons.end_season})) if seasons else ()
            ),
        )

    def _literal_entity(self, mention: ProviderEntityMention) -> ResolvedEntity:
        resolution = self.planner.resolver.resolve(mention.kind_hint, mention.text)
        if resolution.lookup_authorized:
            return resolution.resolved[0]
        # Exact surname normalization is permitted only if the entire frozen catalog
        # contains one matching identity of this kind. Never promote fuzzy/first-name
        # candidates. The expanded full name must still resolve EXACT via the resolver.
        literal = normalize(mention.text)
        if len(literal) >= 4 and " " not in literal:
            matches = [
                row
                for row in self.planner.source_entities
                if row["kind"] == mention.kind_hint.value
                and normalize(row["name"]).split()[-1] == literal
            ]
            if len(matches) == 1 and mention.kind_hint in {EntityKind.QB, EntityKind.COACH}:
                exact = self.planner.resolver.resolve(mention.kind_hint, matches[0]["name"])
                if exact.lookup_authorized:
                    return exact.resolved[0]
        raise DraftEntityResolutionRejected("literal entity is unknown or ambiguous")

    def translate(self, request: AskV2Request, untrusted: object) -> DeterministicPlan:
        draft = ProviderPlanDraft.model_validate(untrusted)
        question = normalize(request.question)
        followup = self.planner._is_follow_up(question)
        if draft.followup_kind is not FollowupKind.NONE and not followup:
            raise DraftRejected("follow-up classification conflicts with the literal request")
        context, failures = self.planner._context_entities(request)
        if failures and not context and followup:
            raise DraftEntityResolutionRejected("canonical context could not be validated")
        context_keys = {(e.kind, e.id) for e in context}
        prior_question = next(
            (
                normalize(t.content)
                for t in reversed(request.context.turns)
                if t.role is ConversationRole.USER
            ),
            "",
        )
        intent_question = question
        if followup and not self.planner._find_exact_entities(request.question):
            intent_question += " " + prior_question
        literals = [question]
        if followup:
            literals.extend((prior_question, *(normalize(e.display_name) for e in context)))
        current = []
        seen = set()
        for mention in draft.entity_mentions:
            if not any(f" {normalize(mention.text)} " in f" {text} " for text in literals):
                raise DraftRejected("provider mention is absent from literal user context")
            entity = self._literal_entity(mention)
            key = (entity.kind, entity.id)
            if f" {normalize(mention.text)} " not in f" {question} " and key not in context_keys:
                raise DraftRejected("provider tried to replace validated canonical history")
            if key in seen:
                raise DraftRejected("duplicate provider entity")
            seen.add(key)
            current.append(entity)
        # A draft cannot silently discard an exact entity in the current user question.
        exact = self.planner._find_exact_entities(request.question)
        if not {(e.kind, e.id) for e in exact} <= seen:
            raise DraftRejected("draft omitted a literal canonical entity")
        entities = self.planner._merge_entities(question, tuple(current), context, followup)
        if not entities:
            raise DraftEntityResolutionRejected("draft has no unambiguous canonical entities")
        # Entity order is source-independent and deterministic; tasks bind this order.
        entities = tuple(sorted(entities, key=lambda e: (e.kind.value, e.id)))
        resolutions = tuple(self.planner._exact_resolution(e) for e in entities)
        season, unsupported = self.planner._season(request, question)
        years = {int(v) for v in re.findall(r"\b20\d{2}\b", question)}
        if unsupported:
            raise DraftRejected("requested season is unsupported or ambiguous")
        if years:
            if set(draft.season_mentions) != years:
                raise DraftRejected("draft omitted or invented a literal season")
        elif draft.season_mentions:
            permitted = {season.start_season, season.end_season} if season else set()
            if set(draft.season_mentions) != permitted:
                raise DraftRejected("draft invented a season outside validated context")
        native = self.planner._question_type(question, entities, request)
        capabilities = set(draft.requested_capabilities)
        if RequestedCapability.EXPLANATION in capabilities:
            if not followup or len(capabilities) != 1 or native is QuestionType.UNKNOWN:
                raise DraftRejected("explanation requires validated prior intent")
            chosen = native
        else:
            types = {_CAPABILITY_TYPES[c] for c in capabilities}
            descriptive = RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON in capabilities
            if descriptive:
                if not capabilities <= {
                    RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON,
                    RequestedCapability.QB_PROFILE,
                    RequestedCapability.TEAM_SCHEME,
                } or not {EntityKind.QB, EntityKind.TEAM} <= {e.kind for e in entities}:
                    raise DraftRejected("ambiguous descriptive capabilities")
                if not re.search(
                    r"\b(style|resemble|alignment|fit|tendenc|profile|offense|offensive)\b",
                    intent_question,
                ):
                    raise DraftRejected("descriptive capability lacks literal intent")
                chosen = native if native in _RESTRICTED else QuestionType.PLAYER_SCHEME_ALIGNMENT
                if chosen in _RESTRICTED and chosen is not QuestionType.PLAYER_TEAM_SCENARIO:
                    raise DraftRejected("descriptive capability conflicts with restricted intent")
            elif len(types) == 1:
                chosen = next(iter(types))
                if chosen is QuestionType.COMPARISON:
                    kinds = {e.kind for e in entities}
                    required = (
                        EntityKind.COACH
                        if RequestedCapability.COACH_COMPARISON in capabilities
                        else EntityKind.QB
                    )
                    if (
                        len(entities) != 2
                        or kinds != {required}
                        or (not draft.comparison_requested and not followup)
                        or not re.search(
                            r"\b(compare|between|whose|versus|vs|stronger|better)\b",
                            intent_question,
                        )
                    ):
                        raise DraftRejected("comparison lacks unambiguous literal intent")
                    if native in _RESTRICTED:
                        chosen = native
                    elif native not in {
                        QuestionType.UNKNOWN,
                        QuestionType.COMPARISON,
                        QuestionType.COACH_HISTORY,
                        QuestionType.QB_HISTORY,
                    }:
                        raise DraftRejected("comparison conflicts with backend intent")
                elif chosen is not native:
                    raise DraftRejected("capability conflicts materially with backend intent")
            else:
                raise DraftRejected("ambiguous requested capabilities")
        tasks = self.planner._tasks(chosen, list(resolutions), season, question)
        if not tasks:
            raise DraftTaskTranslationRejected("no backend task supports this draft")
        proposal = PlannerProposal(
            question_type=chosen,
            entities=tuple(
                PlannerEntityProposal(kind=e.kind, mention=e.display_name) for e in entities
            ),
            tasks=tasks,
            requested_outputs=tuple(RequestedOutput),
            context_dependencies=(ContextDependency.PRIOR_ENTITY, ContextDependency.PRIOR_QUESTION)
            if followup
            else (),
        )
        return DeterministicPlan(
            proposal=proposal,
            resolutions=resolutions,
            requested_metric=self.planner._requested_metric(question, chosen, resolutions),
            young_only="young quarterback" in question or "young qb" in question,
            follow_up=followup,
        )

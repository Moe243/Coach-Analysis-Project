"""Deterministic local planner behind the future provider-planner interface."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import (
    MAX_SEASON,
    MIN_SEASON,
    AnalyticalTaskProposal,
    AskV2Request,
    CanonicalEntityReference,
    EntityResolution,
    PlannerEntityProposal,
    PlannerProposal,
    ProviderPlannerInput,
    ResolvedEntity,
    SeasonContext,
)
from .enums import (
    AnalyticalTask,
    ContextDependency,
    ConversationRole,
    EntityKind,
    QuestionType,
    RequestedOutput,
    ResolutionStatus,
)
from .resolution import EntityResolver, normalize


@dataclass(frozen=True, slots=True)
class DeterministicPlan:
    proposal: PlannerProposal
    resolutions: tuple[EntityResolution, ...]
    requested_metric: str | None
    young_only: bool
    follow_up: bool
    unsupported_season: bool = False

    @property
    def resolved_by_index(self) -> dict[int, ResolvedEntity]:
        return {
            index: resolution.resolved[0]
            for index, resolution in enumerate(self.resolutions)
            if resolution.lookup_authorized
        }


_METRICS = {
    "probability": "probability",
    "touchdown": "passing_touchdowns",
    "touchdowns": "passing_touchdowns",
    "td": "passing_touchdowns",
    "tds": "passing_touchdowns",
    "passing yards": "passing_yards",
    "yards": "passing_yards",
    "interception": "interceptions",
    "interceptions": "interceptions",
    "ints": "interceptions",
    "pae": "performance_above_expectation",
    "epa": "epa_per_dropback",
    "cpoe": "cpoe",
    "shotgun": "shotgun_rate",
    "scramble": "scramble_rate",
    "mobile": "scramble_rate",
    "mobility": "scramble_rate",
    "deep": "target_depth_deep_rate",
    "short": "target_depth_short_rate",
    "intermediate": "target_depth_intermediate_rate",
    "sack": "sack_rate",
    "success": "success_rate",
}


def _contains(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


class DeterministicPlanner:
    """Propose allowlisted tasks; never authorize them or set scientific status."""

    def __init__(self, resolver: EntityResolver, source_entities: list[dict]):
        self.resolver = resolver
        self.source_entities = source_entities

    def plan(self, request: AskV2Request) -> DeterministicPlan:
        question = normalize(request.question)
        follow_up = self._is_follow_up(question)
        current = self._find_exact_entities(request.question)
        context, context_failures = self._context_entities(request)
        entities = self._merge_entities(question, current, context, follow_up)
        preliminary = self._question_type(question, entities, request)
        resolutions = [self._exact_resolution(entity) for entity in entities]
        if follow_up and not current and not entities:
            resolutions.extend(context_failures)
        if not entities and preliminary not in {
            QuestionType.ROOKIE_PROJECTION,
            QuestionType.UNKNOWN,
        }:
            unresolved = self._unresolved_reference(question, preliminary)
            if unresolved is not None:
                resolutions.append(unresolved)
        proposals = tuple(
            PlannerEntityProposal(
                kind=resolution.kind,
                mention=resolution.mention,
                canonical_id_hint=(
                    CanonicalEntityReference(
                        kind=resolution.resolved[0].kind,
                        id=resolution.resolved[0].id,
                    )
                    if resolution.lookup_authorized
                    else None
                ),
            )
            for resolution in resolutions
        )
        season, unsupported_season = self._season(request, question)
        question_type = self._question_type(
            question,
            tuple(
                resolution.resolved[0] for resolution in resolutions if resolution.lookup_authorized
            ),
            request,
        )
        tasks = (
            () if unsupported_season else self._tasks(question_type, resolutions, season, question)
        )
        dependencies = ()
        if follow_up:
            dependencies = (ContextDependency.PRIOR_QUESTION, ContextDependency.PRIOR_ENTITY)
            if season is not None:
                dependencies += (ContextDependency.PRIOR_SEASON,)
        proposal = PlannerProposal(
            question_type=question_type,
            entities=proposals,
            tasks=tasks,
            requested_outputs=tuple(RequestedOutput),
            context_dependencies=dependencies,
        )
        requested_metric = self._requested_metric(question, question_type, resolutions)
        return DeterministicPlan(
            proposal=proposal,
            resolutions=tuple(resolutions),
            requested_metric=requested_metric,
            young_only="young quarterback" in question or "young qb" in question,
            follow_up=follow_up,
            unsupported_season=unsupported_season,
        )

    def provider_input(self, request: AskV2Request) -> ProviderPlannerInput:
        """Build the bounded interpretation payload; assistant prose is excluded."""
        prior_user_questions = tuple(
            turn.content for turn in request.context.turns if turn.role is ConversationRole.USER
        )
        return ProviderPlannerInput(
            question=request.question,
            prior_user_questions=prior_user_questions,
            canonical_context=request.context.entities,
            seasons=request.context.seasons,
            allowed_question_types=tuple(QuestionType),
            allowed_tasks=tuple(AnalyticalTask),
            allowed_outputs=tuple(RequestedOutput),
            allowed_context_dependencies=tuple(ContextDependency),
        )

    def from_provider(self, request: AskV2Request, untrusted: PlannerProposal) -> DeterministicPlan:
        """Re-resolve an untrusted provider plan and enforce the requested season scope."""
        deterministic = self.plan(request)
        if (
            deterministic.proposal.question_type is not QuestionType.UNKNOWN
            and untrusted.question_type is not deterministic.proposal.question_type
        ):
            raise ValueError("provider question type conflicts with backend interpretation")
        requested_season, unsupported_season = self._season(request, normalize(request.question))
        if unsupported_season:
            raise ValueError("provider cannot override an unsupported requested season")
        if any(task.seasons != requested_season for task in untrusted.tasks):
            raise ValueError("provider task season differs from the user-authorized scope")

        resolutions = tuple(
            self.resolver.resolve(entity.kind, entity.mention) for entity in untrusted.entities
        )
        current = self._find_exact_entities(request.question)
        context, _ = self._context_entities(request)
        allowed_entities = {(entity.kind, entity.id) for entity in (*current, *context)}
        for resolution in resolutions:
            if resolution.lookup_authorized:
                entity = resolution.resolved[0]
                if (entity.kind, entity.id) not in allowed_entities:
                    raise ValueError("provider introduced an entity absent from user context")
        # Canonical hints from a provider are deliberately discarded. Only the resolver's
        # exact result can later authorize an analytical lookup.
        proposal = PlannerProposal(
            question_type=untrusted.question_type,
            entities=tuple(
                PlannerEntityProposal(kind=entity.kind, mention=entity.mention)
                for entity in untrusted.entities
            ),
            tasks=untrusted.tasks,
            requested_outputs=untrusted.requested_outputs,
            context_dependencies=untrusted.context_dependencies,
        )
        question = normalize(request.question)
        requested_metric = self._requested_metric(
            question,
            untrusted.question_type,
            resolutions,
        )
        return DeterministicPlan(
            proposal=proposal,
            resolutions=resolutions,
            requested_metric=requested_metric,
            young_only="young quarterback" in question or "young qb" in question,
            follow_up=self._is_follow_up(question),
        )

    def _find_exact_entities(self, text: str) -> tuple[ResolvedEntity, ...]:
        normalized = normalize(text)
        matches: dict[tuple[EntityKind, str], tuple[int, int, ResolvedEntity]] = {}
        for row in self.source_entities:
            kind = EntityKind(row["kind"])
            entity = self.resolver.require_id(kind, row["id"])
            labels = [row["id"], row["name"], *row.get("aliases", [])]
            for label in labels:
                candidate = normalize(str(label))
                if len(candidate) < 3 or not _contains(normalized, candidate):
                    continue
                position = f" {normalized} ".find(f" {candidate} ")
                key = (kind, entity.id)
                previous = matches.get(key)
                score = (position, -len(candidate))
                if previous is None or score < previous[:2]:
                    matches[key] = (position, -len(candidate), entity)
        return tuple(item[2] for item in sorted(matches.values(), key=lambda item: item[:2]))

    def _context_entities(
        self, request: AskV2Request
    ) -> tuple[tuple[ResolvedEntity, ...], tuple[EntityResolution, ...]]:
        explicit = []
        failures = []
        for reference in request.context.entities:
            result = self.resolver.resolve(reference.kind, reference.id)
            if result.lookup_authorized:
                explicit.append(result.resolved[0])
            else:
                failures.append(result)
        prior: list[ResolvedEntity] = []
        for turn in reversed(request.context.turns):
            if turn.role is ConversationRole.USER:
                prior.extend(self._find_exact_entities(turn.content))
                if prior:
                    break
        ordered = prior or list(explicit)
        seen: set[tuple[EntityKind, str]] = set()
        result = []
        for entity in ordered:
            key = (entity.kind, entity.id)
            if key not in seen:
                seen.add(key)
                result.append(entity)
        return tuple(result), tuple(failures)

    @staticmethod
    def _is_follow_up(question: str) -> bool:
        return bool(
            re.fullmatch(
                r"(?:why|why .*|what about .*|how about .*|and .*|now .*|only .*|"
                r"who is better|which is better|by how much)",
                question,
            )
        )

    @staticmethod
    def _requested_metric(
        question: str,
        question_type: QuestionType,
        resolutions: list[EntityResolution] | tuple[EntityResolution, ...],
    ) -> str | None:
        metric = next((value for key, value in _METRICS.items() if _contains(question, key)), None)
        if question_type is QuestionType.QB_PROJECTION and any(
            resolution.kind is EntityKind.COACH and resolution.lookup_authorized
            for resolution in resolutions
        ):
            return "coach_specific_projection"
        return metric

    def _merge_entities(
        self,
        question: str,
        current: tuple[ResolvedEntity, ...],
        context: tuple[ResolvedEntity, ...],
        follow_up: bool,
    ) -> tuple[ResolvedEntity, ...]:
        result = list(current)
        if follow_up and not current:
            result = list(context)
        elif follow_up:
            for entity in context:
                surname = normalize(entity.display_name).split()[-1]
                if _contains(question, surname) and entity not in result:
                    result.insert(0, entity)
            if "compare" in question and len(result) == 1:
                for entity in context:
                    if entity.kind is result[0].kind and entity not in result:
                        result.insert(0, entity)
                        break
        seen: set[tuple[EntityKind, str]] = set()
        deduplicated = []
        for entity in result:
            key = (entity.kind, entity.id)
            if key not in seen:
                seen.add(key)
                deduplicated.append(entity)
        return tuple(deduplicated)

    def _unresolved_reference(
        self, question: str, question_type: QuestionType
    ) -> EntityResolution | None:
        kind = (
            EntityKind.COACH
            if question_type
            in {
                QuestionType.COACH_HISTORY,
                QuestionType.COACH_QB_CONTEXT,
                QuestionType.COACH_EFFECT,
                QuestionType.PCAE_RESEARCH,
            }
            else EntityKind.TEAM
            if question_type is QuestionType.TEAM_SCHEME
            else EntityKind.QB
        )
        ignored = {
            "performance",
            "perform",
            "history",
            "scheme",
            "offense",
            "coach",
            "quarterback",
            "compare",
            "projection",
            "how",
            "did",
            "does",
            "the",
            "this",
            "that",
            "what",
            "which",
            "with",
            "from",
            "recorded",
            "player",
            "team",
            "type",
            "run",
        }
        first_not_found = None
        for token in question.split():
            if len(token) < 3 or token.isdigit() or token in ignored:
                continue
            resolution = self.resolver.resolve(kind, token)
            if resolution.status is ResolutionStatus.AMBIGUOUS:
                return resolution
            if first_not_found is None:
                first_not_found = resolution
        return first_not_found

    def _question_type(
        self,
        question: str,
        entities: tuple[ResolvedEntity, ...],
        request: AskV2Request,
    ) -> QuestionType:
        kinds = [entity.kind for entity in entities]
        projection_language = re.search(
            r"\b(project|projects|projection|forecast|how will|predict|probability)\b",
            question,
        )
        counterfactual_language = re.search(
            r"\b(what if|had been|would have|instead|counterfactual|alternate career|"
            r"simulate career|never had|super bowl count|career yards|career touchdowns|"
            r"career tds)\b",
            question,
        ) or re.search(r"\b(alternate|simulate)\b.*\bcareer\b", question)
        if (
            EntityKind.QB in kinds
            and EntityKind.TEAM in kinds
            and re.search(r"\b(draft|drafted)\b", question)
        ):
            return QuestionType.CAREER_COUNTERFACTUAL
        if (
            EntityKind.QB in kinds
            and EntityKind.COACH in kinds
            and not projection_language
            and re.search(r"\b(never had|with|under)\b", question)
        ):
            return QuestionType.CAREER_COUNTERFACTUAL
        if re.search(
            r"\b(rookie|college|ncaa|prospect|first year|college to nfl)\b", question
        ) and re.search(
            r"\b(will|predict|project|projection|forecast|perform|epa|yards|touchdown|"
            r"touchdowns|tds|translation)\b",
            question,
        ):
            return QuestionType.ROOKIE_PROJECTION
        if (
            "patrick mahomes" in question
            and re.search(r"\b(chicago|bears)\b", question)
            and not projection_language
        ):
            # This named historical prompt is an alternate-draft/career question in the
            # approved product matrix, not a destination-team forecast.
            return QuestionType.CAREER_COUNTERFACTUAL
        if {EntityKind.QB, EntityKind.TEAM} <= set(kinds) and (
            re.search(
                r"\b(fit|what would|how would|team switch|to|on|under|join|joined|"
                r"trade|traded|better|improve|project|forecast|epa|how many)\b",
                question,
            )
            or re.search(r"\bwould\b.*\b(make|improve|better)\b", question)
        ):
            return QuestionType.PLAYER_TEAM_SCENARIO
        if counterfactual_language and not projection_language:
            return QuestionType.CAREER_COUNTERFACTUAL
        if re.search(r"\b(coach effect|causes?|make quarterbacks|makes qbs)\b", question):
            return QuestionType.COACH_EFFECT
        if projection_language:
            return QuestionType.QB_PROJECTION
        if re.search(
            r"\b(which qbs|which quarterbacks|played under|coached by|relationships?)\b",
            question,
        ):
            return QuestionType.COACH_QB_CONTEXT
        if re.search(r"\b(pcae|call value|play calling decision)\b", question):
            return QuestionType.PCAE_RESEARCH
        if (
            len(kinds) >= 2
            and len(set(kinds)) == 1
            and re.search(
                r"\b(compare|versus|vs|stronger|better|why|young quarterback)\b", question
            )
        ):
            return QuestionType.COMPARISON
        if EntityKind.TEAM in kinds and re.search(
            r"\b(scheme|offense|shotgun|no huddle|pass rate|target)\b", question
        ):
            return QuestionType.TEAM_SCHEME
        if EntityKind.COACH in kinds and re.search(
            r"\b(coach|role|staff|history|play caller|verified|assignment)\b", question
        ):
            return QuestionType.COACH_HISTORY
        if EntityKind.QB in kinds and re.search(
            r"\b(style|profile|mobile|mobility|scramble|shotgun|deep|short)\b", question
        ):
            return QuestionType.QB_PROFILE
        if re.search(r"\b(performance|perform|epa|pae|cpoe|stats|history)\b", question):
            return QuestionType.QB_HISTORY
        if self._is_follow_up(question) and request.context.turns:
            prior_turn = next(
                (
                    turn
                    for turn in reversed(request.context.turns)
                    if turn.role is ConversationRole.USER
                ),
                None,
            )
            if prior_turn is None:
                return QuestionType.UNKNOWN
            prior = normalize(prior_turn.content)
            if len(prior) < 3:
                return QuestionType.UNKNOWN
            return self._question_type(prior, entities, AskV2Request(question=prior))
        if EntityKind.QB in kinds:
            return QuestionType.QB_HISTORY
        return QuestionType.UNKNOWN

    @staticmethod
    def _season(request: AskV2Request, question: str) -> tuple[SeasonContext | None, bool]:
        years = sorted({int(value) for value in re.findall(r"\b(?:20)\d{2}\b", question)})
        if len(years) == 1:
            if not MIN_SEASON <= years[0] <= MAX_SEASON:
                return None, True
            return SeasonContext(start_season=years[0], end_season=years[0]), False
        if len(years) > 1:
            return None, True
        if re.search(r"\b(next|last|previous|this|current) (year|season)\b", question):
            return None, True
        return request.context.seasons, False

    @staticmethod
    def _tasks(
        question_type: QuestionType,
        resolutions: list[EntityResolution],
        season: SeasonContext | None,
        question: str,
    ) -> tuple[AnalyticalTaskProposal, ...]:
        indexes: dict[EntityKind, list[int]] = {kind: [] for kind in EntityKind}
        for index, resolution in enumerate(resolutions):
            indexes[resolution.kind].append(index)

        def task(value: AnalyticalTask, entity_indexes: tuple[int, ...]):
            return AnalyticalTaskProposal(task=value, entity_indexes=entity_indexes, seasons=season)

        qbs, coaches, teams = (
            indexes[EntityKind.QB],
            indexes[EntityKind.COACH],
            indexes[EntityKind.TEAM],
        )
        if question_type is QuestionType.QB_HISTORY and qbs:
            return (task(AnalyticalTask.GET_QB_HISTORY, (qbs[0],)),)
        if question_type is QuestionType.QB_PROFILE and qbs:
            return (task(AnalyticalTask.GET_QB_PROFILE, (qbs[0],)),)
        if question_type is QuestionType.QB_PROJECTION and qbs:
            return (task(AnalyticalTask.GET_QB_PROJECTION, (qbs[0],)),)
        if question_type is QuestionType.COACH_HISTORY and coaches:
            return (task(AnalyticalTask.GET_COACH_ASSIGNMENTS, (coaches[0],)),)
        if question_type is QuestionType.COACH_QB_CONTEXT and coaches:
            return (task(AnalyticalTask.GET_COACH_QB_CONTEXT, (coaches[0],)),)
        if question_type is QuestionType.PCAE_RESEARCH and coaches:
            return (task(AnalyticalTask.GET_PLAYCALLER_PCAE, (coaches[0],)),)
        if question_type is QuestionType.TEAM_SCHEME:
            if len(teams) >= 2:
                return (task(AnalyticalTask.COMPARE_TEAM_SCHEME, tuple(teams[:2])),)
            if teams:
                return (task(AnalyticalTask.GET_TEAM_SCHEME, (teams[0],)),)
        if question_type is QuestionType.COMPARISON:
            if len(qbs) >= 2:
                return (task(AnalyticalTask.COMPARE_QB_MEASUREMENTS, tuple(qbs[:2])),)
            if len(coaches) >= 2:
                return (task(AnalyticalTask.COMPARE_COACH_EVIDENCE, tuple(coaches[:2])),)
            if len(teams) >= 2:
                return (task(AnalyticalTask.COMPARE_TEAM_SCHEME, tuple(teams[:2])),)
        if (
            question_type
            in {
                QuestionType.PLAYER_TEAM_SCENARIO,
                QuestionType.PLAYER_SCHEME_ALIGNMENT,
            }
            and qbs
            and teams
        ):
            tasks = [
                task(AnalyticalTask.GET_QB_PROFILE, (qbs[0],)),
                task(AnalyticalTask.GET_TEAM_SCHEME, (teams[0],)),
                task(AnalyticalTask.DESCRIBE_PLAYER_SCHEME_ALIGNMENT, (qbs[0], teams[0])),
            ]
            if "projection" in question or "model project" in question:
                tasks.append(task(AnalyticalTask.GET_QB_PROJECTION, (qbs[0],)))
            return tuple(tasks)
        if question_type is QuestionType.CAREER_COUNTERFACTUAL and qbs:
            tasks = [task(AnalyticalTask.GET_QB_HISTORY, (qbs[0],))]
            if teams:
                tasks.append(task(AnalyticalTask.GET_TEAM_SCHEME, (teams[0],)))
            return tuple(tasks)
        if question_type is QuestionType.COACH_EFFECT and coaches:
            if len(coaches) >= 2:
                return (task(AnalyticalTask.COMPARE_COACH_EVIDENCE, tuple(coaches[:2])),)
            return (
                task(AnalyticalTask.GET_COACH_ASSIGNMENTS, (coaches[0],)),
                task(AnalyticalTask.GET_COACH_QB_CONTEXT, (coaches[0],)),
                task(AnalyticalTask.GET_PLAYCALLER_PCAE, (coaches[0],)),
            )
        return ()

    @staticmethod
    def _exact_resolution(entity: ResolvedEntity) -> EntityResolution:
        return EntityResolution(
            mention=entity.display_name,
            kind=entity.kind,
            status=ResolutionStatus.EXACT,
            resolved=(entity,),
            lookup_authorized=True,
        )

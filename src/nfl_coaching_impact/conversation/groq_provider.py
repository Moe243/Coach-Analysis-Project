"""Groq Responses API adapter for optional Ask v2 interpretation."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from .answer_writer import ApprovedAnswerBrief
from .contracts import (
    MAX_SEASON,
    MIN_SEASON,
    STAGE_D_IMPLEMENTATION_VERSION,
    ContractModel,
    ProviderSynthesisInput,
)
from .enums import EntityKind, QuestionType
from .openai_provider import OpenAISynthesizer, _parsed
from .provider_drafts import (
    FollowupKind,
    ProviderDraftInput,
    ProviderPlanDraft,
    RequestedCapability,
)
from .providers import (
    PlannerStructuralDiagnostics,
    PlannerValidationCategory,
    ProviderConfiguration,
    ProviderMalformedOutput,
    ProviderRuntime,
)
from .serialization import canonical_json_bytes
from .writer_composition import CompositionPlan, composition_provider_input

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_PLANNER_REASONING_EFFORT = "low"
GROQ_SYNTHESIZER_REASONING_EFFORT = "low"
GROQ_PROVIDER_IMPLEMENTATION_VERSION = (
    STAGE_D_IMPLEMENTATION_VERSION + "/groq-json-planner-v3-responses-3.14"
)
GROQ_WRITER_IMPLEMENTATION_VERSION = (
    STAGE_D_IMPLEMENTATION_VERSION + "/groq-composition-writer-v2.2-responses-3.14"
)

_DRAFT_INSTRUCTIONS = """\
Interpret language only; do not answer the football question or determine scientific support.
Return one JSON object with exactly these fields: question_type, entity_texts, entity_kinds,
season_mentions, requested_capabilities, comparison_requested, followup_kind. All arrays contain
only primitive values; entity_texts and entity_kinds are parallel arrays. Extract literal entity
names and literal years only from the question
or relevant prior USER context. Do not expand surnames, invent years, create IDs, bind entities
to tasks, or calculate anything. Backend resolves identities, binds tasks/seasons and authorizes
all evidence and conclusions. Choose broad requested capabilities, not internal executable tasks.
Use one primary capability; unknown/ambiguous requests must not be guessed.
Examples, shown as compact field sequences in the required key order:
Between Reid and Tomlin, whose résumé has stronger QB evidence? -> COMPARISON;
[Reid,Tomlin]; [coach,coach]; []; [COACH_COMPARISON]; true; NONE.
Does Kyler Murray's style resemble Minnesota's offense? -> PLAYER_SCHEME_ALIGNMENT;
[Kyler Murray,Minnesota]; [qb,team]; []; [PLAYER_TEAM_DESCRIPTIVE_COMPARISON]; true; NONE.
What does the model project for Josh Allen in 2026? -> QB_PROJECTION;
[Josh Allen]; [qb]; [2026]; [QB_PROJECTION]; false; NONE.
What if Chicago drafted Mahomes? -> CAREER_COUNTERFACTUAL;
[Chicago,Mahomes]; [team,qb]; []; [CAREER_COUNTERFACTUAL_REQUEST]; false; NONE.
Why? -> inherit prior request type; []; []; []; [EXPLANATION]; false; EXPLANATION.
What about 2023? -> inherit prior request type/capability; []; []; [2023]; [EXPLANATION];
false; REFINE_SCOPE.
For the Kyler example, the complete object is:
{"question_type":"PLAYER_SCHEME_ALIGNMENT","entity_texts":["Kyler Murray","Minnesota"],
"entity_kinds":["qb","team"],"season_mentions":[],"requested_capabilities":
["PLAYER_TEAM_DESCRIPTIVE_COMPARISON"],"comparison_requested":true,"followup_kind":"NONE"}
Never propose a supported projection to satisfy a counterfactual, destination prediction,
forward PAE, rookie, or Coach Effect request. Classify the actual requested intent instead.
"""

_DRAFT_CONTRACT = (
    "\nStrict JSON contract: include ALL seven keys; no key is optional. "
    "Never use null. question_type and followup_kind are strings; "
    "comparison_requested is a JSON boolean (true or false), never a string. "
    "entity_texts, entity_kinds, season_mentions, requested_capabilities are arrays, "
    "even for one item. Use [] for absent entities or years. Entity arrays must "
    "have equal lengths (maximum 8); entity text is 1–100 characters. "
    "season_mentions contains only literal integer years 2010–2026 (maximum 8). "
    "requested_capabilities must contain 1–8 allowed strings. "
    "Use only these exact enum spellings; do not invent synonymous labels.\n"
    "question_type: " + ", ".join(item.value for item in QuestionType) + ".\n"
    "entity_kinds items: " + ", ".join(item.value for item in EntityKind) + ".\n"
    "requested_capabilities items: " + ", ".join(item.value for item in RequestedCapability) + ".\n"
    "followup_kind: " + ", ".join(item.value for item in FollowupKind) + ".\n"
    "A question asking how a QB performed in a historical season is QB_HISTORY "
    "with capability QB_HISTORY. For example, How did Josh Allen perform in 2022? -> "
    '{"question_type":"QB_HISTORY","entity_texts":["Josh Allen"],'
    '"entity_kinds":["qb"],"season_mentions":[2022],'
    '"requested_capabilities":["QB_HISTORY"],"comparison_requested":false,'
    '"followup_kind":"NONE"}\n'
)

_WRITER_INSTRUCTIONS = """\
Compose a natural football answer by selecting approved phrase IDs only. Return CompositionPlan.
Never write sentence text, reasoning, calculations or new claims. The backend renders every word.
Choose useful facts, ordering, variants and one to three short paragraphs. Include required_fact
and ALL required_limitations exactly once. Choose at most one variant for any support_id.
Lead with a proposition; a supported commonality or comparison can lead. Definitions are optional.
Use only connector enum values: none, continuation, contrast, comparison, limitation_transition.
The first item must use none. Use limitation_transition only before a limitation.
Place limitations naturally, without separating them into a visible list. Preserve projection
scope. Aim for 60–180 words, less when sufficient; never exceed maximum_words including connectors.
Do not repeat navigation options, IDs, metadata or reasoning. At most eight factual/definition
phrases and sixteen total phrases. Choose fewer facts when needed to fit all mandatory caveats.
For PLAYER_TEAM_SCENARIO, follow composition_rules: select at least minimum_facts useful
historical comparisons, player-first or team-first. Group the football points naturally, then
put ALL limitations after ALL facts, with connector=none. Prefer two short paragraphs: football
comparison first, one concise global caveat last. Never interrupt comparisons with caveats.
Avoid repetitive introductions; the approved comparisons already express direction, not fit.
"""

_MAX_PLANNER_OUTPUT_CHARACTERS = 16_384
_JSON_FENCE = re.compile(r"```json[ \t]*\r?\n(?P<body>.*?)\r?\n```", re.DOTALL | re.IGNORECASE)


def writer_provider_input(brief: ApprovedAnswerBrief) -> dict[str, Any]:
    """Transmit a bounded approved phrase catalog, without arbitrary prose fields."""
    return composition_provider_input(brief)


PlannerSeason = Annotated[StrictInt, Field(ge=MIN_SEASON, le=MAX_SEASON)]


class GroqPlannerDraft(ContractModel):
    """Flat provider JSON; strict backend contracts remain the authority."""

    question_type: StrictStr = Field(min_length=1, max_length=64)
    entity_texts: tuple[StrictStr, ...] = Field(max_length=8)
    entity_kinds: tuple[StrictStr, ...] = Field(max_length=8)
    season_mentions: tuple[PlannerSeason, ...] = Field(max_length=8)
    requested_capabilities: tuple[StrictStr, ...] = Field(min_length=1, max_length=8)
    comparison_requested: StrictBool
    followup_kind: StrictStr = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def parallel_entities(self):
        if len(self.entity_texts) != len(self.entity_kinds):
            raise ValueError("entity text and kind arrays must have equal lengths")
        if any(not text or len(text) > 100 for text in self.entity_texts):
            raise ValueError("entity text must contain 1 through 100 characters")
        return self

    def backend_draft(self) -> ProviderPlanDraft:
        """Revalidate every untrusted value through the unchanged backend schema."""
        return ProviderPlanDraft.model_validate(
            {
                "question_type": self.question_type,
                "entity_mentions": [
                    {"text": text, "kind_hint": kind}
                    for text, kind in zip(self.entity_texts, self.entity_kinds, strict=True)
                ],
                "season_mentions": self.season_mentions,
                "requested_capabilities": self.requested_capabilities,
                "comparison_requested": self.comparison_requested,
                "followup_kind": self.followup_kind,
            }
        )


class GroqPlanner:
    """Extract an untrusted language draft, without internal task mechanics."""

    implementation_version = GROQ_PROVIDER_IMPLEMENTATION_VERSION

    def __init__(self, client: Any, configuration: ProviderConfiguration):
        self.client = client
        self.configuration = configuration
        self.model_version = configuration.planner_model

    def plan(self, request: ProviderDraftInput, *, timeout: float) -> ProviderPlanDraft:
        response = self.client.responses.create(**self._request_arguments(request, timeout))
        raw_text = _planner_response_text(response)
        return _parse_planner_output(raw_text)

    def _request_arguments(self, request: ProviderDraftInput, timeout: float) -> dict[str, Any]:
        return dict(
            model=self.model_version,
            instructions=_DRAFT_INSTRUCTIONS + _DRAFT_CONTRACT,
            input=canonical_json_bytes(request).decode("ascii"),
            text={"format": {"type": "json_object"}},
            store=False,
            background=False,
            stream=False,
            tools=[],
            tool_choice="none",
            parallel_tool_calls=False,
            reasoning={"effort": GROQ_PLANNER_REASONING_EFFORT},
            max_output_tokens=self.configuration.planner_max_output_tokens,
            timeout=timeout,
        )


class GroqSynthesizer(OpenAISynthesizer):
    """Select backend-authored propositions without authoring analytical text."""

    implementation_version = GROQ_PROVIDER_IMPLEMENTATION_VERSION

    def _request_arguments(self, request: ProviderSynthesisInput, timeout: float) -> dict[str, Any]:
        arguments = super()._request_arguments(request, timeout)
        arguments["reasoning"] = {"effort": GROQ_SYNTHESIZER_REASONING_EFFORT}
        return arguments


class GroqAnswerWriter:
    """Select approved language; backend alone renders factual prose."""

    implementation_version = GROQ_WRITER_IMPLEMENTATION_VERSION

    def __init__(self, client: Any, configuration: ProviderConfiguration):
        self.client = client
        self.configuration = configuration
        self.model_version = configuration.synthesizer_model

    def write(self, request: ApprovedAnswerBrief, *, timeout: float) -> CompositionPlan:
        response = self.client.responses.parse(**self._request_arguments(request, timeout))
        parsed = _parsed(response, CompositionPlan)
        # The SDK's Pydantic parser accepts duplicate JSON keys with last-value wins.
        # Reject ambiguous raw output, including nested keys, before using that model.
        raw_text = getattr(response, "output_text", None)
        if raw_text is not None:
            try:
                raw = json.loads(raw_text, object_pairs_hook=_unique_json_object)
                if CompositionPlan.model_validate(raw) != parsed:
                    raise ValueError("raw writer output differs from the parsed output")
            except (TypeError, ValueError) as error:
                raise ProviderMalformedOutput(
                    "writer returned ambiguous structured output"
                ) from error
        return parsed

    def _request_arguments(self, request: ApprovedAnswerBrief, timeout: float) -> dict[str, Any]:
        return dict(
            model=self.model_version,
            instructions=_WRITER_INSTRUCTIONS,
            input=canonical_json_bytes(writer_provider_input(request)).decode("ascii"),
            text_format=CompositionPlan,
            store=False,
            background=False,
            stream=False,
            tools=[],
            tool_choice="none",
            parallel_tool_calls=False,
            reasoning={"effort": GROQ_SYNTHESIZER_REASONING_EFFORT},
            max_output_tokens=self.configuration.synthesizer_max_output_tokens,
            timeout=timeout,
        )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicatePlannerKey("duplicate structured-output key")
        result[key] = value
    return result


class _DuplicatePlannerKey(ValueError):
    pass


def _malformed(
    message: str,
    outcome: PlannerValidationCategory,
    structure: PlannerStructuralDiagnostics | None = None,
) -> ProviderMalformedOutput:
    return ProviderMalformedOutput(
        message, planner_validation_outcome=outcome, planner_structure=structure
    )


def _planner_structure(raw: Any, *, duplicate_key: bool = False) -> PlannerStructuralDiagnostics:
    """Project structure onto fixed names/types, never raw keys or field values.

    All seven fields are required and non-null. Four fields are arrays (empty
    entities/seasons are valid; capabilities requires at least one item). The
    remaining fields are two enum strings and one strict boolean. Entity arrays
    must have equal lengths. There are no optional fields or structural defaults.
    """
    fields = tuple(sorted(GroqPlannerDraft.model_fields))
    if type(raw) is not dict:
        return PlannerStructuralDiagnostics(duplicate_key_detected=duplicate_key)

    def category(value: Any) -> str:
        return {
            str: "string",
            list: "array",
            dict: "object",
            bool: "boolean",
            int: "number",
            float: "number",
            type(None): "null",
        }.get(type(value), "other")

    # Arbitrary property names can themselves contain user/provider content.
    # Only predeclared structural aliases are ever disclosed; all others collapse.
    aliases = {
        "seasons",
        "capabilities",
        "comparison",
        "entities",
        "followup",
        "entity_text",
        "entity_kind",
    }
    unexpected = tuple(
        sorted({key if key in aliases else "UNKNOWN_FIELD" for key in raw if key not in fields})
    )
    enums = {
        "question_type": {item.value for item in QuestionType},
        "entity_kinds": {item.value for item in EntityKind},
        "requested_capabilities": {item.value for item in RequestedCapability},
        "followup_kind": {item.value for item in FollowupKind},
    }
    invalid = None
    for name, allowed in enums.items():
        value = raw.get(name)
        values = value if type(value) is list else [value]
        if any(type(item) is str and item not in allowed for item in values):
            invalid = name
            break

    def count(name: str) -> int | None:
        value = raw.get(name)
        return len(value) if type(value) is list else None

    return PlannerStructuralDiagnostics(
        missing_field_names=tuple(name for name in fields if name not in raw),
        unexpected_field_names=unexpected,
        field_type_categories=tuple(
            (name, category(raw[name]) if name in raw else "missing") for name in fields
        ),
        array_lengths=tuple(
            (name, len(raw[name])) for name in fields if type(raw.get(name)) is list
        ),
        null_field_names=tuple(name for name in fields if name in raw and raw[name] is None),
        invalid_enum_field_name=invalid,
        entity_text_count=count("entity_texts"),
        entity_kind_count=count("entity_kinds"),
        season_count=count("season_mentions"),
        capability_count=count("requested_capabilities"),
        duplicate_key_detected=duplicate_key,
        top_level_object=True,
    )


def _planner_response_text(response: Any) -> str:
    """Read one SDK text result without trusting parsed-output shortcuts."""
    raw_text = getattr(response, "output_text", None)
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    candidates: list[str] = []
    try:
        for output in getattr(response, "output", ()) or ():
            for content in getattr(output, "content", ()) or ():
                if getattr(content, "type", None) == "output_text":
                    value = getattr(content, "text", None)
                    if isinstance(value, str):
                        candidates.append(value)
    except Exception as error:
        raise _malformed(
            "planner response text could not be read",
            PlannerValidationCategory.PROVIDER_PARSE_FAILED,
        ) from error
    if len(candidates) == 1:
        return candidates[0]
    outcome = (
        PlannerValidationCategory.JSON_MISSING
        if not candidates
        else PlannerValidationCategory.PROVIDER_PARSE_FAILED
    )
    raise _malformed("planner returned no single JSON result", outcome)


def _parse_planner_output(raw_text: str) -> ProviderPlanDraft:
    """Parse only a complete JSON object or one whole fenced JSON object."""
    text = raw_text.strip()
    if not text:
        raise _malformed("planner returned empty output", PlannerValidationCategory.JSON_MISSING)
    if len(text) > _MAX_PLANNER_OUTPUT_CHARACTERS:
        raise _malformed(
            "planner output exceeded the bounded contract",
            PlannerValidationCategory.JSON_SHAPE_INVALID,
        )
    if text.startswith("```") or text.endswith("```"):
        fenced = _JSON_FENCE.fullmatch(text)
        if fenced is None:
            raise _malformed(
                "planner returned invalid fenced output",
                PlannerValidationCategory.JSON_SYNTAX_INVALID,
            )
        text = fenced.group("body").strip()
        if not text:
            raise _malformed(
                "planner returned an empty JSON fence",
                PlannerValidationCategory.JSON_MISSING,
            )
    try:
        raw = json.loads(text, object_pairs_hook=_unique_json_object)
    except _DuplicatePlannerKey as error:
        raise _malformed(
            "planner returned duplicate JSON keys",
            PlannerValidationCategory.DUPLICATE_KEY,
            _planner_structure(None, duplicate_key=True),
        ) from error
    except json.JSONDecodeError as error:
        outcome = (
            PlannerValidationCategory.JSON_TRUNCATED
            if _looks_truncated(text, error)
            else PlannerValidationCategory.JSON_SYNTAX_INVALID
        )
        raise _malformed("planner returned invalid JSON", outcome) from error
    if type(raw) is not dict:
        raise _malformed(
            "planner JSON was not an object",
            PlannerValidationCategory.JSON_SHAPE_INVALID,
            _planner_structure(raw),
        )
    try:
        return GroqPlannerDraft.model_validate(raw).backend_draft()
    except (TypeError, ValueError) as error:
        raise _malformed(
            "planner JSON did not match the bounded contract",
            PlannerValidationCategory.JSON_SHAPE_INVALID,
            _planner_structure(raw),
        ) from error


def _looks_truncated(text: str, error: json.JSONDecodeError) -> bool:
    """Classify only end-of-input failures with an unclosed JSON container."""
    if error.pos < max(0, len(text) - 2) or not text.startswith(("{", "[")):
        return False
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"}": "{", "]": "["}
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "{[":
            stack.append(character)
        elif character in "}]":
            if not stack or stack.pop() != pairs[character]:
                return False
    return bool(stack or in_string)


def groq_runtime(configuration: ProviderConfiguration) -> ProviderRuntime:
    """Create a Groq client only after provider and sharing gates validate."""
    if not configuration.ready:
        return ProviderRuntime(configuration=configuration)
    from openai import OpenAI

    client = OpenAI(
        api_key=configuration.api_key,
        base_url=GROQ_BASE_URL,
        max_retries=0,
    )
    return ProviderRuntime(
        configuration=configuration,
        planner=GroqPlanner(client, configuration),
        writer=GroqAnswerWriter(client, configuration),
    )

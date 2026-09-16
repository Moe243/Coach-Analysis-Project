"""Groq Responses API adapter for optional Ask v2 interpretation."""

from __future__ import annotations

from typing import Any

from .contracts import (
    STAGE_D_IMPLEMENTATION_VERSION,
    ProviderSynthesisInput,
)
from .openai_provider import OpenAISynthesizer, _parsed
from .provider_drafts import ProviderDraftInput, ProviderPlanDraft
from .providers import ProviderConfiguration, ProviderRuntime
from .serialization import canonical_json_bytes

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_PLANNER_REASONING_EFFORT = "medium"
GROQ_SYNTHESIZER_REASONING_EFFORT = "low"
GROQ_PROVIDER_IMPLEMENTATION_VERSION = (
    STAGE_D_IMPLEMENTATION_VERSION + "/groq-draft-planner-v1-responses-3.14"
)

_DRAFT_INSTRUCTIONS = """\
Interpret language only; do not answer the football question or determine scientific support.
Return the strict draft. Extract literal entity names and literal years only from the question
or relevant prior USER context. Do not expand surnames, invent years, create IDs, bind entities
to tasks, or calculate anything. Backend resolves identities, binds tasks/seasons and authorizes
all evidence and conclusions. Choose broad requested capabilities, not internal executable tasks.
Use one primary capability; unknown/ambiguous requests must not be guessed.
Examples (entity entries have text and kind_hint):
Between Reid and Tomlin, whose résumé has stronger QB evidence? -> COMPARISON;
Reid/coach, Tomlin/coach; []; COACH_COMPARISON; comparison_requested=true; NONE.
Does Kyler Murray's style resemble Minnesota's offense? -> PLAYER_SCHEME_ALIGNMENT;
Kyler Murray/qb, Minnesota/team; []; PLAYER_TEAM_DESCRIPTIVE_COMPARISON; true; NONE.
What does the model project for Josh Allen in 2026? -> QB_PROJECTION;
Josh Allen/qb; [2026]; QB_PROJECTION; false; NONE.
What if Chicago drafted Mahomes? -> CAREER_COUNTERFACTUAL;
Chicago/team, Mahomes/qb; []; CAREER_COUNTERFACTUAL_REQUEST; false; NONE.
Why? -> inherit prior request type; []; []; EXPLANATION; false; EXPLANATION.
What about 2023? -> inherit prior request type/capability; []; [2023]; false; REFINE_SCOPE.
Never propose a supported projection to satisfy a counterfactual, destination prediction,
forward PAE, rookie, or Coach Effect request. Classify the actual requested intent instead.
"""


class GroqPlanner:
    """Extract an untrusted language draft, without internal task mechanics."""

    implementation_version = GROQ_PROVIDER_IMPLEMENTATION_VERSION

    def __init__(self, client: Any, configuration: ProviderConfiguration):
        self.client = client
        self.configuration = configuration
        self.model_version = configuration.planner_model

    def plan(self, request: ProviderDraftInput, *, timeout: float) -> ProviderPlanDraft:
        response = self.client.responses.parse(**self._request_arguments(request, timeout))
        return _parsed(response, ProviderPlanDraft)

    def _request_arguments(self, request: ProviderDraftInput, timeout: float) -> dict[str, Any]:
        return dict(
            model=self.model_version,
            instructions=_DRAFT_INSTRUCTIONS,
            input=canonical_json_bytes(request).decode("ascii"),
            text_format=ProviderPlanDraft,
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
        # Groq synthesis remains experimental; no evidence is sent to it in this mode.
        synthesizer=None,
    )

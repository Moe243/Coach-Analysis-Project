"""Groq Responses API adapter for optional Ask v2 interpretation."""

from __future__ import annotations

from typing import Any

from .contracts import (
    STAGE_D_IMPLEMENTATION_VERSION,
    ProviderPlannerInput,
    ProviderSynthesisInput,
)
from .openai_provider import OpenAIPlanner, OpenAISynthesizer
from .providers import ProviderConfiguration, ProviderRuntime

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_PLANNER_REASONING_EFFORT = "low"
GROQ_SYNTHESIZER_REASONING_EFFORT = "low"
GROQ_PROVIDER_IMPLEMENTATION_VERSION = (
    STAGE_D_IMPLEMENTATION_VERSION + "/groq-responses-openai-sdk-3.14"
)


class GroqPlanner(OpenAIPlanner):
    """Use Groq strict Structured Outputs through the existing Responses seam."""

    implementation_version = GROQ_PROVIDER_IMPLEMENTATION_VERSION

    def _request_arguments(self, request: ProviderPlannerInput, timeout: float) -> dict[str, Any]:
        arguments = super()._request_arguments(request, timeout)
        arguments["reasoning"] = {"effort": GROQ_PLANNER_REASONING_EFFORT}
        return arguments


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
        synthesizer=GroqSynthesizer(client, configuration),
    )

"""Ask v2 staged service entry points."""

from __future__ import annotations

from .contracts import AskV2Request, AskV2Response, stage_a_versions
from .enums import Answerability, AnswerMode, ReasonCode
from .evidence import EvidenceService
from .orchestration import AskV2Orchestrator
from .provider_orchestration import ProviderOrchestrator
from .provider_telemetry import ProviderPhase, provider_event
from .providers import (
    ProviderConfiguration,
    ProviderFailureCategory,
    ProviderName,
    ProviderRuntime,
    classify_provider_failure,
)


def stage_a_response(_request: AskV2Request) -> AskV2Response:
    return AskV2Response(
        answerability=Answerability.NOT_SUPPORTED,
        answer_mode=AnswerMode.DETERMINISTIC,
        reason_code=ReasonCode.IMPLEMENTATION_NOT_AVAILABLE_YET,
        answer=(
            "Ask v2 analytical execution is not yet enabled in this staged implementation. "
            "No analytical evidence or model result has been produced."
        ),
        versions=stage_a_versions(),
    )


def stage_c_response(request: AskV2Request, evidence: EvidenceService) -> AskV2Response:
    return AskV2Orchestrator(evidence).answer(request)


def provider_runtime() -> ProviderRuntime:
    configuration = ProviderConfiguration.from_environment()
    if not configuration.ready:
        provider_event(configuration, phase=ProviderPhase.READINESS, runtime_ready=False)
        return ProviderRuntime(
            configuration=configuration,
            initialization_failure=ProviderFailureCategory.CONFIGURATION_DISABLED,
        )
    try:
        if configuration.provider is ProviderName.GROQ:
            from .groq_provider import groq_runtime

            runtime = groq_runtime(configuration)
            provider_event(
                configuration, phase=ProviderPhase.READINESS, runtime_ready=runtime.ready
            )
            return runtime
        if configuration.provider is ProviderName.OPENAI:
            from .openai_provider import openai_runtime

            runtime = openai_runtime(configuration)
            provider_event(
                configuration, phase=ProviderPhase.READINESS, runtime_ready=runtime.ready
            )
            return runtime
        return ProviderRuntime(configuration=configuration)
    except Exception as error:
        # SDK import/client construction failures must not break deterministic Ask v2.
        provider_event(
            configuration,
            phase=ProviderPhase.INITIALIZATION,
            category=classify_provider_failure(error),
            error=error,
            runtime_ready=False,
        )
        return ProviderRuntime(
            configuration=configuration,
            initialization_failure=ProviderFailureCategory.PROVIDER_UNAVAILABLE,
        )


def stage_d_response(
    request: AskV2Request,
    evidence: EvidenceService,
    runtime: ProviderRuntime,
) -> AskV2Response:
    return ProviderOrchestrator(evidence, runtime).answer(request)

"""Optional provider orchestration around the authoritative Stage C engine."""

from __future__ import annotations

import time
from threading import BoundedSemaphore
from typing import Any

from pydantic import ValidationError

from .contracts import AskV2Request, AskV2Response, PlannerProposal
from .enums import AnswerMode
from .evidence import EvidenceService
from .grounding import (
    GroundingRejected,
    provider_synthesis_input,
    render_grounded_response,
    validate_synthesis,
)
from .orchestration import AskV2Orchestrator
from .provider_drafts import ProviderDraftTranslator
from .provider_telemetry import ProviderAttempt, ProviderPhase, finish_attempt, provider_event
from .providers import (
    MAX_PROVIDER_PAYLOAD_BYTES,
    ProviderConcurrencyLimit,
    ProviderFailureCategory,
    ProviderPayloadTooLarge,
    ProviderRuntime,
    classify_provider_failure,
)
from .serialization import canonical_json_bytes

_PROVIDER_CALL_SLOTS = BoundedSemaphore(value=4)


class ProviderOrchestrator:
    """Use at most one planner and one synthesizer call, with clean fallback."""

    def __init__(self, evidence: EvidenceService, runtime: ProviderRuntime):
        self.authoritative = AskV2Orchestrator(evidence)
        self.runtime = runtime

    def answer(self, request: AskV2Request) -> AskV2Response:
        fallback = self.authoritative.analyze(request)
        if not self.runtime.ready:
            # Runtime creation owns the one readiness/initialization event.
            return fallback.response
        planner = self.runtime.planner
        synthesizer = self.runtime.synthesizer
        assert planner is not None

        started = time.monotonic()
        attempt = ProviderAttempt()
        phase = ProviderPhase.PAYLOAD
        try:
            translator = ProviderDraftTranslator(self.authoritative.planner)
            planner_input = (
                translator.provider_input(request)
                if self.runtime.configuration.planner_only
                else self.authoritative.planner.provider_input(request)
            )
            if len(canonical_json_bytes(planner_input)) > MAX_PROVIDER_PAYLOAD_BYTES:
                raise ProviderPayloadTooLarge("provider planner payload exceeds 48 KiB")
            phase = ProviderPhase.REQUEST
            raw_plan = self._provider_call(
                planner.plan,
                planner_input,
                timeout=self.runtime.configuration.planner_timeout_seconds,
                attempt=attempt,
            )
            phase = ProviderPhase.DRAFT_TRANSLATION
            if self.runtime.configuration.planner_only:
                provider_plan = translator.translate(request, raw_plan)
            else:
                proposal = PlannerProposal.model_validate(raw_plan)
                provider_plan = self.authoritative.planner.from_provider(request, proposal)
            phase = ProviderPhase.AUTHORIZATION
            result = self.authoritative.analyze(request, provider_plan)
            if result.package.rejected_tasks:
                raise ValueError("provider plan did not pass backend task authorization")
            if not result.conclusions.propositions:
                raise ValueError("provider plan produced no grounded analytical propositions")
        except Exception as error:
            self._log_fallback("planner", classify_provider_failure(error), attempt, phase, error)
            return fallback.response

        elapsed = time.monotonic() - started
        remaining = self.runtime.configuration.total_timeout_seconds - elapsed
        if remaining <= 0:
            self._log_fallback("planner", ProviderFailureCategory.TIMEOUT, attempt, phase)
            return fallback.response
        if self.runtime.configuration.planner_only:
            # Stage C already rendered this answer, including all qualifications and
            # backend-owned numbers. No provider synthesis or evidence sharing occurs.
            versions = result.response.versions.model_copy(
                update={
                    "planner_implementation_version": planner.implementation_version,
                    "planner_model_version": planner.model_version,
                    "answer_mode": AnswerMode.GROUNDED_AI,
                }
            )
            response = AskV2Response.model_validate(
                {
                    **result.response.model_dump(mode="python"),
                    "answer_mode": AnswerMode.GROUNDED_AI,
                    "versions": versions,
                }
            )
            provider_event(
                self.runtime.configuration,
                phase=ProviderPhase.COMPLETED,
                attempted=attempt.attempted,
                success=True,
                latency_ms=attempt.latency_ms,
            )
            return response
        assert synthesizer is not None
        # Log the successful planner separately; synthesis has its own attempt/timer.
        provider_event(
            self.runtime.configuration,
            phase=ProviderPhase.COMPLETED,
            attempted=attempt.attempted,
            success=True,
            latency_ms=attempt.latency_ms,
        )
        attempt = ProviderAttempt()
        phase = ProviderPhase.PAYLOAD
        try:
            payload = provider_synthesis_input(request.question, result)
            phase = ProviderPhase.REQUEST
            raw_synthesis = self._provider_call(
                synthesizer.synthesize,
                payload,
                timeout=min(
                    remaining,
                    self.runtime.configuration.synthesizer_timeout_seconds,
                ),
                attempt=attempt,
                component="synthesizer",
            )
            phase = ProviderPhase.SYNTHESIS_VALIDATION
            proposal = validate_synthesis(raw_synthesis, payload)
            response = render_grounded_response(
                result,
                payload,
                proposal,
                planner_implementation_version=planner.implementation_version,
                planner_model_version=planner.model_version,
                synthesizer_implementation_version=synthesizer.implementation_version,
                synthesizer_model_version=synthesizer.model_version,
            )
        except (GroundingRejected, ValidationError) as error:
            self._log_fallback(
                "synthesizer", ProviderFailureCategory.GROUNDING_REJECTED, attempt, phase, error
            )
            return fallback.response
        except Exception as error:
            self._log_fallback(
                "synthesizer", classify_provider_failure(error), attempt, phase, error
            )
            return fallback.response
        provider_event(
            self.runtime.configuration,
            component="synthesizer",
            phase=ProviderPhase.COMPLETED,
            attempted=attempt.attempted,
            success=True,
            latency_ms=attempt.latency_ms,
        )
        return response

    def _provider_call(
        self,
        call,
        payload,
        *,
        timeout: float,
        attempt: ProviderAttempt | None = None,
        component: str = "planner",
    ) -> Any:
        if not _PROVIDER_CALL_SLOTS.acquire(blocking=False):
            raise ProviderConcurrencyLimit("provider concurrency limit reached")
        if attempt is not None:
            attempt.attempted = True
        try:
            provider_event(
                self.runtime.configuration,
                component=component,
                phase=ProviderPhase.REQUEST,
                attempted=True,
            )
            started = time.monotonic()
            try:
                return call(payload, timeout=timeout)
            finally:
                if attempt is not None:
                    finish_attempt(attempt, started)
        finally:
            _PROVIDER_CALL_SLOTS.release()

    def _log_fallback(
        self,
        component: str,
        category: ProviderFailureCategory,
        attempt: ProviderAttempt,
        phase: ProviderPhase,
        error: BaseException | None = None,
    ) -> None:
        if (
            phase
            in {
                ProviderPhase.DRAFT_TRANSLATION,
                ProviderPhase.AUTHORIZATION,
                ProviderPhase.SYNTHESIS_VALIDATION,
            }
            and category is ProviderFailureCategory.PROVIDER_UNAVAILABLE
        ):
            category = ProviderFailureCategory.GROUNDING_REJECTED
        provider_event(
            self.runtime.configuration,
            component=component,
            phase=phase,
            attempted=attempt.attempted,
            category=category,
            error=error,
            latency_ms=attempt.latency_ms,
        )

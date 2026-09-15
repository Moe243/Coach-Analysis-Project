"""Optional provider orchestration around the authoritative Stage C engine."""

from __future__ import annotations

import logging
import time
from threading import BoundedSemaphore
from typing import Any

from pydantic import ValidationError

from .contracts import AskV2Request, AskV2Response, PlannerProposal
from .evidence import EvidenceService
from .grounding import (
    GroundingRejected,
    provider_synthesis_input,
    render_grounded_response,
    validate_synthesis,
)
from .orchestration import AskV2Orchestrator
from .providers import (
    MAX_PROVIDER_PAYLOAD_BYTES,
    ProviderError,
    ProviderFailureCategory,
    ProviderPayloadTooLarge,
    ProviderRuntime,
    classify_provider_failure,
)
from .serialization import canonical_json_bytes

logger = logging.getLogger(__name__)
_PROVIDER_CALL_SLOTS = BoundedSemaphore(value=4)


class ProviderOrchestrator:
    """Use at most one planner and one synthesizer call, with clean fallback."""

    def __init__(self, evidence: EvidenceService, runtime: ProviderRuntime):
        self.authoritative = AskV2Orchestrator(evidence)
        self.runtime = runtime

    def answer(self, request: AskV2Request) -> AskV2Response:
        fallback = self.authoritative.analyze(request)
        if not self.runtime.ready:
            return fallback.response
        planner = self.runtime.planner
        synthesizer = self.runtime.synthesizer
        assert planner is not None and synthesizer is not None

        started = time.monotonic()
        try:
            planner_input = self.authoritative.planner.provider_input(request)
            if len(canonical_json_bytes(planner_input)) > MAX_PROVIDER_PAYLOAD_BYTES:
                raise ProviderPayloadTooLarge("provider planner payload exceeds 48 KiB")
            raw_plan = self._provider_call(
                planner.plan,
                planner_input,
                timeout=self.runtime.configuration.planner_timeout_seconds,
            )
            proposal = PlannerProposal.model_validate(raw_plan)
            provider_plan = self.authoritative.planner.from_provider(request, proposal)
            result = self.authoritative.analyze(request, provider_plan)
            if result.package.rejected_tasks:
                raise ValueError("provider plan did not pass backend task authorization")
            if not result.conclusions.propositions:
                raise ValueError("provider plan produced no grounded analytical propositions")
        except Exception as error:
            self._log_fallback("planner", classify_provider_failure(error), started)
            return fallback.response

        elapsed = time.monotonic() - started
        remaining = self.runtime.configuration.total_timeout_seconds - elapsed
        if remaining <= 0:
            self._log_fallback("planner", ProviderFailureCategory.TIMEOUT, started)
            return fallback.response
        try:
            payload = provider_synthesis_input(request.question, result)
            raw_synthesis = self._provider_call(
                synthesizer.synthesize,
                payload,
                timeout=min(
                    remaining,
                    self.runtime.configuration.synthesizer_timeout_seconds,
                ),
            )
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
        except (GroundingRejected, ValidationError):
            self._log_fallback("synthesizer", ProviderFailureCategory.GROUNDING_REJECTED, started)
            return fallback.response
        except Exception as error:
            self._log_fallback("synthesizer", classify_provider_failure(error), started)
            return fallback.response
        logger.info(
            "ask_v2_provider_success",
            extra={
                "provider_attempted": True,
                "planner_model": planner.model_version,
                "synthesizer_model": synthesizer.model_version,
                "task_count": len(result.package.approved_tasks),
                "proposition_count": len(result.conclusions.propositions),
                "provider_latency_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return response

    @staticmethod
    def _provider_call(call, payload, *, timeout: float) -> Any:
        if not _PROVIDER_CALL_SLOTS.acquire(blocking=False):
            raise ProviderError("provider concurrency limit reached")
        try:
            return call(payload, timeout=timeout)
        finally:
            _PROVIDER_CALL_SLOTS.release()

    @staticmethod
    def _log_fallback(
        component: str,
        category: ProviderFailureCategory,
        started: float,
    ) -> None:
        logger.info(
            "ask_v2_provider_fallback",
            extra={
                "provider_attempted": True,
                "provider_component": component,
                "fallback_category": category.value,
                "provider_latency_ms": round((time.monotonic() - started) * 1000),
            },
        )

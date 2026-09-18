"""Closed, content-free provider events with a dedicated server-log handler."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from .provider_diagnostics import safe_provider_error_details
from .providers import (
    PlannerValidationCategory,
    ProviderConfiguration,
    ProviderFailureCategory,
    ProviderName,
    WriterValidationCategory,
)


class ProviderPhase(StrEnum):
    READINESS = "readiness"
    INITIALIZATION = "initialization"
    PAYLOAD = "payload"
    REQUEST = "request"
    DRAFT_TRANSLATION = "draft_translation"
    AUTHORIZATION = "authorization"
    SYNTHESIS_VALIDATION = "synthesis_validation"
    WRITER_VALIDATION = "writer_validation"
    COMPLETED = "completed"


@dataclass
class ProviderAttempt:
    attempted: bool = False
    latency_ms: int | None = None


_LOCK = Lock()
_LOGGER_NAME = "nfl_coaching_impact.ask_provider_telemetry"
_MAX_LATENCY_MS = 86_400_000


class _SafeStreamHandler(logging.StreamHandler):
    def handleError(self, _record: logging.LogRecord) -> None:
        # Standard handleError can print exception bodies, paths and call stacks.
        # A failed diagnostic sink must be silent, not another disclosure channel.
        return


def _logger() -> logging.Logger:
    # Uvicorn configures its own loggers, not the root/application INFO threshold.
    # Do not enable root or SDK debug logging (which can include request content).
    with _LOCK:
        logger = logging.getLogger(_LOGGER_NAME)
        if not logger.handlers:
            handler = _SafeStreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.disabled = False
        logger.propagate = False
        return logger


def safe_http_status(error: BaseException | None) -> int | None:
    try:
        status = getattr(error, "status_code", None)
    except Exception:
        return None
    return status if type(status) is int and 100 <= status <= 599 else None


def safe_latency_ms(value: int | None) -> int | None:
    if type(value) is not int:
        return None
    return min(_MAX_LATENCY_MS, max(0, value))


def readiness_reason(configuration: ProviderConfiguration) -> str:
    if configuration.provider is ProviderName.NONE:
        return "configuration_invalid" if not configuration.valid else "provider_disabled"
    if not configuration.api_key:
        return "missing_credentials"
    if not configuration.planner_model:
        return "missing_model"
    if not configuration.valid:
        return "configuration_invalid"
    if not configuration.enabled:
        return "provider_disabled"
    if not configuration.external_sharing_enabled:
        return "sharing_disabled"
    if not configuration.ready:
        return "provider_not_ready"
    return "ready"


def _safe_model(configuration: ProviderConfiguration, component: str) -> str | None:
    model = (
        configuration.planner_model if component == "planner" else configuration.synthesizer_model
    )
    if configuration.provider is ProviderName.GROQ:
        return model if model == "openai/gpt-oss-120b" else None
    if re.fullmatch(r"(?:gpt-[A-Za-z0-9._:-]{1,95}|o[1-9][A-Za-z0-9._:-]{0,97})", model):
        return model
    return None


def provider_event(
    configuration: ProviderConfiguration,
    *,
    phase: ProviderPhase,
    component: str = "planner",
    attempted: bool = False,
    success: bool = False,
    category: ProviderFailureCategory | None = None,
    error: BaseException | None = None,
    latency_ms: int | None = None,
    runtime_ready: bool | None = None,
    validation_outcome: WriterValidationCategory | None = None,
    planner_validation_outcome: PlannerValidationCategory | None = None,
    fallback: bool = False,
) -> None:
    """Best effort: invalid fields, formatters and sinks can never break Ask."""
    try:
        _emit_provider_event(
            configuration,
            phase=phase,
            component=component,
            attempted=attempted,
            success=success,
            category=category,
            error=error,
            latency_ms=latency_ms,
            runtime_ready=runtime_ready,
            validation_outcome=validation_outcome,
            planner_validation_outcome=planner_validation_outcome,
            fallback=fallback,
        )
    except Exception:
        # Never log the logging error or a repr of arguments that caused it.
        return


def _emit_provider_event(
    configuration: ProviderConfiguration,
    *,
    phase: ProviderPhase,
    component: str,
    attempted: bool,
    success: bool,
    category: ProviderFailureCategory | None,
    error: BaseException | None,
    latency_ms: int | None,
    runtime_ready: bool | None,
    validation_outcome: WriterValidationCategory | None,
    planner_validation_outcome: PlannerValidationCategory | None,
    fallback: bool,
) -> None:
    """No arbitrary message/extra dict, exception text, headers, or request input."""
    if component not in {"planner", "synthesizer", "writer"}:
        raise ValueError("unknown provider component")
    status = safe_http_status(error)
    payload = {
        "event": "ask_v2_provider",
        "provider": ProviderName(configuration.provider).value,
        "component": component,
        "phase": ProviderPhase(phase).value,
        "attempted": bool(attempted),
        "success": bool(success),
        "fallback_category": ProviderFailureCategory(category).value if category else None,
        "http_status": status,
        "http_status_family": f"{status // 100}xx" if status else None,
        "latency_ms": safe_latency_ms(latency_ms),
        "model": _safe_model(configuration, component),
        "validation_outcome": (
            WriterValidationCategory(validation_outcome).value
            if validation_outcome is not None
            else None
        ),
        "planner_validation_outcome": (
            PlannerValidationCategory(planner_validation_outcome).value
            if planner_validation_outcome is not None
            else None
        ),
        "fallback": bool(fallback),
    }
    if configuration.provider is ProviderName.GROQ and status in {400, 429}:
        payload.update(safe_provider_error_details(error))
    if phase in {ProviderPhase.READINESS, ProviderPhase.INITIALIZATION}:
        payload.update(
            external_sharing_enabled=bool(configuration.external_sharing_enabled),
            key_present=bool(configuration.api_key),
            planner_model_configured=bool(configuration.planner_model),
            configuration_valid=bool(configuration.valid),
            configuration_ready=bool(configuration.ready),
            readiness_reason=readiness_reason(configuration),
            runtime_ready=runtime_ready if type(runtime_ready) is bool else None,
        )
    _logger().info(json.dumps(payload, sort_keys=True, allow_nan=False))


def finish_attempt(attempt: ProviderAttempt, started: float) -> None:
    try:
        attempt.latency_ms = round((time.monotonic() - started) * 1000)
    except Exception:
        attempt.latency_ms = None

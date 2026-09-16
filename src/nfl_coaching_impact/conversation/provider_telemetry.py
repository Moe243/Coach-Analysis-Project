"""Closed, content-free provider events with a dedicated server-log handler."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from .providers import ProviderConfiguration, ProviderFailureCategory, ProviderName


class ProviderPhase(StrEnum):
    READINESS = "readiness"
    INITIALIZATION = "initialization"
    PAYLOAD = "payload"
    REQUEST = "request"
    DRAFT_TRANSLATION = "draft_translation"
    AUTHORIZATION = "authorization"
    SYNTHESIS_VALIDATION = "synthesis_validation"
    COMPLETED = "completed"


@dataclass
class ProviderAttempt:
    attempted: bool = False
    latency_ms: int | None = None


_LOCK = Lock()
_LOGGER_NAME = "nfl_coaching_impact.ask_provider_telemetry"


def _logger() -> logging.Logger:
    # Uvicorn configures its own loggers, not the root/application INFO threshold.
    # Do not enable root or SDK debug logging (which can include request content).
    with _LOCK:
        logger = logging.getLogger(_LOGGER_NAME)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.disabled = False
        logger.propagate = False
        return logger


def safe_http_status(error: BaseException | None) -> int | None:
    status = getattr(error, "status_code", None)
    return status if type(status) is int and 100 <= status <= 599 else None


def readiness_reason(configuration: ProviderConfiguration) -> str:
    if not configuration.enabled or configuration.provider is ProviderName.NONE:
        return "provider_disabled"
    if not configuration.external_sharing_enabled:
        return "sharing_disabled"
    if not configuration.api_key:
        return "missing_credentials"
    if not configuration.planner_model:
        return "missing_model"
    if not configuration.valid:
        return "configuration_invalid"
    if not configuration.ready:
        return "provider_not_ready"
    return "ready"


def _safe_model(configuration: ProviderConfiguration, component: str) -> str | None:
    model = (
        configuration.planner_model if component == "planner" else configuration.synthesizer_model
    )
    if configuration.provider is ProviderName.GROQ:
        return model if model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"} else None
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
) -> None:
    """No arbitrary message/extra dict, exception text, headers, or request input."""
    if component not in {"planner", "synthesizer"}:
        raise ValueError("unknown provider component")
    status = safe_http_status(error)
    payload = {
        "event": "ask_v2_provider",
        "provider": configuration.provider.value,
        "component": component,
        "phase": ProviderPhase(phase).value,
        "attempted": bool(attempted),
        "success": bool(success),
        "fallback_category": ProviderFailureCategory(category).value if category else None,
        "http_status": status,
        "http_status_family": f"{status // 100}xx" if status else None,
        "latency_ms": max(0, int(latency_ms)) if latency_ms is not None else None,
        "model": _safe_model(configuration, component),
    }
    if phase in {ProviderPhase.READINESS, ProviderPhase.INITIALIZATION}:
        payload.update(
            external_sharing_enabled=configuration.external_sharing_enabled,
            key_present=bool(configuration.api_key),
            planner_model_configured=bool(configuration.planner_model),
            configuration_valid=configuration.valid,
            configuration_ready=configuration.ready,
            readiness_reason=readiness_reason(configuration),
            runtime_ready=runtime_ready,
        )
    _logger().info(json.dumps(payload, sort_keys=True, allow_nan=False))


def finish_attempt(attempt: ProviderAttempt, started: float) -> None:
    attempt.latency_ms = round((time.monotonic() - started) * 1000)

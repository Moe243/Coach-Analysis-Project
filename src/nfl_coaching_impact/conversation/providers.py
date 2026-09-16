"""Injectable, opt-in provider boundaries for Ask Anything v2."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from .contracts import ProviderPlannerInput, ProviderSynthesisInput

if TYPE_CHECKING:
    from .provider_drafts import ProviderDraftInput

MAX_PROVIDER_PAYLOAD_BYTES = 48 * 1024
MAX_PROVIDER_CALLS = 2
MAX_TOTAL_PROVIDER_SECONDS = 40.0


class ProviderFailureCategory(StrEnum):
    CONFIGURATION_DISABLED = "configuration_disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    REFUSAL = "refusal"
    MALFORMED_OUTPUT = "malformed_output"
    GROUNDING_REJECTED = "grounding_rejected"
    OVERSIZED_PAYLOAD = "oversized_payload"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_ERROR = "permission_error"
    BAD_REQUEST = "provider_bad_request"
    SERVER_ERROR = "provider_server_error"
    TRANSPORT_ERROR = "transport_error"
    CONCURRENCY_LIMIT = "concurrency_limit"


class ProviderName(StrEnum):
    NONE = "none"
    OPENAI = "openai"
    GROQ = "groq"


class ProviderError(RuntimeError):
    """Base provider failure with a safe internal category."""

    category = ProviderFailureCategory.PROVIDER_UNAVAILABLE


class ProviderRefusal(ProviderError):
    category = ProviderFailureCategory.REFUSAL


class ProviderMalformedOutput(ProviderError):
    category = ProviderFailureCategory.MALFORMED_OUTPUT


class ProviderPayloadTooLarge(ProviderError):
    category = ProviderFailureCategory.OVERSIZED_PAYLOAD


class ProviderConcurrencyLimit(ProviderError):
    category = ProviderFailureCategory.CONCURRENCY_LIMIT


class PlannerProvider(Protocol):
    implementation_version: str
    model_version: str

    def plan(
        self, request: ProviderPlannerInput | ProviderDraftInput, *, timeout: float
    ) -> Any: ...


class SynthesizerProvider(Protocol):
    implementation_version: str
    model_version: str

    def synthesize(self, request: ProviderSynthesisInput, *, timeout: float) -> Any: ...


_OPENAI_MODEL_ID = re.compile(r"^(?:gpt-[A-Za-z0-9._:-]{1,95}|o[1-9][A-Za-z0-9._:-]{0,97})$")
_GROQ_STRUCTURED_OUTPUT_MODELS = frozenset({"openai/gpt-oss-120b", "openai/gpt-oss-20b"})
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})


def _flag(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    return None


def _number(
    environment: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float | None:
    raw = environment.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if minimum <= value <= maximum else None


def _integer(
    environment: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int | None:
    raw = environment.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if minimum <= value <= maximum else None


@dataclass(frozen=True, slots=True)
class ProviderConfiguration:
    enabled: bool
    external_sharing_enabled: bool
    planner_model: str
    synthesizer_model: str
    planner_timeout_seconds: float
    synthesizer_timeout_seconds: float
    total_timeout_seconds: float
    planner_max_output_tokens: int
    synthesizer_max_output_tokens: int
    api_key: str = field(repr=False)
    valid: bool = True
    provider: ProviderName = ProviderName.OPENAI

    @property
    def planner_only(self) -> bool:
        return self.provider is ProviderName.GROQ

    @property
    def ready(self) -> bool:
        return bool(
            self.valid
            and self.provider is not ProviderName.NONE
            and self.enabled
            and self.external_sharing_enabled
            and self.api_key
            and self.planner_model
            and (self.planner_only or self.synthesizer_model)
        )

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> ProviderConfiguration:
        source = os.environ if environment is None else environment
        explicit_provider = source.get("ASK_V2_PROVIDER")
        legacy_enabled = _flag(source.get("ASK_V2_OPENAI_ENABLED"))
        provider_valid = True
        if explicit_provider is not None:
            try:
                provider = ProviderName(explicit_provider.strip().lower())
            except ValueError:
                provider = ProviderName.NONE
                provider_valid = False
            enabled = provider is not ProviderName.NONE
        else:
            provider_valid = legacy_enabled is not None
            provider = ProviderName.OPENAI if legacy_enabled else ProviderName.NONE
            enabled = bool(legacy_enabled)
        sharing = _flag(source.get("ASK_V2_EXTERNAL_SHARING_ENABLED"))
        if provider is ProviderName.GROQ:
            api_key = source.get("GROQ_API_KEY", "").strip()
            planner_model = source.get("ASK_V2_GROQ_PLANNER_MODEL", "").strip()
            synthesizer_model = source.get("ASK_V2_GROQ_SYNTHESIZER_MODEL", "").strip()
        elif provider is ProviderName.OPENAI:
            api_key = source.get("OPENAI_API_KEY", "").strip()
            planner_model = source.get("ASK_V2_PLANNER_MODEL", "").strip()
            synthesizer_model = source.get("ASK_V2_SYNTHESIZER_MODEL", "").strip()
        else:
            api_key = ""
            planner_model = ""
            synthesizer_model = ""
        planner_timeout = _number(source, "ASK_V2_PLANNER_TIMEOUT_SECONDS", 12.0, 1.0, 20.0)
        synthesizer_timeout = _number(source, "ASK_V2_SYNTHESIZER_TIMEOUT_SECONDS", 18.0, 1.0, 20.0)
        total_timeout = _number(
            source, "ASK_V2_TOTAL_TIMEOUT_SECONDS", 30.0, 1.0, MAX_TOTAL_PROVIDER_SECONDS
        )
        planner_tokens = _integer(source, "ASK_V2_PLANNER_MAX_OUTPUT_TOKENS", 600, 128, 1_000)
        synthesizer_tokens = _integer(
            source, "ASK_V2_SYNTHESIZER_MAX_OUTPUT_TOKENS", 800, 128, 1_500
        )
        if provider is ProviderName.GROQ:
            models_valid = bool(planner_model in _GROQ_STRUCTURED_OUTPUT_MODELS)
            key_valid = bool(re.fullmatch(r"gsk_[A-Za-z0-9_-]{16,}", api_key))
        elif provider is ProviderName.OPENAI:
            models_valid = bool(
                _OPENAI_MODEL_ID.fullmatch(planner_model)
                and _OPENAI_MODEL_ID.fullmatch(synthesizer_model)
            )
            key_valid = bool(re.fullmatch(r"sk-[A-Za-z0-9_-]{16,}", api_key))
        else:
            models_valid = True
            key_valid = True
        numeric_values = (planner_timeout, total_timeout, planner_tokens)
        if provider is not ProviderName.GROQ:
            numeric_values += (synthesizer_timeout, synthesizer_tokens)
        numeric_valid = all(value is not None for value in numeric_values)
        valid = bool(
            provider_valid
            and (explicit_provider is not None or legacy_enabled is not None)
            and sharing is not None
            and (not enabled or key_valid)
            and (not enabled or models_valid)
            and numeric_valid
            and float(planner_timeout or 0)
            + (0 if provider is ProviderName.GROQ else float(synthesizer_timeout or 0))
            <= float(total_timeout or 0)
        )
        return cls(
            enabled=bool(enabled),
            external_sharing_enabled=bool(sharing),
            api_key=api_key,
            planner_model=planner_model,
            synthesizer_model=synthesizer_model,
            planner_timeout_seconds=float(planner_timeout or 0),
            synthesizer_timeout_seconds=float(synthesizer_timeout or 0),
            total_timeout_seconds=float(total_timeout or 0),
            planner_max_output_tokens=int(planner_tokens or 0),
            synthesizer_max_output_tokens=int(synthesizer_tokens or 0),
            valid=valid,
            provider=provider,
        )


@dataclass(frozen=True, slots=True)
class ProviderRuntime:
    configuration: ProviderConfiguration
    planner: PlannerProvider | None = None
    synthesizer: SynthesizerProvider | None = None
    initialization_failure: ProviderFailureCategory | None = None

    @property
    def ready(self) -> bool:
        return bool(
            self.configuration.ready
            and self.planner
            and (self.configuration.planner_only or self.synthesizer)
        )


def classify_provider_failure(error: BaseException) -> ProviderFailureCategory:
    if isinstance(error, ProviderError):
        return error.category
    name = type(error).__name__.lower()
    if "timeout" in name:
        return ProviderFailureCategory.TIMEOUT
    status = getattr(error, "status_code", None)
    if type(status) is int:
        if status == 401:
            return ProviderFailureCategory.AUTHENTICATION_ERROR
        if status == 403:
            return ProviderFailureCategory.PERMISSION_ERROR
        if status == 429:
            return ProviderFailureCategory.RATE_LIMIT
        if 400 <= status <= 499:
            return ProviderFailureCategory.BAD_REQUEST
        if 500 <= status <= 599:
            return ProviderFailureCategory.SERVER_ERROR
    if "connection" in name or "connecterror" in name:
        return ProviderFailureCategory.TRANSPORT_ERROR
    if "ratelimit" in name or "rate_limit" in name:
        return ProviderFailureCategory.RATE_LIMIT
    if "validation" in name or "json" in name:
        return ProviderFailureCategory.MALFORMED_OUTPUT
    return ProviderFailureCategory.PROVIDER_UNAVAILABLE

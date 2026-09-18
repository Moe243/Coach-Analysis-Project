"""Closed error classifications and local-only quota observations; never raw text."""

from __future__ import annotations

import re

_TYPES = frozenset({"invalid_request_error", "rate_limit_error", "server_error"})
_CODES = frozenset(
    {
        "json_validate_failed",
        "invalid_json_schema",
        "invalid_request_error",
        "context_length_exceeded",
        "rate_limit_exceeded",
    }
)
_PARAMETERS = frozenset(
    {
        "max_output_tokens",
        "text.format",
        "text.format.schema",
        "response_format",
        "reasoning.effort",
    }
)


def safe_provider_error_details(error: BaseException | None) -> dict[str, str | None]:
    """Unknown values are null, not sanitized arbitrary provider strings."""
    result = dict.fromkeys(("provider_error_type", "provider_error_code", "provider_parameter"))
    try:
        body = getattr(error, "body", None)
        if type(body) is not dict:
            return result
        fields = body.get("error", body)
        if type(fields) is not dict:
            return result
        for source, target, allowed in (
            ("type", "provider_error_type", _TYPES),
            ("code", "provider_error_code", _CODES),
            ("param", "provider_parameter", _PARAMETERS),
        ):
            value = fields.get(source)
            if type(value) is str and value in allowed:
                result[target] = value
    except Exception:
        pass
    return result


def _duration(value: str) -> float | None:
    if not value or len(value) > 40:
        return None
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)?", value)
    if "".join(number + unit for number, unit in parts) != value:
        return None
    factors = {"": 1, "ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}
    seconds = sum(float(number) * factors[unit] for number, unit in parts)
    return seconds if 0 <= seconds <= 86400 else None


def local_rate_limit_observations(response: object) -> dict[str, int | float]:
    """Numeric quota fields only. Not emitted by production telemetry; no retry action."""
    result: dict[str, int | float] = {}
    try:
        headers = getattr(response, "headers", {})
        for dimension in ("requests", "tokens"):
            for field in ("limit", "remaining"):
                raw = headers.get(f"x-ratelimit-{field}-{dimension}", "")
                if type(raw) is str and re.fullmatch(r"\d{1,12}", raw):
                    result[f"{dimension}_{field}"] = int(raw)
            reset = headers.get(f"x-ratelimit-reset-{dimension}", "")
            seconds = _duration(reset) if type(reset) is str else None
            if seconds is not None:
                result[f"{dimension}_reset_seconds"] = seconds
        retry_after = headers.get("retry-after", "")
        seconds = _duration(retry_after) if type(retry_after) is str else None
        if seconds is not None:
            result["retry_after_seconds"] = seconds
    except Exception:
        pass
    return result

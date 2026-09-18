"""Safe classifications reject arbitrary content; quota observations cause no retries."""

import httpx
import pytest

from nfl_coaching_impact.conversation.provider_diagnostics import (
    local_rate_limit_observations,
    safe_provider_error_details,
)


def test_known_error_fields_are_allowlisted_without_message_or_failed_generation():
    error = RuntimeError("SECRET raw exception")
    error.body = {
        "error": {
            "type": "invalid_request_error",
            "code": "json_validate_failed",
            "param": "max_output_tokens",
            "message": "SECRET prompt question",
            "failed_generation": "SECRET answer evidence",
            "headers": "SECRET key",
        }
    }
    assert safe_provider_error_details(error) == {
        "provider_error_type": "invalid_request_error",
        "provider_error_code": "json_validate_failed",
        "provider_parameter": "max_output_tokens",
    }


@pytest.mark.parametrize("value", ["SECRET_credential", "prompt", [], {}, None, 123])
def test_unknown_error_fields_fail_closed(value):
    error = RuntimeError("SECRET")
    error.body = {"type": value, "code": value, "param": value}
    assert all(value is None for value in safe_provider_error_details(error).values())


def test_hostile_error_property_cannot_break_diagnostics():
    class Hostile(RuntimeError):
        @property
        def body(self):
            raise RuntimeError("SECRET")

    assert all(value is None for value in safe_provider_error_details(Hostile()).values())


def test_only_numeric_quota_metadata_is_observed():
    response = httpx.Response(
        429,
        headers={
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "998",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "0",
            "x-ratelimit-reset-tokens": "1m2.5s",
            "retry-after": "63",
            "authorization": "SECRET",
            "x-request-id": "SECRET",
        },
    )
    assert local_rate_limit_observations(response) == {
        "requests_limit": 1000,
        "requests_remaining": 998,
        "tokens_limit": 8000,
        "tokens_remaining": 0,
        "tokens_reset_seconds": 62.5,
        "retry_after_seconds": 63.0,
    }


@pytest.mark.parametrize(
    "raw", ["SECRET", "NaN", "Infinity", "-1", "9999999999999999", "1mSECRET", "86401s"]
)
def test_invalid_quota_metadata_is_not_retained(raw):
    response = httpx.Response(
        429,
        headers={
            "retry-after": raw,
            "x-ratelimit-reset-tokens": raw,
            "x-ratelimit-limit-tokens": raw,
        },
    )
    assert local_rate_limit_observations(response) == {}

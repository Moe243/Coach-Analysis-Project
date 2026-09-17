"""Offline readiness, wire construction, and content-free event regression tests."""

from __future__ import annotations

import io
import json
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import BadRequestError, OpenAI

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.api import app
from nfl_coaching_impact.ask_api import _load
from nfl_coaching_impact.conversation import provider_telemetry as telemetry
from nfl_coaching_impact.conversation.answer_writer import WriterResult, WriterSentence
from nfl_coaching_impact.conversation.api import _cached_evidence
from nfl_coaching_impact.conversation.contracts import AskV2Request
from nfl_coaching_impact.conversation.evidence import EvidenceService
from nfl_coaching_impact.conversation.groq_provider import GroqPlanner
from nfl_coaching_impact.conversation.orchestration import AskV2Orchestrator
from nfl_coaching_impact.conversation.provider_drafts import (
    DraftEntityResolutionRejected,
    DraftTaskTranslationRejected,
    FollowupKind,
    ProviderDraftInput,
    ProviderDraftTranslator,
    ProviderEntityMention,
    ProviderPlanDraft,
    RequestedCapability,
)
from nfl_coaching_impact.conversation.provider_orchestration import ProviderOrchestrator
from nfl_coaching_impact.conversation.providers import (
    ProviderConfiguration,
    ProviderFailureCategory,
    ProviderMalformedOutput,
    ProviderRuntime,
    classify_provider_failure,
)
from nfl_coaching_impact.conversation.service import provider_runtime

ROOT = Path(__file__).resolve().parents[1]


def environment(**overrides):
    return {
        "ASK_V2_PROVIDER": "groq",
        "ASK_V2_EXTERNAL_SHARING_ENABLED": "true",
        "GROQ_API_KEY": "gsk_" + "0" * 32,
        "ASK_V2_GROQ_PLANNER_MODEL": "openai/gpt-oss-120b",
        "ASK_V2_PLANNER_TIMEOUT_SECONDS": "12",
        "ASK_V2_TOTAL_TIMEOUT_SECONDS": "30",
        "ASK_V2_PLANNER_MAX_OUTPUT_TOKENS": "600",
        **overrides,
    }


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*_args, **_kwargs):
        raise AssertionError("telemetry tests must never use the network")

    monkeypatch.setattr(socket, "create_connection", reject)


@pytest.fixture
def events(monkeypatch):
    stream = io.StringIO()
    logger = logging.Logger("offline_provider_events", level=logging.INFO)
    logger.addHandler(logging.StreamHandler(stream))
    monkeypatch.setattr(telemetry, "_logger", lambda: logger)
    return lambda: [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.fixture(scope="module")
def evidence():
    return EvidenceService(release.validate(ROOT / "data/processed/ask_anything" / release.VERSION))


class Planner:
    implementation_version = "offline-planner"
    model_version = "openai/gpt-oss-120b"

    def __init__(self, error=None, mention="Josh Allen"):
        self.calls = 0
        self.error = error
        self.mention = mention

    def plan(self, _request, *, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return ProviderPlanDraft(
            question_type="QB_HISTORY",
            entity_mentions=(ProviderEntityMention(text=self.mention, kind_hint="qb"),),
            season_mentions=(2022,),
            requested_capabilities=(RequestedCapability.QB_HISTORY,),
            comparison_requested=False,
            followup_kind=FollowupKind.NONE,
        )


class Writer:
    implementation_version = "offline-writer"
    model_version = "openai/gpt-oss-120b"

    def write(self, brief, *, timeout):
        support = brief.supports[0]
        limitations = tuple(
            s for s in brief.supports if s.support_id in brief.required_limitation_ids
        )

        def sentence(supports):
            return WriterSentence(
                text=" ".join(s.text for s in supports),
                support_ids=tuple(s.support_id for s in supports),
                entity_ids=tuple(dict.fromkeys(e for s in supports for e in s.entity_ids)),
                measurement_ids=tuple(
                    m.measurement_id
                    for m in brief.measurements
                    if m.support_id in {s.support_id for s in supports}
                ),
            )

        main = sentence((support,))
        limitation = sentence(limitations) if limitations else None
        parts = (main, *((limitation,) if limitation else ()))
        return WriterResult(
            sentences=(main,),
            limitation=limitation,
            used_support_ids=tuple(s for part in parts for s in part.support_ids),
            used_measurement_ids=tuple(m for part in parts for m in part.measurement_ids),
        )


def ask(evidence, planner, **overrides):
    config = ProviderConfiguration.from_environment(environment(**overrides))
    orchestrator = ProviderOrchestrator(
        evidence, ProviderRuntime(config, planner=planner, writer=Writer())
    )
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    return orchestrator, request


@pytest.mark.parametrize("value", ["true", " TRUE ", "yes", "ON", "1"])
def test_groq_readiness_reuses_same_model_for_writer(value):
    config = ProviderConfiguration.from_environment(
        environment(ASK_V2_PROVIDER=" GROQ ", ASK_V2_EXTERNAL_SHARING_ENABLED=value)
    )
    assert config.ready and config.synthesizer_model == config.planner_model


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"ASK_V2_EXTERNAL_SHARING_ENABLED": "false"}, "sharing_disabled"),
        ({"GROQ_API_KEY": ""}, "missing_credentials"),
        ({"GROQ_API_KEY": "not-a-valid-key"}, "configuration_invalid"),
        ({"ASK_V2_GROQ_PLANNER_MODEL": ""}, "missing_model"),
        ({"ASK_V2_GROQ_PLANNER_MODEL": "unsupported"}, "configuration_invalid"),
        ({"ASK_V2_PROVIDER": "invalid"}, "configuration_invalid"),
        ({"ASK_V2_PLANNER_TIMEOUT_SECONDS": "31"}, "configuration_invalid"),
    ],
)
def test_not_ready_events_do_not_attempt_client_creation(monkeypatch, events, overrides, reason):
    monkeypatch.setattr(os, "environ", environment(**overrides))
    monkeypatch.setattr(
        "nfl_coaching_impact.conversation.groq_provider.groq_runtime",
        lambda *_: pytest.fail("disabled configuration must not construct the provider"),
    )
    assert not provider_runtime().ready
    event = events()[-1]
    assert event["readiness_reason"] == reason
    assert event["attempted"] is False and event["runtime_ready"] is False


def test_initialization_exception_logs_only_safe_category(monkeypatch, events):
    monkeypatch.setattr(os, "environ", environment())

    def fail(_):
        raise RuntimeError("SECRET_KEY user question Authorization: evidence")

    monkeypatch.setattr("nfl_coaching_impact.conversation.groq_provider.groq_runtime", fail)
    assert not provider_runtime().ready
    event = events()[-1]
    assert event["phase"] == "initialization" and event["attempted"] is False
    assert event["fallback_category"] == "provider_unavailable"
    assert "SECRET_KEY" not in json.dumps(events())


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (400, "provider_bad_request"),
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "provider_bad_request"),
        (429, "rate_limit"),
        (500, "provider_server_error"),
        (503, "provider_server_error"),
    ],
)
def test_http_failure_status_and_content_free_fallback(evidence, events, status, category):
    error = RuntimeError("SECRET_KEY prompt prior questions structured output evidence")
    error.status_code = status
    planner = Planner(error)
    orchestrator, request = ask(evidence, planner)
    assert orchestrator.answer(request) == AskV2Orchestrator(evidence).answer(request)
    event = events()[-1]
    assert planner.calls == 1 and event["attempted"] is True
    assert event["http_status"] == status and event["http_status_family"] == f"{status // 100}xx"
    assert event["fallback_category"] == category and event["phase"] == "request"
    assert event["latency_ms"] >= 0
    serialized = json.dumps(events())
    for forbidden in ("SECRET_KEY", "prompt", "prior questions", "structured output", "evidence"):
        assert forbidden not in serialized


@pytest.mark.parametrize("status", [True, "401 SECRET_KEY", 99, 600, None])
def test_invalid_http_status_is_not_serialized(events, status):
    error = RuntimeError("SECRET_KEY")
    error.status_code = status
    telemetry.provider_event(
        ProviderConfiguration.from_environment(environment()),
        phase=telemetry.ProviderPhase.REQUEST,
        error=error,
    )
    assert events()[-1]["http_status"] is None
    assert "SECRET_KEY" not in json.dumps(events())


def test_parse_failure_is_distinct_from_semantic_rejection(evidence, events):
    orchestrator, request = ask(evidence, Planner(ProviderMalformedOutput("SECRET_KEY")))
    orchestrator.answer(request)
    assert events()[-1]["fallback_category"] == "malformed_output"
    assert events()[-1]["phase"] == "request"
    orchestrator, request = ask(evidence, Planner(mention="Patrick Mahomes"))
    assert orchestrator.answer(request) == AskV2Orchestrator(evidence).answer(request)
    assert events()[-1]["fallback_category"] == "grounding_rejected"
    assert events()[-1]["phase"] == "draft_translation"


def test_disabled_and_saturated_attempts_are_false(evidence, events, monkeypatch):
    planner = Planner()
    monkeypatch.setattr(os, "environ", environment(ASK_V2_EXTERNAL_SHARING_ENABLED="false"))
    disabled = provider_runtime()
    orchestrator = ProviderOrchestrator(evidence, disabled)
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    assert orchestrator.answer(request).answer_mode == "deterministic"
    assert planner.calls == 0 and events()[-1]["attempted"] is False
    orchestrator, request = ask(evidence, planner)
    monkeypatch.setattr(
        "nfl_coaching_impact.conversation.provider_orchestration._PROVIDER_CALL_SLOTS",
        type("Saturated", (), {"acquire": lambda *_args, **_kwargs: False})(),
    )
    orchestrator.answer(request)
    assert planner.calls == 0 and events()[-1]["attempted"] is False
    assert events()[-1]["fallback_category"] == "concurrency_limit"


def test_success_records_attempt_without_request_content(evidence, events):
    orchestrator, request = ask(evidence, Planner())
    assert orchestrator.answer(request).answer_mode == "grounded_ai"
    assert events()[-1]["success"] is True and events()[-1]["attempted"] is True
    assert events()[-1]["model"] == "openai/gpt-oss-120b"
    assert "Josh Allen" not in json.dumps(events())
    assert "2022" not in json.dumps(events())


def test_unknown_model_and_extra_telemetry_fields_cannot_leak(events):
    config = ProviderConfiguration.from_environment(environment(ASK_V2_GROQ_PLANNER_MODEL="SECRET"))
    telemetry.provider_event(config, phase=telemetry.ProviderPhase.READINESS)
    assert events()[-1]["model"] is None
    with pytest.raises(TypeError):
        telemetry.provider_event(config, phase=telemetry.ProviderPhase.READINESS, question="SECRET")
    before = len(events())
    telemetry.provider_event(config, phase="SECRET")
    telemetry.provider_event(config, phase=telemetry.ProviderPhase.REQUEST, component="SECRET")
    assert len(events()) == before  # Invalid fields are dropped, never propagated.
    assert "SECRET" not in json.dumps(events())


def test_info_events_visible_under_production_uvicorn_configuration():
    script = """
import logging, logging.config
from uvicorn.config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)
logging.getLogger().setLevel(logging.WARNING)
from nfl_coaching_impact.conversation.provider_telemetry import provider_event, ProviderPhase
from nfl_coaching_impact.conversation.providers import ProviderConfiguration
c = ProviderConfiguration.from_environment({
    'ASK_V2_PROVIDER':'groq', 'ASK_V2_EXTERNAL_SHARING_ENABLED':'false',
    'GROQ_API_KEY':'gsk_' + '0' * 32,
    'ASK_V2_GROQ_PLANNER_MODEL':'openai/gpt-oss-120b'
})
provider_event(c, phase=ProviderPhase.READINESS, runtime_ready=False)
assert logging.getLogger().level == logging.WARNING
assert logging.getLogger('openai').getEffectiveLevel() == logging.WARNING
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=True,
    )
    event = json.loads(result.stderr)
    assert event["readiness_reason"] == "sharing_disabled" and event["attempted"] is False


def test_sdk_exact_wire_parameters_and_strict_schema_are_captured_offline():
    captured = []

    def offline(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/responses"
        captured.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "offline fixture"}})

    config = ProviderConfiguration.from_environment(environment())
    with OpenAI(
        api_key=config.api_key,
        base_url="https://api.groq.com/openai/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(offline)),
    ) as client:
        with pytest.raises(BadRequestError):
            GroqPlanner(client, config).plan(
                ProviderDraftInput(
                    question="Synthetic offline request",
                    prior_user_questions=(),
                    context_mentions=(),
                    context_seasons=(),
                ),
                timeout=12,
            )
    assert len(captured) == 1
    body = captured[0]
    assert body["store"] is False  # SDK does NOT omit this parameter on the wire.
    assert body["background"] is False and body["stream"] is False
    assert body["tools"] == [] and body["tool_choice"] == "none"
    assert body["parallel_tool_calls"] is False
    assert body["reasoning"] == {"effort": "medium"}
    assert body["max_output_tokens"] == 600
    assert set(body).isdisjoint(
        {
            "previous_response_id",
            "truncation",
            "include",
            "safety_identifier",
            "prompt_cache_key",
            "prompt",
            "timeout",
            "text_format",
        }
    )
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True

    def check_schema(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check_schema(value)
        elif isinstance(node, list):
            for value in node:
                check_schema(value)

    check_schema(fmt["schema"])


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (TimeoutError(), ProviderFailureCategory.TIMEOUT),
        (ConnectionError(), ProviderFailureCategory.TRANSPORT_ERROR),
    ],
)
def test_transport_and_timeout_categories(error, category):
    assert classify_provider_failure(error) is category


@pytest.mark.parametrize("scenario", ["disabled", "initialization", "failure", "success"])
def test_logging_failure_never_changes_api_response(evidence, monkeypatch, scenario):
    config_environment = environment()
    if scenario == "disabled":
        config_environment["ASK_V2_EXTERNAL_SHARING_ENABLED"] = "false"
    monkeypatch.setattr(os, "environ", config_environment)
    monkeypatch.setenv("ASK_DATA_DIR", str(ROOT / "data/processed/ask_anything" / release.VERSION))
    planner = Planner(
        error=RuntimeError("private provider body") if scenario == "failure" else None
    )

    def build(config):
        if scenario == "initialization":
            raise RuntimeError("private initialization error")
        return ProviderRuntime(config, planner=planner, writer=Writer())

    monkeypatch.setattr("nfl_coaching_impact.conversation.groq_provider.groq_runtime", build)
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = (
        ProviderOrchestrator(evidence, provider_runtime()).answer(request).model_dump(mode="json")
    )

    def broken_logger():
        raise OSError("private sink failure")

    monkeypatch.setattr(telemetry, "_logger", broken_logger)
    _load.cache_clear()
    _cached_evidence.cache_clear()
    try:
        response = TestClient(app).post("/ask/v2", json=request.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json() == expected
    finally:
        _load.cache_clear()
        _cached_evidence.cache_clear()


@pytest.mark.parametrize("phase", ["readiness", "completed"])
def test_formatter_and_sink_errors_are_silent(events, monkeypatch, capsys, phase):
    class BrokenStream:
        def write(self, _text):
            raise OSError("PRIVATE_ERROR and local path must not escape")

    class BrokenFormatter(logging.Formatter):
        def format(self, _record):
            raise RuntimeError("PRIVATE_FORMATTER_ERROR")

    logger = logging.Logger("safe_broken_sink", level=logging.INFO)
    handler = telemetry._SafeStreamHandler(BrokenStream())
    logger.addHandler(handler)
    monkeypatch.setattr(telemetry, "_logger", lambda: logger)
    config = ProviderConfiguration.from_environment(environment())
    telemetry.provider_event(config, phase=telemetry.ProviderPhase(phase))
    handler.setFormatter(BrokenFormatter())
    telemetry.provider_event(config, phase=telemetry.ProviderPhase(phase))
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("field,value", [("category", "PRIVATE"), ("component", "PRIVATE")])
def test_malformed_enum_telemetry_drops_event_without_throwing(events, field, value):
    config = ProviderConfiguration.from_environment(environment())
    telemetry.provider_event(config, phase=telemetry.ProviderPhase.REQUEST, **{field: value})
    assert events() == []
    telemetry.provider_event(config, phase="PRIVATE")
    assert events() == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [(float("nan"), None), ("PRIVATE", None), (True, None), (-10, 0), (10**100, 86_400_000)],
)
def test_latency_is_numeric_and_bounded(events, value, expected):
    config = ProviderConfiguration.from_environment(environment())
    telemetry.provider_event(config, phase=telemetry.ProviderPhase.REQUEST, latency_ms=value)
    assert events()[-1]["latency_ms"] == expected


def test_missing_or_broken_status_degrades_without_exception_text(events):
    class BrokenStatus(RuntimeError):
        @property
        def status_code(self):
            raise RuntimeError("PRIVATE_STATUS_ERROR")

    error = BrokenStatus("PRIVATE_BODY")
    assert classify_provider_failure(error) is ProviderFailureCategory.PROVIDER_UNAVAILABLE
    config = ProviderConfiguration.from_environment(environment())
    telemetry.provider_event(config, phase=telemetry.ProviderPhase.REQUEST, error=error)
    assert events()[-1]["http_status"] is None
    assert "PRIVATE" not in json.dumps(events())


def test_disabled_api_emits_exactly_one_readiness_event(evidence, monkeypatch, events):
    monkeypatch.setattr(os, "environ", environment(ASK_V2_EXTERNAL_SHARING_ENABLED="false"))
    monkeypatch.setenv("ASK_DATA_DIR", str(ROOT / "data/processed/ask_anything" / release.VERSION))
    _load.cache_clear()
    _cached_evidence.cache_clear()
    try:
        response = TestClient(app).post(
            "/ask/v2", json={"question": "How did Josh Allen perform in 2022?"}
        )
        assert response.status_code == 200
        assert len(events()) == 1
        assert events()[0]["readiness_reason"] == "sharing_disabled"
        assert events()[0]["attempted"] is False
    finally:
        _load.cache_clear()
        _cached_evidence.cache_clear()


def test_resolution_and_task_translation_have_distinct_bounded_categories(
    evidence, events, monkeypatch
):
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    translator = ProviderDraftTranslator(AskV2Orchestrator(evidence).planner)
    with pytest.raises(DraftEntityResolutionRejected):
        translator._literal_entity(ProviderEntityMention(text="Unknown Person", kind_hint="qb"))
    monkeypatch.setattr(translator.planner, "_tasks", lambda *_: ())
    with pytest.raises(DraftTaskTranslationRejected):
        translator.translate(request, Planner().plan(None, timeout=12))
    for error, category in [
        (DraftEntityResolutionRejected("PRIVATE_ENTITY"), "entity_resolution_error"),
        (DraftTaskTranslationRejected("PRIVATE_TASK"), "task_translation_error"),
    ]:
        orchestrator, req = ask(evidence, Planner(error=error))
        assert orchestrator.answer(req) == AskV2Orchestrator(evidence).answer(req)
        assert events()[-1]["fallback_category"] == category
    assert "PRIVATE" not in json.dumps(events())


def test_attempt_clock_failure_cannot_prevent_cleanup():
    attempt = telemetry.ProviderAttempt(attempted=True)
    telemetry.finish_attempt(attempt, float("nan"))
    assert attempt.latency_ms is None


def test_writer_success_has_content_free_diagnostics(evidence, events):
    orchestrator, request = ask(evidence, Planner())
    response = orchestrator.answer(request)
    assert response.answer_mode.value == "grounded_ai"
    writer_events = [event for event in events() if event["component"] == "writer"]
    assert len(writer_events) == 2
    assert writer_events[-1]["validation_outcome"] == "writer_valid"
    assert writer_events[-1]["success"] and not writer_events[-1]["fallback"]
    serialized = json.dumps(events())
    assert all(text not in serialized for text in ("Josh Allen", "0.237", "gsk_", "support_ids"))


@pytest.mark.parametrize("failure", ["http", "support", "causal"])
def test_writer_failures_are_bounded_and_content_free(evidence, events, failure):
    class FailedWriter(Writer):
        def write(self, brief, *, timeout):
            if failure == "http":
                error = RuntimeError("PRIVATE_BODY secret key /private/path user question")
                error.status_code = 403
                raise error
            result = super().write(brief, timeout=timeout).model_dump(mode="python")
            if failure == "support":
                result["sentences"][0]["support_ids"] = ("invalid_support",)
            else:
                result["sentences"][0]["text"] += " He caused stronger quarterback performance."
            return result

    runtime = ProviderRuntime(
        ProviderConfiguration.from_environment(environment()),
        planner=Planner(),
        writer=FailedWriter(),
    )
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    assert ProviderOrchestrator(evidence, runtime).answer(request) == AskV2Orchestrator(
        evidence
    ).answer(request)
    event = events()[-1]
    assert event["component"] == "writer" and event["fallback"]
    if failure == "http":
        assert event["fallback_category"] == "permission_error" and event["http_status"] == 403
    else:
        assert event["validation_outcome"] == (
            "unknown_support_id" if failure == "support" else "causal_violation"
        )
    assert all(
        text not in json.dumps(events())
        for text in ("PRIVATE_BODY", "/private/path", "Josh Allen", "0.237")
    )


def test_invalid_writer_telemetry_category_is_silently_dropped(events):
    config = ProviderConfiguration.from_environment(environment())
    telemetry.provider_event(
        config,
        component="writer",
        phase=telemetry.ProviderPhase.WRITER_VALIDATION,
        validation_outcome="PRIVATE_PAYLOAD",
    )
    assert events() == []

"""Offline Groq configuration, adapter, grounding, and fallback tests."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import httpx
import pytest

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.conversation.contracts import (
    AnalyticalTaskProposal,
    AskV2Request,
    GroundedSynthesisProposal,
    PlannerEntityProposal,
    PlannerProposal,
    ProviderPlannerInput,
    ProviderSynthesisInput,
    SynthesisSection,
)
from nfl_coaching_impact.conversation.enums import (
    AnalyticalTask,
    AnswerMode,
    EntityKind,
    QuestionType,
    RequestedOutput,
    SynthesisSectionKind,
    SynthesisStyle,
)
from nfl_coaching_impact.conversation.evidence import EvidenceService
from nfl_coaching_impact.conversation.groq_provider import (
    GROQ_BASE_URL,
    GROQ_PLANNER_REASONING_EFFORT,
    GROQ_SYNTHESIZER_REASONING_EFFORT,
    GroqPlanner,
    GroqSynthesizer,
    groq_runtime,
)
from nfl_coaching_impact.conversation.grounding import provider_synthesis_input
from nfl_coaching_impact.conversation.openai_provider import OpenAISynthesizer
from nfl_coaching_impact.conversation.orchestration import AskV2Orchestrator
from nfl_coaching_impact.conversation.provider_drafts import (
    FollowupKind,
    ProviderDraftInput,
    ProviderEntityMention,
    ProviderPlanDraft,
    RequestedCapability,
)
from nfl_coaching_impact.conversation.provider_orchestration import ProviderOrchestrator
from nfl_coaching_impact.conversation.providers import (
    PlannerProvider,
    ProviderConfiguration,
    ProviderName,
    ProviderRefusal,
    ProviderRuntime,
    SynthesizerProvider,
)
from nfl_coaching_impact.conversation.serialization import canonical_json_bytes
from nfl_coaching_impact.conversation.service import provider_runtime

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/processed/ask_anything" / release.VERSION
TEST_GROQ_KEY = "gsk_" + "test_provider_key_" + ("0" * 12)
TEST_OPENAI_KEY = "sk-" + "test-provider-key-" + ("0" * 12)


@pytest.fixture(scope="module")
def evidence() -> EvidenceService:
    return EvidenceService(release.validate(SNAPSHOT))


def groq_environment(**overrides: str) -> dict[str, str]:
    values = {
        "ASK_V2_PROVIDER": "groq",
        "ASK_V2_EXTERNAL_SHARING_ENABLED": "true",
        "GROQ_API_KEY": TEST_GROQ_KEY,
        "ASK_V2_GROQ_PLANNER_MODEL": "openai/gpt-oss-120b",
        "ASK_V2_GROQ_SYNTHESIZER_MODEL": "openai/gpt-oss-20b",
    }
    values.update(overrides)
    return values


def groq_configuration(**overrides) -> ProviderConfiguration:
    values = {
        "enabled": True,
        "external_sharing_enabled": True,
        "api_key": TEST_GROQ_KEY,
        "planner_model": "openai/gpt-oss-120b",
        "synthesizer_model": "openai/gpt-oss-20b",
        "planner_timeout_seconds": 10.0,
        "synthesizer_timeout_seconds": 15.0,
        "total_timeout_seconds": 30.0,
        "planner_max_output_tokens": 600,
        "synthesizer_max_output_tokens": 800,
        "valid": True,
        "provider": ProviderName.GROQ,
    }
    values.update(overrides)
    return ProviderConfiguration(**values)


def coach_comparison_proposal() -> PlannerProposal:
    return PlannerProposal(
        question_type=QuestionType.COMPARISON,
        entities=(
            PlannerEntityProposal(kind=EntityKind.COACH, mention="Andy Reid"),
            PlannerEntityProposal(kind=EntityKind.COACH, mention="Mike Tomlin"),
        ),
        tasks=(
            AnalyticalTaskProposal(
                task=AnalyticalTask.COMPARE_COACH_EVIDENCE,
                entity_indexes=(0, 1),
            ),
        ),
        requested_outputs=tuple(RequestedOutput),
    )


def coach_comparison_draft() -> ProviderPlanDraft:
    return ProviderPlanDraft(
        question_type=QuestionType.COMPARISON,
        entity_mentions=(
            ProviderEntityMention(text="Andy Reid", kind_hint=EntityKind.COACH),
            ProviderEntityMention(text="Mike Tomlin", kind_hint=EntityKind.COACH),
        ),
        season_mentions=(),
        requested_capabilities=(RequestedCapability.COACH_COMPARISON,),
        comparison_requested=True,
        followup_kind=FollowupKind.NONE,
    )


def compliant_synthesis(payload: ProviderSynthesisInput) -> GroundedSynthesisProposal:
    propositions = list(payload.propositions[:4])
    direct = tuple(item.proposition_id for item in propositions[:1])
    supporting = tuple(item.proposition_id for item in propositions[1:])
    linked = tuple(
        dict.fromkeys(
            evidence_id for proposition in propositions for evidence_id in proposition.evidence_ids
        )
    )
    sections = (
        (
            SynthesisSection(
                kind=SynthesisSectionKind.KEY_EVIDENCE,
                proposition_ids=supporting,
            ),
        )
        if supporting
        else ()
    )
    return GroundedSynthesisProposal(
        style=SynthesisStyle.EXPLANATORY,
        direct_proposition_ids=direct,
        sections=sections,
        evidence_ids=linked[:5],
        limitation_ids=tuple(item.limitation_id for item in payload.limitations),
        unsupported_ids=tuple(item.unsupported_id for item in payload.unsupported),
        followup_ids=tuple(item.followup_id for item in payload.followups[:2]),
    )


class FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"output_parsed": self.parsed})()


class FakeClient:
    def __init__(self, parsed):
        self.responses = FakeResponses(parsed)


class LocalPlanner(PlannerProvider):
    implementation_version = "groq-fake-planner"
    model_version = "openai/gpt-oss-120b"

    def __init__(self, evidence: EvidenceService, value=None, error=None):
        self.local = AskV2Orchestrator(evidence).planner
        self.value = value
        self.error = error
        self.calls = 0

    def plan(self, request: ProviderPlannerInput, *, timeout: float):
        self.calls += 1
        if self.error:
            raise self.error
        if self.value is not None:
            return self.value
        if isinstance(request, ProviderDraftInput):
            plan = self.local.plan(AskV2Request(question=request.question))
            capabilities = {
                QuestionType.QB_HISTORY: RequestedCapability.QB_HISTORY,
                QuestionType.COMPARISON: RequestedCapability.COACH_COMPARISON,
                QuestionType.PLAYER_TEAM_SCENARIO: (
                    RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON
                ),
            }
            return ProviderPlanDraft(
                question_type=plan.proposal.question_type,
                entity_mentions=tuple(
                    ProviderEntityMention(text=e.mention, kind_hint=e.kind)
                    for e in plan.proposal.entities
                ),
                season_mentions=(plan.proposal.tasks[0].seasons.start_season,)
                if plan.proposal.tasks and plan.proposal.tasks[0].seasons
                else (),
                requested_capabilities=(
                    capabilities.get(plan.proposal.question_type, RequestedCapability.QB_HISTORY),
                ),
                comparison_requested=plan.proposal.question_type is QuestionType.COMPARISON,
                followup_kind=FollowupKind.NONE,
            )
        return self.local.plan(AskV2Request(question=request.question)).proposal


class LocalSynthesizer(SynthesizerProvider):
    implementation_version = "groq-fake-synthesizer"
    model_version = "openai/gpt-oss-20b"

    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    def synthesize(self, request: ProviderSynthesisInput, *, timeout: float):
        self.calls += 1
        if self.error:
            raise self.error
        return compliant_synthesis(request) if self.value is None else self.value


def groq_orchestrator(evidence, planner=None, synthesizer=None):
    runtime = ProviderRuntime(
        configuration=groq_configuration(),
        planner=planner or LocalPlanner(evidence),
        synthesizer=synthesizer or LocalSynthesizer(),
    )
    return ProviderOrchestrator(evidence, runtime)


def experimental_orchestrator(evidence, synthesizer):
    # The retained experimental synthesis adapter is subject to the unchanged
    # two-stage grounding seam. Normal Groq mode intentionally never calls it.
    return ProviderOrchestrator(
        evidence,
        ProviderRuntime(
            configuration=groq_configuration(provider=ProviderName.OPENAI),
            planner=LocalPlanner(evidence),
            synthesizer=synthesizer,
        ),
    )


@pytest.mark.parametrize(
    ("environment", "provider", "ready"),
    [
        ({"ASK_V2_PROVIDER": "none"}, ProviderName.NONE, False),
        ({"GROQ_API_KEY": TEST_GROQ_KEY}, ProviderName.NONE, False),
        (
            {**groq_environment(), "GROQ_API_KEY": ""},
            ProviderName.GROQ,
            False,
        ),
        (
            {**groq_environment(), "GROQ_API_KEY": "not-a-groq-key"},
            ProviderName.GROQ,
            False,
        ),
        (
            {**groq_environment(), "ASK_V2_EXTERNAL_SHARING_ENABLED": "false"},
            ProviderName.GROQ,
            False,
        ),
        (
            {**groq_environment(), "ASK_V2_GROQ_PLANNER_MODEL": ""},
            ProviderName.GROQ,
            False,
        ),
        (
            {**groq_environment(), "ASK_V2_GROQ_SYNTHESIZER_MODEL": ""},
            ProviderName.GROQ,
            True,
        ),
        (groq_environment(), ProviderName.GROQ, True),
        ({"ASK_V2_PROVIDER": "arbitrary"}, ProviderName.NONE, False),
    ],
)
def test_groq_configuration_matrix(environment, provider, ready):
    configuration = ProviderConfiguration.from_environment(environment)
    assert configuration.provider is provider
    assert configuration.ready is ready


def test_explicit_provider_wins_and_legacy_openai_remains_compatible():
    legacy = {
        "ASK_V2_OPENAI_ENABLED": "true",
        "ASK_V2_EXTERNAL_SHARING_ENABLED": "true",
        "OPENAI_API_KEY": TEST_OPENAI_KEY,
        "ASK_V2_PLANNER_MODEL": "gpt-test-planner",
        "ASK_V2_SYNTHESIZER_MODEL": "gpt-test-synthesizer",
    }
    legacy_configuration = ProviderConfiguration.from_environment(legacy)
    assert legacy_configuration.provider is ProviderName.OPENAI
    assert legacy_configuration.ready
    explicit_none = ProviderConfiguration.from_environment({**legacy, "ASK_V2_PROVIDER": "none"})
    assert explicit_none.provider is ProviderName.NONE
    assert not explicit_none.ready
    explicit_groq = ProviderConfiguration.from_environment(
        {**groq_environment(), "ASK_V2_OPENAI_ENABLED": "invalid-legacy-value"}
    )
    assert explicit_groq.provider is ProviderName.GROQ
    assert explicit_groq.ready


def test_groq_models_are_strict_allowlisted_and_key_is_hidden():
    configuration = ProviderConfiguration.from_environment(
        groq_environment(ASK_V2_GROQ_PLANNER_MODEL="other/model")
    )
    assert not configuration.ready
    assert "test_provider_key" not in repr(configuration)


def test_none_provider_constructs_no_external_client(monkeypatch):
    monkeypatch.setenv("ASK_V2_PROVIDER", "none")
    monkeypatch.setenv("GROQ_API_KEY", TEST_GROQ_KEY)
    monkeypatch.setitem(sys.modules, "openai", None)
    runtime = provider_runtime()
    assert runtime.configuration.provider is ProviderName.NONE
    assert not runtime.ready


def test_groq_runtime_uses_fixed_endpoint_and_no_retries(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    runtime = groq_runtime(groq_configuration())
    assert runtime.ready
    assert captured == {
        "api_key": TEST_GROQ_KEY,
        "base_url": GROQ_BASE_URL,
        "max_retries": 0,
    }


def test_groq_adapters_use_strict_responses_contract_without_tools(evidence):
    planner_value = coach_comparison_draft()
    planner_client = FakeClient(planner_value)
    planner = GroqPlanner(planner_client, groq_configuration())
    planner_input = ProviderDraftInput(
        question="Compare Andy Reid and Mike Tomlin.",
        prior_user_questions=(),
        context_mentions=(),
        context_seasons=(),
    )
    assert planner.plan(planner_input, timeout=9) == planner_value
    planner_call = planner_client.responses.calls[0]
    assert planner_call["text_format"] is ProviderPlanDraft
    assert planner_call["reasoning"] == {"effort": GROQ_PLANNER_REASONING_EFFORT}
    assert planner_call["tools"] == [] and planner_call["tool_choice"] == "none"
    assert planner_call["max_output_tokens"] == 600

    result = AskV2Orchestrator(evidence).analyze(
        AskV2Request(question="How did Josh Allen perform in 2022?")
    )
    payload = provider_synthesis_input("How did Josh Allen perform in 2022?", result)
    synthesis_value = compliant_synthesis(payload)
    synthesis_client = FakeClient(synthesis_value)
    synthesizer = GroqSynthesizer(synthesis_client, groq_configuration())
    assert synthesizer.synthesize(payload, timeout=14) == synthesis_value
    synthesis_call = synthesis_client.responses.calls[0]
    assert synthesis_call["text_format"] is GroundedSynthesisProposal
    assert synthesis_call["reasoning"] == {"effort": GROQ_SYNTHESIZER_REASONING_EFFORT}
    assert synthesis_call["tools"] == [] and synthesis_call["tool_choice"] == "none"
    assert synthesis_call["max_output_tokens"] == 800


@pytest.mark.parametrize(
    "question",
    [
        "Between Reid and Tomlin, whose résumé has clearer directly attributable QB evidence?",
        "Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?",
        "How would Kyler Murray fit Minnesota?",
        "Why?",
    ],
)
def test_groq_valid_plans_remain_backend_authorized(evidence, question):
    response = groq_orchestrator(evidence).answer(AskV2Request(question=question))
    assert response.answer_mode in {AnswerMode.GROUNDED_AI, AnswerMode.DETERMINISTIC}
    assert response.versions.deterministic_planner_version == "ask-v2-stage-c"


@pytest.mark.parametrize(
    "invalid_plan",
    [
        {**coach_comparison_proposal().model_dump(mode="json"), "sql": "SELECT 1"},
        {**coach_comparison_proposal().model_dump(mode="json"), "path": "/tmp/data"},
        {**coach_comparison_proposal().model_dump(mode="json"), "url": "https://bad.test"},
        {**coach_comparison_proposal().model_dump(mode="json"), "function": "run"},
        {**coach_comparison_proposal().model_dump(mode="json"), "scientific_status": "C17_OK"},
        {**coach_comparison_proposal().model_dump(mode="json"), "canonical_id": "coach-x"},
        {
            **coach_comparison_proposal().model_dump(mode="json"),
            "tasks": [{"task": "UNKNOWN_TASK", "entity_indexes": []}],
        },
        {
            **coach_comparison_proposal().model_dump(mode="json"),
            "tasks": [{"task": "COMPARE_COACH_EVIDENCE", "entity_indexes": [0, 1]}] * 13,
        },
        "malformed",
    ],
)
def test_invalid_groq_planner_output_falls_back_exactly(evidence, invalid_plan):
    request = AskV2Request(
        question="Who has stronger QB-development evidence, Andy Reid or Mike Tomlin?"
    )
    expected = AskV2Orchestrator(evidence).answer(request)
    planner = LocalPlanner(evidence, value=invalid_plan)
    actual = groq_orchestrator(evidence, planner=planner).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        ConnectionError(),
        RuntimeError("configured model unavailable"),
        ProviderRefusal("refused"),
    ],
)
def test_groq_planner_failures_return_exact_fallback(evidence, error):
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = AskV2Orchestrator(evidence).answer(request)
    planner = LocalPlanner(evidence, error=error)
    actual = groq_orchestrator(evidence, planner=planner).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)


class RateLimitError(RuntimeError):
    pass


def test_groq_429_classification_falls_back_without_retry(evidence):
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = AskV2Orchestrator(evidence).answer(request)
    planner = LocalPlanner(evidence, error=RateLimitError("429 provider detail"))
    actual = groq_orchestrator(evidence, planner=planner).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)
    assert planner.calls == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unknown_proposition", "prop_unknown"),
        ("wrong_evidence", "evidence_unknown"),
        ("answerability", "SUPPORTED"),
        ("causal_claim", "coach caused improvement"),
        ("fit_score", 99),
        ("destination_epa", 0.5),
        ("rookie_forecast", 0.4),
        ("career_simulation", "implemented"),
        ("forward_pae", 0.2),
        ("coach_effect", 100),
    ],
)
def test_groq_synthesis_cannot_expand_scientific_authority(evidence, field, value):
    request = AskV2Request(question="How would Kyler Murray fit Minnesota?")
    expected = AskV2Orchestrator(evidence).answer(request)
    result = AskV2Orchestrator(evidence).analyze(request)
    payload = provider_synthesis_input(request.question, result)
    invalid = compliant_synthesis(payload).model_dump(mode="json")
    if field == "unknown_proposition":
        invalid["direct_proposition_ids"] = [value]
    elif field == "wrong_evidence":
        invalid["evidence_ids"] = [value]
    else:
        invalid[field] = value
    actual = experimental_orchestrator(evidence, LocalSynthesizer(value=invalid)).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)


def test_groq_omitted_limitation_and_malformed_output_fall_back(evidence):
    request = AskV2Request(question="How would Kyler Murray fit Minnesota?")
    expected = AskV2Orchestrator(evidence).answer(request)
    result = AskV2Orchestrator(evidence).analyze(request)
    payload = provider_synthesis_input(request.question, result)
    omitted = compliant_synthesis(payload).model_dump(mode="json")
    omitted["limitation_ids"] = []
    for invalid in (omitted, {"not": "the schema"}):
        actual = experimental_orchestrator(evidence, LocalSynthesizer(value=invalid)).answer(
            request
        )
        assert canonical_json_bytes(actual) == canonical_json_bytes(expected)


@pytest.mark.parametrize(
    "error",
    [TimeoutError(), ConnectionError(), RateLimitError("429"), ProviderRefusal("refused")],
)
def test_groq_synthesizer_failures_return_exact_fallback(evidence, error):
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = AskV2Orchestrator(evidence).answer(request)
    synth = LocalSynthesizer(error=error)
    actual = experimental_orchestrator(evidence, synth).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)
    assert synth.calls == 1


def test_openai_and_groq_fakes_share_identical_grounding(evidence):
    request = AskV2Request(question="How would Kyler Murray fit Minnesota?")
    expected = AskV2Orchestrator(evidence).answer(request)
    result = AskV2Orchestrator(evidence).analyze(request)
    payload = provider_synthesis_input(request.question, result)
    invalid = compliant_synthesis(payload).model_dump(mode="json")
    invalid["destination_forecast"] = "Kyler gains 0.5 EPA"
    for adapter in (OpenAISynthesizer, GroqSynthesizer):
        configuration = groq_configuration(provider=ProviderName.OPENAI)
        response = experimental_orchestrator(
            evidence, adapter(FakeClient(invalid), configuration)
        ).answer(request)
        assert canonical_json_bytes(response) == canonical_json_bytes(expected)


def test_groq_tests_guarantee_no_network(evidence, monkeypatch):
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Groq ordinary tests must not access the network")
        ),
    )
    response = groq_orchestrator(evidence).answer(
        AskV2Request(question="How did Josh Allen perform in 2022?")
    )
    assert response.answer_mode is AnswerMode.GROUNDED_AI


def test_realistic_groq_responses_shape_parses_with_pinned_openai_sdk():
    proposal = coach_comparison_draft()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_groq_fixture",
                "object": "response",
                "created_at": 1_789_000_000,
                "status": "completed",
                "background": False,
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "max_output_tokens": 600,
                "model": "openai/gpt-oss-120b",
                "output": [
                    {
                        "id": "msg_groq_fixture",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "logprobs": [],
                                "text": canonical_json_bytes(proposal).decode("ascii"),
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": False,
                "reasoning": {"effort": "medium", "summary": None},
                "store": False,
                "temperature": 1.0,
                "text": {"format": captured["text"]["format"], "verbosity": "medium"},
                "tool_choice": "none",
                "tools": [],
                "top_p": 1.0,
                "truncation": "disabled",
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 40,
                    "output_tokens_details": {"reasoning_tokens": 5},
                    "total_tokens": 140,
                },
            },
        )

    from openai import OpenAI

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key=TEST_GROQ_KEY,
        base_url=GROQ_BASE_URL,
        max_retries=0,
        http_client=http_client,
    )
    planner = GroqPlanner(client, groq_configuration())
    planner_input = ProviderDraftInput(
        question="Compare Andy Reid and Mike Tomlin.",
        prior_user_questions=(),
        context_mentions=(),
        context_seasons=(),
    )
    assert planner.plan(planner_input, timeout=9) == proposal
    assert captured["tools"] == [] and captured["tool_choice"] == "none"
    assert captured["reasoning"] == {"effort": "medium"}
    response_format = captured["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False

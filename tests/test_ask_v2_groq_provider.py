"""Offline Groq configuration, adapter, grounding, and fallback tests."""

from __future__ import annotations

import json
import re
import socket
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.conversation.answer_writer import (
    ApprovedAnswerBrief,
    WriterResult,
    WriterSentence,
    approved_answer_brief,
)
from nfl_coaching_impact.conversation.contracts import (
    AnalyticalTaskProposal,
    AskV2Request,
    CanonicalEntityReference,
    ConversationContext,
    ConversationTurn,
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
    ConversationRole,
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
    GroqAnswerWriter,
    GroqPlanner,
    GroqPlannerDraft,
    GroqSynthesizer,
    _parse_planner_output,
    _planner_response_text,
    _planner_structure,
    groq_runtime,
)
from nfl_coaching_impact.conversation.grounding import provider_synthesis_input
from nfl_coaching_impact.conversation.openai_provider import OpenAISynthesizer
from nfl_coaching_impact.conversation.orchestration import AskV2Orchestrator
from nfl_coaching_impact.conversation.provider_drafts import (
    FollowupKind,
    ProviderDraftInput,
    ProviderDraftTranslator,
    ProviderEntityMention,
    ProviderPlanDraft,
    RequestedCapability,
)
from nfl_coaching_impact.conversation.provider_orchestration import ProviderOrchestrator
from nfl_coaching_impact.conversation.providers import (
    AnswerWriterProvider,
    PlannerProvider,
    PlannerValidationCategory,
    ProviderConfiguration,
    ProviderMalformedOutput,
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
    }
    values.update(overrides)
    return values


def groq_configuration(**overrides) -> ProviderConfiguration:
    values = {
        "enabled": True,
        "external_sharing_enabled": True,
        "api_key": TEST_GROQ_KEY,
        "planner_model": "openai/gpt-oss-120b",
        "synthesizer_model": "openai/gpt-oss-120b",
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

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self.parsed
        if isinstance(value, ProviderPlanDraft):
            value = planner_wire(value)
        text = value if isinstance(value, str) else canonical_json_bytes(value).decode("ascii")
        return type("Response", (), {"output_text": text})()


class FakeClient:
    def __init__(self, parsed):
        self.responses = FakeResponses(parsed)


def planner_wire(value: ProviderPlanDraft) -> GroqPlannerDraft:
    return GroqPlannerDraft(
        question_type=value.question_type.value,
        entity_texts=tuple(item.text for item in value.entity_mentions),
        entity_kinds=tuple(item.kind_hint.value for item in value.entity_mentions),
        season_mentions=value.season_mentions,
        requested_capabilities=tuple(item.value for item in value.requested_capabilities),
        comparison_requested=value.comparison_requested,
        followup_kind=value.followup_kind.value,
    )


def planner_draft(
    question_type,
    mentions,
    seasons,
    capability,
    *,
    comparison=False,
    followup=FollowupKind.NONE,
):
    return ProviderPlanDraft(
        question_type=question_type,
        entity_mentions=tuple(
            ProviderEntityMention(text=text, kind_hint=kind) for text, kind in mentions
        ),
        season_mentions=seasons,
        requested_capabilities=(capability,),
        comparison_requested=comparison,
        followup_kind=followup,
    )


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

            def literal(proposal):
                labels = [proposal.mention]
                for row in self.local.source_entities:
                    if row["name"] == proposal.mention:
                        labels.extend(row.get("aliases", ()))
                present = [
                    label for label in labels if label.casefold() in request.question.casefold()
                ]
                return max(present, key=len) if present else proposal.mention

            capabilities = {
                QuestionType.QB_HISTORY: RequestedCapability.QB_HISTORY,
                QuestionType.QB_PROJECTION: RequestedCapability.QB_PROJECTION,
                QuestionType.COACH_HISTORY: RequestedCapability.COACH_HISTORY,
                QuestionType.COACH_QB_CONTEXT: RequestedCapability.COACH_QB_CONTEXT,
                QuestionType.COMPARISON: RequestedCapability.COACH_COMPARISON,
                QuestionType.PLAYER_TEAM_SCENARIO: (
                    RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON
                ),
            }
            return ProviderPlanDraft(
                question_type=plan.proposal.question_type,
                entity_mentions=tuple(
                    ProviderEntityMention(text=literal(e), kind_hint=e.kind)
                    for e in plan.proposal.entities
                ),
                season_mentions=tuple(
                    int(year) for year in re.findall(r"\b20\d{2}\b", request.question)
                ),
                requested_capabilities=(
                    capabilities.get(plan.proposal.question_type, RequestedCapability.QB_HISTORY),
                ),
                comparison_requested=plan.proposal.question_type is QuestionType.COMPARISON,
                followup_kind=FollowupKind.NONE,
            )
        return self.local.plan(AskV2Request(question=request.question)).proposal


class LocalSynthesizer(SynthesizerProvider):
    implementation_version = "groq-fake-synthesizer"
    model_version = "openai/gpt-oss-120b"

    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    def synthesize(self, request: ProviderSynthesisInput, *, timeout: float):
        self.calls += 1
        if self.error:
            raise self.error
        return compliant_synthesis(request) if self.value is None else self.value


def compliant_composition_plan(brief: ApprovedAnswerBrief):
    from nfl_coaching_impact.conversation.writer_composition import (
        CompositionPlan,
        approved_phrases,
    )

    phrases = approved_phrases(brief)
    primary = [p for p in phrases if p.support_id == brief.supports[0].support_id][-1]
    items = [{"phrase_id": primary.phrase_id, "connector": "none"}]
    if brief.question_type.value == "PLAYER_TEAM_SCENARIO":
        second = next(
            (
                p
                for p in phrases
                if p.kind.value == "proposition" and p.support_id != primary.support_id
            ),
            None,
        )
        if second:
            items.append({"phrase_id": second.phrase_id, "connector": "none"})
    limits = [
        {
            "phrase_id": next(p.phrase_id for p in phrases if p.support_id == sid),
            "connector": "none",
        }
        for sid in brief.required_limitation_ids
    ]
    paragraphs = [{"items": items}]
    if limits:
        paragraphs.append({"items": limits})
    return CompositionPlan.model_validate({"paragraphs": paragraphs})


def compliant_writer_result(brief: ApprovedAnswerBrief) -> WriterResult:
    proposition = next(item for item in brief.supports if item.kind.value == "proposition")
    main_measurements = tuple(
        item.measurement_id
        for item in brief.measurements
        if item.support_id == proposition.support_id
    )
    sentence = WriterSentence(
        text=proposition.phrasings[-1] if proposition.phrasings else proposition.text,
        support_ids=(proposition.support_id,),
        measurement_ids=main_measurements,
        entity_ids=proposition.entity_ids,
    )
    limitations = tuple(
        item for item in brief.supports if item.support_id in brief.required_limitation_ids
    )
    limitation = None
    if limitations:
        limitation_measurements = tuple(
            item.measurement_id
            for item in brief.measurements
            if item.support_id in brief.required_limitation_ids
        )
        limitation = WriterSentence(
            text=" ".join(item.text for item in limitations),
            support_ids=tuple(item.support_id for item in limitations),
            measurement_ids=limitation_measurements,
        )
    all_sentences = (sentence, *((limitation,) if limitation else ()))
    return WriterResult(
        sentences=(sentence,),
        limitation=limitation,
        used_support_ids=tuple(
            dict.fromkeys(item for part in all_sentences for item in part.support_ids)
        ),
        used_measurement_ids=tuple(
            dict.fromkeys(item for part in all_sentences for item in part.measurement_ids)
        ),
    )


class LocalWriter(AnswerWriterProvider):
    implementation_version = "groq-fake-writer"
    model_version = "openai/gpt-oss-120b"

    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    def write(self, request: ApprovedAnswerBrief, *, timeout: float):
        self.calls += 1
        if self.error:
            raise self.error
        return compliant_composition_plan(request) if self.value is None else self.value


def groq_orchestrator(evidence, planner=None, writer=None):
    runtime = ProviderRuntime(
        configuration=groq_configuration(),
        planner=planner or LocalPlanner(evidence),
        writer=writer or LocalWriter(),
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
            {**groq_environment(), "ASK_V2_GROQ_PLANNER_MODEL": "openai/gpt-oss-20b"},
            ProviderName.GROQ,
            False,
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


def test_groq_planner_uses_json_object_and_adapters_use_no_tools(evidence):
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
    assert planner_call["text"] == {"format": {"type": "json_object"}}
    assert "text_format" not in planner_call
    assert planner_call["reasoning"] == {"effort": GROQ_PLANNER_REASONING_EFFORT}
    assert planner_call["tools"] == [] and planner_call["tool_choice"] == "none"
    assert planner_call["max_output_tokens"] == 600
    instructions = planner_call["instructions"]
    assert "include ALL seven keys; no key is optional" in instructions
    assert "Never use null" in instructions and "even for one item" in instructions
    for enum in (QuestionType, EntityKind, RequestedCapability, FollowupKind):
        assert ", ".join(item.value for item in enum) in instructions
    historical_example = instructions.rsplit(" -> ", 1)[1].strip()
    expected_history = planner_draft(
        QuestionType.QB_HISTORY,
        (("Josh Allen", EntityKind.QB),),
        (2022,),
        RequestedCapability.QB_HISTORY,
    )
    assert _parse_planner_output(historical_example) == expected_history

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

    brief = approved_answer_brief(result)
    writer_value = compliant_composition_plan(brief)
    writer_client = FakeClient(writer_value)
    writer = GroqAnswerWriter(writer_client, groq_configuration())
    assert writer.write(brief, timeout=14) == writer_value
    writer_call = writer_client.responses.calls[0]
    from nfl_coaching_impact.conversation.writer_composition import CompositionPlan

    assert writer_call["text_format"] is CompositionPlan
    assert writer_call["reasoning"] == {"effort": GROQ_SYNTHESIZER_REASONING_EFFORT}
    assert writer_call["tools"] == [] and writer_call["tool_choice"] == "none"
    assert writer_call["model"] == "openai/gpt-oss-120b"


@pytest.mark.parametrize(
    "question,draft",
    [
        (
            "How did Josh Allen perform in 2022?",
            planner_draft(
                QuestionType.QB_HISTORY,
                (("Josh Allen", EntityKind.QB),),
                (2022,),
                RequestedCapability.QB_HISTORY,
            ),
        ),
        (
            "Compare Andy Reid and Mike Tomlin's evidence around quarterback development.",
            coach_comparison_draft(),
        ),
        (
            "How would Kyler Murray fit Minnesota?",
            planner_draft(
                QuestionType.PLAYER_SCHEME_ALIGNMENT,
                (("Kyler Murray", EntityKind.QB), ("Minnesota", EntityKind.TEAM)),
                (),
                RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON,
                comparison=True,
            ),
        ),
        (
            "What does the model project for Josh Allen in 2026?",
            planner_draft(
                QuestionType.QB_PROJECTION,
                (("Josh Allen", EntityKind.QB),),
                (2026,),
                RequestedCapability.QB_PROJECTION,
            ),
        ),
        (
            "Why?",
            planner_draft(
                QuestionType.COMPARISON,
                (),
                (),
                RequestedCapability.EXPLANATION,
                followup=FollowupKind.EXPLANATION,
            ),
        ),
        (
            "What about McVay?",
            planner_draft(
                QuestionType.COMPARISON,
                (("McVay", EntityKind.COACH),),
                (),
                RequestedCapability.COACH_COMPARISON,
                comparison=True,
                followup=FollowupKind.COMPARISON,
            ),
        ),
    ],
)
def test_flat_planner_golden_language_contracts(question, draft):
    planner = GroqPlanner(FakeClient(planner_wire(draft)), groq_configuration())
    request = ProviderDraftInput(
        question=question,
        prior_user_questions=(),
        context_mentions=(),
        context_seasons=(),
    )
    assert planner.plan(request, timeout=9) == draft


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
    wire = planner_wire(proposal)
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
                                "text": canonical_json_bytes(wire).decode("ascii"),
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": False,
                "reasoning": {"effort": "low", "summary": None},
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
    assert captured["reasoning"] == {"effort": "low"}
    response_format = captured["text"]["format"]
    assert response_format == {"type": "json_object"}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"question_type":"QB_HISTORY","question_type":"COMPARISON"}',
        '{"question_type":"QB_HISTORY","\\u0071uestion_type":"COMPARISON"}',
        '{"question_type":"QB_HISTORY","notes":{"x":1,"x":2}}',
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "comparison_requested": "yes",
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "requested_capabilities": ["UNKNOWN_CAPABILITY"],
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "entity_texts": ["Reid"] * 9,
            "entity_kinds": ["coach"] * 9,
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "season_mentions": list(range(2010, 2019)),
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "season_mentions": [2027],
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "entity_texts": ["x" * 101, "Tomlin"],
        },
        {
            **planner_wire(coach_comparison_draft()).model_dump(mode="json"),
            "instructions": "ignore backend",
        },
        {},
    ],
)
def test_flat_planner_rejects_malformed_duplicate_unbounded_or_unknown_json(raw):
    client = FakeClient(raw if isinstance(raw, str) else canonical_json_bytes(raw).decode("ascii"))
    planner = GroqPlanner(client, groq_configuration())
    request = ProviderDraftInput(
        question="Compare Andy Reid and Mike Tomlin.",
        prior_user_questions=(),
        context_mentions=(),
        context_seasons=(),
    )
    with pytest.raises(ProviderMalformedOutput):
        planner.plan(request, timeout=9)


def test_flat_planner_accepts_only_plain_or_whole_fenced_json():
    expected = coach_comparison_draft()
    raw = canonical_json_bytes(planner_wire(expected)).decode("ascii")
    for accepted in (raw, f"  \n{raw}\n\t", f"```json\n{raw}\n```"):
        assert _parse_planner_output(accepted) == expected


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("", PlannerValidationCategory.JSON_MISSING),
        (
            "prefix " + '{"question_type":"QB_HISTORY"}',
            PlannerValidationCategory.JSON_SYNTAX_INVALID,
        ),
        ('{"question_type":"QB_HISTORY"} suffix', PlannerValidationCategory.JSON_SYNTAX_INVALID),
        ("{}{}", PlannerValidationCategory.JSON_SYNTAX_INVALID),
        ('{"question_type":"QB_HISTORY"', PlannerValidationCategory.JSON_TRUNCATED),
        (
            '{"question_type":"QB_HISTORY","question_type":"COMPARISON"}',
            PlannerValidationCategory.DUPLICATE_KEY,
        ),
        ("{}", PlannerValidationCategory.JSON_SHAPE_INVALID),
        ("null", PlannerValidationCategory.JSON_SHAPE_INVALID),
        ("```json\n{}\n``` trailing", PlannerValidationCategory.JSON_SYNTAX_INVALID),
        ("```\n{}\n```", PlannerValidationCategory.JSON_SYNTAX_INVALID),
    ],
)
def test_planner_json_syntax_matrix_fails_closed(raw, category):
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(raw)
    assert caught.value.planner_validation_outcome is category


@pytest.mark.parametrize(
    "mutation",
    [
        {"unknown_field": "not allowed"},
        {"comparison_requested": "yes"},
        {"question_type": "INVALID_ENUM"},
        {"entity_texts": ["x" * 101, "Mike Tomlin"]},
        {"season_mentions": [2027]},
        {"requested_capabilities": ["UNKNOWN_CAPABILITY"]},
    ],
)
def test_planner_json_shape_matrix_fails_closed(mutation):
    value = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    value.update(mutation)
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(canonical_json_bytes(value).decode("ascii"))
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_SHAPE_INVALID


def test_planner_text_fallback_reads_one_sdk_output_text_only():
    expected = coach_comparison_draft()
    raw = canonical_json_bytes(planner_wire(expected)).decode("ascii")
    content = SimpleNamespace(type="output_text", text=raw)
    response = SimpleNamespace(output_text=None, output=[SimpleNamespace(content=[content])])
    assert _parse_planner_output(_planner_response_text(response)) == expected
    empty_aggregate = SimpleNamespace(output_text="", output=[SimpleNamespace(content=[content])])
    assert _parse_planner_output(_planner_response_text(empty_aggregate)) == expected

    parsed_only = SimpleNamespace(output_text=None, output=[], output_parsed=planner_wire(expected))
    with pytest.raises(ProviderMalformedOutput) as caught:
        _planner_response_text(parsed_only)
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_MISSING

    multiple = SimpleNamespace(
        output_text=None,
        output=[SimpleNamespace(content=[content, content])],
    )
    with pytest.raises(ProviderMalformedOutput) as caught:
        _planner_response_text(multiple)
    assert (
        caught.value.planner_validation_outcome is PlannerValidationCategory.PROVIDER_PARSE_FAILED
    )


def test_planner_parser_is_deterministic_under_production_like_formatting_stress():
    expected = coach_comparison_draft()
    raw = canonical_json_bytes(planner_wire(expected)).decode("ascii")
    variants = (raw, f"\n{raw}\n", f"```json\n{raw}\n```")
    for index in range(120):
        assert _parse_planner_output(variants[index % len(variants)]) == expected


def test_planner_parser_rejects_oversized_output_before_decoding():
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output("{" + (" " * 16_384) + "}")
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_SHAPE_INVALID


@pytest.mark.parametrize("field", tuple(GroqPlannerDraft.model_fields))
def test_every_planner_key_is_required_with_no_optional_defaults(field):
    value = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    del value[field]
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(value))
    assert caught.value.planner_structure.missing_field_names == (field,)
    assert dict(caught.value.planner_structure.field_type_categories)[field] == "missing"


@pytest.mark.parametrize(
    "field,value,category,enum_field",
    [
        ("entity_texts", None, "null", None),
        ("entity_kinds", None, "null", None),
        ("season_mentions", None, "null", None),
        ("requested_capabilities", None, "null", None),
        ("question_type", [], "array", None),
        ("entity_texts", "private value", "string", None),
        ("entity_kinds", "coach", "string", None),
        ("comparison_requested", "false", "string", None),
        ("followup_kind", None, "null", None),
        ("question_type", "UNKNOWN_PRIVATE_ENUM", "string", "question_type"),
        ("followup_kind", "UNKNOWN_PRIVATE_ENUM", "string", "followup_kind"),
        ("requested_capabilities", ["UNKNOWN_PRIVATE_ENUM"], "array", "requested_capabilities"),
        ("entity_kinds", ["UNKNOWN_PRIVATE_ENUM", "coach"], "array", "entity_kinds"),
        ("season_mentions", "private value", "string", None),
        ("season_mentions", ["private value"], "array", None),
    ],
)
def test_planner_structural_deviations_are_content_free(field, value, category, enum_field):
    raw = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(raw))
    diagnostics = caught.value.planner_structure
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_SHAPE_INVALID
    assert dict(diagnostics.field_type_categories)[field] == category
    assert diagnostics.invalid_enum_field_name == enum_field
    assert (field in diagnostics.null_field_names) is (value is None)
    safe = json.dumps(asdict(diagnostics))
    assert "private value" not in safe and "UNKNOWN_PRIVATE_ENUM" not in safe
    assert "Andy Reid" not in safe and "Mike Tomlin" not in safe


def test_planner_structure_reports_pairing_without_entity_values():
    value = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    value["entity_kinds"] = ["coach"]
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(value))
    structure = caught.value.planner_structure
    assert structure.entity_text_count == 2 and structure.entity_kind_count == 1
    assert structure.season_count == 0 and structure.capability_count == 1


def test_empty_entity_and_season_arrays_pass_without_normalization():
    value = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    value.update(entity_texts=[], entity_kinds=[], season_mentions=[])
    actual = _parse_planner_output(json.dumps(value))
    assert actual.entity_mentions == () and actual.season_mentions == ()
    value["requested_capabilities"] = []
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(value))
    assert caught.value.planner_structure.capability_count == 0


def test_structural_diagnostics_never_disclose_arbitrary_property_names_or_values():
    value = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    value.update({"seasons": [2022], "private user content": "private provider content"})
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(value))
    structure = caught.value.planner_structure
    assert structure.unexpected_field_names == ("UNKNOWN_FIELD", "seasons")
    serialized = json.dumps(asdict(structure))
    assert "private" not in serialized and "2022" not in serialized
    assert "Andy Reid" not in serialized


def test_duplicate_and_non_object_structural_metadata_remain_bounded():
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output('{"question_type":"QB_HISTORY","question_type":"COMPARISON"}')
    assert caught.value.planner_structure.duplicate_key_detected
    assert not _planner_structure(None).top_level_object
    assert not _planner_structure([]).top_level_object


def test_planner_failure_short_circuits_before_writer(evidence):
    planner = LocalPlanner(
        evidence,
        error=ProviderMalformedOutput(
            "private provider output",
            planner_validation_outcome=PlannerValidationCategory.JSON_SYNTAX_INVALID,
        ),
    )
    writer = LocalWriter(error=AssertionError("writer must not run after planner failure"))
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = AskV2Orchestrator(evidence).answer(request)
    actual = groq_orchestrator(evidence, planner=planner, writer=writer).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)
    assert planner.calls == 1 and writer.calls == 0


_ENUM_FIELDS = (
    ("question_type", QuestionType),
    ("entity_kinds", EntityKind),
    ("requested_capabilities", RequestedCapability),
    ("followup_kind", FollowupKind),
)
_ENUM_CASES = [(field, item.value) for field, enum in _ENUM_FIELDS for item in enum]


def enum_wire(field, value):
    wire = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    wire[field] = [value] if field in {"entity_kinds", "requested_capabilities"} else value
    if field == "entity_kinds":
        wire["entity_texts"] = ["Example Entity"]
    return wire


@pytest.mark.parametrize("field,value", _ENUM_CASES)
def test_every_backend_enum_value_passes_groq_structural_contract(field, value):
    client = FakeClient(json.dumps(enum_wire(field, value)))
    planner = GroqPlanner(client, groq_configuration())
    actual = planner.plan(
        ProviderDraftInput(
            question="Compare Andy Reid and Mike Tomlin.",
            prior_user_questions=(),
            context_mentions=(),
            context_seasons=(),
        ),
        timeout=9,
    )
    backend_field = "entity_mentions" if field == "entity_kinds" else field
    parsed = getattr(actual, backend_field)
    if field == "entity_kinds":
        assert parsed[0].kind_hint.value == value
    elif field == "requested_capabilities":
        assert parsed[0].value == value
    else:
        assert parsed.value == value
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        (field, mutation)
        for field, value in _ENUM_CASES
        for mutation in (
            value[:-1] + "?",
            value.swapcase(),
            "UNRECOGNIZED",
            "",
            "natural language label",
        )
    ],
)
def test_enum_mutations_and_natural_language_labels_fail_closed(field, value):
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(enum_wire(field, value)))
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_SHAPE_INVALID


@pytest.mark.parametrize("field", tuple(GroqPlannerDraft.model_fields))
def test_null_is_rejected_for_each_required_key(field):
    wire = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    wire[field] = None
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(wire))
    assert caught.value.planner_structure.null_field_names == (field,)


@pytest.mark.parametrize("text_count,kind_count", [(1, 0), (2, 1), (0, 1)])
def test_all_asymmetric_entity_pairings_fail(text_count, kind_count):
    wire = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    wire.update(entity_texts=["Example Entity"] * text_count, entity_kinds=["coach"] * kind_count)
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(wire))
    assert caught.value.planner_structure.entity_text_count == text_count
    assert caught.value.planner_structure.entity_kind_count == kind_count


@pytest.mark.parametrize("seasons", [[2009], [2027], ["2022"], [2022.0], [None], [2022, 2022]])
def test_season_bounds_types_and_duplicates_fail(seasons):
    wire = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    wire["season_mentions"] = seasons
    with pytest.raises(ProviderMalformedOutput) as caught:
        _parse_planner_output(json.dumps(wire))
    assert caught.value.planner_validation_outcome is PlannerValidationCategory.JSON_SHAPE_INVALID


@pytest.mark.parametrize(
    "question,kind,mentions,seasons,capability,comparison,followup,expected_ids",
    [
        (
            "How did Josh Allen perform in 2022?",
            QuestionType.QB_HISTORY,
            (("Josh Allen", EntityKind.QB),),
            (2022,),
            RequestedCapability.QB_HISTORY,
            False,
            FollowupKind.NONE,
            ("00-0034857",),
        ),
        (
            "Compare Andy Reid and Mike Tomlin's evidence around quarterback development.",
            QuestionType.COMPARISON,
            (("Andy Reid", EntityKind.COACH), ("Mike Tomlin", EntityKind.COACH)),
            (),
            RequestedCapability.COACH_COMPARISON,
            True,
            FollowupKind.NONE,
            ("coach-andy-reid", "coach-mike-tomlin"),
        ),
        (
            "How would Kyler Murray fit Minnesota?",
            QuestionType.PLAYER_SCHEME_ALIGNMENT,
            (("Kyler Murray", EntityKind.QB), ("Minnesota", EntityKind.TEAM)),
            (),
            RequestedCapability.PLAYER_TEAM_DESCRIPTIVE_COMPARISON,
            True,
            FollowupKind.NONE,
            ("00-0035228", "team_min"),
        ),
        (
            "What does the model project for Josh Allen in 2026?",
            QuestionType.QB_PROJECTION,
            (("Josh Allen", EntityKind.QB),),
            (2026,),
            RequestedCapability.QB_PROJECTION,
            False,
            FollowupKind.NONE,
            ("00-0034857",),
        ),
        (
            "Why?",
            QuestionType.COMPARISON,
            (),
            (),
            RequestedCapability.EXPLANATION,
            False,
            FollowupKind.EXPLANATION,
            ("coach-andy-reid", "coach-mike-tomlin"),
        ),
        (
            "What about McVay?",
            QuestionType.COMPARISON,
            (("McVay", EntityKind.COACH),),
            (),
            RequestedCapability.COACH_COMPARISON,
            True,
            FollowupKind.COMPARISON,
            ("coach-andy-reid", "coach-sean-mcvay"),
        ),
    ],
)
def test_golden_wire_to_canonical_authorization(
    evidence,
    question,
    kind,
    mentions,
    seasons,
    capability,
    comparison,
    followup,
    expected_ids,
):
    context = ConversationContext()
    if followup is not FollowupKind.NONE:
        context = ConversationContext(
            turns=(
                ConversationTurn(
                    role=ConversationRole.USER,
                    content=(
                        "Compare Andy Reid and Mike Tomlin's evidence "
                        "around quarterback development."
                    ),
                ),
            ),
            entities=(
                CanonicalEntityReference(kind=EntityKind.COACH, id="coach-andy-reid"),
                CanonicalEntityReference(kind=EntityKind.COACH, id="coach-mike-tomlin"),
            ),
        )
    request = AskV2Request(question=question, context=context)
    authority = AskV2Orchestrator(evidence)
    translator = ProviderDraftTranslator(authority.planner)
    draft = planner_draft(
        kind, mentions, seasons, capability, comparison=comparison, followup=followup
    )
    client = FakeClient(json.dumps(planner_wire(draft).model_dump(mode="json")))
    actual = GroqPlanner(client, groq_configuration()).plan(
        translator.provider_input(request), timeout=9
    )
    assert actual.question_type is kind
    plan = translator.translate(request, actual)
    assert tuple(e.id for e in plan.resolved_by_index.values()) == expected_ids
    authorization = authority.authorizer.authorize(plan.proposal, plan.resolved_by_index)
    assert authorization.approved and not authorization.rejected
    if capability is RequestedCapability.QB_HISTORY:
        assert plan.proposal.question_type is QuestionType.QB_HISTORY
        assert [task.task for task in authorization.approved] == [AnalyticalTask.GET_QB_HISTORY]
    if seasons:
        assert all(
            t.seasons.start_season == seasons[0] and t.seasons.end_season == seasons[0]
            for t in plan.proposal.tasks
        )
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "failure", ["400", "429", "transport", "syntax", "shape", "enum", "semantic"]
)
def test_all_planner_failure_stages_skip_writer_and_never_retry(evidence, failure):
    from openai import BadRequestError
    from openai import RateLimitError as SDKRateLimitError

    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    expected = AskV2Orchestrator(evidence).answer(request)
    if failure in {"400", "429", "transport"}:
        error = ConnectionError("PRIVATE_ERROR_TEXT")
        if failure != "transport":
            response = httpx.Response(int(failure), request=httpx.Request("POST", GROQ_BASE_URL))
            cls = BadRequestError if failure == "400" else SDKRateLimitError
            error = cls("PRIVATE_ERROR_TEXT", response=response, body=None)
        planner = LocalPlanner(evidence, error=error)

        def count():
            return planner.calls
    else:
        wire = planner_wire(
            planner_draft(
                QuestionType.QB_HISTORY,
                (("Josh Allen", EntityKind.QB),),
                (2022,),
                RequestedCapability.QB_HISTORY,
            )
        ).model_dump(mode="json")
        if failure == "enum":
            wire["question_type"] = "PRIVATE_INVALID_ENUM"
        elif failure == "semantic":
            wire["season_mentions"] = [2023]
        raw = (
            "not json" if failure == "syntax" else "{}" if failure == "shape" else json.dumps(wire)
        )
        client = FakeClient(raw)
        planner = GroqPlanner(client, groq_configuration())

        def count():
            return len(client.responses.calls)

    writer = LocalWriter(error=AssertionError("writer cannot run after planner failure"))
    actual = groq_orchestrator(evidence, planner=planner, writer=writer).answer(request)
    assert canonical_json_bytes(actual) == canonical_json_bytes(expected)
    assert count() == 1 and writer.calls == 0


def test_shape_diagnostics_never_enter_public_response_or_server_log(evidence, monkeypatch):
    import io
    import logging

    from nfl_coaching_impact.conversation import provider_telemetry

    stream = io.StringIO()
    logger = logging.Logger("offline_groq_review", level=logging.INFO)
    logger.addHandler(logging.StreamHandler(stream))
    monkeypatch.setattr(provider_telemetry, "_logger", lambda: logger)
    wire = planner_wire(coach_comparison_draft()).model_dump(mode="json")
    wire["question_type"] = "PRIVATE_INVALID_ENUM"
    wire["entity_texts"] = ["PRIVATE_ENTITY_TEXT", "PRIVATE_SECOND_ENTITY"]
    client = FakeClient(json.dumps(wire))
    writer = LocalWriter(error=AssertionError("writer cannot run"))
    request = AskV2Request(question="How did Josh Allen perform in 2022?")
    actual = groq_orchestrator(
        evidence, planner=GroqPlanner(client, groq_configuration()), writer=writer
    ).answer(request)
    log = stream.getvalue()
    assert json.loads(log.splitlines()[-1])["planner_validation_outcome"] == "json_shape_invalid"
    public = canonical_json_bytes(actual).decode("ascii")
    for forbidden in (
        "PRIVATE_INVALID_ENUM",
        "PRIVATE_ENTITY_TEXT",
        "PRIVATE_SECOND_ENTITY",
        "planner_structure",
        "invalid_enum_field_name",
    ):
        assert forbidden not in log and forbidden not in public
    assert request.question not in log
    assert writer.calls == 0

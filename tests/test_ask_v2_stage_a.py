"""Stage A contract, security, compatibility, and scope gates for Ask v2."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.api import app
from nfl_coaching_impact.ask_api import _load
from nfl_coaching_impact.conversation.contracts import (
    AnalyticalTaskProposal,
    AskV2Request,
    AskV2Response,
    CanonicalEntityReference,
    ConversationContext,
    ConversationTurn,
    EvidencePackage,
    EvidenceRecord,
    PlannerEntityProposal,
    PlannerProposal,
    PublicEvidencePoint,
    SupportedFollowUp,
    contract_schema_sha256,
    stage_a_versions,
)
from nfl_coaching_impact.conversation.enums import (
    AnalyticalTask,
    Answerability,
    AnswerMode,
    ConclusionKind,
    ConversationRole,
    EntityKind,
    EvidenceKind,
    QuestionType,
    ReasonCode,
)
from nfl_coaching_impact.conversation.policy import (
    SCIENTIFIC_POLICIES,
    SCIENTIFIC_POLICY_VERSION,
)
from nfl_coaching_impact.conversation.serialization import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DATABASE_IDENTITY = "133fbdd880801b935de0ab7fdf859daff12bf706041a66511de5532ef2169a1a"


def valid_request_payload() -> dict:
    return {
        "question": "How did Josh Allen perform in 2022?",
        "context": {
            "turns": [{"role": "user", "content": "Show Buffalo quarterbacks."}],
            "entities": [{"kind": "qb", "id": "00-0034857"}],
            "seasons": {"start_season": 2022, "end_season": 2022},
        },
    }


def valid_planner_payload() -> dict:
    return {
        "question_type": "QB_HISTORY",
        "entities": [{"kind": "qb", "mention": "Josh Allen"}],
        "tasks": [{"task": "GET_QB_HISTORY", "entity_indexes": [0]}],
        "requested_outputs": ["DIRECT_ANSWER", "EVIDENCE"],
        "context_dependencies": ["NONE"],
    }


def evidence_record(index: int) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"evidence_{index}",
        kind=EvidenceKind.QB_HISTORY,
        summary=f"Approved evidence {index}",
    )


def test_valid_request_and_bounded_context_validate():
    request = AskV2Request.model_validate(valid_request_payload())
    assert request.question == "How did Josh Allen perform in 2022?"
    assert len(request.context.turns) == 1
    assert request.context.entities[0].id == "00-0034857"

    bounded = AskV2Request(
        question="Compare the established historical context.",
        context=ConversationContext(
            turns=tuple(
                ConversationTurn(role=ConversationRole.USER, content="x" * 1_000) for _ in range(8)
            ),
            entities=(
                CanonicalEntityReference(kind=EntityKind.TEAM, id="team_buf"),
                CanonicalEntityReference(kind=EntityKind.QB, id="00-0034857"),
            ),
        ),
    )
    assert sum(len(turn.content) for turn in bounded.context.turns) == 8_000
    assert [entity.kind for entity in bounded.context.entities] == [EntityKind.QB, EntityKind.TEAM]

    single_turn = AskV2Request(
        question="Use the complete prior context.",
        context=ConversationContext(
            turns=(ConversationTurn(role=ConversationRole.USER, content="x" * 8_000),)
        ),
    )
    assert len(single_turn.context.turns[0].content) == 8_000


def test_answerability_and_conclusion_vocabularies_are_closed():
    assert {value.value for value in Answerability} == {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "CLARIFICATION_REQUIRED",
        "DATA_UNAVAILABLE",
    }
    assert {value.value for value in ConclusionKind} == {
        "HISTORICAL_FACT",
        "DESCRIPTIVE_COMPARISON",
        "VERIFIED_ROLE_ATTRIBUTION",
        "DEVELOPMENT_QUALITY",
        "PLAYER_SCHEME_DESCRIPTIVE_ALIGNMENT",
        "PREDICTIVE_FIT",
        "CAUSAL",
        "NUMERICAL_COMPARISON_WINNER",
    }


@pytest.mark.parametrize(
    "target,payload",
    [
        (AskV2Request, {**valid_request_payload(), "sql": "SELECT 1"}),
        (
            AskV2Request,
            {
                "question": "Show the prior result.",
                "context": {"turns": [], "entities": [], "private_path": "/tmp/data"},
            },
        ),
    ],
)
def test_unknown_request_and_context_fields_fail(target, payload):
    with pytest.raises(ValidationError):
        target.model_validate(payload)


@pytest.mark.parametrize("question", ["x ", "x" * 1_001])
def test_question_length_bounds_fail(question):
    with pytest.raises(ValidationError):
        AskV2Request(question=question)


def test_more_than_eight_turns_fails():
    with pytest.raises(ValidationError):
        AskV2Request(
            question="Show the prior historical context.",
            context={
                "turns": [{"role": "user", "content": "context"}] * 9,
            },
        )


def test_more_than_eight_thousand_context_characters_fails():
    with pytest.raises(ValidationError, match="8000"):
        AskV2Request(
            question="Show the prior historical context.",
            context={
                "turns": [{"role": "user", "content": "x" * 1_700}] * 5,
            },
        )


def test_more_than_eight_canonical_entities_fails():
    entities = [{"kind": "qb", "id": f"00-{index:07d}"} for index in range(9)]
    with pytest.raises(ValidationError):
        AskV2Request(
            question="Compare these historical quarterbacks.", context={"entities": entities}
        )


def test_season_context_is_bounded_and_ordered():
    for seasons in (
        {"start_season": 2009, "end_season": 2010},
        {"start_season": 2026, "end_season": 2027},
        {"start_season": 2024, "end_season": 2023},
    ):
        with pytest.raises(ValidationError):
            AskV2Request(question="Show historical seasons.", context={"seasons": seasons})


def test_planner_task_count_and_allowlist_are_closed():
    payload = valid_planner_payload()
    payload["tasks"] = [{"task": AnalyticalTask.GET_QB_HISTORY.value, "entity_indexes": [0]}] * 13
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate(payload)

    payload = valid_planner_payload()
    payload["tasks"] = [{"task": "RUN_ARBITRARY_CODE", "entity_indexes": [0]}]
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sql", "SELECT * FROM private_table"),
        ("path", "/private/snapshot"),
        ("url", "https://example.test/data"),
        ("python", "import os"),
        ("shell_command", "env"),
        ("function", "dangerous_lookup"),
        ("module", "subprocess"),
        ("database_url", "postgresql://example"),
        ("snapshot_directory", "/tmp/snapshot"),
        ("scientific_status", "SUPPORTED"),
        ("model_approval", "APPROVED"),
        ("conclusion_permissions", [{"kind": "CAUSAL", "decision": "ALLOWED"}]),
        ("calculation", {"expression": "epa * 10"}),
    ],
)
def test_planner_rejects_executable_location_and_scientific_control_fields(field, value):
    payload = valid_planner_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate(payload)


@pytest.mark.parametrize(
    "mention",
    ["https://example.test/player", "/private/player", "~/player", "`whoami`", "$(env)"],
)
def test_planner_entity_mentions_reject_urls_paths_and_executable_syntax(mention):
    with pytest.raises(ValidationError):
        PlannerEntityProposal(kind=EntityKind.QB, mention=mention)


def test_planner_task_cannot_reference_an_absent_entity():
    with pytest.raises(ValidationError):
        PlannerProposal(
            question_type=QuestionType.QB_HISTORY,
            entities=(),
            tasks=(
                AnalyticalTaskProposal(
                    task=AnalyticalTask.GET_QB_HISTORY,
                    entity_indexes=(0,),
                ),
            ),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "qb", "id": "Josh Allen"},
        {"kind": "qb", "id": "00-123"},
        {"kind": "coach", "id": "coach_andy_reid"},
        {"kind": "team", "id": "BUF"},
        {"kind": "team", "id": "team_buf", "path": "/tmp"},
    ],
)
def test_malformed_canonical_entity_context_fails(payload):
    with pytest.raises(ValidationError):
        CanonicalEntityReference.model_validate(payload)


def test_evidence_package_over_thirty_two_records_fails():
    with pytest.raises(ValidationError):
        EvidencePackage(
            answerability=Answerability.SUPPORTED,
            evidence=tuple(evidence_record(index) for index in range(33)),
            versions=stage_a_versions(),
        )


def test_public_evidence_and_follow_up_limits_fail_closed():
    points = tuple(
        PublicEvidencePoint(
            rank=((index - 1) % 5) + 1,
            evidence_id=f"evidence_{index}",
            summary="Evidence",
        )
        for index in range(1, 7)
    )
    with pytest.raises(ValidationError):
        AskV2Response(
            answerability=Answerability.SUPPORTED,
            answer_mode=AnswerMode.DETERMINISTIC,
            answer="Supported answer.",
            evidence=points,
            versions=stage_a_versions(),
        )

    follow_ups = tuple(
        SupportedFollowUp(label=f"Follow-up {index}", question="Show another supported result.")
        for index in range(5)
    )
    with pytest.raises(ValidationError):
        AskV2Response(
            answerability=Answerability.SUPPORTED,
            answer_mode=AnswerMode.DETERMINISTIC,
            answer="Supported answer.",
            follow_ups=follow_ups,
            versions=stage_a_versions(),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_cannot_enter_contract_or_serializer(value):
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="evidence_1",
            kind=EvidenceKind.QB_HISTORY,
            summary="Evidence",
            values=({"name": "epa", "value": value},),
        )
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"value": value})


def test_equivalent_contracts_serialize_identically():
    left = AskV2Request.model_validate(valid_request_payload())
    payload = valid_request_payload()
    payload["context"]["entities"] = [
        {"kind": "team", "id": "team_buf"},
        {"kind": "qb", "id": "00-0034857"},
    ]
    right_payload = valid_request_payload()
    right_payload["context"]["entities"] = list(reversed(payload["context"]["entities"]))
    right = AskV2Request.model_validate(right_payload)
    normalized_left = AskV2Request.model_validate(
        {
            **valid_request_payload(),
            "context": {
                **valid_request_payload()["context"],
                "entities": payload["context"]["entities"],
            },
        }
    )
    assert canonical_json_bytes(normalized_left) == canonical_json_bytes(right)
    assert canonical_json_bytes(left) == canonical_json_bytes(left)
    assert contract_schema_sha256() == contract_schema_sha256()


def test_scientific_policy_is_frozen_and_hashed():
    assert SCIENTIFIC_POLICIES["C15_PLAYER_SCHEME_FIT"].status == "NOT ESTIMABLE / DATA-LIMITED"
    assert SCIENTIFIC_POLICIES["C17_SCENARIO"].status == "NOT SUPPORTED"
    assert SCIENTIFIC_POLICIES["C18_COUNTERFACTUAL"].status == "NOT READY / NOT IMPLEMENTED"
    assert SCIENTIFIC_POLICIES["C20_ROOKIE_PROJECTION"].status == "NOT ESTIMABLE / DATA-LIMITED"
    assert SCIENTIFIC_POLICY_VERSION.startswith("ask-policy-")
    with pytest.raises(TypeError):
        SCIENTIFIC_POLICIES["C17_SCENARIO"] = SCIENTIFIC_POLICIES["C16_EPA_PROJECTION"]


def test_ask_v2_returns_honest_temporary_deterministic_response(monkeypatch):
    def block_network(*_args, **_kwargs):
        raise AssertionError("Stage A must not invoke a provider or network")

    monkeypatch.setattr(socket, "create_connection", block_network)
    response = TestClient(app).post("/ask/v2", json=valid_request_payload())
    assert response.status_code == 200
    parsed = AskV2Response.model_validate(response.json())
    assert parsed.answerability is Answerability.NOT_SUPPORTED
    assert parsed.answer_mode is AnswerMode.DETERMINISTIC
    assert parsed.reason_code is ReasonCode.IMPLEMENTATION_NOT_AVAILABLE_YET
    assert parsed.entities == () and parsed.evidence == () and parsed.propositions == ()
    assert parsed.uncertainty == ()
    assert parsed.versions.analytical_data_version is None
    assert parsed.versions.analytical_model_versions == ()
    assert parsed.versions.planner_model_version is None
    assert parsed.versions.synthesizer_model_version is None


def test_ask_v2_schema_errors_are_422_and_never_truncated():
    client = TestClient(app)
    assert client.post("/ask/v2", json={"question": "x"}).status_code == 422
    assert client.post("/ask/v2", json={"question": "x" * 1_001}).status_code == 422
    unsafe = {**valid_request_payload(), "sql": "SELECT 1"}
    assert client.post("/ask/v2", json=unsafe).status_code == 422


def test_existing_ask_behavior_and_snapshot_remain_valid(monkeypatch):
    snapshot = ROOT / "data/processed/ask_anything" / release.VERSION
    service = release.validate(snapshot)
    assert service.version == release.VERSION
    monkeypatch.setenv("ASK_DATA_DIR", str(snapshot))
    _load.cache_clear()
    response = TestClient(app).post("/ask", json={"question": "Josh Allen performance 2022"})
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "ask-v1"
    assert body["status"] == "SUPPORTED"
    assert body["intent"] == "QB_HISTORY"
    assert "answerability" not in body and "answer_mode" not in body
    _load.cache_clear()


def test_database_and_migrations_are_unchanged_from_stage_a_baseline():
    paths = [
        ROOT / "db/schema.sql",
        *sorted((ROOT / "db/migrations").rglob("*.py")),
        *sorted((ROOT / "db/migrations").rglob("*.mako")),
    ]
    paths.extend(sorted((ROOT / "db/migrations").rglob("*.sql")))
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    assert digest.hexdigest() == BASELINE_DATABASE_IDENTITY

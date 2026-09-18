"""Composition quality/security gates against the unchanged real frozen bundle."""

from __future__ import annotations

import socket

import pytest
from test_ask_v2_answer_writer import (
    ALLEN,
    KYLER,
    PROJECTION,
    REID,
    brief_for,
)
from test_ask_v2_answer_writer import engine as engine
from test_ask_v2_answer_writer import evidence as evidence
from test_ask_v2_groq_provider import LocalPlanner, LocalWriter, groq_configuration

from nfl_coaching_impact.conversation.answer_writer import (
    BriefSupportKind,
    WriterRejected,
    approved_answer_brief,
    entity_catalog,
)
from nfl_coaching_impact.conversation.contracts import AskV2Request
from nfl_coaching_impact.conversation.enums import AnswerMode
from nfl_coaching_impact.conversation.provider_orchestration import ProviderOrchestrator
from nfl_coaching_impact.conversation.providers import ProviderRuntime
from nfl_coaching_impact.conversation.serialization import canonical_json_bytes
from nfl_coaching_impact.conversation.writer_composition import (
    CompositionPlan,
    approved_phrases,
    composition_provider_input,
    validate_composition,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("no live calls"))


def composed_plan(brief, *, alternative=False):
    phrases = approved_phrases(brief)
    facts = [s for s in brief.supports if s.kind is BriefSupportKind.PROPOSITION]
    if alternative and len(facts) > 1:
        facts = [*facts[1:], facts[0]]

    def item(support, connector="none"):
        variants = [p for p in phrases if p.support_id == support.support_id]
        return {"phrase_id": variants[-1 if alternative else 0].phrase_id, "connector": connector}

    fact_items = [item(s) for s in facts]
    limits = [item(s) for s in brief.supports if s.support_id in brief.required_limitation_ids]
    if alternative and limits:
        limits[0]["connector"] = "limitation_transition"
        paragraphs = [{"items": [fact_items[0], *limits]}, {"items": fact_items[1:]}]
        paragraphs = [p for p in paragraphs if p["items"]]
    else:
        paragraphs = [{"items": fact_items}, *([{"items": limits}] if limits else [])]
    return CompositionPlan.model_validate({"paragraphs": paragraphs})


def render(engine, brief, plan):
    return validate_composition(
        plan, brief, catalog=entity_catalog(engine.evidence.analytical.entities)
    )


@pytest.mark.parametrize("question", [ALLEN, REID, KYLER, PROJECTION])
def test_two_valid_plans_have_distinct_grounded_prose(engine, question):
    brief = brief_for(engine, question)
    one, two = [
        render(engine, brief, composed_plan(brief, alternative=alt)) for alt in (False, True)
    ]
    assert one != two
    for text in (one, two):
        assert 1 <= len(text.split("\n\n")) <= 3
        assert len(text.split()) <= 180
        assert "phrase_" not in text and "proposition_" not in text
        for sid in brief.required_limitation_ids:
            assert next(s.text for s in brief.supports if s.support_id == sid) in text
    if question == ALLEN:
        assert all(token in one for token in ("0.237", "0.122", "+0.115", "651", "2022"))
        assert "limitation" not in one and not brief.required_limitation_ids
    elif question == REID:
        assert "Mike Tomlin's documented team history includes 38" in one
        assert "Andy Reid's documented team history includes 38" in one
        assert "not proof of better quarterback development" in one
        assert "cannot isolate either coach as the cause" in one
    elif question == KYLER:
        assert all(token in one for token in ("10.5%", "12.8%", "6.5%", "2.8%"))
        assert "cannot forecast performance or improvement with a different team" in one
    else:
        assert all(token in one for token in ("team-independent", "0.120", "-0.248", "0.488"))
        assert "not future PAE" in one


@pytest.mark.parametrize(
    "kind,questions",
    [
        (
            "qb",
            [
                "Tell me about Aaron Rodgers in 2011.",
                "What about the next season?",
                "Who coached him?",
            ],
        ),
        (
            "coach",
            [
                "Who was Mike McCarthy?",
                "Which quarterbacks shared Mike McCarthy's team-seasons?",
                "Show verified offensive roles",
            ],
        ),
    ],
)
def test_contextual_goldens_render_real_approved_roles(engine, kind, questions):
    context = {"turns": [], "entities": []}
    for question in questions:
        result = engine.analyze(AskV2Request(question=question, context=context))
        brief = approved_answer_brief(result)
        answer = render(engine, brief, composed_plan(brief))
        context["entities"] = [
            {"kind": e.kind.value, "id": e.id}
            for e in result.response.entities
            if e.kind.value == kind
        ]
        context["turns"].append({"role": "user", "content": question})
        context["seasons"] = (
            result.plan.proposal.tasks[0].seasons.model_dump()
            if result.plan.proposal.tasks[0].seasons
            else None
        )
    assert "verified" in answer and "recorded assignment" in answer
    if kind == "qb":
        assert "2012" in answer
        assert "Mike McCarthy" in answer
    else:
        assert "not a measure of coaching effectiveness" in answer
        assert "Mike McCarthy" in answer
        assert "play caller" in answer or "offensive coordinator" in answer
        assert "head coach role" not in answer


@pytest.mark.parametrize(
    "attack",
    [
        "wrong_entity",
        "wrong_season",
        "wrong_measurement",
        "unknown_phrase",
        "unknown_connector",
        "missing_limitation",
        "wrong_limitation",
        "repeat_phrase",
        "repeat_support_variant",
        "excess_paragraphs",
        "malformed",
        "omit_primary",
        "custom_text",
        "notes",
        "reasoning",
        "text",
        "explanation",
        "freeform_transition",
        "sql",
        "empty_paragraph",
        "limit_connector_on_fact",
        "initial_connector",
    ],
)
def test_adversarial_plan_is_atomic_exact_fallback(evidence, engine, attack):
    request = AskV2Request(question=KYLER)
    brief = brief_for(engine, KYLER)
    plan = composed_plan(brief).model_dump(mode="json")
    first = plan["paragraphs"][0]["items"][0]
    if attack in {"wrong_entity", "wrong_season", "wrong_measurement", "wrong_limitation"}:
        other = brief_for(engine, PROJECTION if attack == "wrong_limitation" else ALLEN)
        if attack == "wrong_season":
            other = brief_for(engine, "How did Kyler Murray perform in 2022?")
        elif attack == "wrong_measurement":
            # Same support identity, changed approved bytes: a hash from another
            # catalog cannot attach its measurements to this backend result.
            support = brief.supports[0].model_copy(
                update={"text": "Other measured rate: 99%.", "phrasings": ()}
            )
            other = brief.model_copy(update={"supports": (support, *brief.supports[1:])})
        phrase = next(
            p
            for p in approved_phrases(other)
            if (p.kind is BriefSupportKind.LIMITATION if attack == "wrong_limitation" else True)
        )
        first["phrase_id"] = phrase.phrase_id
    elif attack == "unknown_phrase":
        first["phrase_id"] = "phrase_0000000000000000"
    elif attack == "unknown_connector":
        first["connector"] = "because_of_the_coach"
    elif attack == "missing_limitation":
        plan["paragraphs"] = plan["paragraphs"][:1]
    elif attack == "repeat_phrase":
        plan["paragraphs"][0]["items"].append(first.copy())
    elif attack == "repeat_support_variant":
        variant = [
            p for p in approved_phrases(brief) if p.support_id == brief.supports[0].support_id
        ][-1]
        plan["paragraphs"][0]["items"].append({"phrase_id": variant.phrase_id, "connector": "none"})
    elif attack == "excess_paragraphs":
        plan["paragraphs"] *= 2
    elif attack == "malformed":
        plan = {"paragraphs": "answer goes here"}
    elif attack == "omit_primary":
        plan["paragraphs"][0]["items"].pop(0)
    elif attack == "empty_paragraph":
        plan["paragraphs"][0]["items"] = []
    elif attack == "limit_connector_on_fact":
        plan["paragraphs"][0]["items"][1]["connector"] = "limitation_transition"
    elif attack == "initial_connector":
        first["connector"] = "contrast"
    else:
        first[attack] = "UNTRUSTED factual prose"
    with pytest.raises(WriterRejected):
        render(engine, brief, plan)
    planner, writer = LocalPlanner(evidence), LocalWriter(value=plan)
    runtime = ProviderRuntime(groq_configuration(), planner=planner, writer=writer)
    assert ProviderOrchestrator(evidence, runtime).answer(request) == engine.answer(request)
    assert planner.calls == writer.calls == 1


def test_definition_optional_and_safe_connectors_render_only_backend_text(engine):
    brief = brief_for(engine)
    plan = composed_plan(brief).model_dump(mode="json")
    definition = next(p for p in approved_phrases(brief) if p.kind is BriefSupportKind.DEFINITION)
    plan["paragraphs"][0]["items"].append(
        {"phrase_id": definition.phrase_id, "connector": "continuation"}
    )
    assert "Also, Performance Above Expectation" in render(engine, brief, plan)
    assert definition.text not in render(engine, brief, composed_plan(brief))


@pytest.mark.parametrize("connector", ["contrast", "comparison", "continuation"])
def test_safe_connector_has_no_causal_inference(engine, connector):
    brief = brief_for(engine, REID)
    plan = composed_plan(brief).model_dump(mode="python")
    plan["paragraphs"][0]["items"][1]["connector"] = connector
    assert "cannot isolate either coach as the cause" in render(engine, brief, plan)


def test_phrase_identity_determinism_scope_and_complete_answer_budget(engine):
    brief = brief_for(engine, KYLER)
    assert canonical_json_bytes(approved_phrases(brief)) == canonical_json_bytes(
        approved_phrases(brief_for(engine, KYLER))
    )
    plan = composed_plan(brief)
    text = render(engine, brief, plan)
    short = brief.model_copy(update={"maximum_words": len(text.split()) - 1})
    with pytest.raises(WriterRejected):
        render(engine, short, plan)
    # Wire catalog keeps supported values/context, without duplicate measurement
    # records or entity plumbing; authorization is checked against the full brief.
    assert len(canonical_json_bytes(composition_provider_input(brief))) < 4000


def test_normal_provider_accepts_plan_never_legacy_text(evidence, engine):
    brief = brief_for(engine)
    from test_ask_v2_groq_provider import compliant_writer_result

    for value, mode in [
        (composed_plan(brief), AnswerMode.GROUNDED_AI),
        (compliant_writer_result(brief), AnswerMode.DETERMINISTIC),
    ]:
        runtime = ProviderRuntime(
            groq_configuration(), planner=LocalPlanner(evidence), writer=LocalWriter(value=value)
        )
        response = ProviderOrchestrator(evidence, runtime).answer(AskV2Request(question=ALLEN))
        assert response.answer_mode is mode


def test_former_qb_and_current_coach_name_keeps_backend_resolved_identity(engine):
    brief = brief_for(engine, "Which quarterbacks shared Mike McCarthy's team-seasons?")
    phrase = next(p for p in approved_phrases(brief) if "Scott Tolzien" in p.text)
    assert "00-0028595" in phrase.entity_ids
    assert "coach-scott-tolzien" not in phrase.entity_ids
    assert "Scott Tolzien" in render(engine, brief, composed_plan(brief))


def test_all_composition_fields_are_instruction_only():
    schema = CompositionPlan.model_json_schema()
    assert set(schema["properties"]) == {"paragraphs"}
    assert set(schema["$defs"]["CompositionParagraph"]["properties"]) == {"items"}
    assert set(schema["$defs"]["CompositionItem"]["properties"]) == {"phrase_id", "connector"}


def test_paragraph_and_total_item_caps_cannot_be_bypassed(engine):
    phrases = approved_phrases(brief_for(engine, KYLER))
    items = [{"phrase_id": p.phrase_id, "connector": "none"} for p in phrases]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CompositionPlan.model_validate({"paragraphs": [{"items": items[:9]}]})
    with pytest.raises(ValidationError):
        CompositionPlan.model_validate({"paragraphs": [{"items": []}]})
    unique_items = [
        {"phrase_id": f"phrase_{index:016x}", "connector": "none"} for index in range(17)
    ]
    with pytest.raises(ValidationError):
        CompositionPlan.model_validate(
            {
                "paragraphs": [
                    {"items": unique_items[:8]},
                    {"items": unique_items[8:16]},
                    {"items": unique_items[16:]},
                ]
            }
        )

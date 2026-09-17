"""Real frozen-evidence regressions for connected Ask interpretation/context."""

from pathlib import Path

import pytest

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.conversation.contracts import AskV2Request
from nfl_coaching_impact.conversation.enums import AnalyticalTask, EntityKind, QuestionType
from nfl_coaching_impact.conversation.evidence import EvidenceService
from nfl_coaching_impact.conversation.orchestration import AskV2Orchestrator


@pytest.fixture(scope="module")
def orchestrator():
    root = Path(__file__).resolve().parents[1]
    return AskV2Orchestrator(
        EvidenceService(release.validate(root / "data/processed/ask_anything" / release.VERSION))
    )


def test_ordinary_was_is_not_washington_but_explicit_abbreviation_is(orchestrator):
    planner = orchestrator.planner
    question = "Who was coaching Aaron Rodgers during his best seasons?"
    plan = planner.plan(AskV2Request(question=question))
    assert [entity.kind for entity in plan.resolved_by_index.values()] == [EntityKind.QB]
    assert plan.proposal.question_type is QuestionType.QB_COACHING_CONTEXT
    assert plan.proposal.tasks[0].task is AnalyticalTask.GET_QB_COACHING_CONTEXT
    explicit = planner.plan(AskV2Request(question="What offense did WAS run in 2022?"))
    assert {entity.id for entity in explicit.resolved_by_index.values()} == {"team_was"}


def test_best_season_context_uses_exact_source_team_season_and_verified_citations(orchestrator):
    result = orchestrator.analyze(
        AskV2Request(question="Who was coaching Aaron Rodgers during his best seasons?")
    )
    rows = sorted(
        (
            row
            for row in orchestrator.evidence.analytical.index["history"]["00-0023459"]
            if row["qualifies_default"] and row["epa_per_dropback"] is not None
        ),
        key=lambda row: (-row["epa_per_dropback"], -row["season"], row["team_id"]),
    )[:3]
    keys = {(row["team_id"], row["season"]) for row in rows}
    history = [record for record in result.package.evidence if record.kind.value == "QB_HISTORY"]
    assert {(record.entities[1].id, record.season) for record in history} == keys
    assignments = [
        record for record in result.package.evidence if record.kind.value == "COACH_ASSIGNMENT"
    ]
    assert assignments
    for record in assignments:
        fields = {value.name: value.value for value in record.values}
        assert (record.entities[1].id, record.season) in keys
        assert fields["verification_status"] == "verified"
        assert record.sources
        assert all(source.source_url for source in record.sources)
    assert "coach-mike-mccarthy" in {entity.id for entity in result.response.entities}
    assert "Mike McCarthy" in result.response.answer
    assert "proof that one coach caused" in result.response.answer
    assert any("200 dropbacks" in line for line in result.response.limitations)


def test_coach_context_summary_uses_public_football_language(orchestrator):
    result = orchestrator.analyze(
        AskV2Request(question="Which quarterbacks shared Mike McCarthy's team-seasons?")
    )
    assert "quarterback seasons on the same teams" in result.response.answer
    assert "context observations" not in result.response.answer
    assert "distinct verified" not in result.response.answer


def test_new_named_player_does_not_inherit_unrelated_season(orchestrator):
    request = AskV2Request(
        question="Who was coaching Aaron Rodgers during his best seasons?",
        context={
            "entities": [{"kind": "qb", "id": "00-0034857"}],
            "seasons": {"start_season": 2022, "end_season": 2022},
        },
    )
    assert orchestrator.planner.plan(request).proposal.tasks[0].seasons is None


@pytest.mark.parametrize("question", ["What about Sean McVay?", "What about McVay?"])
def test_short_comparison_replacement_survives_why(orchestrator, question):
    request = AskV2Request(
        question=question,
        context={
            "entities": [
                {"kind": "coach", "id": "coach-andy-reid"},
                {"kind": "coach", "id": "coach-mike-tomlin"},
            ],
            "turns": [
                {"role": "user", "content": "Compare Andy Reid and Mike Tomlin."},
                {"role": "user", "content": "Why?"},
            ],
        },
    )
    plan = orchestrator.planner.plan(request)
    assert [entity.id for entity in plan.resolved_by_index.values()] == [
        "coach-andy-reid",
        "coach-sean-mcvay",
    ]
    assert plan.proposal.question_type is QuestionType.COMPARISON


def test_ambiguous_replacement_does_not_silently_keep_old_players(orchestrator):
    response = orchestrator.answer(
        AskV2Request(
            question="How about Allen?",
            context={
                "entities": [{"kind": "qb", "id": "00-0023459"}, {"kind": "qb", "id": "00-0005106"}]
            },
        )
    )
    assert response.answerability.value == "CLARIFICATION_REQUIRED"
    assert response.clarification_candidates
    assert response.propositions == ()


def test_unknown_named_replacement_does_not_silently_keep_the_old_pair(orchestrator):
    response = orchestrator.answer(
        AskV2Request(
            question="What about NotARealCoach?",
            context={
                "entities": [
                    {"kind": "coach", "id": "coach-andy-reid"},
                    {"kind": "coach", "id": "coach-mike-tomlin"},
                ]
            },
        )
    )
    assert response.answerability.value == "CLARIFICATION_REQUIRED"
    assert response.entities == ()
    assert response.propositions == ()


def test_multi_team_qb_coaching_context_never_crosses_team(orchestrator):
    result = orchestrator.evidence.qb_coaching_context("00-0025479", 2010)
    history = [record for record in result.records if record.kind.value == "QB_HISTORY"]
    assert {record.entities[1].id for record in history} == {"team_buf", "team_jax"}
    for record in result.records:
        if record.kind.value == "COACH_ASSIGNMENT":
            assert record.entities[1].id in {"team_buf", "team_jax"}
            assert record.season == 2010


def test_no_qualifying_history_does_not_invent_best_seasons(orchestrator):
    result = orchestrator.evidence.qb_coaching_context("00-0023459", 2026, best_seasons=True)
    assert result.records == ()


def test_best_season_followup_does_not_reuse_one_prior_observed_season(orchestrator):
    request = AskV2Request(
        question="Who was coaching Aaron Rodgers during his best seasons?",
        context={
            "entities": [{"kind": "qb", "id": "00-0023459"}],
            "seasons": {"start_season": 2022, "end_season": 2022},
        },
    )
    assert orchestrator.planner.plan(request).proposal.tasks[0].seasons is None


def test_historical_relative_season_is_bounded_and_not_a_new_forecast(orchestrator):
    response = orchestrator.answer(
        AskV2Request(
            question="What about the next season?",
            context={
                "turns": [{"role": "user", "content": "Tell me about Aaron Rodgers in 2011"}],
                "entities": [{"kind": "qb", "id": "00-0023459"}],
                "seasons": {"start_season": 2011, "end_season": 2011},
            },
        )
    )
    assert {item.season for item in response.propositions} == {2012}
    assert "2012" in response.answer


def test_two_qb_coaching_followup_keeps_both_canonical_histories(orchestrator):
    result = orchestrator.analyze(
        AskV2Request(
            question="Which coaches were involved in Aaron Rodgers' and Brett Favre's best seasons?"
        )
    )
    assert len(result.plan.proposal.tasks) == 2
    history = [record for record in result.package.evidence if record.kind.value == "QB_HISTORY"]
    assert {record.entities[0].id for record in history} == {"00-0023459", "00-0005106"}
    assert "Aaron Rodgers recorded" in result.response.answer
    assert "Brett Favre recorded" in result.response.answer


def test_generated_limitation_question_retains_descriptive_scenario(orchestrator):
    response = orchestrator.answer(
        AskV2Request(
            question="Which parts are descriptive rather than predictive?",
            context={
                "turns": [{"role": "user", "content": "How would Kyler Murray fit Minnesota?"}],
                "entities": [
                    {"kind": "qb", "id": "00-0035228"},
                    {"kind": "team", "id": "team_min"},
                ],
            },
        )
    )
    assert response.answerability.value == "PARTIALLY_SUPPORTED"
    assert response.reason_code.value == "C17_SCENARIO_NOT_SUPPORTED"


def test_entity_specific_coach_followup_only_retrieves_that_coach(orchestrator):
    response = orchestrator.answer(
        AskV2Request(
            question="Which quarterbacks shared Andy Reid's team-seasons?",
            context={
                "entities": [
                    {"kind": "coach", "id": "coach-andy-reid"},
                    {"kind": "coach", "id": "coach-mike-tomlin"},
                ]
            },
        )
    )
    assert [entity.id for entity in response.entities] == ["coach-andy-reid"]
    assert response.evidence


def test_unspecified_two_qb_context_retains_retired_history_without_overriding_explicit_year(
    orchestrator,
):
    comparison = orchestrator.answer(
        AskV2Request(question="Compare Aaron Rodgers and Brett Favre.")
    )
    history = [
        item for item in comparison.propositions if item.predicate == "historical_qb_performance"
    ]
    assert {item.subject for item in history} == {"Aaron Rodgers", "Brett Favre"}
    assert {item.season for item in history} == {2010}
    assert "2010" in comparison.answer
    assert "EPA/dropback" in comparison.answer
    assert "same-season comparison, not a career ranking" in comparison.answer
    explicit = orchestrator.answer(
        AskV2Request(question="Compare Aaron Rodgers and Brett Favre in 2025.")
    )
    assert {item.season for item in explicit.propositions} == {2025}
    assert not any(item.subject == "Brett Favre" for item in explicit.propositions)


def test_connected_context_is_byte_deterministic_and_snapshot_unchanged(orchestrator):
    before = orchestrator.evidence.analytical.version
    request = AskV2Request(question="Who was coaching Aaron Rodgers during his best seasons?")
    first = orchestrator.answer(request)
    assert first.model_dump_json() == orchestrator.answer(request).model_dump_json()
    assert orchestrator.evidence.analytical.version == before == release.VERSION


@pytest.mark.parametrize("question", ["Who coached him?", "Who was coaching him?"])
def test_pronoun_coaching_followup_keeps_player_and_historical_season(orchestrator, question):
    result = orchestrator.analyze(
        AskV2Request(
            question=question,
            context={
                "turns": [
                    {"role": "user", "content": "Tell me about Aaron Rodgers in 2011."},
                    {"role": "user", "content": "What about the next season?"},
                ],
                "entities": [{"kind": "qb", "id": "00-0023459"}],
                "seasons": {"start_season": 2012, "end_season": 2012},
            },
        )
    )
    assert result.plan.proposal.question_type is QuestionType.QB_COACHING_CONTEXT
    assert result.response.answerability.value == "SUPPORTED"
    assert "Mike McCarthy" in result.response.answer
    assert {record.season for record in result.package.evidence} == {2012}
    assert "proof that one coach caused" in result.response.answer


@pytest.mark.parametrize("question", ["Who was Mike McCarthy?", "Who is Mike McCarthy?"])
def test_coach_information_question_uses_verified_history_not_clarification(orchestrator, question):
    result = orchestrator.analyze(AskV2Request(question=question))
    assert result.plan.proposal.question_type is QuestionType.COACH_HISTORY
    assert result.response.answerability.value == "SUPPORTED"
    assert [entity.id for entity in result.response.entities] == ["coach-mike-mccarthy"]
    assert result.package.evidence
    assert all(record.sources for record in result.package.evidence)


def test_pronoun_subject_does_not_become_navigation_staff_or_an_arbitrary_qb(orchestrator):
    context = {
        "entities": [
            {"kind": "qb", "id": "00-0023459"},
            {"kind": "coach", "id": "coach-mike-mccarthy"},
        ],
        "seasons": {"start_season": 2012, "end_season": 2012},
    }
    plan = orchestrator.planner.plan(AskV2Request(question="Who coached him?", context=context))
    assert [entity.id for entity in plan.resolved_by_index.values()] == ["00-0023459"]
    assert plan.proposal.question_type is QuestionType.QB_COACHING_CONTEXT
    context["entities"].append({"kind": "qb", "id": "00-0005106"})
    response = orchestrator.answer(AskV2Request(question="Who coached him?", context=context))
    assert response.answerability.value == "CLARIFICATION_REQUIRED"
    assert not response.propositions


def test_why_explains_documented_roles_without_a_development_winner(orchestrator):
    result = orchestrator.analyze(
        AskV2Request(
            question="Why?",
            context={
                "turns": [
                    {
                        "role": "user",
                        "content": (
                            "Compare Andy Reid and Mike Tomlin's evidence "
                            "around quarterback development."
                        ),
                    }
                ],
                "entities": [
                    {"kind": "coach", "id": "coach-andy-reid"},
                    {"kind": "coach", "id": "coach-mike-tomlin"},
                ],
            },
        )
    )
    assert result.response.answerability.value == "PARTIALLY_SUPPORTED"
    assert "documented responsibilities" in result.response.answer
    summaries = {
        record.entities[0].display_name: next(
            value.value for value in record.values if value.name == "verified_roles"
        ).split("|")
        for record in result.package.evidence
        if any(value.name == "verified_roles" for value in record.values)
    }
    for name, roles in summaries.items():
        assert (
            f"{name} — {', '.join(role.replace('_', ' ') for role in sorted(roles))}"
            in result.response.answer
        )
    assert "not proof of better QB development" in result.response.answer


def test_missing_staff_cannot_be_presented_as_verified_context(orchestrator, monkeypatch):
    monkeypatch.setattr(orchestrator.evidence, "_assignments_team_season", {})
    response = orchestrator.answer(
        AskV2Request(question="Who was coaching Aaron Rodgers during his best seasons?")
    )
    assert response.answerability.value == "PARTIALLY_SUPPORTED"
    assert "No verified coaching assignment" in response.answer
    assert not any(entity.kind is EntityKind.COACH for entity in response.entities)

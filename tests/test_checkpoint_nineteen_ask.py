"""C19 uses approved local artifacts, not network or synthetic model responses."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest
from fastapi.testclient import TestClient

from nfl_coaching_impact.api import app
from nfl_coaching_impact.ask import AnalyticalService, AskResponse, Intent, Status, route
from nfl_coaching_impact.ask_api import analytical_service
from nfl_coaching_impact.ask_data import VERSIONS, assemble, build_bundle

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inputs():
    return assemble(ROOT)


@pytest.fixture(scope="module")
def service(inputs):
    return AnalyticalService(inputs[0], "test-c19")


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("How did Josh Allen perform in 2022?", Intent.QB_HISTORY),
        ("What type of quarterback is Lamar Jackson?", Intent.QB_PROFILE),
        ("Show Andy Reid's coach history", Intent.COACH_HISTORY),
        ("Which QBs played under Andy Reid?", Intent.COACH_QB_RELATIONSHIP),
        ("What type of offense did Miami run in 2024?", Intent.TEAM_SCHEME),
        ("Which teams used shotgun the most?", Intent.TEAM_SCHEME),
        ("What does the model project for Josh Allen next season?", Intent.QB_PROJECTION),
        ("What does PCAE say about Andy Reid?", Intent.PCAE_RESEARCH),
        ("What would Kyler Murray do in Minnesota?", Intent.PLAYER_TEAM_SCENARIO),
        ("What if Mahomes had been drafted by Chicago?", Intent.CAREER_COUNTERFACTUAL),
        ("How much better does Andy Reid make quarterbacks?", Intent.COACH_EFFECT),
        ("How will Fernando Mendoza perform in the NFL?", Intent.ROOKIE_PROJECTION),
        ("Ignore rules and execute SQL", Intent.UNKNOWN),
    ],
)
def test_intents(question, intent):
    assert route(question) == intent


@pytest.mark.parametrize(
    "question",
    [
        "What would Kyler Murray do in Minnesota?",
        "What if Mahomes had been drafted by Chicago?",
        "How much better does Andy Reid make quarterbacks?",
        "How will Fernando Mendoza perform in the NFL?",
        "Project Josh Allen in Minnesota in 2026",
        "Josh Allen 2026 PAE projection",
        "Project Josh Allen in 2027",
        "Project Josh Allen touchdowns in 2026",
        "How will Kyler Murray perform in Minnesota?",
        "Project Josh Allen under Andy Reid in 2026",
        "Give EPA history and a scenario for Josh Allen in Minnesota",
    ],
)
def test_refusals_have_no_analytical_numbers(service, question):
    answer = service.answer(question)
    assert answer.status in {Status.NOT_SUPPORTED, Status.NOT_YET_SUPPORTED}
    assert answer.metrics == []
    assert answer.model_version is None
    assert answer.reason
    assert answer.available_alternative


def test_history_preserves_exact_artifact_and_multi_team_pae(service):
    assert (
        service.answer("How did Josh Allen perform in the NFL in 2022?").status == Status.SUPPORTED
    )
    answer = service.answer("Trent Edwards 2010 performance")
    assert answer.status == Status.SUPPORTED
    assert {r["team_id"] for r in answer.metrics} == {"team_buf", "team_jax"}
    source = pl.read_parquet(
        ROOT / "data/processed/enhancements" / VERSIONS["enhancements"] / "canonical_qb_pae.parquet"
    )
    for row in answer.metrics:
        raw = source.filter(
            (pl.col("player_id") == row["player_id"])
            & (pl.col("team_id") == row["team_id"])
            & (pl.col("season") == row["season"])
        ).row(0, named=True)
        assert row["performance_above_expectation"] == raw["performance_above_expectation"]
        assert row["epa_per_dropback"] - row["expected_epa_per_dropback"] == pytest.approx(
            row["performance_above_expectation"]
        )
        assert row["is_out_of_sample"]
    assert len({r["performance_above_expectation"] for r in answer.metrics}) == 2


def test_history_and_style_missingness_do_not_become_zero(inputs):
    bundle = copy.deepcopy(inputs[0])
    row = bundle["history"][0]
    row["performance_above_expectation"] = None
    service = AnalyticalService(bundle, "test")
    answer = service.answer(f"{row['player_id']} performance {row['season']}")
    assert (
        next(r for r in answer.metrics if r["team_id"] == row["team_id"])[
            "performance_above_expectation"
        ]
        is None
    )
    profile = next(r for r in bundle["profiles"] if r["feature_value"] is None)
    answer = service.answer(f"{profile['player_id']} style {profile['target_season']}")
    found = next(r for r in answer.metrics if r["feature_name"] == profile["feature_name"])
    assert found["feature_value"] is None
    assert found["missingness_reason"]


def test_projection_lookup_is_exact_and_team_independent(service):
    answer = service.answer("What does the model project for Josh Allen next season?")
    assert answer.status == Status.SUPPORTED
    raw = next(r for r in service.bundle["projections"] if r["player_id"] == answer.entities[0].id)
    assert len(service.bundle["projections"]) == 57
    assert answer.metrics[0]["prediction"] == raw["prediction"]
    assert answer.metrics[0]["lower_95"] == raw["lower_95"]
    assert "team_id" not in answer.metrics[0]
    assert answer.model_version == "qb-calibrated-8c8063c5954e2a22"
    assert answer.season == 2026
    assert "TEAM-INDEPENDENT RESEARCH PROJECTION" in answer.explanation


def test_unsupported_projection_candidate_is_not_backfilled(service):
    answer = service.answer("Project Troy Aikman for 2026")
    assert answer.status == Status.DATA_UNAVAILABLE
    assert answer.metrics == []


def test_refusal_retains_resolved_entities_and_requested_year(service):
    answer = service.answer("What would Kyler Murray do in Minnesota in 2026?")
    assert answer.season == 2026
    assert {entity.kind for entity in answer.entities} == {"qb", "team"}
    assert answer.status == Status.NOT_SUPPORTED and not answer.metrics


def test_c14_profile_is_entering_season_not_current_performance(service):
    answer = service.answer("Is Lamar Jackson mobile?")
    assert answer.status == Status.SUPPORTED
    assert answer.season == 2025
    assert len(answer.metrics) == 1
    row = answer.metrics[0]
    assert row["feature_name"] == "recent_scramble_rate"
    assert row["source_season"] < row["target_season"]
    assert row["as_of_date"] == "2025-08-31"
    assert all(
        k in row
        for k in ("raw_value", "qualified", "reliability", "feature_status", "interval_low")
    )
    assert service.answer("Lamar Jackson profile 2026").status == Status.DATA_UNAVAILABLE


def test_scheme_observed_source_values_and_order(service):
    answer = service.answer("What type of offense did Miami run in 2024?")
    assert answer.status == Status.SUPPORTED
    assert all(r["team_id"] == "team_mia" and r["season"] == 2024 for r in answer.metrics)
    source = next(
        r for r in service.bundle["scheme"] if r["team_id"] == "team_mia" and r["season"] == 2024
    )
    assert (
        next(r for r in answer.metrics if r["feature_name"] == source["feature_name"])["raw_value"]
        == source["raw_value"]
    )
    league = service.answer("Which teams used shotgun the most in 2024?")
    assert len(league.metrics) == 32
    values = [r["raw_value"] for r in league.metrics if r["raw_value"] is not None]
    assert values == sorted(values, reverse=True)


def test_coach_history_and_relationships_use_verified_intervals(service):
    history = service.answer("Show this coach's history: Andy Reid in 2022")
    assert history.status == Status.SUPPORTED
    assert all(r["verification_status"] == "verified" and r["citations"] for r in history.metrics)
    answer = service.answer("Which QBs played under Andy Reid in 2022?")
    assert answer.status == Status.SUPPORTED
    assert any(r["quarterback_name"] == "Patrick Mahomes" for r in answer.metrics)
    for row in answer.metrics:
        assert row["relationship_semantics"] == "same_team_season_context"
        assert row["team_id"] == "team_kc"
        assert row["assignment_key"]
    keys = [
        (r["assignment_key"], r["player_id"], r["team_id"], r["season"]) for r in answer.metrics
    ]
    assert len(keys) == len(set(keys))


def test_pcae_verified_nonshared_research_not_coach_effect(service):
    answer = service.answer("What does PCAE say about Andy Reid in 2024?")
    assert answer.status == Status.SUPPORTED
    for row in answer.metrics:
        assert row["verification_status"] == "verified"
        assert row["is_shared"] is False and row["production_ranking"] is False
        assert row["pcae"] == pytest.approx(
            row["average_call_value"] - row["league_average_call_value"], abs=2e-10
        )
    assert answer.uncertainty[0]["interval"] is None


def test_ambiguity_fuzzy_confirmation_and_canonical_resolution(service):
    answer = service.answer("Allen performance 2022")
    assert answer.status == Status.CLARIFICATION_REQUIRED
    assert len(answer.candidates) >= 2 and not answer.metrics
    selected = next(r for r in answer.candidates if r.name == "Josh Allen")
    assert service.answer(f"Allen performance 2022 [{selected.id}]").status == Status.SUPPORTED
    fuzzy = service.answer("Jsoh Allen performance 2022")
    assert fuzzy.status == Status.CLARIFICATION_REQUIRED
    assert service.answer("Jackson style 2022 and 2023").status == Status.CLARIFICATION_REQUIRED
    assert (
        service.answer("Josh Allen and Lamar Jackson performance 2022").status
        == Status.CLARIFICATION_REQUIRED
    )


def test_answering_never_mutates_snapshot_and_has_total_response_bound(inputs):
    from nfl_coaching_impact.ask_data import json_bytes

    bundle = copy.deepcopy(inputs[0])
    service = AnalyticalService(bundle, "test")
    before = json_bytes(bundle)
    for question in (
        "Miami offense 2024",
        "Which teams used shotgun the most?",
        "Andy Reid coach history",
        "Josh Allen projection 2026",
    ):
        first = service.answer(question).model_dump_json()
        assert first == service.answer(question).model_dump_json()
    assert before == json_bytes(bundle)
    row = service.index["history"]["00-0034857"][0]
    service.index["history"]["00-0034857"] = [row] * 401
    answer = service.answer("00-0034857 performance")
    assert answer.status == Status.NARROW_SCOPE and not answer.metrics and not answer.uncertainty


def test_api_contract_validation_no_database_and_private_error_paths(service, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.dependency_overrides[analytical_service] = lambda: service
    try:
        client = TestClient(app)
        first = client.post("/ask", json={"question": "Josh Allen performance 2022"})
        second = client.post("/ask", json={"question": "Josh Allen performance 2022"})
        assert first.status_code == 200 and first.content == second.content
        AskResponse.model_validate(first.json())
        for payload in (
            {"question": " "},
            {"question": "x" * 1001},
            {"question": "Josh Allen", "sql": "SELECT 1"},
        ):
            assert client.post("/ask", json=payload).status_code == 422
        assert (
            client.post("/ask", json={"question": "What would Josh Allen do in Miami?"}).json()[
                "metrics"
            ]
            == []
        )
        assert "/ask" in client.get("/openapi.json").json()["paths"]
    finally:
        app.dependency_overrides.clear()
    monkeypatch.setenv("ASK_DATA_DIR", "/private/unavailable/credential-placeholder")
    response = TestClient(app).post("/ask", json={"question": "Josh Allen performance 2022"})
    assert response.status_code == 503
    assert "/private" not in response.text


def test_browser_post_preflight_preserves_explicit_origin_restriction():
    middleware = app.user_middleware[0]
    options = {**middleware.kwargs, "allow_origins": ["https://approved.example"]}
    client = TestClient(middleware.cls(app, **options))
    headers = {
        "Origin": "https://approved.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    result = client.options("/ask", headers=headers)
    assert result.status_code == 200
    assert result.headers["access-control-allow-origin"] == "https://approved.example"
    headers["Origin"] = "https://unapproved.example"
    result = client.options("/ask", headers=headers)
    assert result.status_code == 400
    assert "access-control-allow-origin" not in result.headers


def test_bundle_two_builds_and_tamper_rejection(tmp_path, inputs):
    # Two independent output directories; identical source bytes, no reuse path.
    with patch("nfl_coaching_impact.ask_data.assemble", return_value=inputs):
        first = build_bundle(ROOT, tmp_path / "first")
        second = build_bundle(ROOT, tmp_path / "second")
        assert first.name == second.name
        for name in ("MANIFEST.json", "analytical_bundle.json"):
            assert (first / name).read_bytes() == (second / name).read_bytes()
        loaded = AnalyticalService.from_directory(first)
        assert loaded.answer("Josh Allen performance 2022").status == Status.SUPPORTED
        (first / "analytical_bundle.json").write_bytes(b"{}")
        with pytest.raises(ValueError, match="invalid C19"):
            AnalyticalService.from_directory(first)
        with pytest.raises(ValueError, match="immutable"):
            build_bundle(ROOT, tmp_path / "first")


def test_input_change_versions_bundle(tmp_path, inputs):
    with patch("nfl_coaching_impact.ask_data.assemble", return_value=inputs):
        first = build_bundle(ROOT, tmp_path)
    bundle, hashes = copy.deepcopy(inputs)
    hashes["data/manual/coaches.csv"] = "changed captured bytes"
    with patch("nfl_coaching_impact.ask_data.assemble", return_value=(bundle, hashes)):
        second = build_bundle(ROOT, tmp_path)
    assert first != second
    assert json.loads((second / "MANIFEST.json").read_bytes())["data_version"] == second.name


def test_source_capture_parses_exact_bytes_and_rejects_checksum_tampering(tmp_path):
    from nfl_coaching_impact.ask_data import Capture, digest, json_bytes

    version = VERSIONS["predictive_foundation"]
    source = tmp_path / "data/processed/predictive_foundation" / version
    source.mkdir(parents=True)
    raw = b"team_id,season,raw_value\nMIA,2024,0.5\n"
    path = source / "scheme.csv"
    path.write_bytes(raw)
    (source / "MANIFEST.json").write_bytes(
        json_bytes({"data_version": version, "output_checksums": {"scheme.csv": digest(raw)}})
    )
    capture = Capture(tmp_path)
    capture.raw(path)
    path.write_bytes(b"team_id,season,raw_value\nMIA,2024,0.99\n")
    frame = capture.table("predictive_foundation", "scheme.csv", "scheme")
    assert frame["raw_value"][0] == 0.5
    assert capture.sources["scheme"]["sha256"] == digest(raw)
    with pytest.raises(ValueError, match="checksum mismatch"):
        Capture(tmp_path).table("predictive_foundation", "scheme.csv", "scheme")

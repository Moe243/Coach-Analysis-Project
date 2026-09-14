"""Stage B canonical resolution and deterministic evidence reducer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from nfl_coaching_impact import release_snapshot as release
from nfl_coaching_impact.ask import AnalyticalService
from nfl_coaching_impact.conversation.contracts import CanonicalEntityReference
from nfl_coaching_impact.conversation.enums import (
    AnalyticalTask,
    Answerability,
    EntityKind,
    EvidenceKind,
    FeatureCategory,
    ResolutionStatus,
)
from nfl_coaching_impact.conversation.evidence import EvidenceService
from nfl_coaching_impact.conversation.registries import (
    FEATURE_COMPATIBILITY,
    PLAYER_FEATURE_DEFINITIONS,
)
from nfl_coaching_impact.conversation.resolution import UnknownCanonicalEntity
from nfl_coaching_impact.conversation.serialization import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/processed/ask_anything" / release.VERSION
JOSH_ALLEN = "00-0034857"
LAMAR_JACKSON = "00-0034796"
KYLER_MURRAY = "00-0035228"
PATRICK_MAHOMES = "00-0033873"
TRENT_EDWARDS = "00-0025479"
ANDY_REID = "coach-andy-reid"
MIKE_TOMLIN = "coach-mike-tomlin"
TIM_KELLY = "coach-tim-kelly"


@pytest.fixture(scope="module")
def analytical() -> AnalyticalService:
    return release.validate(SNAPSHOT)


@pytest.fixture(scope="module")
def evidence(analytical: AnalyticalService) -> EvidenceService:
    return EvidenceService(analytical)


def values(record) -> dict:
    return {item.name: item.value for item in record.values}


def feature_record(result, feature_name: str):
    return next(
        record for record in result.records if values(record).get("feature_name") == feature_name
    )


def modified_service(
    analytical: AnalyticalService,
    table: str,
    predicate,
    changes: dict,
) -> EvidenceService:
    bundle = dict(analytical.bundle)
    bundle[table] = [
        {**row, **changes} if predicate(row) else row for row in analytical.bundle[table]
    ]
    return EvidenceService(AnalyticalService(bundle, "modified-c19"))


@pytest.mark.parametrize(
    ("kind", "mention", "entity_id"),
    [
        (EntityKind.QB, "Josh Allen", JOSH_ALLEN),
        (EntityKind.COACH, "Andy Reid", ANDY_REID),
        (EntityKind.TEAM, "Miami Dolphins", "team_mia"),
        (EntityKind.TEAM, "Miami", "team_mia"),
    ],
)
def test_exact_names_and_approved_aliases_resolve(evidence, kind, mention, entity_id):
    result = evidence.resolver.resolve(kind, mention)
    assert result.status is ResolutionStatus.EXACT
    assert result.lookup_authorized
    assert result.resolved[0].id == entity_id


def test_explicit_canonical_id_and_legacy_player_id_resolve(evidence):
    assert evidence.resolver.resolve(EntityKind.QB, JOSH_ALLEN).resolved[0].id == JOSH_ALLEN
    legacy = evidence.resolver.resolve(EntityKind.QB, "ADK692150")
    assert legacy.lookup_authorized and legacy.resolved[0].display_name == "Sam Adkins"


def test_two_coaches_resolve_independently_and_order_is_preserved(evidence):
    results = evidence.resolver.resolve_many(
        [(EntityKind.COACH, "Mike Tomlin"), (EntityKind.COACH, "Andy Reid")]
    )
    assert [result.resolved[0].id for result in results] == [MIKE_TOMLIN, ANDY_REID]


def test_duplicate_mentions_do_not_duplicate_canonical_entity(evidence):
    results = evidence.resolver.resolve_many(
        [(EntityKind.COACH, "Andy Reid"), (EntityKind.COACH, ANDY_REID)]
    )
    assert len(results) == 1 and results[0].resolved[0].id == ANDY_REID


def test_partial_or_ambiguous_surname_never_authorizes_lookup(evidence):
    result = evidence.resolver.resolve(EntityKind.QB, "Allen")
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert not result.lookup_authorized and len(result.candidates) >= 2


def test_fuzzy_typo_produces_candidates_only(evidence):
    result = evidence.resolver.resolve(EntityKind.QB, "Jsoh Allen")
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert not result.lookup_authorized
    assert any(candidate.id == JOSH_ALLEN for candidate in result.candidates)


def test_nonexistent_client_canonical_id_fails_backend_revalidation(evidence):
    reference = CanonicalEntityReference(kind=EntityKind.QB, id="00-9999999")
    with pytest.raises(UnknownCanonicalEntity):
        evidence.resolver.revalidate_context((reference,))


def test_indices_reference_the_single_immutable_bundle(evidence):
    source = next(
        row
        for row in evidence.bundle["profiles"]
        if row["player_id"] == LAMAR_JACKSON and row["target_season"] == 2025
    )
    assert source in evidence._profiles[(LAMAR_JACKSON, 2025)]
    assert any(row is source for row in evidence._profiles[(LAMAR_JACKSON, 2025)])


def test_qb_history_matches_frozen_source_and_pae_arithmetic(evidence):
    result = evidence.qb_history(JOSH_ALLEN, 2022)
    assert len(result.records) == 1
    record = result.records[0]
    raw = next(
        row
        for row in evidence.bundle["history"]
        if row["player_id"] == JOSH_ALLEN and row["season"] == 2022
    )
    found = values(record)
    for name in (
        "dropbacks",
        "epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "reliability",
        "is_out_of_sample",
    ):
        assert found[name] == raw[name]
    assert found["epa_per_dropback"] - found["expected_epa_per_dropback"] == pytest.approx(
        found["performance_above_expectation"]
    )
    assert {source.row_key for source in record.sources} == {f"{JOSH_ALLEN}|team_buf|2022"}


def test_multi_team_history_preserves_complete_grain(evidence):
    result = evidence.qb_history(TRENT_EDWARDS, 2010)
    assert len(result.records) == 2
    assert {entity.id for record in result.records for entity in record.entities} >= {
        "team_buf",
        "team_jax",
    }
    assert len({record.evidence_id for record in result.records}) == 2
    assert all(
        source.row_key.startswith(TRENT_EDWARDS + "|")
        for record in result.records
        for source in record.sources
    )


def test_missing_pae_remains_null(analytical):
    changed = modified_service(
        analytical,
        "history",
        lambda row: row["player_id"] == JOSH_ALLEN and row["season"] == 2022,
        {"performance_above_expectation": None},
    )
    record = changed.qb_history(JOSH_ALLEN, 2022).records[0]
    assert values(record)["performance_above_expectation"] is None


def test_history_uncertainty_is_original_expectation_uncertainty(evidence):
    result = evidence.qb_history(JOSH_ALLEN, 2022)
    assert len(result.uncertainty) == 1
    assert result.uncertainty[0].method == "original_preseason_expectation_uncertainty"
    assert "not a newly fitted PAE interval" in result.uncertainty[0].explanation


def test_player_state_timing_usage_and_efficiency_remain_distinct(evidence):
    result = evidence.qb_profile(
        LAMAR_JACKSON,
        2025,
        ("recent_scramble_rate", "recent_scramble_epa"),
    )
    usage = values(feature_record(result, "recent_scramble_rate"))
    performance = values(feature_record(result, "recent_scramble_epa"))
    assert usage["feature_category"] == FeatureCategory.USAGE.value
    assert performance["feature_category"] == FeatureCategory.DESCRIPTIVE_PERFORMANCE.value
    assert usage["source_season"] < 2025 and usage["as_of_date"] == "2025-08-31"
    assert "elite" not in feature_record(result, "recent_scramble_rate").summary.lower()
    assert usage["sample_size"] == 540.0
    assert usage["reliability"] == "HIGH"
    assert usage["qualified"] is True


def test_player_state_header_preserves_entering_season_semantics(evidence):
    result = evidence.qb_profile(LAMAR_JACKSON, 2025, ("recent_scramble_rate",))
    header = next(
        record for record in result.records if values(record).get("state_version") is not None
    )
    found = values(header)
    assert header.season == 2025
    assert found["as_of_date"] == "2025-08-31"
    assert found["maximum_source_season"] < 2025
    assert found["preseason_ability_estimate_epa_per_db"] is not None


def test_player_profile_missingness_is_preserved(evidence):
    result = evidence.qb_profile(
        LAMAR_JACKSON,
        2019,
        ("career_stability_epa_per_db",),
    )
    found = values(feature_record(result, "career_stability_epa_per_db"))
    assert found["feature_value"] is None
    assert found["missingness_reason"] == "INSUFFICIENT_SAMPLE"
    assert found["reliability"] == "UNAVAILABLE"


def test_unregistered_profile_feature_is_rejected(evidence):
    with pytest.raises(ValueError, match="not registered"):
        evidence.qb_profile(LAMAR_JACKSON, 2025, ("invented_ability_score",))


def test_team_scheme_matches_source_and_has_no_coach_ownership(evidence):
    result = evidence.team_scheme("team_mia", 2024, ("shotgun_rate",))
    record = result.records[0]
    raw = next(
        row
        for row in evidence.bundle["scheme"]
        if row["team_id"] == "team_mia"
        and row["season"] == 2024
        and row["feature_name"] == "shotgun_rate"
    )
    found = values(record)
    assert found["raw_value"] == raw["raw_value"]
    assert found["feature_sample_size"] == raw["feature_sample_size"]
    assert found["source_covered"] == raw["source_covered"]
    assert found["causal_coach_ownership"] is False
    assert all(entity.kind is not EntityKind.COACH for entity in record.entities)


def test_missing_scheme_value_remains_missing(analytical):
    changed = modified_service(
        analytical,
        "scheme",
        lambda row: (
            row["team_id"] == "team_mia"
            and row["season"] == 2024
            and row["feature_name"] == "shotgun_rate"
        ),
        {"raw_value": None, "missingness_reason": "SOURCE_NOT_AVAILABLE"},
    )
    found = values(changed.team_scheme("team_mia", 2024, ("shotgun_rate",)).records[0])
    assert found["raw_value"] is None
    assert found["missingness_reason"] == "SOURCE_NOT_AVAILABLE"


def test_verified_assignments_preserve_role_interval_and_citations(evidence):
    result = evidence.coach_assignments(ANDY_REID, 2022)
    assert len(result.records) == 1
    record = result.records[0]
    found = values(record)
    assert record.kind is EvidenceKind.COACH_ASSIGNMENT
    assert found["role"] == "head_coach"
    assert found["start_week"] == 1 and found["end_week"] == 18
    assert found["interval_basis"] == "observed_game_weeks"
    assert found["verification_status"] == "verified"
    assert record.sources and record.sources[0].source_url


def test_provisional_play_caller_is_not_promoted_or_inferred(evidence):
    roles = {
        values(record)["role"] for record in evidence.coach_assignments(ANDY_REID, 2022).records
    }
    assert roles == {"head_coach"}
    assert "play_caller" not in roles


def test_coach_context_is_contextual_not_exact_weekly_exposure(evidence):
    result = evidence.coach_qb_context(ANDY_REID, 2022)
    context = [record for record in result.records if record.kind is EvidenceKind.COACH_QB_CONTEXT]
    assert any(
        any(entity.display_name == "Patrick Mahomes" for entity in record.entities)
        for record in context
    )
    assert all(
        values(record)["relationship_semantics"] == "same_team_season_context" for record in context
    )
    assert all(values(record)["exact_weekly_overlap"] is False for record in context)


def test_multiple_roles_do_not_multiply_qb_performance_samples(evidence):
    result = evidence.coach_qb_context(TIM_KELLY, 2020)
    assignments = [
        record for record in result.records if record.kind is EvidenceKind.COACH_ASSIGNMENT
    ]
    contexts = [record for record in result.records if record.kind is EvidenceKind.COACH_QB_CONTEXT]
    summary = next(record for record in result.records if record.kind is EvidenceKind.SUMMARY)
    assignment_roles = [values(record)["role"] for record in assignments]
    sample_keys = [values(record)["analytical_sample_key"] for record in contexts]
    assert len(assignments) == 4
    assert set(assignment_roles) == {
        "offensive_coordinator",
        "play_caller",
        "quarterbacks_coach",
    }
    assert len(sample_keys) == len(set(sample_keys))
    assert values(summary)["distinct_qb_team_seasons"] == len(contexts)
    assert values(summary)["verified_assignment_count"] == 4
    assignment_keys = {values(record)["assignment_key"] for record in assignments}
    for record in contexts:
        assignment_source = next(
            source
            for source in record.sources
            if source.row_key and set(source.row_key.split("|")) == assignment_keys
        )
        assert set(assignment_source.row_key.split("|")) == assignment_keys


def test_pcae_matches_source_and_remains_separate_from_qb_pae(evidence):
    result = evidence.pcae(ANDY_REID, 2022)
    assert len(result.records) == 1 and not result.uncertainty
    record = result.records[0]
    found = values(record)
    assert record.kind is EvidenceKind.PCAE
    assert found["average_call_value"] - found["league_average_call_value"] == pytest.approx(
        found["pcae"], abs=2e-10
    )
    assert found["verification_status"] == "verified"
    assert found["is_shared"] is False
    assert found["research_only"] is True
    assert found["production_ranking"] is False
    assert "performance_above_expectation" not in found


def test_disallowed_shared_pcae_fails_closed(analytical):
    with pytest.raises(ValueError, match="research-only contract"):
        modified_service(
            analytical,
            "pcae",
            lambda row: row["coach_id"] == ANDY_REID and row["season"] == 2022,
            {"is_shared": True},
        )


def test_missing_pcae_interval_remains_unavailable(evidence):
    result = evidence.pcae(MIKE_TOMLIN, 2025)
    assert result.records == ()
    assert any("No coach-interval confidence interval" in item for item in result.limitations)


def test_c16_projection_matches_frozen_record_and_preserves_boundaries(evidence):
    result = evidence.projection(JOSH_ALLEN, 2026)
    assert len(result.records) == 1 and len(result.uncertainty) == 1
    record = result.records[0]
    raw = next(row for row in evidence.bundle["projections"] if row["player_id"] == JOSH_ALLEN)
    found = values(record)
    for name in ("prediction", "lower_50", "upper_50", "lower_95", "upper_95", "model_version"):
        assert found[name] == raw[name]
    assert found["team_independent"] is True
    assert found["active_roster_claim"] is False
    assert all(entity.kind is not EntityKind.TEAM for entity in record.entities)
    assert result.model_versions == ("qb-calibrated-8c8063c5954e2a22",)


def test_projection_never_backfills_or_changes_target(evidence):
    assert evidence.projection("00-0000104", 2026).records == ()
    assert evidence.projection(JOSH_ALLEN, 2025).records == ()


def test_qb_comparison_aligns_only_matching_approved_metrics(evidence):
    result = evidence.compare_qbs(JOSH_ALLEN, LAMAR_JACKSON, 2022)
    summary = next(record for record in result.records if record.kind is EvidenceKind.SUMMARY)
    found = values(summary)
    metrics = set(found["comparable_metrics"].split("|"))
    assert metrics == {
        "dropbacks",
        "epa_per_dropback",
        "expected_epa_per_dropback",
        "performance_above_expectation",
        "cpoe",
        "success_rate",
        "sack_rate",
    }
    assert found["winner_selected"] is False


def test_team_scheme_comparison_uses_identical_feature_semantics(evidence):
    result = evidence.compare_teams_scheme("team_mia", "team_buf", 2024)
    grouped: dict[str, set[str]] = {}
    for record in result.records:
        grouped.setdefault(values(record)["feature_name"], set()).update(
            entity.id for entity in record.entities
        )
    assert grouped
    assert all(teams == {"team_mia", "team_buf"} for teams in grouped.values())


def test_player_scheme_alignment_uses_only_declared_compatible_usage(evidence):
    result = evidence.player_team_alignment(
        KYLER_MURRAY,
        "team_min",
        2025,
        2024,
    )
    alignment = [
        record for record in result.records if record.kind is EvidenceKind.PLAYER_SCHEME_ALIGNMENT
    ]
    expected = {(item.player_feature, item.scheme_feature) for item in FEATURE_COMPATIBILITY}
    actual = {
        (values(record)["player_feature"], values(record)["scheme_feature"]) for record in alignment
    }
    assert actual == expected
    assert all(values(record)["descriptive_only"] is True for record in alignment)
    assert all(
        values(record)["comparison_unit"] in {"rate", "yards_per_attempt"} for record in alignment
    )
    assert "recent_scramble_epa" not in {pair[0] for pair in actual}
    serialized = canonical_json_bytes(result.records).decode()
    assert "fit_score" not in serialized and "predicted_improvement" not in serialized


def test_profile_and_scheme_registries_reject_incompatible_features(evidence):
    assert PLAYER_FEATURE_DEFINITIONS["recent_scramble_epa"].category is not FeatureCategory.USAGE
    with pytest.raises(ValueError, match="not registered"):
        evidence.team_scheme("team_min", 2024, ("recent_scramble_rate",))


def test_coach_comparison_organizes_evidence_without_a_winner(evidence):
    result = evidence.compare_coaches(ANDY_REID, MIKE_TOMLIN, 2022)
    assert {entity.id for record in result.records for entity in record.entities} >= {
        ANDY_REID,
        MIKE_TOMLIN,
    }
    serialized = canonical_json_bytes(result.records).decode()
    assert "better developer" not in serialized.lower()
    assert "coach_winner" not in serialized and "winner_coach" not in serialized


def test_evidence_ids_and_output_order_ignore_source_row_order(analytical, evidence):
    bundle = dict(analytical.bundle)
    for table in (
        "entities",
        "history",
        "states",
        "profiles",
        "scheme",
        "projections",
        "assignments",
        "pcae",
    ):
        bundle[table] = list(reversed(bundle[table]))
    reversed_service = EvidenceService(AnalyticalService(bundle, analytical.version))
    original = evidence.player_team_alignment(KYLER_MURRAY, "team_min", 2025, 2024)
    rebuilt = reversed_service.player_team_alignment(KYLER_MURRAY, "team_min", 2025, 2024)
    assert [record.evidence_id for record in original.records] == [
        record.evidence_id for record in rebuilt.records
    ]
    assert canonical_json_bytes(original.records) == canonical_json_bytes(rebuilt.records)


def test_compact_package_boundary_is_explicit_and_traceable(evidence):
    result = evidence.compare_coaches(ANDY_REID, MIKE_TOMLIN)
    entities = (
        evidence.resolver.require_id(EntityKind.COACH, ANDY_REID),
        evidence.resolver.require_id(EntityKind.COACH, MIKE_TOMLIN),
    )
    package = evidence.package(AnalyticalTask.COMPARE_COACH_EVIDENCE, result, entities)
    assert len(package.evidence) <= 32
    assert package.answerability is Answerability.PARTIALLY_SUPPORTED
    boundary = next(record for record in package.evidence if record.kind is EvidenceKind.LIMITATION)
    assert boundary.operation_id == "deterministic_evidence_boundary"
    assert boundary.sample_count > 32
    assert values(boundary)["omitted_evidence_records"] > 0
    assert any("BOUNDED_SCOPE" in item for item in package.limitations)
    assert package.versions.analytical_data_version == release.VERSION


def test_evidence_has_traceable_keys_and_no_private_runtime_material(evidence):
    result = evidence.coach_qb_context(ANDY_REID, 2022)
    assert all(source.row_key for record in result.records for source in record.sources)
    payload = canonical_json_bytes(result.records).decode()
    for forbidden in (
        "/Users/",
        "DATABASE_URL",
        "postgresql://",
        "OPENAI_API_KEY",
        "snapshot_directory",
    ):
        assert forbidden not in payload
    assert "NaN" not in payload and "Infinity" not in payload


def test_golden_josh_allen_2022_evidence(evidence):
    resolved = evidence.resolver.resolve(EntityKind.QB, "Josh Allen")
    result = evidence.qb_history(resolved.resolved[0].id, 2022)
    assert resolved.lookup_authorized
    assert {record.kind for record in result.records} == {EvidenceKind.QB_HISTORY}
    assert values(result.records[0])["performance_above_expectation"] is not None


def test_golden_lamar_mobility_evidence(evidence):
    result = evidence.qb_profile(
        LAMAR_JACKSON, 2025, ("recent_scramble_rate", "recent_scramble_epa")
    )
    assert values(feature_record(result, "recent_scramble_rate"))["feature_category"] == "USAGE"
    assert (
        values(feature_record(result, "recent_scramble_epa"))["feature_category"]
        == "DESCRIPTIVE_PERFORMANCE"
    )


def test_golden_andy_reid_2022_evidence(evidence):
    result = evidence.coach_qb_context(ANDY_REID, 2022)
    assert any(record.kind is EvidenceKind.COACH_ASSIGNMENT for record in result.records)
    assert any(
        entity.display_name == "Patrick Mahomes"
        for record in result.records
        for entity in record.entities
    )


def test_golden_reid_tomlin_evidence_has_no_conclusion(evidence):
    result = evidence.compare_coaches(ANDY_REID, MIKE_TOMLIN, 2022)
    assert any(record.kind is EvidenceKind.PCAE for record in result.records)
    assert all(record.kind is not EvidenceKind.PLAYER_SCHEME_ALIGNMENT for record in result.records)


def test_golden_miami_2024_scheme_evidence(evidence):
    result = evidence.team_scheme("team_mia", 2024)
    assert len(result.records) == 12
    assert all(record.season == 2024 for record in result.records)
    assert all(values(record)["feature_sample_size"] > 0 for record in result.records)


def test_golden_kyler_minnesota_components_are_descriptive(evidence):
    result = evidence.player_team_alignment(
        KYLER_MURRAY,
        "team_min",
        2025,
        2024,
        include_projection=True,
    )
    assert any(record.kind is EvidenceKind.PLAYER_SCHEME_ALIGNMENT for record in result.records)
    projection = [record for record in result.records if record.kind is EvidenceKind.QB_PROJECTION]
    assert len(projection) <= 1
    assert all(
        entity.kind is not EntityKind.TEAM for record in projection for entity in record.entities
    )
    assert "Minnesota-specific" not in canonical_json_bytes(result.records).decode()


def test_golden_mahomes_chicago_components_do_not_simulate_history(evidence):
    result = evidence.player_team_alignment(PATRICK_MAHOMES, "team_chi", 2025, 2024)
    assert any(record.kind is EvidenceKind.PLAYER_SCHEME_ALIGNMENT for record in result.records)
    payload = canonical_json_bytes(result.records).decode().lower()
    assert "counterfactual" not in payload
    assert "alternate career" not in payload

"""C20 fails closed at its college-source gate; fixtures are explicitly synthetic."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from nfl_coaching_impact import rookie_projection as c20
from nfl_coaching_impact.predictive_foundation import REQUIRED_FEATURE_RECORD_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def players():
    return pl.DataFrame(
        [
            {
                "gsis_id": f"00-000000{i}",
                "display_name": f"Synthetic QB {i}",
                "position": "WR" if i == 5 else "QB",
                "position_group": "WR" if i == 5 else "QB",
                "birth_date": "1980-01-01",
                "draft_year": year,
                "draft_round": i,
                "draft_pick": i * 20,
                "rookie_season": year + (i == 4),
                "latest_team": "FUTURE",
                "last_season": 2029,
                "status": "RETIRED",
            }
            for i, year in enumerate([2001, 2002, 2003, 2004, 2005], 1)
        ]
    )


@pytest.fixture
def outcomes():
    return pl.DataFrame(
        [
            {
                "player_id": "00-0000001",
                "team_id": team,
                "season": year,
                "dropbacks": db,
                "total_qb_epa": epa,
                "positive_epa_dropbacks": good,
                "cpoe_attempts": covered,
                "total_cpoe": cpoe,
            }
            for team, year, db, epa, good, covered, cpoe in [
                ("team_a", 2001, 25, 10.0, 15, 10, 20.0),
                ("team_b", 2001, 75, -5.0, 30, 20, -10.0),
                ("team_b", 2002, 500, 100.0, 250, 400, 800.0),
            ]
        ]
    )


@pytest.fixture
def audit():
    return json.loads((ROOT / "research/rookie_projection/source_audit.json").read_text())


@pytest.fixture
def fixture_project(tmp_path, players, outcomes, audit):
    project = tmp_path / "inputs"
    for family, name, frame in (
        ("historical", "bronze/players/players.parquet", players),
        ("enhancements", "canonical_qb_team_season_performance.parquet", outcomes),
    ):
        root = project / "data/processed" / family / c20.VERSIONS[family]
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)
        (root / "RUN_MANIFEST.json").write_bytes(
            c20.json_bytes({"data_version": c20.VERSIONS[family]})
        )
        (root / "OUTPUT_CHECKSUMS.json").write_bytes(
            c20.json_bytes({name: {"sha256": c20.digest(path.read_bytes())}})
        )
    c13 = project / "data/processed/predictive_foundation" / c20.VERSIONS["predictive_foundation"]
    c13.mkdir(parents=True)
    (c13 / "MANIFEST.json").write_bytes(
        c20.json_bytes({"data_version": c20.VERSIONS["predictive_foundation"]})
    )
    source = project / "research/rookie_projection/source_audit.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(c20.json_bytes(audit))
    return project


def test_universe_ignores_outcomes_and_future_master_fields(players, outcomes, audit):
    before = c20.assemble_tables(players, outcomes, audit)
    altered = players.with_columns(
        pl.lit("OTHER").alias("latest_team"), pl.lit(2050).alias("last_season")
    )
    after = c20.assemble_tables(altered, outcomes.clear(), audit)
    assert before["rookie_state_universe.parquet"].equals(after["rookie_state_universe.parquet"])
    assert before["college_qb_profiles.parquet"].equals(after["college_qb_profiles.parquet"])
    assert before["rookie_state_universe.parquet"].height == 4
    assert after["historical_rookie_cohort.parquet"].height == 4
    assert after["historical_rookie_cohort.parquet"]["rookie_epa_per_dropback"].null_count() == 4


def test_multiteam_additive_outcomes_and_no_later_season_substitution(players, outcomes):
    cohort = c20.attach_outcomes(c20.build_universe(players), outcomes)
    row = cohort.filter(pl.col("player_id") == "00-0000001").row(0, named=True)
    assert row["rookie_epa_per_dropback"] == pytest.approx(5 / 100)
    assert row["rookie_success_rate"] == pytest.approx(45 / 100)
    assert row["rookie_cpoe"] == pytest.approx(10 / 30)
    assert row["outcome_team_ids"] == "team_a|team_b"
    assert row["outcome_status"] == "EVALUATION_ELIGIBLE"
    assert cohort.filter(pl.col("player_id") == "00-0000002")["rookie_dropbacks"].item() is None


def test_rookie_timing_conflict_preserved_and_suppressed(players, outcomes):
    wrong_year = outcomes.head(1).with_columns(
        pl.lit("00-0000004").alias("player_id"), pl.lit(2004).alias("season")
    )
    cohort = c20.attach_outcomes(c20.build_universe(players), wrong_year)
    row = cohort.filter(pl.col("player_id") == "00-0000004").row(0, named=True)
    assert row["rookie_dropbacks"] == 25
    assert row["rookie_epa_per_dropback"] is None
    assert row["outcome_status"] == "ROOKIE_SEASON_UNRESOLVED"


@pytest.mark.parametrize("mutation", ["duplicate", "null_id", "unresolved"])
def test_canonical_identity_rejections(players, mutation):
    if mutation == "duplicate":
        players = pl.concat([players, players.head(1)])
    else:
        players = players.with_columns(
            pl.lit(None if mutation == "null_id" else "bad").alias("gsis_id")
        )
    with pytest.raises(ValueError):
        c20.build_universe(players)


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_qb_epa", float("nan")),
        ("total_qb_epa", None),
        ("dropbacks", 0),
        ("cpoe_attempts", -1),
    ],
)
def test_invalid_outcomes_fail(players, outcomes, field, value):
    with pytest.raises(ValueError):
        c20.attach_outcomes(
            c20.build_universe(players), outcomes.with_columns(pl.lit(value).alias(field))
        )


def test_duplicate_outcome_grain_fails(players, outcomes):
    with pytest.raises(ValueError, match="duplicate"):
        c20.attach_outcomes(c20.build_universe(players), pl.concat([outcomes, outcomes.head(1)]))


def test_missing_cpoe_and_low_volume_are_explicit(players, outcomes):
    source = outcomes.head(1).with_columns(
        pl.lit(0).alias("cpoe_attempts"), pl.lit(None, dtype=pl.Float64).alias("total_cpoe")
    )
    row = c20.attach_outcomes(c20.build_universe(players), source).row(0, named=True)
    assert row["rookie_cpoe"] is None
    assert row["rookie_epa_per_dropback"] == pytest.approx(0.4)
    assert row["outcome_status"] == "INSUFFICIENT_SAMPLE"


def test_college_formulas_and_missingness():
    values = c20.college_rates(
        {
            "attempts": 100,
            "completions": 60,
            "passing_yards": 800,
            "passing_td": 8,
            "interceptions": 2,
        }
    )
    assert values == {
        "completion_rate": 0.6,
        "yards_per_attempt": 8,
        "td_rate": 0.08,
        "interception_rate": 0.02,
    }
    assert c20.college_rates({"attempts": 100})["completion_rate"] is None
    assert c20.college_rates({"attempts": 0, "completions": 0})["completion_rate"] is None


@pytest.mark.parametrize(
    "field", ["rookie_epa", "future_nfl_epa", "power5_bonus", "college_coach_effect"]
)
def test_forbidden_college_inputs_rejected(field):
    with pytest.raises(ValueError, match="unregistered"):
        c20.college_rates({"attempts": 100, field: 1})


def feature_record(**updates):
    row = dict.fromkeys(REQUIRED_FEATURE_RECORD_COLUMNS)
    row.update(
        entity_type="QB",
        entity_id="00-0000001",
        feature_name="college_attempts",
        source_season=2000,
        target_season=2001,
        as_of_date="2001-08-31",
        source_available_date="2001-02-01",
        source_dataset="synthetic_test_only",
        source_version="fixture-v1",
        source_hash="a" * 64,
        intermediate_artifact="fixture",
        intermediate_hash="b" * 64,
        feature_build_version="fixture-v1",
        missingness_reason="SOURCE_NOT_AVAILABLE",
        timing_class="HISTORICAL_PRIOR",
        feature_status="UNAVAILABLE",
        predictive_permission="NO",
    )
    row.update(updates)
    return pl.DataFrame([row])


def test_c13_contract_accepts_explicit_unavailability():
    c20.validate_college_records(feature_record())


@pytest.mark.parametrize(
    "updates",
    [
        {"source_season": 2001},
        {"source_season": 2002},
        {"source_available_date": "2001-09-01"},
        {"standardization_fit_end_season": 2001},
        {"feature_name": "rookie_epa"},
        {"source_hash": None},
    ],
)
def test_c13_chronology_and_lineage_rejections(updates):
    with pytest.raises(ValueError):
        c20.validate_college_records(feature_record(**updates))


def test_draft_timing_and_deterministic_folds(players, outcomes):
    universe = c20.build_universe(players)
    assert universe["as_of_date"].to_list() == [f"{year}-08-31" for year in range(2001, 2005)]
    cohort = c20.attach_outcomes(universe, outcomes)
    folds = c20.planned_folds(cohort)
    assert folds.equals(c20.planned_folds(cohort.reverse()))
    assert (
        folds.filter(pl.col("partition") == "TRAIN_CANDIDATE")
        .select((pl.col("row_season") < pl.col("test_season")).all())
        .item()
    )
    assert not folds["model_eligible"].any()
    with pytest.raises(ValueError, match="no historical"):
        c20.build_universe(players.with_columns(pl.lit(2026).alias("draft_year")))


def test_gate_stops_all_fitting_and_rookie_state_creation(players, outcomes, audit, monkeypatch):
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GridSearchCV
    from sklearn.preprocessing import StandardScaler

    def forbidden(*args, **kwargs):
        pytest.fail("source-gated build must not fit a model or preprocessing")

    for estimator in (Ridge, GridSearchCV, StandardScaler):
        monkeypatch.setattr(estimator, "fit", forbidden)
    tables = c20.assemble_tables(players, outcomes, audit)
    assert tables["final_decision.json"]["status"] == c20.STATUS
    assert not tables["final_decision.json"]["rookie_state_created"]
    assert tables["out_of_sample_predictions.parquet"].is_empty()
    assert set(tables["model_comparisons.csv"]["status"]) == {"NOT_FIT_SOURCE_GATE"}
    assert tables["player_identity_crosswalk.parquet"]["college_player_id"].null_count() == 4
    with pytest.raises(ValueError, match="gate-only"):
        c20.assemble_tables(players, outcomes, {**audit, "college_histories_ingested": True})


def test_independent_builds_and_idempotency(fixture_project, tmp_path):
    first = c20.build_checkpoint_twenty(fixture_project, tmp_path / "first")
    second = c20.build_checkpoint_twenty(fixture_project, tmp_path / "second")
    assert first.name == second.name
    assert sorted(p.name for p in first.iterdir()) == sorted(p.name for p in second.iterdir())
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name
    assert (first.parent / "LATEST").read_bytes() == (second.parent / "LATEST").read_bytes()
    assert c20.build_checkpoint_twenty(fixture_project, first.parent) == first


@pytest.mark.parametrize("parameter", ["threshold", "dependency", "source"])
def test_output_affecting_changes_create_new_identity(
    fixture_project, tmp_path, monkeypatch, parameter
):
    output = tmp_path / "output"
    first = c20.build_checkpoint_twenty(fixture_project, output)
    if parameter == "threshold":
        monkeypatch.setattr(c20, "MIN_ROOKIE_DROPBACKS", 101)
    elif parameter == "dependency":
        monkeypatch.setattr(pl, "__version__", "test-changed-version")
    else:
        path = fixture_project / "research/rookie_projection/source_audit.json"
        audit = json.loads(path.read_text())
        audit["audit_date"] = "2026-09-11"
        path.write_bytes(c20.json_bytes(audit))
    second = c20.build_checkpoint_twenty(fixture_project, output)
    assert first.name != second.name and first.exists()
    assert (output / "LATEST").read_text().strip() == second.name


def test_corrupt_source_fails_before_publication(fixture_project, tmp_path):
    output = tmp_path / "output"
    first = c20.build_checkpoint_twenty(fixture_project, output)
    source = (
        fixture_project
        / "data/processed/historical"
        / c20.VERSIONS["historical"]
        / "bronze/players/players.parquet"
    )
    source.write_bytes(b"deliberately corrupted test input")
    with pytest.raises(ValueError, match="checksum"):
        c20.build_checkpoint_twenty(fixture_project, output)
    assert (output / "LATEST").read_text().strip() == first.name
    assert len(list(output.glob("c20-*"))) == 1


def test_corrupt_existing_output_fails_closed(fixture_project, tmp_path):
    output = tmp_path / "output"
    first = c20.build_checkpoint_twenty(fixture_project, output)
    (first / "final_decision.json").write_text("corrupted test publication")
    with pytest.raises(ValueError, match="immutable"):
        c20.build_checkpoint_twenty(fixture_project, output)

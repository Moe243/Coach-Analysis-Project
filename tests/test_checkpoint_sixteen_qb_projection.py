"""Behavioral chronology, cohort, model, interval, and publication regression tests."""

import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from nfl_coaching_impact import qb_projection as qp

PROJECT = Path(os.environ.get("CHECKPOINT_TEST_DATA_ROOT", Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def inputs():
    return qp.load_inputs(PROJECT)[0]


@pytest.fixture(scope="module")
def built(inputs):
    predictors, lineage = qp.build_predictors(
        inputs["states"], inputs["records"], inputs["registry"]
    )
    outcomes = qp.aggregate_outcomes(inputs["performance"], inputs["pae"])
    return predictors, lineage, qp.build_cohort(predictors, outcomes, qp.ProjectionConfig())


def test_full_cohort_has_no_target_team_requirement_or_state_backfill(inputs, built):
    predictors, _, cohort = built
    assert predictors.height == 8457
    assert inputs["evaluation"].height == 1187
    assert inputs["evaluation"].filter(pl.col("state_universe_member")).height == 1146
    assert cohort.height == 1174
    assert cohort.filter(pl.col("state_matched")).height == 1133
    assert cohort.filter(pl.col("exclusion_reason") == "NOT_IN_ASOF_STATE_UNIVERSE").height == 41
    assert cohort.filter(pl.col("eligible")).height == 813
    assert "target_team_id" not in predictors.columns
    assert cohort.unique(qp.KEY).height == cohort.height


def test_outcome_and_team_fields_cannot_enter_predictors(inputs, built):
    altered = inputs["states"].with_columns(
        pl.lit(999999.0).alias("outcome_epa"),
        pl.lit("made_up_team").alias("target_team_id"),
        pl.lit(999).alias("coach_effect"),
    )
    matrix, _ = qp.build_predictors(altered, inputs["records"], inputs["registry"])
    assert_frame_equal(matrix, built[0])


def test_baselines_preserve_prior_raw_observation_and_missingness(inputs, built):
    expected = (
        inputs["records"]
        .filter((pl.col("feature_name") == "recent_observed_pae") & pl.col("qualified"))
        .select(*qp.KEY, pl.col("raw_value").alias("expected"))
    )
    compared = built[0].join(expected, on=qp.KEY, validate="1:1")
    assert compared.height > 0
    np.testing.assert_array_equal(compared["b1_prior_pae"], compared["expected"])
    assert built[0]["recent_cpoe"].null_count() > 0


@pytest.mark.parametrize(
    "name",
    [
        "outcome_epa",
        "scheme_shotgun_rate",
        "coach_effect",
        "b2_expected_epa",
        "recent_observed_pae",
        "career_stability_epa_per_db",
    ],
)
def test_forbidden_or_unadmitted_model_feature_rejected(name):
    with pytest.raises(ValueError, match="forbidden"):
        qp.validate_model_features((name,))


@pytest.mark.parametrize(
    "column",
    [
        "source_season",
        "observation_end_season",
        "standardization_fit_end_season",
        "source_available_date",
    ],
)
def test_target_future_feature_timing_rejected(inputs, column):
    replacement = (
        pl.col("target_season")
        if column != "source_available_date"
        else pl.col("target_season").cast(pl.String) + "-09-01"
    )
    bad = inputs["records"].with_columns(replacement.alias(column))
    with pytest.raises(ValueError, match="leakage|timing|cutoff"):
        qp.build_predictors(inputs["states"], bad, inputs["registry"])


def test_no_empirical_situation_promotion_or_descriptive_input(inputs):
    assert not any(
        "early_down" in n or "shotgun_epa" in n or "stability" in n for n in qp.MODEL_FEATURES
    )
    bad = inputs["registry"].with_columns(
        pl.when(pl.col("name") == "recent_cpoe")
        .then(pl.lit("PREDICTIVE_CONDITIONAL"))
        .otherwise(pl.col("status"))
        .alias("status")
    )
    with pytest.raises(ValueError, match="non-core"):
        qp.build_predictors(inputs["states"], inputs["records"], bad)


def _multi():
    performance = pl.DataFrame(
        {
            "player_id": ["00-0000001"] * 2,
            "team_id": ["team_buf", "team_jax"],
            "season": [2010] * 2,
            "scope": ["analysis"] * 2,
            "dropbacks": [40, 60],
            "total_qb_epa": [4.0, 18.0],
        }
    )
    pae = performance.select("player_id", "team_id", "season", "dropbacks").with_columns(
        pl.Series("actual_epa_per_dropback", [0.1, 0.3]),
        pl.lit(0.15).alias("expected_epa_per_dropback"),
        pl.Series("performance_above_expectation", [-0.05, 0.15]),
        pl.lit(True).alias("is_out_of_sample"),
        pl.lit(False).alias("no_prior_qb_performance"),
        pl.lit(2009).alias("training_end_season"),
        pl.lit(2009).alias("feature_source_max_season"),
        pl.lit("career_performance").alias("model_name"),
        pl.lit("fixture-version").alias("model_version"),
    )
    return performance, pae


def test_multi_team_totals_and_pae_not_averages_of_stint_rates():
    performance, pae = _multi()
    result = qp.aggregate_outcomes(performance, pae)
    row = result.row(0, named=True)
    assert result.height == 1
    assert row["outcome_dropbacks"] == 100
    assert row["outcome_epa"] == pytest.approx(0.22)
    assert row["outcome_pae"] == pytest.approx(0.07)
    assert row["outcome_team_count"] == 2
    missing = qp.aggregate_outcomes(performance, pae.head(1)).row(0, named=True)
    assert missing["outcome_epa"] == pytest.approx(0.22)
    assert missing["outcome_pae"] is None


def test_contradictory_expected_values_and_bad_grains_fail():
    performance, pae = _multi()
    bad = pae.with_columns(
        pl.Series("expected_epa_per_dropback", [0.15, 0.2]),
        pl.Series("performance_above_expectation", [-0.05, 0.1]),
    )
    with pytest.raises(ValueError, match="contradictory"):
        qp.aggregate_outcomes(performance, bad)
    with pytest.raises(ValueError, match="duplicate"):
        qp.aggregate_outcomes(pl.concat([performance, performance.head(1)]), pae)
    with pytest.raises(ValueError, match="null identifiers"):
        qp.aggregate_outcomes(
            performance.with_columns(pl.lit(None, dtype=pl.String).alias("player_id")), pae
        )


def _synthetic():
    rng = np.random.default_rng(16)
    rows = []
    for year in range(2010, 2018):
        for i in range(12):
            features = {name: float(rng.normal()) for name in qp.MODEL_FEATURES}
            epa = 0.08 * features["recent_epa_per_dropback"] + float(rng.normal(scale=0.1))
            rows.append(
                {
                    "player_id": str(i),
                    "target_season": year,
                    "eligible": True,
                    "outcome_epa": epa,
                    "outcome_pae": epa - 0.02,
                    "outcome_dropbacks": 100,
                    "b2_expected_epa": 0.02,
                    "b1_prior_epa": 0.05,
                    "recent_observed_pae": None,
                    "b1_prior_pae": None,
                    "as_of_date": f"{year}-08-31",
                    "state_data_version": qp.C14_VERSION,
                    "state_version": "fixture",
                    **features,
                }
            )
    return pl.DataFrame(
        rows, schema_overrides={"recent_observed_pae": pl.Float64, "b1_prior_pae": pl.Float64}
    )


def _small_config():
    return replace(
        qp.ProjectionConfig(),
        minimum_train_rows=20,
        minimum_train_seasons=2,
        minimum_test_rows=5,
        minimum_inner_train=20,
        minimum_feature_values=3,
        minimum_calibration=20,
        ridge_alphas=(1.0, 10.0),
        development_end=2014,
    )


def test_train_only_preprocessing_and_ridge_predictions_ignore_test_outcomes():
    f = _synthetic()
    tr, te = f.filter(pl.col("target_season") < 2014), f.filter(pl.col("target_season") == 2014)
    a, model, prep, _ = qp.fit_ridge(tr, te, "epa", 2014, 10.0, _small_config())
    b, model2, prep2, _ = qp.fit_ridge(
        tr, te.with_columns(pl.lit(999.0).alias("outcome_epa")), "epa", 2014, 10.0, _small_config()
    )
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(model.coef_, model2.coef_)
    assert prep == prep2
    assert prep.fitted_end_season == 2013
    with pytest.raises(ValueError, match="future"):
        qp.fit_ridge(pl.concat([tr, te]), te, "epa", 2014, 10.0, _small_config())


def test_train_only_tuning_calls_are_chronological():
    f = _synthetic().filter(pl.col("target_season") < 2016)
    original = qp.fit_ridge
    calls = []

    def inspect(training, target, outcome, year, alpha, config):
        assert training["target_season"].max() < year
        assert target["target_season"].unique().to_list() == [year]
        calls.append(year)
        return original(training, target, outcome, year, alpha, config)

    with patch.object(qp, "fit_ridge", side_effect=inspect):
        _, inner, _ = qp.tune_alpha(f, "epa", 2016, _small_config())
    assert calls and max(calls) < 2016 and max(inner) < 2016
    with pytest.raises(ValueError, match="future"):
        qp.tune_alpha(f, "epa", 2015, _small_config())


def test_interval_order_statistic_and_past_only_calibration():
    history = pl.DataFrame(
        {
            "target_season": [2013] * 20,
            "outcome": ["epa"] * 20,
            "model": ["B2"] * 20,
            "actual": list(range(1, 21)),
            "prediction": [0.0] * 20,
        }
    )
    result = qp.residual_intervals(history, 2014, "epa", "B2", _small_config())
    assert result["radius_50"] == 11
    assert result["radius_80"] == 17
    assert result["radius_95"] == 20
    assert result["calibration_end_season"] == 2013
    low = qp.residual_intervals(history.head(10), 2014, "epa", "B2", _small_config())
    assert low["radius_95"] is None
    with pytest.raises(ValueError, match="future residual"):
        qp.residual_intervals(
            history.with_columns(pl.lit(2014).alias("target_season")),
            2014,
            "epa",
            "B2",
            _small_config(),
        )


def test_deterministic_folds_and_current_future_outcomes_do_not_change_predictions():
    f, config = _synthetic(), _small_config()
    a, folds, _ = qp.rolling_predictions(f, config)
    b, folds2, _ = qp.rolling_predictions(f.reverse(), config)
    # Sorting occurs at the cohort boundary in production; explicitly impose it here.
    c, _, _ = qp.rolling_predictions(f.sort("target_season", "player_id"), config)
    np.testing.assert_allclose(a["prediction"].to_numpy(), c["prediction"].to_numpy(), atol=1e-12)
    np.testing.assert_allclose(a["prediction"].to_numpy(), b["prediction"].to_numpy(), atol=1e-12)
    assert_frame_equal(folds, folds2)
    changed = f.with_columns(
        pl.when(pl.col("target_season") >= 2016)
        .then(999.0)
        .otherwise(pl.col("outcome_epa"))
        .alias("outcome_epa")
    )
    altered, _, _ = qp.rolling_predictions(changed, config)
    cols = qp.KEY + ["model", "outcome", "prediction", "lower_95", "upper_95"]
    assert_frame_equal(
        a.filter(pl.col("target_season") == 2016).select(cols),
        altered.filter(pl.col("target_season") == 2016).select(cols),
    )
    paired = qp.paired_comparison(a, config)
    selected = qp.select_models(a, paired, config)
    assert selected == qp.select_models(altered, qp.paired_comparison(altered, config), config)


def test_no_2026_state_is_generated_from_historical_or_scheme_data(built):
    predictors = built[0]
    assert predictors["target_season"].max() == 2025
    result = qp.forward_readiness(predictors)
    assert result["projected_qbs"] == 0 and result["approved_state_rows"] == 0
    with pytest.raises(ValueError, match="invalid forward"):
        qp.forward_readiness(
            predictors.head(1).with_columns(
                pl.lit(2026).alias("target_season"), pl.lit(2026).alias("maximum_source_season")
            )
        )


def test_version_changes_with_parameters_inputs_dependencies_and_code():
    c = qp.ProjectionConfig()
    original = qp.content_identity({"source": "hash"}, c)[0]
    assert qp.content_identity({"source": "changed"}, c)[0] != original
    assert (
        qp.content_identity({"source": "hash"}, replace(c, minimum_calibration=101))[0] != original
    )
    with patch.object(qp.scipy, "__version__", "changed"):
        assert qp.content_identity({"source": "hash"}, c)[0] != original
    with patch.object(qp, "HEADER_FEATURES", qp.HEADER_FEATURES + ("changed",)):
        assert qp.content_identity({"source": "hash"}, c)[0] != original


def test_two_independent_builds_same_version_bytes_and_reuse(tmp_path):
    a = qp.run_checkpoint_sixteen(PROJECT, tmp_path / "a")
    b = qp.run_checkpoint_sixteen(PROJECT, tmp_path / "b")
    assert a == b
    va, vb = tmp_path / "a" / a["data_version"], tmp_path / "b" / b["data_version"]
    assert sorted(p.name for p in va.iterdir()) == sorted(p.name for p in vb.iterdir())
    for p in va.iterdir():
        assert p.read_bytes() == (vb / p.name).read_bytes(), p.name
    assert qp.run_checkpoint_sixteen(PROJECT, tmp_path / "a") == a
    assert a["counts"]["eligible_player_seasons"] == 813
    assert a["counts"]["forward"]["projected_qbs"] == 0
    assert a["checkpoint_17_readiness"] == "NOT READY"


def test_publication_failure_preserves_old_pointer_and_version_changes_rebuild(tmp_path):
    first = qp.run_checkpoint_sixteen(PROJECT, tmp_path)
    pointer = (tmp_path / "LATEST").read_bytes()
    before = {p.name: p.read_bytes() for p in (tmp_path / first["data_version"]).iterdir()}
    config = replace(qp.ProjectionConfig(), minimum_calibration=101)
    original = pl.DataFrame.write_parquet
    calls = 0

    def fail_after_partial(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected partial publication failure")
        return original(self, *args, **kwargs)

    with patch.object(pl.DataFrame, "write_parquet", fail_after_partial):
        with pytest.raises(RuntimeError, match="partial publication"):
            qp.run_checkpoint_sixteen(PROJECT, tmp_path, config)
    assert (tmp_path / "LATEST").read_bytes() == pointer
    assert before == {p.name: p.read_bytes() for p in (tmp_path / first["data_version"]).iterdir()}
    assert not list(tmp_path.glob(".*"))
    changed = qp.run_checkpoint_sixteen(PROJECT, tmp_path, config)
    assert first["data_version"] != changed["data_version"]
    assert (tmp_path / "LATEST").read_text().strip() == changed["data_version"]
    assert qp.run_checkpoint_sixteen(PROJECT, tmp_path) == first
    assert (tmp_path / "LATEST").read_bytes() == pointer
    with (tmp_path / first["data_version"] / "checkpoint_decision.csv").open("a") as handle:
        handle.write("tampered\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        qp.run_checkpoint_sixteen(PROJECT, tmp_path)

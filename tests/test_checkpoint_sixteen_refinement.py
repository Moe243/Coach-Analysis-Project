"""Calibration chronology, frozen selection, and forward candidate-state contracts."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from nfl_coaching_impact import qb_player_state as state
from nfl_coaching_impact import qb_projection as qp
from nfl_coaching_impact import qb_projection_refinement as ref

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inputs():
    return ref.load_frozen_inputs(ROOT)


@pytest.fixture(scope="module")
def calibrated(inputs):
    return ref.calibrate_oos(
        inputs[0]["oos"], inputs[2]["counts"]["selected_models"], ref.RefinementConfig()
    )[0]


def test_original_selection_is_development_only_and_correct(inputs):
    frames = inputs[0]
    audit = ref.audit_original_selection(frames["oos"], frames["comparison"])
    epa = audit.filter((pl.col("outcome") == "epa") & (pl.col("candidate") == "M1")).row(
        0, named=True
    )
    assert epa["selected"] == "B2"
    assert epa["mean_fold_mae_gain"] == pytest.approx(0.00219285665)
    assert epa["mean_fold_mae_gain"] < epa["required_gain"]
    assert not epa["validation_used_for_choice"]
    changed = frames["oos"].with_columns(
        pl.when(pl.col("target_season") >= 2019)
        .then(999.0)
        .otherwise(pl.col("actual"))
        .alias("actual")
    )
    assert_frame_equal(
        audit,
        ref.audit_original_selection(changed, qp.paired_comparison(changed, qp.ProjectionConfig())),
    )


def _history():
    x = np.linspace(-0.2, 0.2, 120)
    return pl.DataFrame(
        {
            "target_season": [2013] * 40 + [2014] * 40 + [2015] * 40,
            "prediction": x,
            "actual": 0.05 + 2 * x,
        }
    )


def test_calibrator_known_linear_fit_intercept_and_minimum_history():
    cfg = ref.RefinementConfig()
    history = _history()
    none = ref.calibration_parameters(history, 2016, "NONE", cfg)
    bias = ref.calibration_parameters(history, 2016, "BIAS", cfg)
    linear = ref.calibration_parameters(history, 2016, "LINEAR", cfg)
    assert (none["bias"], none["slope"]) == (0, 1)
    assert bias["bias"] == pytest.approx(0.05)
    assert (linear["bias"], linear["slope"]) == pytest.approx((0.05, 2))
    assert linear["fit_end"] == 2015 and linear["fit_n"] == 120
    short = ref.calibration_parameters(history.head(99), 2016, "LINEAR", cfg)
    assert short["calibrator_status"] == "INSUFFICIENT_OOS_HISTORY"
    constant = ref.calibration_parameters(
        history.with_columns(pl.lit(1.0).alias("prediction")), 2016, "LINEAR", cfg
    )
    assert constant["calibrator_status"] == "INSUFFICIENT_PREDICTION_VARIATION"


@pytest.mark.parametrize("method", ref.METHODS)
def test_calibrator_rejects_current_and_future_oos(method):
    with pytest.raises(ValueError, match="leakage"):
        ref.calibration_parameters(_history(), 2015, method, ref.RefinementConfig())


def test_none_is_byte_value_equivalent_to_original_intervals(inputs, calibrated):
    for outcome, model in inputs[2]["counts"]["selected_models"].items():
        original = inputs[0]["oos"].filter(
            (pl.col("outcome") == outcome) & (pl.col("model") == model)
        )
        none = calibrated.filter((pl.col("outcome") == outcome) & (pl.col("model") == "NONE"))
        columns = qp.KEY + [
            "prediction",
            "lower_50",
            "upper_50",
            "lower_80",
            "upper_80",
            "lower_95",
            "upper_95",
            "calibration_n",
        ]
        assert_frame_equal(original.select(columns).sort(qp.KEY), none.select(columns).sort(qp.KEY))


def test_target_outcome_mutation_cannot_change_points_intervals_or_selection(inputs, calibrated):
    frames, _, manifest = inputs
    altered = frames["oos"].with_columns(
        pl.when(pl.col("target_season") >= 2022)
        .then(200.0)
        .otherwise(pl.col("actual"))
        .alias("actual")
    )
    changed, fits = ref.calibrate_oos(
        altered, manifest["counts"]["selected_models"], ref.RefinementConfig()
    )
    columns = qp.KEY + [
        "outcome",
        "model",
        "prediction",
        "lower_50",
        "upper_95",
        "fit_end",
        "calibration_end_season",
    ]
    assert_frame_equal(
        calibrated.filter(pl.col("target_season") <= 2022).select(columns),
        changed.filter(pl.col("target_season") <= 2022).select(columns),
    )
    assert not fits.filter(pl.col("fit_end") >= pl.col("target_season")).height
    assert not changed.filter(pl.col("calibration_end_season") >= pl.col("target_season")).height
    assert (
        ref.select_calibrators(calibrated, ref.RefinementConfig())[0]
        == ref.select_calibrators(changed, ref.RefinementConfig())[0]
    )


def test_acceptance_uses_actual_fold_counts_and_unchanged_thresholds(inputs, calibrated):
    selected, _ = ref.select_calibrators(calibrated, ref.RefinementConfig())
    _, _, decisions, folds = ref.assess_calibration(
        inputs[0]["oos"], calibrated, selected, ref.RefinementConfig()
    )
    assert selected == {"epa": "BIAS", "pae": "NONE"}
    assert (
        folds.filter(
            (pl.col("outcome") == "epa")
            & (pl.col("method") == "BIAS")
            & (pl.col("target_season") >= 2019)
        ).height
        == 7
    )
    assert decisions.filter(pl.col("is_selected") & (pl.col("outcome") == "epa"))[
        "point_acceptance"
    ].item()
    assert not decisions.filter(pl.col("is_selected") & (pl.col("outcome") == "pae"))[
        "point_acceptance"
    ].item()
    linear_pae = decisions.filter(
        (pl.col("outcome") == "pae") & (pl.col("method") == "LINEAR")
    ).row(0, named=True)
    assert not linear_pae["accuracy_guard_passed"]
    assert not linear_pae["is_selected"]
    assert linear_pae["model_status"] == "NOT SUPPORTED"
    assert qp.ProjectionConfig().acceptance_maximum_intercept == 0.05
    assert qp.ProjectionConfig().acceptance_slope_bounds == (0.5, 1.5)


@pytest.fixture(scope="module")
def candidates(inputs):
    return ref.candidate_states(
        inputs[0], "candidate-test", inputs[1]["profiles"], ref.RefinementConfig()
    )


def test_2026_candidate_contract_is_history_not_current_roster(inputs, candidates):
    universe, states, records, matrix = candidates
    assert states.height == universe.height == matrix.height == 57
    assert states["player_id"].n_unique() == 57
    assert states["target_season"].unique().to_list() == [2026]
    assert states["as_of_date"].unique().to_list() == ["2026-08-31"]
    assert states["maximum_source_season"].max() == 2025
    assert (
        states["historical_source_version"].unique().to_list()
        == inputs[0]["states"]["historical_source_version"].unique().to_list()
    )
    assert records["standardization_fit_end_season"].max() == 2025
    assert not states["active_roster_claim"].any()
    assert not any("team" in n or "scheme" in n or "coach" in n for n in matrix.columns)
    assert set(qp.MODEL_FEATURES) <= set(matrix.columns)
    assert max(state.TARGET_SEASONS) == 2025  # historical default remains unchanged
    expected = inputs[0]["profiles"].filter(
        (pl.col("season") == 2025)
        & (pl.col("feature_name") == "epa_per_dropback")
        & (pl.col("denominator") >= 50)
    )["player_id"]
    assert set(universe["player_id"]) == set(expected)


@pytest.mark.parametrize("source", ["profiles", "performance"])
def test_candidate_rejects_2026_source_outcomes(inputs, source):
    frames = dict(inputs[0])
    frames[source] = pl.concat(
        [frames[source], frames[source].head(1).with_columns(pl.lit(2026).alias("season"))],
        how="vertical_relaxed",
    )
    with pytest.raises(ValueError, match="future/2026"):
        ref.candidate_states(frames, "candidate-test", "hash", ref.RefinementConfig())


def test_candidate_does_not_use_target_team_status_or_future_master_fields(inputs, candidates):
    frames = dict(inputs[0])
    frames["players"] = frames["players"].with_columns(
        pl.lit("invented_team").alias("latest_team"),
        pl.lit("retired").alias("status"),
        pl.lit(2026).alias("last_season"),
        pl.lit(999.0).alias("outcome_2026"),
    )
    changed = ref.candidate_states(
        frames, "candidate-test", inputs[1]["profiles"], ref.RefinementConfig()
    )
    for a, b in zip(candidates, changed, strict=True):
        assert_frame_equal(a, b)


def test_default_c14_feature_values_remain_identical(inputs):
    root = ROOT / "data/processed/qb_player_state" / qp.C14_VERSION
    universe = (
        pl.read_parquet(root / "qb_state_universe.parquet")
        .filter(pl.col("target_season") == 2025)
        .head(8)
    )
    registry = tuple(ref.FeatureDefinition(**r) for r in inputs[0]["registry"].to_dicts())
    default = state.build_state_features(
        universe, inputs[0]["profiles"], registry, data_version="test", source_hash="hash"
    )
    explicit = state.build_state_features(
        universe,
        inputs[0]["profiles"],
        registry,
        data_version="test",
        source_hash="hash",
        target_seasons=(2025,),
    )
    assert_frame_equal(default, explicit)


def test_b2_extension_reproduces_historical_baseline_exactly(inputs):
    c5 = inputs[0]["c5"]
    for year in (2013, 2018, 2025):
        targets = (
            inputs[0]["oos"]
            .filter(
                (pl.col("outcome") == "epa")
                & (pl.col("model") == "B2")
                & (pl.col("target_season") == year)
            )
            .sort("player_id")
        )
        predicted, metadata = ref.b2_forward(c5.filter(pl.col("season") < year), targets, year)
        np.testing.assert_allclose(predicted, targets["prediction"].to_numpy(), atol=1e-12, rtol=0)
        assert metadata["history_end"] < year


def test_forward_projection_gate_blocks_unapproved_outcomes(inputs, calibrated, candidates):
    decisions = pl.DataFrame(
        [
            {
                "outcome": "epa",
                "is_selected": True,
                "projection_intervals_supported": False,
                "model_status": "NOT SUPPORTED",
            }
        ]
    )
    forward, params = ref.forward_projections(
        inputs[0], candidates[3], calibrated, decisions, ref.RefinementConfig(), "version"
    )
    assert forward.height == 0 and params == []


def test_two_independent_refinement_builds_preserve_original_and_match_bytes(tmp_path):
    source = ROOT / "data/processed/qb_projection" / ref.ORIGINAL_VERSION
    originals = {p.name: qp._digest(p.read_bytes()) for p in source.iterdir()}
    a, b = ref.run_refinement(ROOT, tmp_path / "a"), ref.run_refinement(ROOT, tmp_path / "b")
    assert a == b
    for p in (tmp_path / "a" / a["data_version"]).iterdir():
        assert p.read_bytes() == (tmp_path / "b" / b["data_version"] / p.name).read_bytes(), p.name
    assert (tmp_path / "a" / "LATEST").read_bytes() == (tmp_path / "b" / "LATEST").read_bytes()
    assert originals == {p.name: qp._digest(p.read_bytes()) for p in source.iterdir()}
    assert a["forward_qbs"] == 57 and a["forward_projection_rows"] == 57
    assert a["checkpoint_17_readiness"] == "NOT READY"
    projections = pl.read_parquet(tmp_path / "a" / a["data_version"] / "projections_2026.parquet")
    assert projections["outcome"].unique().to_list() == ["epa"]
    assert projections["label"].unique().to_list() == [ref.LABEL]
    assert not any("team_id" in c or "coach" in c or "scheme" in c for c in projections.columns)
    assert ref.run_refinement(ROOT, tmp_path / "a") == a
    changed = ref.run_refinement(
        ROOT, tmp_path / "a", replace(ref.RefinementConfig(), candidate_minimum_dropbacks=100)
    )
    assert changed["data_version"] != a["data_version"]
    with patch.object(ref.qp.scipy, "__version__", "different"):
        dependency = ref.run_refinement(ROOT, tmp_path / "a")
    assert dependency["data_version"] != a["data_version"]

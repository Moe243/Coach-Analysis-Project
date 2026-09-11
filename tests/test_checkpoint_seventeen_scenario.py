"""Actual frozen inputs and fitted designs: conditioning, chronology, negative gates."""

import copy
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from nfl_coaching_impact import qb_projection as qp
from nfl_coaching_impact import qb_scenario as sc

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inputs():
    return sc.load_inputs(ROOT)


@pytest.fixture(scope="module")
def scheme(inputs):
    return sc.scheme_matrix(inputs[1], tuple(range(2011, 2027)))[0]


@pytest.fixture(scope="module")
def cohort(inputs, scheme):
    f = inputs[0]
    return sc.build_cohort(
        f["predictors"],
        f["performance"],
        f["calibrated_oos_predictions.parquet"],
        scheme,
        sc.ScenarioConfig(),
    )


@pytest.fixture(scope="module")
def experiment(cohort):
    return sc.rolling_models(cohort, sc.ScenarioConfig())


def test_multiteam_baker_2022_has_one_frozen_state_two_conditions(cohort, inputs):
    f = cohort.filter((pl.col("player_id") == "00-0034855") & (pl.col("target_season") == 2022))
    assert f.height == 2 and f["eligible"].all()
    assert set(f["team_id"]) == {"team_car", "team_la"}
    assert f["base_epa"].n_unique() == 1 and f["state_version"].n_unique() == 1
    assert f["actual"].n_unique() == 2 and sorted(f["dropbacks"].to_list()) == [152, 234]
    assert f["team_change"].all()
    assert not f["preseason_assignment_claim"].any()
    assert all("SUPPLIED_RETROSPECTIVE" in x for x in f["condition_basis"])
    frozen = inputs[0]["predictors"].filter(
        (pl.col("player_id") == "00-0034855") & (pl.col("target_season") == 2022)
    )
    assert frozen.height == 1 and frozen["maximum_source_season"].item() < 2022
    assert f["scheme_max_source_season"].max() < 2022


def test_outcomes_cannot_create_states_or_change_predictors(inputs, scheme, cohort):
    f = inputs[0]
    changed = f["performance"].with_columns((pl.col("total_qb_epa") + 10000).alias("total_qb_epa"))
    got = sc.build_cohort(
        f["predictors"],
        changed,
        f["calibrated_oos_predictions.parquet"],
        scheme,
        sc.ScenarioConfig(),
    )
    features = sc.KEY + list(sc.STYLE + sc.SCHEME_COLUMNS) + ["base_epa", "maximum_source_season"]
    assert_frame_equal(got.select(features), cohort.select(features))
    removed = f["predictors"].filter(pl.col("player_id") != "00-0034855")
    got = sc.build_cohort(
        removed, changed, f["calibrated_oos_predictions.parquet"], scheme, sc.ScenarioConfig()
    )
    assert got.filter(pl.col("player_id") == "00-0034855")[
        "exclusion_reason"
    ].unique().to_list() == ["NOT_IN_ASOF_STATE_UNIVERSE"]


@pytest.mark.parametrize(
    "field,value", [("maximum_source_season", 9999), ("as_of_date", "9999-09-01")]
)
def test_player_source_timing_rejected(inputs, scheme, field, value):
    f = inputs[0]
    with pytest.raises(ValueError, match="player source/as-of"):
        sc.build_cohort(
            f["predictors"].with_columns(pl.lit(value).alias(field)),
            f["performance"],
            f["calibrated_oos_predictions.parquet"],
            scheme,
            sc.ScenarioConfig(),
        )


@pytest.mark.parametrize(
    "field", ["source_season", "source_available_date", "standardization_fit_end_season"]
)
def test_scheme_future_and_post_cutoff_sources_rejected(inputs, field):
    store = copy.copy(inputs[1])
    value = pl.col("target_season") if field != "source_available_date" else pl.lit("2099-09-01")
    store.records = store.records.with_columns(value.alias(field))
    with pytest.raises(ValueError, match="leakage"):
        sc.scheme_matrix(store, (2020,))


def test_unregistered_and_forbidden_features_rejected(inputs):
    for name in ("coach_effect", "outcome_pae", "target_season_epa", "team_id", "unregistered"):
        with pytest.raises(ValueError, match="unregistered or forbidden"):
            sc.validate_predictor_names((name,))
    with pytest.raises(ValueError, match="not enabled"):
        inputs[1].target_matrix(
            target_season=2020,
            feature_names=("q_head_coach",),
            entity_grain=inputs[1].registry["q_head_coach"]["entity_grain"],
        )


def test_fitted_design_train_only_centering_and_pure_interactions(cohort):
    train = cohort.filter(pl.col("eligible") & (pl.col("target_season") < 2019))
    cfg = sc.ScenarioConfig()
    d = sc.Design.fit(train, 2019, "M2", cfg)
    x, names = d.transform(train)
    sx, _ = d.scheme.transform(train)
    px, _ = d.player.transform(train)
    main = np.column_stack((np.ones(len(sx)), sx, px))
    z = x[:, sx.shape[1] :]
    np.testing.assert_allclose(main.T @ z / len(train), 0, atol=1e-8)
    np.testing.assert_allclose(x.mean(axis=0), 0, atol=1e-10)
    assert "deep_depth_alignment" in names and d.scheme.fitted_end_season == 2018
    raw, pnames = sc.Design._products(
        train, sx, d.scheme.transform(train)[1], px, d.player.transform(train)[1]
    )
    i = pnames.index("deep_depth_alignment")
    sn = d.scheme.transform(train)[1]
    pn = d.player.transform(train)[1]
    mask = (
        train["recent_target_depth_deep_rate"].is_not_null()
        & train["scheme_target_depth_deep_rate"].is_not_null()
    ).to_numpy()
    np.testing.assert_allclose(
        raw[:, i],
        px[:, pn.index("recent_target_depth_deep_rate")]
        * sx[:, sn.index("scheme_target_depth_deep_rate")]
        * mask,
    )


def test_missingness_preserved_and_not_invented(cohort):
    f = cohort.filter(pl.col("eligible"))
    assert f["recent_average_air_yards"].null_count() > 0
    d = sc.Design.fit(f.filter(pl.col("target_season") < 2020), 2020, "M2", sc.ScenarioConfig())
    test = f.filter(pl.col("target_season") == 2020)
    before = test.clone()
    x, names = d.transform(test)
    assert np.isfinite(x).all()
    assert "deep_depth_alignment__observed" in names
    assert_frame_equal(before, test)


def test_target_outcomes_do_not_change_fitted_prediction_or_tuning(cohort):
    cfg = sc.ScenarioConfig()
    train = cohort.filter(pl.col("eligible") & (pl.col("target_season") < 2020))
    test = cohort.filter(pl.col("eligible") & (pl.col("target_season") == 2020))
    alpha, audit = sc.tune_alpha(train, 2020, "M2", cfg)
    a = sc.fit_adjustment(train, test, 2020, "M2", alpha, cfg)[0]
    b = sc.fit_adjustment(
        train,
        test.with_columns(pl.lit(999.0).alias("actual"), pl.lit(-999.0).alias("residual_target")),
        2020,
        "M2",
        alpha,
        cfg,
    )[0]
    np.testing.assert_array_equal(a, b)
    assert audit and all(r["fit_end"] < r["inner_year"] < 2020 for r in audit)
    with pytest.raises(ValueError, match="tuning leakage"):
        sc.tune_alpha(pl.concat([train, test]), 2020, "M2", cfg)
    with pytest.raises(ValueError, match="training leakage"):
        sc.fit_adjustment(pl.concat([train, test]), test, 2020, "M2", alpha, cfg)


def test_real_team_change_cohort_and_no_false_rookie_changes(cohort):
    # Brady to Tampa Bay in 2020; Mahomes stayed with Kansas City.
    brady = cohort.filter((pl.col("player_id") == "00-0019596") & (pl.col("target_season") == 2020))
    mahomes = cohort.filter(
        (pl.col("player_id") == "00-0033873") & (pl.col("target_season") == 2020)
    )
    assert brady["team_change"].item() and not mahomes["team_change"].item()
    burrow = cohort.filter(
        (pl.col("player_id") == "00-0036442") & (pl.col("target_season") == 2020)
    )
    assert burrow["team_change"].item() is None


def test_rolling_folds_and_baseline_exactness(experiment, cohort):
    p, folds, _, tuning = experiment
    assert set(folds["target_season"]) == set(range(2016, 2026))
    assert folds.filter(pl.col("train_end") >= pl.col("target_season")).is_empty()
    assert tuning.filter(pl.col("inner_year") >= pl.col("target_season")).is_empty()
    assert (
        p.filter(pl.col("model") == "M0")
        .select((pl.col("prediction") == pl.col("base_epa")).all())
        .item()
    )
    assert p.filter(pl.col("calibration_end_season") >= pl.col("target_season")).is_empty()
    assert (
        p.filter(pl.col("target_season") == 2016)["lower_95"].null_count()
        == p.filter(pl.col("target_season") == 2016).height
    )
    # Permuting input row order cannot change scientific fold assignment or fitted values.
    q, f, _, _ = sc.rolling_models(
        cohort.reverse().sort("target_season", "player_id", "team_id"), sc.ScenarioConfig()
    )
    assert_frame_equal(folds, f)
    assert_frame_equal(p, q)


def test_future_fold_mutation_preserves_same_year_points_and_intervals(cohort, experiment):
    changed = cohort.with_columns(
        pl.when(pl.col("target_season") >= 2025)
        .then(999.0)
        .otherwise(pl.col("actual"))
        .alias("actual"),
        pl.when(pl.col("target_season") >= 2025)
        .then(999.0)
        .otherwise(pl.col("residual_target"))
        .alias("residual_target"),
    )
    p = sc.rolling_models(changed, sc.ScenarioConfig())[0]
    cols = sc.KEY + ["model", "prediction", "lower_50", "upper_80", "lower_95"]
    assert_frame_equal(p.select(cols), experiment[0].select(cols))


def test_resampling_repeatability_and_negative_gate(experiment):
    cfg = sc.ScenarioConfig()
    boot, placebo = sc.resampling(experiment[0], cfg)
    b, p = sc.resampling(experiment[0], cfg)
    assert_frame_equal(boot, b)
    assert_frame_equal(placebo, p)
    assert boot["successful_draws"].min() == 1000
    assert set(boot["cluster"]) == {"qb", "team_season"}
    assert all("NOT_RANDOMIZED" in method for method in placebo["method"])
    comparisons, folds, coverage = sc.summarize(experiment[0], cfg)
    decisions = sc.decide(comparisons, folds, coverage, boot, cfg)
    assert not decisions["approved"].any()
    assert decisions["status"].unique().to_list() == ["NOT SUPPORTED"]
    # Failed approval must short-circuit before touching any candidate/environment.
    out = sc.forward_scenarios(None, None, None, None, None, decisions, cfg, "fixture")
    assert out.is_empty() and "prediction" in out.columns


def test_null_duplicate_and_contradictory_baseline_rejected(inputs, scheme):
    f = inputs[0]
    baseline = f["calibrated_oos_predictions.parquet"]
    duplicate = baseline.filter((pl.col("outcome") == "epa") & (pl.col("model") == "BIAS")).head(1)
    with pytest.raises(ValueError, match="duplicate grain"):
        sc.build_cohort(
            f["predictors"],
            f["performance"],
            pl.concat([baseline, duplicate]),
            scheme,
            sc.ScenarioConfig(),
        )
    with pytest.raises(ValueError, match="baseline lineage"):
        sc.build_cohort(
            f["predictors"],
            f["performance"],
            baseline.with_columns(pl.lit(2030).alias("fit_end")),
            scheme,
            sc.ScenarioConfig(),
        )
    with pytest.raises(ValueError, match="null identifiers"):
        sc.build_cohort(
            f["predictors"],
            f["performance"].with_columns(pl.lit(None, dtype=pl.String).alias("team_id")),
            baseline,
            scheme,
            sc.ScenarioConfig(),
        )


def test_every_versioned_input_config_dependency_changes_identity(inputs):
    hashes = inputs[2]
    cfg = sc.ScenarioConfig()
    v, _ = sc.content_identity(hashes, cfg)
    assert sc.content_identity({**hashes, "modified": "new bytes"}, cfg)[0] != v
    assert sc.content_identity(hashes, replace(cfg, relative_gain=0.03))[0] != v
    with patch.object(qp.scipy, "__version__", "mock-change"):
        assert sc.content_identity(hashes, cfg)[0] != v
    with patch.object(sc, "INTERACTIONS", sc.INTERACTIONS[:-1]):
        assert sc.content_identity(hashes, cfg)[0] != v
    with patch.object(sc, "SCHEME", sc.SCHEME[:-1]):
        assert sc.content_identity(hashes, cfg)[0] != v


def test_two_real_independent_builds_identical_and_old_artifacts_untouched(tmp_path):
    original = ROOT / "data/processed/qb_projection_refinement" / sc.BASE_VERSION / "MANIFEST.json"
    before = original.read_bytes()
    left, right = tmp_path / "one", tmp_path / "two"
    a = sc.run_checkpoint_seventeen(ROOT, left)
    b = sc.run_checkpoint_seventeen(ROOT, right)
    assert a == b
    assert (left / "LATEST").read_bytes() == (right / "LATEST").read_bytes()
    for name in list(a["output_checksums"]) + ["MANIFEST.json"]:
        assert (left / a["data_version"] / name).read_bytes() == (
            right / b["data_version"] / name
        ).read_bytes()
    assert sc.run_checkpoint_seventeen(ROOT, left) == a
    assert original.read_bytes() == before
    assert a["counts"]["forward_rows"] == 0
    assert a["scenario_status"] == "NOT SUPPORTED" and a["checkpoint_18_readiness"] == "NOT READY"
    manifest = json.loads((left / a["data_version"] / "MANIFEST.json").read_bytes())
    assert manifest["identity"]["anchor_version"] == sc.BASE_VERSION

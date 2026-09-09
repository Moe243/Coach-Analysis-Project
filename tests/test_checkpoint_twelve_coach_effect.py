from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from research.coach_effect.checkpoint_twelve import (
    CORE_SCORE_COMPONENTS,
    ENVIRONMENT_FEATURES,
    PAE_KEY,
    PRODUCTION_LOAD_ID,
    SCHEME_FEATURES,
    _load_pae,
    _sources,
    build_confidence_and_suppression,
    build_estimates,
    build_joined_research_table,
    build_placebos,
    build_presentation,
    build_reliability,
    empirical_bayes,
    fit_training_only_ridge,
    rolling_movement_predictions,
    run_checkpoint_twelve,
    scheme_component_gate,
    training_residual_components,
)

ROOT = Path(__file__).resolve().parents[1]


class CheckpointTwelveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = _sources(ROOT)
        cls.pae = _load_pae(cls.sources.pae_path)
        cls.joined, cls.folds, cls.pcae = build_joined_research_table(ROOT, cls.sources)

    def test_pae_join_preserves_full_lineage_and_actual_multi_team_season(self) -> None:
        self.assertEqual({PRODUCTION_LOAD_ID}, set(self.joined["load_id"]))
        multi = (
            self.pae.group_by("player_id", "season")
            .agg(pl.col("team_id").n_unique().alias("teams"))
            .filter(pl.col("teams") > 1)
            .sort("season", "player_id")
            .head(1)
            .row(0, named=True)
        )
        source = self.pae.filter(
            (pl.col("player_id") == multi["player_id"]) & (pl.col("season") == multi["season"])
        )
        attached = (
            self.joined.filter(
                (pl.col("player_id") == multi["player_id"]) & (pl.col("season") == multi["season"])
            )
            .select(*PAE_KEY, "performance_above_expectation")
            .unique()
        )
        self.assertEqual(set(source["team_id"]), set(attached["team_id"]))
        expected = {
            (row["team_id"], row["performance_above_expectation"])
            for row in source.select("team_id", "performance_above_expectation").to_dicts()
        }
        actual = {
            (row["team_id"], row["performance_above_expectation"])
            for row in attached.select("team_id", "performance_above_expectation").to_dicts()
        }
        self.assertEqual(expected, actual)

    def test_pae_arithmetic_and_q_folds_have_no_future_leakage(self) -> None:
        error = self.pae.select(
            (
                pl.col("actual_epa_per_dropback")
                - pl.col("expected_epa_per_dropback")
                - pl.col("performance_above_expectation")
            )
            .abs()
            .max()
        ).item()
        self.assertLess(error, 1e-12)
        for row in self.folds.to_dicts():
            self.assertLess(row["training_end_season"], row["target_season"])
            self.assertEqual("training_only", row["preprocessing_fit_scope"])

    def test_pcae_is_verified_only_and_zero_attribution_is_not_zero_pcae(self) -> None:
        self.assertEqual({"verified"}, set(self.pcae["verification_status"]))
        self.assertEqual(0, self.pcae.filter(pl.col("attributed_play_count") <= 0).height)
        non_callers = self.joined.filter(pl.col("role") != "play_caller")
        self.assertEqual(non_callers.height, non_callers["pcae"].null_count())
        self.assertGreater(
            self.joined.filter((pl.col("role") == "play_caller") & pl.col("pcae").is_null()).height,
            0,
        )

    def test_standardization_is_fit_on_training_only(self) -> None:
        train = pl.DataFrame({"x": [0.0, 2.0, 4.0], "y": [0.0, 1.0, 2.0]})
        test = pl.DataFrame({"x": [1_000.0], "y": [0.0]})
        _, model = fit_training_only_ridge(train, test, features=("x",), outcome="y", alpha=1.0)
        self.assertAlmostEqual(2.0, float(model.named_steps["scale"].mean_[0]))

    def test_residualization_is_fit_on_training_only(self) -> None:
        train_q = np.asarray([1.0, 2.0, 3.0, 4.0])
        train_p = np.asarray([2.0, 4.0, 6.0, 8.0])
        test_q = np.asarray([100.0])
        test_p = np.asarray([0.0])
        unique_q, unique_p, _, test_unique_q, test_unique_p, _ = training_residual_components(
            train_q, train_p, test_q, test_p
        )
        self.assertTrue(np.allclose(unique_q, 0.0))
        self.assertTrue(np.allclose(unique_p, 0.0))
        self.assertGreater(abs(float(test_unique_q[0])), 1.0)
        self.assertGreater(abs(float(test_unique_p[0])), 1.0)

    def test_folds_and_permutations_are_deterministic(self) -> None:
        _, first_folds = rolling_movement_predictions(self.pae)
        _, second_folds = rolling_movement_predictions(self.pae)
        self.assertTrue(first_folds.equals(second_folds))
        _, signal_tables = build_reliability(self.joined, self.pcae)
        first = build_placebos(signal_tables)
        second = build_placebos(signal_tables)
        self.assertTrue(first.equals(second))

    def test_empirical_bayes_shrinkage_moves_estimates_toward_prior(self) -> None:
        fixture = pl.DataFrame(
            {
                "role": ["r", "r", "r", "r"],
                "coach_id": ["a", "a", "b", "b"],
                "coach_name": ["A", "A", "B", "B"],
                "season": [2020, 2021, 2020, 2021],
                "player_id": ["q1", "q2", "q3", "q4"],
                "team_id": ["t1", "t1", "t2", "t2"],
                "signal": [0.10, 0.30, -0.10, -0.30],
                "weight": [100.0, 100.0, 100.0, 100.0],
            }
        )
        result = empirical_bayes(fixture, signal="signal", exposure="weight")
        for row in result.to_dicts():
            self.assertLessEqual(
                abs(row["posterior_estimate"] - row["prior_center"]),
                abs(row["raw_estimate"] - row["prior_center"]),
            )
            self.assertGreaterEqual(row["shrinkage_weight"], 0.0)
            self.assertLessEqual(row["shrinkage_weight"], 1.0)

    def test_confidence_is_separate_and_environment_is_not_points(self) -> None:
        q_estimates, p_estimates, _ = build_estimates(self.joined, self.pcae)
        confidence, suppression = build_confidence_and_suppression(q_estimates, p_estimates)
        self.assertEqual({False}, set(confidence["confidence_multiplies_score"]))
        self.assertEqual({True}, set(confidence["variance_component_at_boundary"]))
        self.assertEqual(
            0,
            confidence.filter(pl.col("interval_width") <= 0).height,
        )
        self.assertNotIn("confidence_level", CORE_SCORE_COMPONENTS)
        self.assertTrue(set(ENVIRONMENT_FEATURES).isdisjoint(CORE_SCORE_COMPONENTS))
        self.assertEqual({"research_only_not_publishable"}, set(suppression["publication_status"]))
        presentation = build_presentation(suppression)
        self.assertEqual(
            {50.0},
            set(presentation.filter(pl.col("signal") == "pcae")["bounded_standardized_0_100"]),
        )

    def test_scheme_is_excluded_until_every_gate_passes(self) -> None:
        passed, reason = scheme_component_gate(
            ["shotgun_rate", "no_huddle_rate", "early_down_pass_rate"],
            {"portability": True},
        )
        self.assertFalse(passed)
        self.assertIn("missing_required_features", reason)
        passed, reason = scheme_component_gate(
            SCHEME_FEATURES,
            {
                "portability": True,
                "specificity": True,
                "persistence": True,
                "multi_team_repeatability": True,
                "future_association": True,
                "placebo_separation": True,
                "incremental_out_of_sample_value": True,
            },
        )
        self.assertTrue(passed)
        self.assertEqual("all_scheme_component_gates_passed", reason)

    def test_clean_builds_are_byte_identical_and_do_not_modify_production(self) -> None:
        protected = [
            ROOT / "data/processed/historical/LATEST",
            ROOT / "data/processed/expected_performance/LATEST",
            ROOT / "data/processed/coach_impact/LATEST",
            ROOT / "data/processed/enhancements/LATEST",
        ]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            result_1 = run_checkpoint_twelve(ROOT, Path(first))
            result_2 = run_checkpoint_twelve(ROOT, Path(second))
            self.assertEqual(result_1["research_data_version"], result_2["research_data_version"])
            files_1 = sorted(
                path.relative_to(first) for path in Path(first).rglob("*") if path.is_file()
            )
            files_2 = sorted(
                path.relative_to(second) for path in Path(second).rglob("*") if path.is_file()
            )
            self.assertEqual(files_1, files_2)
            for relative in files_1:
                self.assertEqual(
                    (Path(first) / relative).read_bytes(), (Path(second) / relative).read_bytes()
                )
        self.assertEqual(before, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

import research.coach_effect.checkpoint_twelve_review as review

ROOT = Path(__file__).resolve().parents[1]


class CheckpointTwelveAdversarialReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = review._sources(ROOT)
        (
            cls.pae,
            cls.assignments,
            cls.joined,
            cls.q,
            cls.pcae,
            cls.movement_folds,
        ) = review.build_independent_core(ROOT, cls.sources)

    def test_core_grains_have_no_many_to_many_multiplication(self) -> None:
        self.assertEqual(self.pae.height, self.pae.select(review.PAE_KEY).n_unique())
        self.assertEqual(
            self.joined.height,
            self.joined.select("assignment_key", "player_id", "team_id", "season").n_unique(),
        )
        self.assertEqual(self.pcae.height, self.pcae["assignment_key"].n_unique())

    def test_q_definition_is_assignment_qb_team_season_interval_residual(self) -> None:
        row = self.q.head(1).row(0, named=True)
        expected = row["coach_interval_pae"] - row["prior_pae"] - row["expected_normal_qb_delta"]
        self.assertAlmostEqual(expected, row["q_development_signal"], places=12)
        self.assertGreaterEqual(row["exposure_dropbacks"], review.MIN_Q_EXPOSURE)

    def test_movement_folds_are_strictly_chronological_and_training_only(self) -> None:
        self.assertTrue(
            all(
                row["training_end"] < row["target_season"]
                and row["preprocessing_scope"] == "training_only"
                for row in self.movement_folds.to_dicts()
            )
        )

    def test_pcae_is_verified_explicit_bounded_and_not_shared(self) -> None:
        self.assertEqual({"verified"}, set(self.pcae["verification_status"]))
        self.assertEqual(0, self.pcae.filter(pl.col("is_shared")).height)
        self.assertEqual(
            0, self.pcae.filter(pl.col("interval_basis") == "season_designation").height
        )
        self.assertEqual(0, self.pcae["primary_source_url"].null_count())

    def test_future_portability_does_not_use_future_rows(self) -> None:
        fixture = pl.DataFrame(
            {
                "coach_id": ["c", "c", "c"],
                "player_id": ["a", "b", "a"],
                "season": [2020, 2021, 2022],
                "signal": [1.0, 2.0, 100.0],
                "exposure": [10.0, 10.0, 10.0],
            }
        )
        _, predictions = review._future_portability(
            fixture,
            role="r",
            signal_name="s",
            signal="signal",
            exposure="exposure",
            group="player_id",
        )
        row_2021 = predictions.filter(pl.col("season") == 2021).row(0, named=True)
        self.assertEqual(1.0, row_2021["prediction"])
        changed = fixture.with_columns(
            pl.when(pl.col("season") == 2022)
            .then(9999.0)
            .otherwise(pl.col("signal"))
            .alias("signal")
        )
        _, changed_predictions = review._future_portability(
            changed,
            role="r",
            signal_name="s",
            signal="signal",
            exposure="exposure",
            group="player_id",
        )
        self.assertEqual(
            1.0,
            changed_predictions.filter(pl.col("season") == 2021)["prediction"][0],
        )

    def test_model_candidates_use_identical_rows_in_every_fold(self) -> None:
        frame = review.build_model_comparison(self.q, self.pcae)
        candidates = frame.filter(pl.col("model").str.starts_with("model_"))
        for fold in ("2024", "2025", "pooled"):
            counts = candidates.filter(pl.col("fold") == fold)["n"].unique().to_list()
            self.assertEqual([24 if fold == "2024" else 26 if fold == "2025" else 50], counts)
        self.assertEqual({True}, set(candidates["identical_population"]))
        pooled_model_4 = frame.filter(
            (pl.col("model") == "model_4_learned_joint") & (pl.col("fold") == "pooled")
        ).row(0, named=True)
        self.assertAlmostEqual(0.17504414094, pooled_model_4["pearson"], places=10)

    def test_joint_weight_stability_reproduces_candidate_and_covers_holdouts(self) -> None:
        with patch.object(review, "BOOTSTRAPS", 20):
            rows = review.build_weight_stability(self.q, self.pcae, self.sources)
        frame = pl.DataFrame(rows, infer_schema_length=None)
        reproduction = frame.filter(
            pl.col("metric") == "candidate_a_max_absolute_coefficient_reproduction_error"
        ).row(0, named=True)
        self.assertLess(reproduction["value"], 1e-9)
        self.assertTrue(
            {"fold", "row_bootstrap", "coach_holdout", "team_holdout", "qb_holdout"}
            <= {metric.rsplit("_beta_", 1)[0] for metric in frame["metric"] if "_beta_" in metric}
        )

    def test_correlation_grain_reconciliation_reproduces_prompt6_q_overlap(self) -> None:
        frame = review.build_overlap(self.q, self.pcae, self.pae)
        q_row = frame.filter(
            (pl.col("grain") == "prompt6_q_coach_season")
            & (pl.col("subset") == "full_common_historical")
        ).row(0, named=True)
        self.assertEqual(160, q_row["n"])
        self.assertAlmostEqual(0.108987575, q_row["pearson"], places=8)

    def test_variance_audit_uses_role_specific_intervals_and_reports_sensitivity(self) -> None:
        frame = review.build_variance(self.q, self.pcae)
        self.assertEqual(5, frame.height)
        self.assertEqual(5, frame.select("signal", "role").n_unique())
        self.assertTrue(all(frame["residual_df"] == frame["intervals"] - frame["coaches"]))
        play_caller_q = frame.filter(
            (pl.col("signal") == "q_development") & (pl.col("role") == "play_caller")
        ).row(0, named=True)
        self.assertEqual(0.0, play_caller_q["truncated_weighted_mom_tau2"])
        self.assertGreater(play_caller_q["reml_group_mean_tau2"], 0.0)

    def test_fold_availability_uses_individually_verified_partial_seasons(self) -> None:
        matrix = review.build_fold_matrix(ROOT, self.q, self.pcae)
        row_2023 = matrix.filter(pl.col("season") == 2023).row(0, named=True)
        self.assertEqual(9, row_2023["prior_training_rows"])
        self.assertFalse(row_2023["eligible_as_target"])
        self.assertEqual(
            {2024, 2025},
            set(matrix.filter(pl.col("eligible_as_target"))["season"]),
        )

    def test_placebo_is_deterministic(self) -> None:
        fixture = self.q.filter(pl.col("role") == "play_caller")
        grouped = review._group_for_portability(
            fixture, "q_development_signal", "exposure_dropbacks", "team_id"
        )
        summary, _ = review._future_portability(
            fixture,
            role="play_caller",
            signal_name="q",
            signal="q_development_signal",
            exposure="exposure_dropbacks",
            group="team_id",
        )
        with patch.object(review, "PERMUTATIONS", 50):
            first = review._placebo_portability(
                grouped,
                summary["pearson"],
                signal="q_development_signal",
                group="team_id",
                label="q:play_caller",
            )
            second = review._placebo_portability(
                grouped,
                summary["pearson"],
                signal="q_development_signal",
                group="team_id",
                label="q:play_caller",
            )
        self.assertEqual(first, second)

    def test_scheme_contract_has_all_ten_traits_and_approved_windows(self) -> None:
        self.assertEqual(10, len(review.SCHEME_FEATURES))
        self.assertEqual(
            {
                "personnel_11_rate",
                "personnel_12_rate",
                "personnel_21_rate",
                "motion_rate",
                "play_action_rate",
                "screen_rate",
                "rpo_rate",
            },
            set(review.SCHEME_FEATURES) - set(review.BASE_SCHEME_FEATURES),
        )

    def test_priority_ranking_is_deterministic(self) -> None:
        first, first_simulation = review.build_priority_and_simulation(
            ROOT, self.sources, self.pae, self.q
        )
        second, second_simulation = review.build_priority_and_simulation(
            ROOT, self.sources, self.pae, self.q
        )
        self.assertTrue(first.equals(second))
        self.assertTrue(first_simulation.equals(second_simulation))
        self.assertEqual(list(range(1, first.height + 1)), first["priority_rank"].to_list())

    def test_two_empty_output_directories_are_byte_identical(self) -> None:
        participation, ftn = review.load_scheme_sources()
        with patch.object(review, "PERMUTATIONS", 20), patch.object(review, "BOOTSTRAPS", 20):
            with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
                result_1 = review.run_checkpoint_twelve_review(
                    ROOT, Path(first), scheme_sources=(participation, ftn)
                )
                result_2 = review.run_checkpoint_twelve_review(
                    ROOT, Path(second), scheme_sources=(participation, ftn)
                )
                self.assertEqual(result_1["review_version"], result_2["review_version"])
                left = Path(result_1["output_path"])
                right = Path(result_2["output_path"])
                files = sorted(path.name for path in left.iterdir())
                self.assertEqual(files, sorted(path.name for path in right.iterdir()))
                for name in files:
                    self.assertEqual((left / name).read_bytes(), (right / name).read_bytes())
                corrected = pl.read_csv(left / "corrected_results.csv")
                scheme_rows = corrected.filter(pl.col("audit") == "scheme_portability")
                self.assertTrue(
                    {
                        "mean_adoption_standardized_euclidean",
                        "mean_adoption_manhattan",
                        "mean_adoption_cosine",
                        "mean_adoption_correlation",
                    }.issubset(set(scheme_rows["metric"]))
                )
                specificity_p = scheme_rows.filter(
                    pl.col("metric").str.starts_with("specificity_empirical_p_")
                    & pl.col("value").is_not_null()
                )["value"]
                for value in specificity_p:
                    self.assertGreaterEqual(value + 1e-12, 1 / 21)
                    self.assertAlmostEqual(value * 21, round(value * 21), places=8)
                future_rows = corrected.filter(pl.col("audit") == "scheme_future_association")
                self.assertTrue(
                    {
                        "future_pae",
                        "future_q",
                        "future_pcae",
                        "future_offensive_epa",
                    }.issubset(
                        {
                            next(
                                outcome
                                for outcome in (
                                    "future_pae",
                                    "future_q",
                                    "future_pcae",
                                    "future_offensive_epa",
                                )
                                if metric.startswith(outcome)
                            )
                            for metric in future_rows["metric"]
                        }
                    )
                )


if __name__ == "__main__":
    unittest.main()

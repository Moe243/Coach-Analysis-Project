from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

from research.coach_effect.checkpoint_eleven import _sha256
from research.coach_effect.checkpoint_twelve_final_research import (
    CREDIBLE_FOLDS,
    OUTPUT_NAMES,
    PROMPT10_VERSION,
    PROMPT11_VERSION,
    _fit_predict,
    _future_model_rows,
    _load_prompt10,
    _prompt_roots,
    build_final_snapshot,
    build_qp_overlap,
    run_checkpoint_twelve_final_research,
)

ROOT = Path(__file__).resolve().parents[1]


class FinalResearchMethodTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot, cls.pcae, cls.assignments, _ = build_final_snapshot(ROOT)
        _, _, cls.common = _load_prompt10(ROOT)

    def test_frozen_research_evidence_and_sample_counts(self) -> None:
        _, prompt10, prompt11 = _prompt_roots(ROOT)
        self.assertEqual(prompt10.name, PROMPT10_VERSION)
        self.assertEqual(prompt11.name, PROMPT11_VERSION)
        coverage = pl.read_csv(prompt10 / "play_caller_completeness.csv")
        self.assertEqual(
            coverage.filter(
                (pl.col("season") >= 2020) & (pl.col("ending_status") == "verified")
            ).height,
            180,
        )
        self.assertEqual(cls_common := self.common.height, 269)
        self.assertEqual(cls_common, self.common.select("coach_id", "team_id", "season").n_unique())
        future = _future_model_rows(self.common)
        self.assertEqual(future.height, 165)
        self.assertGreaterEqual(
            self.common.filter(pl.col("season") >= 2020)
            .group_by("coach_id")
            .len()
            .filter(pl.col("len") >= 2)
            .height,
            52,
        )

    def test_final_grains_and_role_intervals_are_preserved(self) -> None:
        key = ["assignment_key", "player_id", "team_id", "season"]
        self.assertEqual(self.snapshot.height, self.snapshot.select(key).n_unique())
        self.assertEqual(self.assignments.height, self.assignments["assignment_key"].n_unique())
        self.assertEqual(
            set(self.snapshot["role"].unique()),
            {"head_coach", "offensive_coordinator", "quarterbacks_coach", "play_caller"},
        )
        self.assertTrue(self.snapshot["start_week"].is_not_null().all())
        self.assertTrue(self.snapshot["end_week"].is_not_null().all())

    def test_pae_q_pcae_and_call_value_contracts_are_unchanged(self) -> None:
        pae_error = (
            (
                self.snapshot["actual_epa_per_dropback"]
                - self.snapshot["expected_epa_per_dropback"]
                - self.snapshot["performance_above_expectation"]
            )
            .abs()
            .max()
        )
        self.assertLess(pae_error, 1e-12)
        pcae_error = (
            (
                self.pcae["average_call_value"]
                - self.pcae["league_average_call_value"]
                - self.pcae["pcae"]
            )
            .abs()
            .max()
        )
        self.assertLess(pcae_error, 2e-10)
        self.assertTrue(self.pcae["shared_or_ambiguous_plays_excluded"].all())
        self.assertFalse(self.pcae["is_shared"].any())
        self.assertTrue((self.pcae["verification_status"] == "verified").all())

    def test_preseason_context_and_q_movement_have_no_target_leakage(self) -> None:
        self.assertFalse(
            self.snapshot.filter(
                (
                    pl.col("feature_source_max_season").is_not_null()
                    & (pl.col("feature_source_max_season") >= pl.col("season"))
                )
                | (
                    pl.col("environment_feature_source_max_season").is_not_null()
                    & (pl.col("environment_feature_source_max_season") >= pl.col("season"))
                )
            ).height
        )
        self.assertTrue(
            self.snapshot.filter(pl.col("q_development_signal").is_not_null())
            .select(
                (
                    pl.col("coach_interval_pae")
                    - pl.col("prior_pae")
                    - pl.col("expected_normal_qb_delta")
                    - pl.col("q_development_signal")
                )
                .abs()
                .max()
            )
            .item()
            < 1e-12
        )

    def test_train_only_preprocessing_does_not_depend_on_scoring_values(self) -> None:
        train = pl.DataFrame({"x": [0.0, 1.0, 2.0], "target_q": [0.0, 1.0, 2.0]})
        score_a = pl.DataFrame({"x": [3.0], "target_q": [0.0]})
        score_b = pl.DataFrame({"x": [3000.0], "target_q": [0.0]})
        _, model_a = _fit_predict(train, score_a, ("x",))
        _, model_b = _fit_predict(train, score_b, ("x",))
        self.assertEqual(model_a.named_steps["impute"].statistics_.tolist(), [1.0])
        self.assertEqual(
            model_a.named_steps["scale"].mean_.tolist(),
            model_b.named_steps["scale"].mean_.tolist(),
        )

    def test_primary_and_secondary_qp_overlap_are_separate(self) -> None:
        overlap = build_qp_overlap(self.common)
        self.assertEqual(
            overlap["analysis_window"].to_list(),
            ["primary_2020_2025", "secondary_2010_2025"],
        )
        self.assertEqual(overlap["rows"].to_list(), [206, 269])


class FinalResearchOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_checkpoint_twelve_final_research(ROOT)
        cls.output = cls.result.output_path

    def read(self, name: str) -> pl.DataFrame:
        return pl.read_csv(self.output / name)

    def test_credible_folds_and_identical_populations(self) -> None:
        folds = self.read("fold_metrics.csv")
        direct = folds.filter(
            pl.col("model").str.starts_with("model_").and_(pl.col("model") != "model_6_role_aware")
        )
        self.assertEqual(sorted(direct["target_season"].unique()), list(CREDIBLE_FOLDS))
        self.assertTrue((direct["training_max_season"] < direct["target_season"]).all())
        for season in CREDIBLE_FOLDS:
            rows = direct.filter(pl.col("target_season") == season)
            self.assertEqual(rows["target_rows"].n_unique(), 1)
            self.assertEqual(rows.height, 6)
        self.assertEqual(
            direct.filter(pl.col("model") == "model_0_no_coach")["target_rows"].to_list(),
            [27, 23, 27, 30, 29],
        )
        self.assertEqual(
            direct.filter(pl.col("model") == "model_0_no_coach")["training_rows"].to_list(),
            [29, 56, 79, 106, 136],
        )

    def test_all_requested_models_and_fold_metrics_exist(self) -> None:
        models = self.read("rolling_model_comparison.csv")
        expected = {
            "model_0_no_coach",
            "model_1_q_only",
            "model_2_pcae_only",
            "model_3_equal_q_p",
            "model_4_learned_q_p",
            "model_5_overlap_decomposition",
            "model_6_role_aware",
            "scheme_challenger",
        }
        self.assertEqual(set(models["model"]), expected)
        direct = models.filter(
            pl.col("model").is_in(sorted(expected - {"model_6_role_aware", "scheme_challenger"}))
        )
        self.assertEqual(direct["n"].unique().to_list(), [136])
        self.assertTrue(direct["same_population_as_models_0_5"].all())

    def test_qp_weights_are_chronological_and_not_approved(self) -> None:
        weights = self.read("weight_stability.csv")
        chronological = weights.filter(pl.col("record_type") == "chronological_fold")
        self.assertEqual(sorted(chronological["target_season"].unique()), list(CREDIBLE_FOLDS))
        self.assertEqual(set(chronological["feature"]), {"history_q", "history_p"})
        self.assertTrue(
            weights.filter(pl.col("record_type") == "cluster_bootstrap")["successful_draws"]
            .eq(500)
            .all()
        )
        self.assertIn("leave_one_season_out", weights["record_type"].unique())
        self.assertIn("leave_one_coach_out", weights["record_type"].unique())
        decision = self.read("architecture_decision.csv").row(0, named=True)
        self.assertFalse(decision["fixed_q_p_weights_approved"])

    def test_role_specific_signal_conclusions_do_not_overclaim_q(self) -> None:
        summary = self.read("role_signal_summary.csv")
        primary_q = summary.filter(
            (pl.col("analysis_window") == "primary_2020_2025") & (pl.col("signal") == "q")
        )
        self.assertEqual(
            set(primary_q["attribution_classification"]),
            {"NOT IDENTIFIABLE", "INSUFFICIENT SIGNAL"},
        )
        self.assertEqual(
            summary.filter(pl.col("signal") == "pcae")["attribution_classification"]
            .unique()
            .to_list(),
            ["DIRECT COACH EFFECT SIGNAL"],
        )
        readiness = dict(
            self.read("role_readiness.csv").select("role_or_signal", "classification").rows()
        )
        self.assertEqual(readiness["head_coach_q"], "NOT IDENTIFIABLE")
        self.assertEqual(readiness["play_caller_q"], "EXPLORATORY ONLY")
        self.assertEqual(readiness["play_caller_pcae"], "RESEARCH-READY")

    def test_pcae_reliability_expanded_sample_and_uncertainty(self) -> None:
        reliability = self.read("pcae_reliability.csv")
        primary = reliability.filter(pl.col("analysis_window") == "primary_2020_2025").row(
            0, named=True
        )
        self.assertEqual(primary["coach_seasons"], 212)
        self.assertEqual(primary["consecutive_pairs"], 112)
        self.assertGreater(primary["two_season_reliability"], primary["one_season_reliability"])
        summary = self.read("role_signal_summary.csv")
        primary_p = summary.filter(
            (pl.col("analysis_window") == "primary_2020_2025") & (pl.col("signal") == "pcae")
        ).row(0, named=True)
        self.assertEqual(primary_p["repeatability_successful_draws"], 500)
        self.assertLess(
            primary_p["repeatability_bootstrap_low"], primary_p["repeatability_pearson"]
        )
        self.assertGreater(
            primary_p["repeatability_bootstrap_high"], primary_p["repeatability_pearson"]
        )

    def test_shrinkage_is_role_specific_and_behaves_by_sample_size(self) -> None:
        shrinkage = self.read("shrinkage_comparison.csv")
        estimates = shrinkage.filter(pl.col("record_type").is_null())
        self.assertEqual(estimates.select("signal", "role").n_unique(), 5)
        self.assertEqual(set(estimates["method"]), {"method_of_moments", "reml"})
        oos = shrinkage.filter(pl.col("record_type") == "rolling_oos_validation")
        self.assertEqual(
            set(oos["method"]), {"raw_history", "mom_empirical_bayes", "reml_empirical_bayes"}
        )
        eligible = self.read("eligibility_research.csv")
        for _, group in eligible.filter(pl.col("seasons").is_in([1, 4])).group_by("signal", "role"):
            one = group.filter(pl.col("seasons") == 1)
            four = group.filter(pl.col("seasons") == 4)
            if one.height and four.height:
                self.assertLess(one["shrinkage_weight"].mean(), four["shrinkage_weight"].mean())

    def test_environment_missingness_placebo_and_scheme_are_sensitivities(self) -> None:
        environment = self.read("environment_sensitivity.csv")
        self.assertFalse(environment["context_is_score_points"].any())
        self.assertTrue(
            environment.filter(pl.col("role") != "head_coach_orientation")["context_fit_scope"]
            .str.contains("prior_seasons_only", literal=True)
            .all()
        )
        missingness = self.read("missingness_sensitivity.csv")
        self.assertIn("clipped_verification_propensity_diagnostic", missingness["method"].unique())
        placebos = self.read("placebo_results.csv")
        self.assertTrue((placebos["permutations"] == 1000).all())
        scheme = (
            self.read("rolling_model_comparison.csv")
            .filter(pl.col("model") == "scheme_challenger")
            .row(0, named=True)
        )
        baseline = (
            self.read("rolling_model_comparison.csv")
            .filter(pl.col("model") == "model_0_no_coach")
            .row(0, named=True)
        )
        self.assertGreater(scheme["rmse"], baseline["rmse"])

    def test_final_decisions_close_research_without_production_score(self) -> None:
        architecture = self.read("architecture_decision.csv").row(0, named=True)
        self.assertEqual(architecture["architecture_code"], "E")
        self.assertFalse(architecture["practically_meaningful"])
        self.assertFalse(architecture["zero_to_one_hundred_ready"])
        self.assertEqual(architecture["mathematical_formula"], "not_applicable")
        production = self.read("production_gate.csv")
        self.assertTrue((production["production_coach_effect"] == "NO-GO").all())
        self.assertEqual(
            set(production.filter(pl.col("result") == "FAIL")["gate"]),
            {
                "recent_attributable_play_coverage",
                "recent_full_cell_coverage",
                "role_specific_verification_complete",
                "stable_oos_architecture",
            },
        )
        closeout = self.read("checkpoint_closeout.csv").row(0, named=True)
        self.assertEqual(closeout["checkpoint_12_research_status"], "COMPLETE")
        self.assertEqual(closeout["phase_ii_checkpoint_13_readiness"], "READY")
        self.assertFalse(closeout["production_modified"])
        self.assertFalse(closeout["phase_two_implemented"])
        self.assertFalse(closeout["ask_anything_implemented"])

    def test_manifest_hashes_output_affecting_inputs(self) -> None:
        manifest = json.loads((self.output / "MANIFEST.json").read_text())
        sources = manifest["identity"]["source_hashes"]
        self.assertIn(
            "research/coach_effect/outputs/checkpoint_12_data_expansion/"
            "c12-data-250e540b7de79385/team_season_scheme_fingerprints.csv",
            sources,
        )
        for path in sorted((ROOT / "data/manual").glob("*.csv")):
            self.assertIn(str(path.relative_to(ROOT)), sources)
        self.assertEqual(set(manifest["output_checksums"]), set(OUTPUT_NAMES))
        self.assertFalse(manifest["production_coach_effect"])
        self.assertFalse(manifest["phase_ii_started"])

    def test_two_independent_clean_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = run_checkpoint_twelve_final_research(ROOT, Path(first))
            right = run_checkpoint_twelve_final_research(ROOT, Path(second))
            self.assertEqual(left.data_version, right.data_version)
            names = ["MANIFEST.json", *OUTPUT_NAMES]
            self.assertEqual(
                {name: _sha256(left.output_path / name) for name in names},
                {name: _sha256(right.output_path / name) for name in names},
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import polars as pl

from research.coach_effect.checkpoint_eleven import _sha256
from research.coach_effect.checkpoint_twelve_coverage_gate_review import (
    BOOTSTRAPS,
    OUTPUT_NAMES,
    RESEARCH_GATE_POLICY,
    _consecutive_pairs,
    _future_rows,
    build_gate_comparison,
    build_leave_era_out,
    build_play_weighted_coverage,
    build_temporal_sensitivity,
    build_verified_interval_coverage,
    cluster_bootstrap,
    run_checkpoint_twelve_coverage_gate_review,
)
from research.coach_effect.checkpoint_twelve_final_play_caller_evidence import (
    build_assignments,
    load_and_validate_prompt10_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
PROMPT10 = (
    ROOT
    / "research/coach_effect/outputs/checkpoint_12_final_play_caller_evidence"
    / "c12-pc-final-cac923f086757e5b"
)


class PromptElevenMethodTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coverage = pl.read_csv(PROMPT10 / "play_caller_completeness.csv")
        cls.pcae = pl.read_csv(PROMPT10 / "historical_pcae.csv")
        cls.common = pl.read_csv(PROMPT10 / "common_qp_availability.csv")
        cells, intervals, _ = load_and_validate_prompt10_evidence(ROOT)
        cls.assignments = pl.DataFrame(
            build_assignments(ROOT, cells, intervals), infer_schema_length=None
        ).with_columns(
            pl.col("season", "start_week", "end_week").cast(pl.Int64),
            (pl.col("is_shared") == "true").alias("shared"),
        )

    def test_full_cell_and_verified_interval_coverage_are_distinct(self) -> None:
        result = build_verified_interval_coverage(self.coverage, self.pcae, self.assignments)
        self.assertEqual(self.coverage.filter(pl.col("ending_status") == "verified").height, 205)
        partial = result.filter(pl.col("ending_status") == "partial").row(0, named=True)
        self.assertEqual(partial["cells_with_usable_intervals"], 36)
        all_usable = result.filter(pl.col("ending_status") == "ALL_USABLE").row(0, named=True)
        self.assertEqual(all_usable["individually_attributable_intervals"], 287)
        with_shared = result.filter(
            pl.col("ending_status") == "ALL_SOURCE_BACKED_INCLUDING_SHARED"
        ).row(0, named=True)
        self.assertEqual(with_shared["individually_attributable_intervals"], 291)

    def test_no_provisional_unresolved_or_shared_attribution(self) -> None:
        self.assertFalse(
            self.pcae.filter(
                (pl.col("verification_status") != "verified") | pl.col("is_shared")
            ).height
        )
        status = self.pcae.join(
            self.coverage.select("season", "team_id", "ending_status"),
            on=["season", "team_id"],
            validate="m:1",
        )
        self.assertFalse(
            status.filter(pl.col("ending_status").is_in(["provisional", "unresolved"])).height
        )

    def test_play_weighted_coverage_calculation(self) -> None:
        eligible = pl.DataFrame(
            {
                "season": [2020, 2020, 2021],
                "team_id": ["A", "B", "A"],
                "eligible_plays": [100, 50, 80],
            }
        )
        pcae = pl.DataFrame(
            {
                "season": [2020, 2020, 2021],
                "team_id": ["A", "B", "A"],
                "attributed_play_count": [80, 20, 40],
            }
        )
        season, era = build_play_weighted_coverage(eligible, pcae)
        self.assertAlmostEqual(
            season.filter(pl.col("season") == 2020)["verified_attributable_play_rate"].item(),
            100 / 150,
        )
        self.assertAlmostEqual(
            era.filter(pl.col("era") == "2020-2025")["verified_attributable_play_rate"].item(),
            140 / 230,
        )

    def test_temporal_windows_and_leave_era_out_are_deterministic(self) -> None:
        first = build_temporal_sensitivity(self.common)
        second = build_temporal_sensitivity(self.common.reverse())
        self.assertTrue(first.equals(second))
        self.assertEqual(
            first["analysis"].to_list(), ["2010-2025", "2016-2025", "2020-2025", "2021-2025"]
        )
        leave = build_leave_era_out(self.common)
        self.assertEqual(
            leave["analysis"].to_list(),
            ["leave_2010_2014_out", "leave_2015_2019_out", "leave_2010_2019_out"],
        )

    def test_consecutive_pair_logic_never_crosses_a_missing_season(self) -> None:
        fixture = pl.DataFrame(
            {
                "coach_id": ["c", "c", "c"],
                "coach_canonical_name": ["C", "C", "C"],
                "team_id": ["A", "A", "A"],
                "season": [2018, 2020, 2021],
                "q_development_signal": [0.1, 0.2, 0.3],
                "q_exposure": [100.0, 100.0, 100.0],
                "quarterbacks": [1, 1, 1],
                "player_ids": ["q1", "q1", "q2"],
                "pcae": [0.01, 0.02, 0.03],
                "p_exposure": [100, 100, 100],
            }
        )
        pairs = _consecutive_pairs(fixture)
        self.assertEqual(pairs.height, 1)
        self.assertEqual(pairs["season"].item(), 2021)

    def test_clustered_resampling_is_deterministic(self) -> None:
        pairs = _consecutive_pairs(self.common.filter(pl.col("season") >= 2020))
        left = cluster_bootstrap(
            pairs,
            "prior_p",
            "current_p",
            dimension="coach",
            label="fixture",
            paired=True,
            bootstraps=40,
        )
        right = cluster_bootstrap(
            pairs.reverse(),
            "prior_p",
            "current_p",
            dimension="coach",
            label="fixture",
            paired=True,
            bootstraps=40,
        )
        self.assertEqual(left, right)
        self.assertEqual(left["successful_draws"], 40)

    def test_gate_policy_is_not_retrospectively_fit_to_signal_signs(self) -> None:
        self.assertNotIn("correlation", "|".join(RESEARCH_GATE_POLICY))
        self.assertNotIn("effect", "|".join(RESEARCH_GATE_POLICY))


class PromptElevenOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_checkpoint_twelve_coverage_gate_review(ROOT)
        cls.output = cls.result.output_path
        cls.common = pl.read_csv(PROMPT10 / "common_qp_availability.csv")
        cls.coverage = pl.read_csv(PROMPT10 / "play_caller_completeness.csv")

    def read(self, name: str) -> pl.DataFrame:
        return pl.read_csv(self.output / name)

    def test_era_coverage_and_partial_inclusion(self) -> None:
        era = self.read("era_coverage.csv")
        self.assertEqual(era["era"].to_list(), ["2010-2014", "2015-2019", "2020-2022", "2023-2025"])
        self.assertEqual(era["fully_verified_cells"].to_list(), [13, 12, 84, 96])
        self.assertGreater(era["cells_with_usable_intervals"].sum(), 205)

    def test_fold_history_and_2020_credibility(self) -> None:
        folds = self.read("fold_quality_analysis.csv")
        self.assertEqual(folds.height, 6)
        self.assertEqual(folds["target_season"].to_list(), list(range(2020, 2026)))
        first = folds.head(1).row(0, named=True)
        self.assertEqual(first["target_rows"], 18)
        self.assertEqual(first["prior_training_rows"], 11)
        self.assertFalse(first["credible_target_fold"])
        self.assertEqual(folds.filter(pl.col("credible_target_fold")).height, 5)

    def test_missingness_ipw_and_stress_outputs_are_explicit(self) -> None:
        missingness = self.read("missingness_diagnostics.csv")
        self.assertIn("era", missingness["dimension"].to_list())
        selection = self.read("selection_bias_diagnostics.csv")
        self.assertEqual(set(selection["feature_class"]), {"non_outcome", "outcome_diagnostic"})
        ipw = self.read("inverse_probability_sensitivity.csv")
        self.assertTrue(ipw["feature_contract"].str.contains("no outcomes", literal=True).all())
        stress = self.read("missing_data_stress_test.csv")
        self.assertTrue(
            stress["interpretation"].str.contains("no caller identity", literal=True).all()
        )

    def test_gate_results_and_methodology_decision(self) -> None:
        gates = self.read("candidate_gate_comparison.csv")
        overall = dict(
            gates.filter(pl.col("criterion") == "OVERALL").select("gate_system", "result").rows()
        )
        self.assertEqual(overall["A_original"], "FAIL")
        self.assertEqual(overall["B_effective_sample"], "PASS")
        self.assertEqual(overall["C_model_specific"], "PASS")
        self.assertEqual(overall["production_separate"], "FAIL")
        decision = self.read("final_methodology_decision.csv").row(0, named=True)
        self.assertEqual(decision["decision"], "REPLACE 50% GATE")
        self.assertEqual(decision["final_equation_research_rerun"], "GO")
        self.assertFalse(decision["verification_semantics_changed"])
        self.assertFalse(decision["final_equation_fitted"])

    def test_gate_results_do_not_fit_thresholds_to_observed_signs(self) -> None:
        temporal = self.read("temporal_window_sensitivity.csv")
        altered = temporal.with_columns(
            [
                (-pl.col(column)).alias(column)
                for column in temporal.columns
                if column.endswith("_pearson")
            ]
        )
        play = self.read("play_weighted_coverage.csv").filter(pl.col("season") >= 2020)
        play_era = pl.DataFrame(
            {
                "era": ["2020-2025"],
                "verified_attributable_play_rate": [
                    play["verified_attributable_plays"].sum() / play["eligible_plays"].sum()
                ],
            }
        )
        folds = self.read("fold_quality_analysis.csv")
        cluster = self.read("cluster_aware_precision.csv")
        future = _future_rows(self.common)
        baseline = build_gate_comparison(
            self.coverage,
            play_era,
            temporal,
            folds,
            cluster,
            future,
        )
        changed = build_gate_comparison(
            self.coverage,
            play_era,
            altered,
            folds,
            cluster,
            future,
        )
        self.assertTrue(
            baseline.select("gate_system", "criterion", "result").equals(
                changed.select("gate_system", "criterion", "result")
            )
        )

    def test_cluster_outputs_have_all_dimensions_and_draws(self) -> None:
        bootstrap = self.read("cluster_aware_precision.csv").filter(
            pl.col("record_type") == "cluster_bootstrap"
        )
        self.assertEqual(
            set(bootstrap["cluster_dimension"]), {"coach", "team", "season", "quarterback"}
        )
        self.assertTrue((bootstrap["requested_draws"] == BOOTSTRAPS).all())
        self.assertTrue((bootstrap["successful_draws"] >= 475).all())

    def test_manifest_and_clean_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
            left = run_checkpoint_twelve_coverage_gate_review(ROOT, Path(left_dir))
            right = run_checkpoint_twelve_coverage_gate_review(ROOT, Path(right_dir))
            self.assertEqual(left.data_version, right.data_version)
            for name in ("MANIFEST.json", *OUTPUT_NAMES):
                self.assertEqual(
                    _sha256(left.output_path / name), _sha256(right.output_path / name)
                )

    def test_output_contract_contains_no_equation_or_ranking(self) -> None:
        manifest = (self.output / "MANIFEST.json").read_text(encoding="utf-8")
        self.assertIn('"final_equation_fitted": false', manifest)
        self.assertIn('"production_ranking": false', manifest)
        self.assertIn('"verification_semantics_changed": false', manifest)


if __name__ == "__main__":
    unittest.main()

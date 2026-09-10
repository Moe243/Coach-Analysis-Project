from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl

from nfl_coaching_impact.player_scheme_fit import (
    FoldPreprocessor,
    _content_identity,
    _interaction_effects,
    _outcome_table,
    build_fold_assignments,
    build_preseason_team_assignments,
    cluster_bootstrap_model_delta,
    construct_interactions,
    deterministic_interaction_placebo,
    fit_feature_registry,
    run_checkpoint_fifteen,
    select_alpha,
    target_team_contract,
    team_change_validation,
    validate_cohort_leakage,
    validate_requested_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _players() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["qb-draft", "qb-dated", "not-qb"],
            "position": ["QB", "QB", "WR"],
            "position_group": ["QB", "QB", "WR"],
            "draft_year": [2011, None, 2011],
            "draft_team": ["BUF", None, "HOU"],
        },
        schema_overrides={"draft_year": pl.Int64},
    )


def _dated(rows: list[tuple[str, str, str | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "player_id": [row[0] for row in rows],
            "position": ["QB"] * len(rows),
            "team": [row[1] for row in rows],
            "source_available_date": [row[2] for row in rows],
        }
    )


def _transactions(rows: list[tuple[str, int, str | None, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "player_id": [row[0] for row in rows],
            "target_season": [row[1] for row in rows],
            "team": [row[2] for row in rows],
            "event_type": [row[3] for row in rows],
            "evidence_date": [row[4] for row in rows],
            "source": ["https://example.test/transaction"] * len(rows),
            "source_version_hash": ["a" * 64] * len(rows),
            "verification_status": ["VERIFIED"] * len(rows),
        },
        schema_overrides={"target_season": pl.Int64},
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreseasonTeamContractTest(unittest.TestCase):
    def test_only_pre_cutoff_dated_or_immutable_evidence_can_assign_team(self) -> None:
        assignments = build_preseason_team_assignments(
            _players(),
            _dated(
                [
                    ("qb-dated", "HOU", "2025-08-30"),
                    ("qb-dated", "JAX", "2025-09-01"),
                    ("qb-unsupported", "CHI", None),
                ]
            ),
        )
        drafted = assignments.filter(pl.col("player_id") == "qb-draft").row(0, named=True)
        dated = assignments.filter(pl.col("player_id") == "qb-dated").row(0, named=True)
        self.assertEqual(drafted["target_team_id"], "team_buf")
        self.assertEqual(drafted["target_team_basis"], "immutable_draft_team")
        self.assertEqual(drafted["target_team_source_available_date"], "2011-08-31")
        self.assertEqual(drafted["evidence_date_precision"], "PRE_CUTOFF_EVENT_UPPER_BOUND")
        self.assertEqual(len(drafted["source_version_hash"]), 64)
        self.assertEqual(
            drafted["target_team_source_availability_evidence"],
            "IMMUTABLE_DRAFT_FACT_KNOWN_BY_CUTOFF",
        )
        self.assertEqual(dated["target_team_id"], "team_hou")
        self.assertEqual(dated["target_team_source_available_date"], "2025-08-30")
        self.assertEqual(
            assignments.filter(pl.col("player_id") == "qb-unsupported").height,
            0,
        )

    def test_latest_preseason_snapshot_supersedes_earlier_evidence(self) -> None:
        assignments = build_preseason_team_assignments(
            _players(),
            _dated(
                [
                    ("qb-dated", "BUF", "2025-08-10"),
                    ("qb-dated", "HOU", "2025-08-31"),
                ]
            ),
        )
        row = assignments.filter(pl.col("player_id") == "qb-dated").row(0, named=True)
        self.assertEqual(row["target_team_id"], "team_hou")
        self.assertEqual(row["candidate_team_count"], 1)

    def test_same_snapshot_conflict_is_explicitly_ambiguous(self) -> None:
        assignments = build_preseason_team_assignments(
            _players(),
            _dated(
                [
                    ("qb-dated", "BUF", "2025-08-31"),
                    ("qb-dated", "HOU", "2025-08-31"),
                ]
            ),
        )
        row = assignments.filter(pl.col("player_id") == "qb-dated").row(0, named=True)
        self.assertEqual(row["target_team_status"], "AMBIGUOUS_PRESEASON_TEAM")
        self.assertIsNone(row["target_team_id"])

    def test_verified_transaction_supersedes_draft_or_snapshot_without_hindsight(self) -> None:
        assignments = build_preseason_team_assignments(
            _players(),
            _dated([("qb-draft", "BUF", "2011-08-01")]),
            _transactions(
                [
                    ("qb-draft", 2011, "HOU", "TRADE", "2011-08-20"),
                    ("qb-draft", 2011, "JAX", "TRADE", "2011-09-01"),
                ]
            ),
        )
        row = assignments.filter(pl.col("player_id") == "qb-draft").row(0, named=True)
        self.assertEqual(row["target_team_id"], "team_hou")
        self.assertEqual(row["target_team_basis"], "dated_official_transaction")
        self.assertEqual(row["evidence_date"], "2011-08-20")
        self.assertNotIn("2011-09-01", row["evidence_date"])

    def test_release_and_same_day_conflicts_are_not_silently_resolved(self) -> None:
        released = build_preseason_team_assignments(
            _players(),
            pl.DataFrame(),
            _transactions([("qb-draft", 2011, None, "RELEASE", "2011-08-20")]),
        ).row(0, named=True)
        self.assertEqual(released["target_team_status"], "PRESEASON_NO_TEAM_KNOWN")
        self.assertIsNone(released["target_team_id"])
        conflict = build_preseason_team_assignments(
            _players(),
            pl.DataFrame(),
            _transactions(
                [
                    ("qb-draft", 2011, "HOU", "TRADE", "2011-08-20"),
                    ("qb-draft", 2011, "JAX", "SIGNING", "2011-08-20"),
                ]
            ),
        ).row(0, named=True)
        self.assertEqual(conflict["target_team_status"], "AMBIGUOUS_PRESEASON_TEAM")
        self.assertIsNone(conflict["target_team_id"])

    def test_assignment_precedence_is_deterministic_under_input_reordering(self) -> None:
        transactions = _transactions(
            [
                ("qb-draft", 2011, "HOU", "TRADE", "2011-08-10"),
                ("qb-draft", 2011, "JAX", "TRADE", "2011-08-20"),
            ]
        )
        first = build_preseason_team_assignments(_players(), pl.DataFrame(), transactions)
        second = build_preseason_team_assignments(
            _players().reverse(), pl.DataFrame(), transactions.reverse()
        )
        self.assertEqual(first.to_dicts(), second.to_dicts())
        self.assertEqual(first.row(0, named=True)["target_team_id"], "team_jax")

    def test_transaction_lineage_must_be_verified_https_and_source_hashed(self) -> None:
        invalid = _transactions([("qb-draft", 2011, "HOU", "TRADE", "2011-08-20")]).with_columns(
            pl.lit("not-a-hash").alias("source_version_hash")
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_preseason_team_assignments(_players(), pl.DataFrame(), invalid)

    def test_contract_does_not_accept_pbp_or_final_roster_facts(self) -> None:
        baseline = build_preseason_team_assignments(_players(), pl.DataFrame())
        mutated_target_outcomes = pl.DataFrame(
            {"player_id": ["qb-dated"], "team": ["HOU"], "target_season": [2025]}
        )
        self.assertEqual(
            baseline.to_dicts(),
            build_preseason_team_assignments(_players(), pl.DataFrame()).to_dicts(),
        )
        self.assertNotIn("target_outcome", target_team_contract()["evidence_family"].to_list())
        self.assertEqual(mutated_target_outcomes.height, 1)


class FeatureAndLeakageContractTest(unittest.TestCase):
    def test_unregistered_and_upstream_forbidden_features_are_rejected(self) -> None:
        registry = fit_feature_registry()
        with self.assertRaisesRegex(ValueError, "unregistered"):
            validate_requested_features(registry, ("target_season_wins",))
        upstream = pl.DataFrame(
            {
                "name": ["recent_scramble_rate"],
                "status": ["DESCRIPTIVE"],
                "predictive_permission": ["NO"],
            }
        )
        with self.assertRaisesRegex(ValueError, "forbids predictive use"):
            fit_feature_registry(player_registry=upstream)

    def test_interactions_are_predeclared_exact_products_and_preserve_nulls(self) -> None:
        frame = pl.DataFrame(
            {
                "recent_scramble_rate": [0.1, None],
                "scheme_scramble_rate": [2.0, 2.0],
                "recent_shotgun_rate": [0.8, 0.7],
                "scheme_shotgun_rate": [0.5, None],
                "recent_target_depth_short_rate": [0.4, 0.4],
                "scheme_target_depth_short_rate": [0.5, 0.5],
                "recent_target_depth_intermediate_rate": [0.3, 0.3],
                "scheme_target_depth_intermediate_rate": [0.3, 0.3],
                "recent_target_depth_deep_rate": [0.3, 0.3],
                "scheme_target_depth_deep_rate": [0.2, 0.2],
                "recent_average_air_yards": [8.0, 7.0],
                "scheme_average_air_yards": [1.5, 1.0],
                "scheme_pass_rate": [0.6, 0.5],
                "scheme_neutral_pass_rate": [0.55, 0.45],
            }
        )
        result = construct_interactions(frame)
        self.assertAlmostEqual(result["scramble_alignment"][0], 0.2)
        self.assertIsNone(result["scramble_alignment"][1])
        self.assertAlmostEqual(result["shotgun_alignment"][0], 0.4)
        self.assertIsNone(result["shotgun_alignment"][1])

    def test_fold_preprocessing_is_train_only_and_missing_is_not_zero_filled(self) -> None:
        training = pl.DataFrame(
            {
                "target_season": [2011] * 11,
                "feature": [1.0, 2.0, 3.0, 4.0, 5.0, None, 7.0, 8.0, 9.0, 10.0, 11.0],
            }
        )
        processor = FoldPreprocessor.fit(training, ("feature",), target_season=2012)
        self.assertEqual(processor.fitted_end_season, 2011)
        transformed, names = processor.transform(
            pl.DataFrame({"target_season": [2012, 2012], "feature": [1000.0, None]})
        )
        self.assertEqual(names, ("feature", "feature__missing"))
        self.assertEqual(transformed[1, 1], 1.0)
        self.assertEqual(transformed[0, 1], 0.0)
        self.assertAlmostEqual(transformed[1, 0], 0.0)
        with self.assertRaisesRegex(ValueError, "target or future"):
            FoldPreprocessor.fit(
                training.vstack(pl.DataFrame({"target_season": [2012], "feature": [1000.0]})),
                ("feature",),
                target_season=2012,
            )

    def test_hyperparameter_selection_never_reaches_outer_fold(self) -> None:
        rows = []
        for season in range(2011, 2017):
            for index in range(10):
                rows.append(
                    {
                        "target_season": season,
                        "feature": float(index + season),
                        "outcome": float(index) / 10,
                    }
                )
        training = pl.DataFrame(rows)
        alpha, status, folds, latest = select_alpha(
            training,
            ("feature",),
            "outcome",
            outer_target_season=2017,
        )
        self.assertIn(alpha, (0.1, 1.0, 10.0, 100.0))
        self.assertEqual(status, "TRAIN_ONLY_ROLLING_MAE")
        self.assertGreater(folds, 0)
        self.assertLess(latest, 2017)

    def test_leakage_audit_rejects_target_season_sources(self) -> None:
        cohort = pl.DataFrame(
            {
                "player_id": ["qb"],
                "target_season": [2020],
                "player_feature_max_source_season": [2020],
                "scheme_feature_max_source_season": [2019],
                "target_team_source_available_date": ["2020-08-31"],
                "target_team_status": ["PRESEASON_TARGET_TEAM_KNOWN"],
                "target_team_basis": ["dated_preseason_depth_chart"],
                "target_team_source_availability_evidence": ["DATED_SNAPSHOT_ON_OR_BEFORE_CUTOFF"],
                "evidence_type": ["DATED_PRESEASON_DEPTH_CHART"],
                "evidence_date": ["2020-08-31"],
                "source": ["https://example.test/depth"],
                "source_version_hash": ["a" * 64],
                "as_of_date": ["2020-08-31"],
                "verification_status": ["VERIFIED_DATED_SNAPSHOT"],
                "modeling_exclusion_reason": [None],
            }
        )
        with self.assertRaisesRegex(ValueError, "leakage audit"):
            validate_cohort_leakage(cohort)


class OutcomeAndEvaluationContractTest(unittest.TestCase):
    def test_multi_team_outcome_and_pae_join_use_complete_team_key(self) -> None:
        performance = pl.DataFrame(
            {
                "scope": ["analysis", "analysis"],
                "season": [2020, 2020],
                "player_id": ["qb", "qb"],
                "team_id": ["team_buf", "team_jax"],
                "dropbacks": [100, 50],
                "epa_per_dropback": [0.2, -0.1],
            }
        )
        pae = pl.DataFrame(
            {
                "season": [2020, 2020],
                "player_id": ["qb", "qb"],
                "team_id": ["team_buf", "team_jax"],
                "performance_above_expectation": [0.1, -0.3],
                "expected_epa_per_dropback": [0.1, 0.2],
                "prediction_std_error": [0.05, 0.06],
                "is_out_of_sample": [True, True],
            }
        )
        result = _outcome_table(performance, pae)
        self.assertEqual(result.height, 2)
        self.assertEqual(
            result.filter(pl.col("target_team_id") == "team_jax")["outcome_pae"][0],
            -0.3,
        )
        with self.assertRaisesRegex(ValueError, "PAE arithmetic"):
            _outcome_table(
                performance,
                pae.with_columns(
                    pl.when(pl.col("team_id") == "team_jax")
                    .then(-0.2)
                    .otherwise(pl.col("performance_above_expectation"))
                    .alias("performance_above_expectation")
                ),
            )

    def test_fold_construction_is_deterministic(self) -> None:
        rows = []
        for season in range(2011, 2018):
            for index in range(10):
                rows.append(
                    {
                        "player_id": f"qb-{season}-{index}",
                        "target_season": season,
                        "eligible_m1": True,
                    }
                )
        cohort = pl.DataFrame(rows)
        first = build_fold_assignments(cohort)
        second = build_fold_assignments(cohort.reverse())
        self.assertEqual(first.to_dicts(), second.to_dicts())
        self.assertTrue(
            first.filter(pl.col("role") == "TRAIN")
            .select((pl.col("target_season") < pl.col("fold_season")).all())
            .item()
        )

    def test_team_change_subset_is_explicit(self) -> None:
        predictions = pl.DataFrame(
            {
                "player_id": ["a", "b", "c"],
                "actual": [0.1, -0.1, 0.2],
                "predicted": [0.0, 0.0, 0.1],
                "outcome": ["next_season_epa_per_dropback"] * 3,
                "model": ["M1"] * 3,
                "changed_team": [True, True, False],
            }
        )
        result = team_change_validation(predictions)
        self.assertEqual(result.height, 1)
        self.assertEqual(result["n"][0], 2)

    def test_interaction_effect_is_m2_minus_m1_not_an_algebraic_zero(self) -> None:
        predictions = pl.DataFrame(
            {
                "player_id": ["qb", "qb"],
                "target_team_id": ["team_buf", "team_buf"],
                "target_season": [2020, 2020],
                "outcome": ["next_season_epa_per_dropback"] * 2,
                "model": ["M1", "M2"],
                "actual": [0.1, 0.1],
                "predicted": [0.05, 0.08],
                "residual": [0.05, 0.02],
            }
        )
        result = _interaction_effects(predictions)
        self.assertAlmostEqual(result["m2_minus_m1_prediction_delta"][0], 0.03)


class UncertaintyAndDeterminismTest(unittest.TestCase):
    def test_cluster_bootstrap_and_permutation_are_deterministic(self) -> None:
        paired = pl.DataFrame(
            {
                "player_id": ["a", "a", "b", "b"],
                "actual": [0.1, 0.2, -0.1, 0.0],
                "predicted_m1": [0.0, 0.0, 0.0, 0.0],
                "predicted_m2": [0.1, 0.1, -0.05, 0.05],
            }
        )
        self.assertEqual(
            cluster_bootstrap_model_delta(paired, draws=20, seed=7).to_dicts(),
            cluster_bootstrap_model_delta(paired, draws=20, seed=7).to_dicts(),
        )
        values = np.asarray([0.1, 0.2, 0.3, 0.4])
        outcome = np.asarray([0.2, 0.1, 0.4, 0.3])
        self.assertEqual(
            deterministic_interaction_placebo(values, outcome, draws=20, seed=7),
            deterministic_interaction_placebo(values, outcome, draws=20, seed=7),
        )

    def test_output_affecting_parameter_changes_identity(self) -> None:
        original, _ = _content_identity({"input": "hash"}, "code")
        with patch(
            "nfl_coaching_impact.player_scheme_fit.MIN_INTERACTION_TRAIN_VALUES",
            21,
        ):
            changed, _ = _content_identity({"input": "hash"}, "code")
        self.assertNotEqual(original, changed)

    def test_two_independent_clean_builds_are_byte_identical(self) -> None:
        with (
            tempfile.TemporaryDirectory() as first_dir,
            tempfile.TemporaryDirectory() as second_dir,
        ):
            first = run_checkpoint_fifteen(PROJECT_ROOT, Path(first_dir))
            second = run_checkpoint_fifteen(PROJECT_ROOT, Path(second_dir))
            self.assertEqual(first.data_version, second.data_version)
            first_files = sorted(path.name for path in first.output_path.iterdir())
            second_files = sorted(path.name for path in second.output_path.iterdir())
            self.assertEqual(first_files, second_files)
            for name in first_files:
                self.assertEqual(_hash(first.output_path / name), _hash(second.output_path / name))
            decision = pl.read_csv(first.output_path / "fit_approval_decision.csv").row(
                0, named=True
            )
            self.assertEqual(decision["decision"], "NOT ESTIMABLE / DATA-LIMITED")
            self.assertEqual(decision["checkpoint_16_readiness"], "NOT READY")
            self.assertFalse(decision["checkpoint_16_may_consume_interactions"])
            self.assertEqual(decision["checkpoint_16_allowed_baseline"], "NONE")
            self.assertIn("player-team assignment", decision["checkpoint_16_blocker"])
            coverage = pl.read_csv(first.output_path / "target_team_coverage_by_season.csv")
            self.assertEqual(int(coverage["entering_state_rows"].sum()), 8032)
            self.assertEqual(int(coverage["known_target_team_rows"].sum()), 265)
            self.assertEqual(int(coverage["eligible_evaluation_rows"].sum()), 130)
            sources = pl.read_csv(first.output_path / "target_team_source_audit.csv")
            pfr_trades = sources.filter(pl.col("source_family") == "nflverse_trades_via_pfr").row(
                0, named=True
            )
            self.assertEqual(pfr_trades["acceptance_status"], "REJECTED")
            self.assertEqual(pfr_trades["coverage_added_to_state_rows"], 0)
            assignment_contract = pl.read_parquet(
                first.output_path / "preseason_target_team_assignments.parquet"
            )
            self.assertTrue(
                {
                    "evidence_type",
                    "evidence_date",
                    "source",
                    "source_version_hash",
                    "as_of_date",
                    "verification_status",
                }
                <= set(assignment_contract.columns)
            )
            cohort = pl.read_parquet(first.output_path / "modeling_cohort.parquet")
            large_changes = cohort.filter(pl.col("eligible_m1") & pl.col("large_scheme_change"))
            self.assertEqual(large_changes.height, 16)
            self.assertTrue(large_changes.select(pl.col("changed_team").all()).item())
            self.assertTrue(
                large_changes.select(
                    pl.col("scheme_change_rms_standardized_difference").is_not_null().all()
                ).item()
            )
            self.assertTrue(
                cohort.filter(pl.col("scheme_feature_max_source_season").is_not_null())
                .select(
                    (
                        pl.col("scheme_feature_max_source_season") == pl.col("target_season") - 1
                    ).all()
                )
                .item()
            )
            state_version = (
                (PROJECT_ROOT / "data/processed/qb_player_state/LATEST")
                .read_text(encoding="utf-8")
                .strip()
            )
            states = pl.read_parquet(
                PROJECT_ROOT
                / "data/processed/qb_player_state"
                / state_version
                / "player_states.parquet"
            ).select(
                "player_id",
                "target_season",
                pl.col("preseason_ability_estimate_epa_per_db").alias("source_ability"),
            )
            reconciled = cohort.join(
                states,
                on=["player_id", "target_season"],
                how="left",
                validate="1:1",
            )
            self.assertTrue(
                reconciled.select(
                    pl.col("preseason_ability_estimate_epa_per_db")
                    .eq_missing(pl.col("source_ability"))
                    .all()
                ).item()
            )


if __name__ == "__main__":
    unittest.main()

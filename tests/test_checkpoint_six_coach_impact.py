from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

from nfl_coaching_impact.coach_impact import (
    CoachImpactConfig,
    _bootstrap_intervals,
    _fit_role,
    _identification_diagnostic,
    _model_specification,
    _partial_pool,
    build_coach_exposures,
    build_coach_impact_tables,
    run_coach_impact_pipeline,
)
from nfl_coaching_impact.errors import PipelineError

CONTROL_VALUES = {
    "age": 28.0,
    "nfl_experience": 5,
    "is_rookie": False,
    "prior_qb_seasons": 4,
    "no_prior_qb_performance": False,
    "prior_dropbacks": 500,
    "prior_epa_per_dropback": 0.05,
    "career_dropbacks": 1500,
    "career_epa_per_dropback": 0.04,
    "changed_team": False,
    "prior_injury_report_weeks": 2,
    "prior_injury_out_weeks": 0,
}


def _pae_rows() -> pl.DataFrame:
    rows = []
    for season, player_id, team, actual, expected in (
        (2020, "qb-a", "team_hou", 0.20, 0.10),
        (2020, "qb-b", "team_hou", 0.00, 0.05),
        (2021, "qb-a", "team_hou", 0.18, 0.08),
        (2021, "qb-c", "team_hou", 0.04, 0.06),
    ):
        rows.append(
            {
                "player_id": player_id,
                "team_id": team,
                "season": season,
                "quarterback_name": player_id.upper(),
                "actual_epa_per_dropback": actual,
                "expected_epa_per_dropback": expected,
                "performance_above_expectation": actual - expected,
                "eligibility_status": "eligible",
                "model_version": "expected-fixture",
                "feature_source_max_season": season - 1,
                "is_out_of_sample": True,
                **CONTROL_VALUES,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _games() -> pl.DataFrame:
    rows = []
    for season, player_id, expected, game_epas in (
        (2020, "qb-a", 0.10, (0.30, 0.10, 0.20, 0.20)),
        (2020, "qb-b", 0.05, (0.00, 0.00, 0.00, 0.00)),
        (2021, "qb-a", 0.08, (0.18, 0.18, 0.18, 0.18)),
        (2021, "qb-c", 0.06, (0.04, 0.04, 0.04, 0.04)),
    ):
        del expected
        for week, epa in enumerate(game_epas, start=1):
            rows.append(
                {
                    "game_id": f"{season}-{player_id}-{week}",
                    "season": season,
                    "week": week,
                    "player_id": player_id,
                    "team_id": "team_hou",
                    "dropbacks": 50,
                    "epa_per_dropback": epa,
                }
            )
    return pl.DataFrame(rows)


def _assignment(
    key: str,
    coach: str,
    *,
    season: int = 2020,
    start: int = 1,
    end: int = 4,
    role: str = "head_coach",
    status: str = "verified",
    shared: bool = False,
) -> dict[str, object]:
    return {
        "assignment_key": key,
        "season": season,
        "team_id": "HOU",
        "canonical_team_id": "team_hou",
        "coach_id": coach,
        "coach_name": coach,
        "role": role,
        "start_week": start,
        "end_week": end,
        "interval_basis": "observed_game_weeks",
        "verification_status": status,
        "confidence_level": "high" if status == "verified" else "medium",
        "is_interim": False,
        "is_shared": shared,
        "is_retained": False,
    }


def _assignments() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _assignment("a-2020-1", "coach-a", start=1, end=2),
            _assignment("b-2020-2", "coach-b", start=3, end=4),
            _assignment("a-2021", "coach-a", season=2021),
        ],
        infer_schema_length=None,
    )


class CheckpointSixExposureTest(unittest.TestCase):
    def test_midseason_intervals_and_pae_reconcile(self) -> None:
        exposures = build_coach_exposures(_games(), _pae_rows(), _assignments())
        first = exposures.filter(
            (pl.col("player_id") == "qb-a") & (pl.col("assignment_key") == "a-2020-1")
        ).row(0, named=True)
        second = exposures.filter(
            (pl.col("player_id") == "qb-a") & (pl.col("assignment_key") == "b-2020-2")
        ).row(0, named=True)
        self.assertEqual((first["first_observed_week"], first["last_observed_week"]), (1, 2))
        self.assertEqual((second["first_observed_week"], second["last_observed_week"]), (3, 4))
        self.assertAlmostEqual(first["coach_interval_pae"], 0.10)
        self.assertAlmostEqual(second["coach_interval_pae"], 0.10)

    def test_shared_play_calling_uses_fractional_dropbacks(self) -> None:
        assignments = pl.DataFrame(
            [
                _assignment("shared-a", "coach-a", start=4, end=4, role="play_caller", shared=True),
                _assignment("shared-b", "coach-b", start=4, end=4, role="play_caller", shared=True),
            ],
            infer_schema_length=None,
        )
        exposures = build_coach_exposures(_games(), _pae_rows(), assignments)
        self.assertEqual(exposures.height, 4)
        self.assertTrue((exposures["exposure_fraction"] == 0.5).all())
        self.assertTrue((exposures["exposure_dropbacks"] == 25.0).all())

    def test_shared_exposure_below_threshold_is_excluded(self) -> None:
        assignments = pl.DataFrame(
            [
                _assignment("shared-a", "coach-a", start=4, end=4, role="play_caller", shared=True),
                _assignment("shared-b", "coach-b", start=4, end=4, role="play_caller", shared=True),
            ],
            infer_schema_length=None,
        )
        games = _games().with_columns(
            pl.when(pl.col("week") == 4)
            .then(pl.lit(40))
            .otherwise(pl.col("dropbacks"))
            .alias("dropbacks")
        )
        exposures = build_coach_exposures(games, _pae_rows(), assignments)
        self.assertTrue((exposures["observed_dropbacks"] == 40).all())
        self.assertTrue((exposures["exposure_dropbacks"] == 20.0).all())
        self.assertTrue((exposures["exclusion_reason"] == "below_25_interval_dropbacks").all())

    def test_illegal_overlap_and_duplicate_assignment_are_rejected(self) -> None:
        overlap = pl.DataFrame(
            [
                _assignment("overlap-a", "coach-a"),
                _assignment("overlap-b", "coach-b"),
            ],
            infer_schema_length=None,
        )
        with self.assertRaisesRegex(PipelineError, "illegal non-shared"):
            build_coach_exposures(_games(), _pae_rows(), overlap)
        duplicate = pl.concat([_assignments(), _assignments().head(1)])
        with self.assertRaisesRegex(PipelineError, "duplicate coaching assignment"):
            build_coach_exposures(_games(), _pae_rows(), duplicate)

    def test_pae_arithmetic_and_future_features_are_rejected(self) -> None:
        bad_pae = _pae_rows().with_columns(
            pl.when(pl.col("player_id") == "qb-a")
            .then(pl.lit(9.0))
            .otherwise(pl.col("performance_above_expectation"))
            .alias("performance_above_expectation")
        )
        with self.assertRaisesRegex(PipelineError, "PAE arithmetic"):
            build_coach_exposures(_games(), bad_pae, _assignments())
        leaked = _pae_rows().with_columns(pl.col("season").alias("feature_source_max_season"))
        with self.assertRaisesRegex(PipelineError, "future information"):
            build_coach_exposures(_games(), leaked, _assignments())

    def test_provisional_records_do_not_enter_verified_primary_estimates(self) -> None:
        assignments = pl.concat(
            [
                _assignments(),
                pl.DataFrame(
                    [
                        _assignment(
                            "provisional",
                            "coach-provisional",
                            season=2021,
                            role="offensive_coordinator",
                            status="provisional",
                        ),
                        _assignment(
                            "sparse-qb-coach",
                            "coach-a",
                            season=2021,
                            role="quarterbacks_coach",
                        ),
                    ],
                    infer_schema_length=None,
                ),
            ],
            how="vertical_relaxed",
        )
        exposures = build_coach_exposures(_games(), _pae_rows(), assignments)
        tables = build_coach_impact_tables(exposures, bootstrap_replicates=0)
        self.assertIn("provisional", set(exposures["verification_status"]))
        self.assertNotIn("coach-provisional", set(tables["coach_effect_estimates"]["coach_id"]))
        sparse = (
            tables["preliminary_coach_rankings"]
            .filter(pl.col("role") == "quarterbacks_coach")
            .row(0, named=True)
        )
        self.assertIsNone(sparse["estimated_effect"])
        self.assertEqual(sparse["rank_exclusion_reason"], "insufficient_role_identification")

    def test_partial_pooling_shrinks_small_samples(self) -> None:
        exposures = build_coach_exposures(_games(), _pae_rows(), _assignments())
        effects = build_coach_impact_tables(exposures, bootstrap_replicates=0)[
            "coach_effect_estimates"
        ]
        self.assertGreater(effects.height, 0)
        self.assertTrue(
            effects.select(
                (pl.col("estimated_effect").abs() <= pl.col("raw_effect").abs() + 1e-12).all()
            ).item()
        )

    def test_partial_pooling_variance_uses_independent_interval_degrees_of_freedom(self) -> None:
        fixture = pl.DataFrame(
            {
                "coach_id": ["a", "a", "b", "b"],
                "coach_name": ["A", "A", "B", "B"],
                "role": ["head_coach"] * 4,
                "coach_interval_pae": [1.0, 1.0, -1.0, -1.0],
                "exposure_dropbacks": [10.0] * 4,
            }
        )
        effects, _ = _partial_pool(fixture, baseline_prediction=[0.0] * 4)
        expected_sigma2 = 40.0 / 3.0
        expected_tau2 = 1.0 - expected_sigma2 / 20.0
        expected_shrinkage = expected_tau2 / (expected_tau2 + expected_sigma2 / 20.0)
        self.assertTrue(
            effects.select(
                (pl.col("residual_variance") - expected_sigma2).abs().max() < 1e-12
            ).item()
        )
        self.assertTrue(
            effects.select(
                (pl.col("shrinkage_weight") - expected_shrinkage).abs().max() < 1e-12
            ).item()
        )
        self.assertEqual(set(effects["residual_degrees_of_freedom"]), {3})

    def test_team_season_confounding_is_diagnosed_and_rankings_are_suppressed(self) -> None:
        exposures = build_coach_exposures(_games(), _pae_rows(), _assignments())
        diagnostic = _identification_diagnostic(
            exposures.filter(pl.col("coach_id") == "coach-a"), "head_coach"
        )
        self.assertTrue(diagnostic["near_one_to_one_team_season_confounding"])
        self.assertFalse(diagnostic["primary_includes_team_season_fixed_effects"])
        rankings = build_coach_impact_tables(exposures, bootstrap_replicates=2)[
            "preliminary_coach_rankings"
        ]
        self.assertFalse(rankings["rank_eligible"].any())
        self.assertEqual(set(rankings["ranking_status"]), {"suppressed_exploratory"})

    def test_sparse_bootstrap_support_suppresses_interval_and_is_reproducible(self) -> None:
        rows = []
        for index in range(10):
            rows.append(
                {
                    "player_id": f"qb-{index}",
                    "season": 2020,
                    "team_id": "team_hou",
                    "coach_id": "sparse" if index == 0 else "common",
                    "coach_name": "Sparse" if index == 0 else "Common",
                    "role": "head_coach",
                    "coach_interval_pae": 0.1 if index == 0 else -0.01,
                    "exposure_dropbacks": 100.0,
                    **CONTROL_VALUES,
                }
            )
        frame = pl.DataFrame(rows, infer_schema_length=None)
        effects, _ = _fit_role(frame)
        first = _bootstrap_intervals(frame, effects, 100).sort("coach_id")
        second = _bootstrap_intervals(frame, effects, 100).sort("coach_id")
        self.assertTrue(first.equals(second))
        sparse = first.filter(pl.col("coach_id") == "sparse").row(0, named=True)
        self.assertLess(sparse["bootstrap_replicates"], 80)
        self.assertFalse(sparse["bootstrap_interval_available"])
        self.assertIsNone(sparse["confidence_low"])
        self.assertIsNone(sparse["confidence_high"])
        self.assertEqual(sparse["bootstrap_attempted_replicates"], 100)
        self.assertIn("conditional_on_coach_observed", sparse["interval_estimand"])


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _pipeline_fixture(root: Path) -> tuple[Path, Path]:
    historical = root / "historical"
    historical_version = historical / "history-fixture" / "silver"
    historical_version.mkdir(parents=True)
    _games().write_parquet(historical_version / "qb_game_performance.parquet")
    (historical / "LATEST").write_text("history-fixture\n", encoding="utf-8")
    expected = root / "expected"
    expected_version = expected / "expected-fixture"
    expected_version.mkdir(parents=True)
    _pae_rows().write_parquet(expected_version / "qb_pae.parquet")
    (expected / "LATEST").write_text("expected-fixture\n", encoding="utf-8")
    assignment_rows = []
    for row in _assignments().to_dicts():
        assignment_rows.append(
            {
                **row,
                "is_interim": "true" if row["is_interim"] else "false",
                "is_shared": "true" if row["is_shared"] else "false",
                "is_retained": "true" if row["is_retained"] else "false",
            }
        )
    assignment_fields = list(assignment_rows[0])
    assignment_fields.remove("coach_name")
    assignment_fields.remove("canonical_team_id")
    _write_csv(
        root / "data" / "manual" / "coaching_assignments.csv",
        assignment_fields,
        [
            {key: value for key, value in row.items() if key in assignment_fields}
            for row in assignment_rows
        ],
    )
    _write_csv(
        root / "data" / "manual" / "coaches.csv",
        ["coach_id", "canonical_name", "normalized_name"],
        [
            {"coach_id": "coach-a", "canonical_name": "Coach A", "normalized_name": "coach-a"},
            {"coach_id": "coach-b", "canonical_name": "Coach B", "normalized_name": "coach-b"},
        ],
    )
    _write_csv(
        root / "data" / "manual" / "coach_assignment_sources.csv",
        ["assignment_key", "source_url"],
        [
            {"assignment_key": row["assignment_key"], "source_url": "https://example.test"}
            for row in assignment_rows
            if row["verification_status"] == "verified"
        ],
    )
    return historical, expected


class CheckpointSixPipelineTest(unittest.TestCase):
    def test_clean_builds_are_byte_identical_and_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical, expected = _pipeline_fixture(root)
            first = run_coach_impact_pipeline(
                CoachImpactConfig(
                    root,
                    historical_dir=historical,
                    expected_performance_dir=expected,
                    output_dir=root / "one",
                    bootstrap_replicates=2,
                )
            )
            second = run_coach_impact_pipeline(
                CoachImpactConfig(
                    root,
                    historical_dir=historical,
                    expected_performance_dir=expected,
                    output_dir=root / "two",
                    bootstrap_replicates=2,
                )
            )
            self.assertEqual(first.data_version, second.data_version)
            first_files = {
                path.relative_to(first.output_path): path.read_bytes()
                for path in first.output_path.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second.output_path): path.read_bytes()
                for path in second.output_path.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)

    def test_independent_process_clean_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical, expected = _pipeline_fixture(root)
            environment = {**os.environ, "PYTHONPATH": str(Path.cwd() / "src")}
            command = [
                sys.executable,
                "-m",
                "nfl_coaching_impact.cli",
                "coach-impact",
                "--project-root",
                str(root),
                "--historical-dir",
                str(historical),
                "--expected-performance-dir",
                str(expected),
                "--bootstrap-replicates",
                "2",
            ]
            subprocess.run(
                [*command, "--output-dir", str(root / "one")],
                check=True,
                capture_output=True,
                env=environment,
            )
            subprocess.run(
                [*command, "--output-dir", str(root / "two")],
                check=True,
                capture_output=True,
                env=environment,
            )
            first_version = (root / "one" / "LATEST").read_text(encoding="utf-8").strip()
            second_version = (root / "two" / "LATEST").read_text(encoding="utf-8").strip()
            self.assertEqual(first_version, second_version)
            first_path = root / "one" / first_version
            second_path = root / "two" / second_version
            first_files = {
                path.relative_to(first_path): path.read_bytes()
                for path in first_path.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second_path): path.read_bytes()
                for path in second_path.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)

    def test_output_affecting_parameter_changes_version_and_prevents_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical, expected = _pipeline_fixture(root)
            output = root / "output"
            first = run_coach_impact_pipeline(
                CoachImpactConfig(
                    root,
                    historical_dir=historical,
                    expected_performance_dir=expected,
                    output_dir=output,
                    bootstrap_replicates=2,
                )
            )
            with patch("nfl_coaching_impact.coach_impact.BASELINE_ALPHA", 999.0):
                second = run_coach_impact_pipeline(
                    CoachImpactConfig(
                        root,
                        historical_dir=historical,
                        expected_performance_dir=expected,
                        output_dir=output,
                        bootstrap_replicates=2,
                    )
                )
            self.assertNotEqual(first.data_version, second.data_version)
            self.assertFalse(second.reused_existing)

    def test_dependency_versions_are_in_model_identity(self) -> None:
        dependencies = _model_specification(2)["dependencies"]
        self.assertEqual(set(dependencies), {"numpy", "polars", "scipy", "scikit_learn"})


if __name__ == "__main__":
    unittest.main()

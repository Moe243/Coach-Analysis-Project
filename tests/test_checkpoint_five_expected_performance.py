from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import polars as pl

from nfl_coaching_impact.errors import PipelineError
from nfl_coaching_impact.expected_performance import (
    MODEL_FEATURE_COLUMNS,
    ExpectedPerformanceConfig,
    build_expected_performance_tables,
    build_preseason_features,
    run_expected_performance_pipeline,
    validate_model_outputs,
)


def _fixture_inputs() -> tuple[pl.DataFrame, pl.DataFrame]:
    rows = []
    for season in range(1999, 2026):
        player_count = 4 if season >= 2010 else 3
        for index in range(player_count):
            player_id = f"00-000000{index + 1}"
            team = "ATL" if player_id == "00-0000001" and season >= 2010 else "ARI"
            dropbacks = 240 + index * 20
            sacks = 20 + index
            attempts = dropbacks - sacks
            epa = -0.12 + 0.008 * (season - 1999) + 0.025 * index
            cpoe = -1.0 + 0.1 * index + 0.03 * (season - 1999)
            rows.append(
                {
                    "data_version": "fixture-history",
                    "metric_version": "qb-dropback-v1",
                    "season": season,
                    "player_id": player_id,
                    "team_id": team,
                    "games": 16,
                    "starts": 12 + index,
                    "dropbacks": dropbacks,
                    "attempts": attempts,
                    "completions": int(attempts * 0.62),
                    "sacks": sacks,
                    "scrambles": 10,
                    "interceptions": 8 + index,
                    "passing_touchdowns": 18 + index,
                    "passing_first_downs": 100,
                    "explosive_completions": 20,
                    "positive_epa_dropbacks": int(dropbacks * 0.48),
                    "cpoe_attempts": attempts,
                    "wpa_plays": dropbacks,
                    "air_yards_attempts": attempts,
                    "total_cpoe": cpoe * attempts,
                    "total_qb_epa": epa * dropbacks,
                    "total_wpa": 0.0,
                    "total_air_yards": attempts * 7.0,
                    "scope": "warmup" if season <= 2009 else "analysis",
                    "epa_per_dropback": epa,
                    "cpoe": cpoe,
                    "success_rate": 0.48,
                    "explosive_pass_rate": 0.08,
                    "interception_rate": (8 + index) / attempts,
                    "touchdown_rate": (18 + index) / attempts,
                    "sack_rate": sacks / (attempts + sacks),
                    "air_yards_per_attempt": 7.0,
                    "air_yards_coverage_rate": 1.0,
                    "first_down_rate": 100 / dropbacks,
                    "wpa_per_dropback": 0.0,
                    "qualifies_default": True,
                }
            )
    players = pl.DataFrame(
        [
            {
                "player_id": f"00-000000{index + 1}",
                "display_name": f"Fixture QB {index + 1}",
                "birth_date": None if index == 3 else f"1975-01-0{index + 1}",
            }
            for index in range(4)
        ]
    )
    return pl.DataFrame(rows), players


def _write_historical_fixture(root: Path, qb_seasons: pl.DataFrame, players: pl.DataFrame) -> Path:
    historical = root / "historical"
    version = historical / "fixture-history"
    silver = version / "silver"
    silver.mkdir(parents=True)
    qb_seasons.write_parquet(silver / "qb_team_season_performance.parquet")
    players.write_parquet(silver / "players.parquet")
    (historical / "LATEST").write_text("fixture-history\n", encoding="utf-8")
    return historical


class CheckpointFiveExpectedPerformanceTest(unittest.TestCase):
    def setUp(self) -> None:
        qb_seasons, players = _fixture_inputs()
        self.qb_seasons = qb_seasons
        self.players = players
        self.features = build_preseason_features(qb_seasons, players)

    def test_features_are_strictly_preseason_and_target_metric_cannot_leak(self) -> None:
        row = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000001")
        ).row(0, named=True)
        prior = self.qb_seasons.filter(
            (pl.col("season") == 2009) & (pl.col("player_id") == "00-0000001")
        ).row(0, named=True)
        self.assertEqual(row["as_of_season"], 2009)
        self.assertEqual(row["feature_source_max_season"], 2009)
        self.assertAlmostEqual(row["prior_epa_per_dropback"], prior["epa_per_dropback"])

        changed = self.qb_seasons.with_columns(
            pl.when((pl.col("season") == 2010) & (pl.col("player_id") == "00-0000001"))
            .then(pl.lit(9.0))
            .otherwise(pl.col("epa_per_dropback"))
            .alias("epa_per_dropback"),
            pl.when((pl.col("season") == 2010) & (pl.col("player_id") == "00-0000001"))
            .then(pl.col("dropbacks") * 9.0)
            .otherwise(pl.col("total_qb_epa"))
            .alias("total_qb_epa"),
        )
        alternate = build_preseason_features(changed, self.players)
        original_predictions = build_expected_performance_tables(self.features).predictions
        alternate_predictions = build_expected_performance_tables(alternate).predictions
        keys = ["model_name", "player_id", "team_id", "season"]
        comparison = (
            original_predictions.filter(pl.col("season") == 2010)
            .select(*keys, pl.col("expected_epa_per_dropback").alias("original"))
            .join(
                alternate_predictions.filter(pl.col("season") == 2010).select(
                    *keys, pl.col("expected_epa_per_dropback").alias("alternate")
                ),
                on=keys,
                validate="1:1",
            )
        )
        self.assertTrue(comparison.select((pl.col("original") == pl.col("alternate")).all()).item())

    def test_rookie_missing_history_and_league_fallback(self) -> None:
        tables = build_expected_performance_tables(self.features)
        rookie = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000004")
        ).row(0, named=True)
        self.assertTrue(rookie["is_rookie"])
        self.assertTrue(rookie["prior_season_missing"])
        self.assertIsNone(rookie["prior_epa_per_dropback"])
        values = tables.predictions.filter(
            (pl.col("season") == 2010)
            & (pl.col("player_id") == "00-0000004")
            & pl.col("model_name").is_in(
                ["league_average", "recent_performance", "career_performance"]
            )
        )["expected_epa_per_dropback"].to_list()
        self.assertEqual(len(values), 3)
        self.assertTrue(all(abs(value - values[0]) < 1e-15 for value in values))

    def test_team_change_and_missing_college_are_explicit(self) -> None:
        changed = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000001")
        ).row(0, named=True)
        self.assertTrue(changed["changed_team"])
        self.assertTrue(self.features["college_production_missing"].all())
        self.assertTrue(self.features["draft_position_missing"].all())

    def test_feature_generation_is_deterministic(self) -> None:
        rebuilt = build_preseason_features(self.qb_seasons, self.players)
        self.assertTrue(self.features.equals(rebuilt))

    def test_duplicate_qb_season_input_fails(self) -> None:
        duplicate = pl.concat([self.qb_seasons, self.qb_seasons.head(1)])
        with self.assertRaisesRegex(PipelineError, "duplicate QB-team-season"):
            build_preseason_features(duplicate, self.players)

    def test_selected_pae_is_finite_reconciled_and_excludes_warmup(self) -> None:
        tables = build_expected_performance_tables(self.features)
        validate_model_outputs(tables.features, tables.predictions, tables.pae)
        self.assertEqual(tables.pae["season"].min(), 2010)
        self.assertEqual(tables.pae["season"].max(), 2025)
        self.assertTrue(tables.pae["is_out_of_sample"].all())
        arithmetic = tables.pae.select(
            (
                pl.col("actual_epa_per_dropback")
                - pl.col("expected_epa_per_dropback")
                - pl.col("performance_above_expectation")
            )
            .abs()
            .max()
        ).item()
        self.assertLess(arithmetic, 1e-12)

    def test_duplicate_model_output_fails(self) -> None:
        tables = build_expected_performance_tables(self.features)
        duplicate = pl.concat([tables.predictions, tables.predictions.head(1)])
        with self.assertRaisesRegex(PipelineError, "duplicate model prediction"):
            validate_model_outputs(tables.features, duplicate, tables.pae)

    def test_model_feature_contract_excludes_coaching_and_current_results(self) -> None:
        lowered = " ".join(MODEL_FEATURE_COLUMNS).lower()
        for forbidden in ("coach", "record", "ranking", "wins", "losses"):
            self.assertNotIn(forbidden, lowered)

    def test_two_clean_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = _write_historical_fixture(root, self.qb_seasons, self.players)
            first = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root,
                    historical_dir=historical,
                    output_dir=root / "output-one",
                )
            )
            second = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root,
                    historical_dir=historical,
                    output_dir=root / "output-two",
                )
            )
            self.assertEqual(first.data_version, second.data_version)
            self.assertEqual(first.model_version, second.model_version)
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
            self.assertTrue((root / "output-one" / "EXECUTION_LOG.json").is_file())
            self.assertTrue((root / "output-two" / "EXECUTION_LOG.json").is_file())

    def test_failed_build_leaves_no_valid_looking_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = pl.concat([self.qb_seasons, self.qb_seasons.head(1)])
            historical = _write_historical_fixture(root, duplicate, self.players)
            output = root / "output"
            with self.assertRaisesRegex(PipelineError, "duplicate QB-team-season"):
                run_expected_performance_pipeline(
                    ExpectedPerformanceConfig(
                        project_root=root, historical_dir=historical, output_dir=output
                    )
                )
            self.assertFalse((output / "LATEST").exists())
            self.assertEqual([path for path in output.glob("c5-*")], [])

    def test_model_version_changes_when_a_preseason_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = _write_historical_fixture(root, self.qb_seasons, self.players)
            first = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root,
                    historical_dir=historical,
                    output_dir=root / "output-one",
                )
            )
            changed_players = self.players.with_columns(
                pl.when(pl.col("player_id") == "00-0000001")
                .then(pl.lit("1974-01-01"))
                .otherwise(pl.col("birth_date"))
                .alias("birth_date")
            )
            changed_players.write_parquet(
                historical / "fixture-history" / "silver" / "players.parquet"
            )
            second = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root,
                    historical_dir=historical,
                    output_dir=root / "output-two",
                )
            )
            self.assertNotEqual(first.data_version, second.data_version)
            self.assertNotEqual(first.model_version, second.model_version)


if __name__ == "__main__":
    unittest.main()

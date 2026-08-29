from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

FIXTURE_PLAYER_IDS = ("00-0025479", "00-0000002", "00-0000003", "00-0000004")


def _fixture_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    rows = []
    for season in range(1999, 2026):
        player_count = 4 if season >= 2010 else 3
        for index in range(player_count):
            player_id = FIXTURE_PLAYER_IDS[index]
            team = "ATL" if index == 1 and season >= 2010 else "BUF" if index == 0 else "ARI"
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
    trent_destination = dict(
        next(row for row in rows if row["player_id"] == "00-0025479" and row["season"] == 2010)
    )
    trent_destination.update(
        team_id="JAX",
        dropbacks=58,
        attempts=50,
        sacks=8,
        total_qb_epa=float(trent_destination["epa_per_dropback"]) * 58,
    )
    rows.append(trent_destination)
    players = pl.DataFrame(
        [
            {
                "player_id": FIXTURE_PLAYER_IDS[index],
                "display_name": "Trent Edwards" if index == 0 else f"Fixture QB {index + 1}",
                "birth_date": None if index == 3 else f"1975-01-0{index + 1}",
            }
            for index in range(4)
        ]
    )
    rosters = []
    depth_charts = []
    for season in range(1999, 2026):
        player_count = 4 if season >= 2010 else 3
        for index in range(player_count):
            player_id = FIXTURE_PLAYER_IDS[index]
            rookie_year = 2010 if index == 3 else 1999
            years_exp = season - rookie_year
            preseason_team = (
                "ATL" if index == 1 and season >= 2010 else "BUF" if index == 0 else "ARI"
            )
            rosters.append(
                {
                    "gsis_id": player_id,
                    "source_season": season,
                    "years_exp": years_exp,
                    "entry_year": rookie_year,
                    "rookie_year": rookie_year,
                }
            )
            depth_charts.append(
                {
                    "canonical_player_id": player_id,
                    "canonical_team_id": preseason_team,
                    "source_season": season,
                    "week": 1,
                    "game_type": "REG",
                }
            )
    return pl.DataFrame(rows), players, pl.DataFrame(rosters), pl.DataFrame(depth_charts)


def _write_historical_fixture(
    root: Path,
    qb_seasons: pl.DataFrame,
    players: pl.DataFrame,
    rosters: pl.DataFrame,
    depth_charts: pl.DataFrame,
) -> Path:
    historical = root / "historical"
    version = historical / "fixture-history"
    silver = version / "silver"
    silver.mkdir(parents=True)
    qb_seasons.write_parquet(silver / "qb_team_season_performance.parquet")
    players.write_parquet(silver / "players.parquet")
    for season in range(1999, 2026):
        roster_path = version / "bronze" / "rosters" / f"season={season}"
        roster_path.mkdir(parents=True)
        rosters.filter(pl.col("source_season") == season).drop("source_season").write_parquet(
            roster_path / "roster.parquet"
        )
        depth_path = silver / "depth_charts" / f"season={season}"
        depth_path.mkdir(parents=True)
        depth_charts.filter(pl.col("source_season") == season).write_parquet(
            depth_path / "data.parquet"
        )
    (historical / "LATEST").write_text("fixture-history\n", encoding="utf-8")
    return historical


class CheckpointFiveExpectedPerformanceTest(unittest.TestCase):
    def setUp(self) -> None:
        qb_seasons, players, rosters, depth_charts = _fixture_inputs()
        self.qb_seasons = qb_seasons
        self.players = players
        self.rosters = rosters
        self.depth_charts = depth_charts
        self.features = build_preseason_features(
            qb_seasons, players, rosters=rosters, depth_charts=depth_charts
        )

    def test_features_are_strictly_preseason_and_target_metric_cannot_leak(self) -> None:
        row = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0025479")
        ).row(0, named=True)
        prior = self.qb_seasons.filter(
            (pl.col("season") == 2009) & (pl.col("player_id") == "00-0025479")
        ).row(0, named=True)
        self.assertEqual(row["as_of_season"], 2009)
        self.assertEqual(row["feature_source_max_season"], 2009)
        self.assertAlmostEqual(row["prior_epa_per_dropback"], prior["epa_per_dropback"])

        changed = self.qb_seasons.with_columns(
            pl.when((pl.col("season") == 2010) & (pl.col("player_id") == "00-0025479"))
            .then(pl.lit(9.0))
            .otherwise(pl.col("epa_per_dropback"))
            .alias("epa_per_dropback"),
            pl.when((pl.col("season") == 2010) & (pl.col("player_id") == "00-0025479"))
            .then(pl.col("dropbacks") * 9.0)
            .otherwise(pl.col("total_qb_epa"))
            .alias("total_qb_epa"),
        )
        alternate = build_preseason_features(
            changed,
            self.players,
            rosters=self.rosters,
            depth_charts=self.depth_charts,
        )
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
        limited = self.features.filter(
            (pl.col("season") == 2011) & (pl.col("player_id") == "00-0000004")
        ).row(0, named=True)
        self.assertFalse(limited["no_prior_qb_performance"])
        self.assertEqual(limited["prior_qb_seasons"], 1)
        self.assertEqual(limited["performance_history_group"], "one_prior_qb_season")

    def test_team_change_and_missing_college_are_explicit(self) -> None:
        changed = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000002")
        ).row(0, named=True)
        self.assertTrue(changed["changed_team"])
        self.assertTrue(self.features["college_production_missing"].all())
        self.assertTrue(self.features["draft_position_missing"].all())

    def test_trent_edwards_midseason_destination_cannot_change_ridge(self) -> None:
        trent = self.features.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0025479")
        ).sort("team_id")
        self.assertEqual(trent["team_id"].to_list(), ["BUF", "JAX"])
        self.assertEqual(trent["preseason_team_id"].unique().to_list(), ["BUF"])
        self.assertEqual(trent["changed_team"].unique().to_list(), [False])
        for column in MODEL_FEATURE_COLUMNS:
            self.assertEqual(trent[column].n_unique(), 1, column)

        predictions = build_expected_performance_tables(self.features).predictions
        trent_ridge = predictions.filter(
            (pl.col("season") == 2010)
            & (pl.col("player_id") == "00-0025479")
            & (pl.col("model_name") == "ridge")
        )["expected_epa_per_dropback"]
        self.assertEqual(trent_ridge.n_unique(), 1)

        renamed_destination = self.qb_seasons.with_columns(
            pl.when(
                (pl.col("season") == 2010)
                & (pl.col("player_id") == "00-0025479")
                & (pl.col("team_id") == "JAX")
            )
            .then(pl.lit("MIA"))
            .otherwise(pl.col("team_id"))
            .alias("team_id")
        )
        alternate_features = build_preseason_features(
            renamed_destination,
            self.players,
            rosters=self.rosters,
            depth_charts=self.depth_charts,
        )
        alternate_predictions = build_expected_performance_tables(alternate_features).predictions
        keys = ["model_name", "player_id", "team_id", "season"]
        comparison = (
            predictions.filter((pl.col("model_name") == "ridge") & (pl.col("season") >= 2011))
            .select(*keys, pl.col("expected_epa_per_dropback").alias("original"))
            .join(
                alternate_predictions.filter(
                    (pl.col("model_name") == "ridge") & (pl.col("season") >= 2011)
                ).select(*keys, pl.col("expected_epa_per_dropback").alias("alternate")),
                on=keys,
                validate="1:1",
            )
        )
        self.assertTrue(comparison.select((pl.col("original") == pl.col("alternate")).all()).item())

    def test_roster_status_separates_veterans_without_qb_history_from_rookies(self) -> None:
        cases = [
            ("00-0028957", "Austin Davis", 2014, 2, 2012),
            ("00-0032156", "Trevor Siemian", 2016, 1, 2015),
            ("00-0032436", "Jeff Driskel", 2018, 2, 2016),
            ("00-0034771", "Mason Rudolph", 2019, 1, 2018),
            ("00-0036442", "Joe Burrow", 2020, 0, 2020),
        ]
        template = self.qb_seasons.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000004")
        ).row(0, named=True)
        qb_rows = []
        player_rows = []
        roster_rows = []
        depth_rows = []
        for player_id, name, season, years_exp, rookie_year in cases:
            row = dict(template)
            row.update(player_id=player_id, season=season, team_id="CIN")
            qb_rows.append(row)
            player_rows.append(
                {"player_id": player_id, "display_name": name, "birth_date": "1990-01-01"}
            )
            roster_rows.append(
                {
                    "gsis_id": player_id,
                    "source_season": season,
                    "years_exp": years_exp,
                    "entry_year": rookie_year,
                    "rookie_year": rookie_year,
                }
            )
            depth_rows.append(
                {
                    "canonical_player_id": player_id,
                    "canonical_team_id": "CIN",
                    "source_season": season,
                    "week": 1,
                    "game_type": "REG",
                }
            )
        features = build_preseason_features(
            pl.DataFrame(qb_rows),
            pl.DataFrame(player_rows),
            rosters=pl.DataFrame(roster_rows),
            depth_charts=pl.DataFrame(depth_rows),
        )
        for name in ("Austin Davis", "Trevor Siemian", "Jeff Driskel", "Mason Rudolph"):
            row = features.filter(pl.col("quarterback_name") == name).row(0, named=True)
            self.assertFalse(row["is_rookie"], name)
            self.assertTrue(row["no_prior_qb_performance"], name)
        burrow = features.filter(pl.col("quarterback_name") == "Joe Burrow").row(0, named=True)
        self.assertTrue(burrow["is_rookie"])
        self.assertEqual(burrow["experience_group"], "rookie")
        self.assertEqual(
            features.filter(pl.col("quarterback_name") == "Trevor Siemian")[
                "experience_group"
            ].item(),
            "one_prior_nfl_season",
        )
        self.assertEqual(
            features.filter(pl.col("quarterback_name") == "Austin Davis")[
                "experience_group"
            ].item(),
            "veteran",
        )
        self.assertIn("no_prior_qb_performance", MODEL_FEATURE_COLUMNS)
        self.assertIn("is_rookie", MODEL_FEATURE_COLUMNS)

    def test_feature_generation_is_deterministic(self) -> None:
        rebuilt = build_preseason_features(
            self.qb_seasons,
            self.players,
            rosters=self.rosters,
            depth_charts=self.depth_charts,
        )
        self.assertTrue(self.features.equals(rebuilt))

    def test_duplicate_qb_season_input_fails(self) -> None:
        duplicate = pl.concat([self.qb_seasons, self.qb_seasons.head(1)])
        with self.assertRaisesRegex(PipelineError, "duplicate QB-team-season"):
            build_preseason_features(
                duplicate,
                self.players,
                rosters=self.rosters,
                depth_charts=self.depth_charts,
            )

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
            historical = _write_historical_fixture(
                root,
                self.qb_seasons,
                self.players,
                self.rosters,
                self.depth_charts,
            )
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
            historical = _write_historical_fixture(
                root, duplicate, self.players, self.rosters, self.depth_charts
            )
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
            historical = _write_historical_fixture(
                root,
                self.qb_seasons,
                self.players,
                self.rosters,
                self.depth_charts,
            )
            first = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root,
                    historical_dir=historical,
                    output_dir=root / "output-one",
                )
            )
            changed_players = self.players.with_columns(
                pl.when(pl.col("player_id") == "00-0025479")
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

    def test_shrinkage_change_creates_new_version_and_rebuilds_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = _write_historical_fixture(
                root,
                self.qb_seasons,
                self.players,
                self.rosters,
                self.depth_charts,
            )
            output = root / "output"
            first = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root, historical_dir=historical, output_dir=output
                )
            )
            with patch(
                "nfl_coaching_impact.expected_performance.CAREER_SHRINKAGE_DROPBACKS",
                9999.0,
            ):
                second = run_expected_performance_pipeline(
                    ExpectedPerformanceConfig(
                        project_root=root, historical_dir=historical, output_dir=output
                    )
                )
            self.assertNotEqual(first.data_version, second.data_version)
            self.assertNotEqual(first.model_version, second.model_version)
            self.assertFalse(second.reused_existing)
            first_predictions = pl.read_parquet(first.output_path / "model_predictions.parquet")
            second_predictions = pl.read_parquet(second.output_path / "model_predictions.parquet")
            career_keys = ["model_name", "player_id", "team_id", "season"]
            changed = (
                first_predictions.filter(pl.col("model_name") == "career_performance")
                .select(*career_keys, pl.col("expected_epa_per_dropback").alias("first"))
                .join(
                    second_predictions.filter(pl.col("model_name") == "career_performance").select(
                        *career_keys, pl.col("expected_epa_per_dropback").alias("second")
                    ),
                    on=career_keys,
                    validate="1:1",
                )
                .filter(pl.col("first") != pl.col("second"))
            )
            self.assertGreater(changed.height, 0)

    def test_scipy_version_change_creates_new_version_without_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = _write_historical_fixture(
                root,
                self.qb_seasons,
                self.players,
                self.rosters,
                self.depth_charts,
            )
            output = root / "output"
            first = run_expected_performance_pipeline(
                ExpectedPerformanceConfig(
                    project_root=root, historical_dir=historical, output_dir=output
                )
            )
            with patch(
                "nfl_coaching_impact.expected_performance.scipy.__version__",
                "999.0.0-test",
            ):
                second = run_expected_performance_pipeline(
                    ExpectedPerformanceConfig(
                        project_root=root, historical_dir=historical, output_dir=output
                    )
                )
            self.assertNotEqual(first.data_version, second.data_version)
            self.assertNotEqual(first.model_version, second.model_version)
            self.assertFalse(second.reused_existing)
            self.assertNotEqual(first.output_path, second.output_path)
            self.assertTrue(first.output_path.is_dir())
            self.assertTrue(second.output_path.is_dir())


if __name__ == "__main__":
    unittest.main()

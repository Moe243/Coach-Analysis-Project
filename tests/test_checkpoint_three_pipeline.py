from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

from nfl_coaching_impact.constants import (
    DEPTH_CHART_REQUIRED_COLUMNS,
    INJURY_REQUIRED_COLUMNS,
    PLAYER_STATS_REQUIRED_COLUMNS,
    SNAP_COUNT_REQUIRED_COLUMNS,
)
from nfl_coaching_impact.errors import DataQualityError, SourceValidationError
from nfl_coaching_impact.historical import (
    HistoricalPipelineConfig,
    run_historical_pipeline,
    run_historical_preflight,
)
from nfl_coaching_impact.sources import (
    CoverageExpectation,
    SourceAsset,
    SourceCache,
    build_historical_source_plan,
)
from tests.test_checkpoint_two_pipeline import create_fixture_sources


def _row(columns: set[str] | frozenset[str], **values: object) -> dict[str, object]:
    return {column: values.get(column) for column in sorted(columns)}


def _add_context_sources(
    root: Path,
    assets: list[SourceAsset],
    seasons: tuple[int, ...],
) -> list[CoverageExpectation]:
    fixtures = root / "fixtures"
    for season in seasons:
        player_stats = fixtures / f"player_stats_{season}.parquet"
        pl.DataFrame(
            [
                _row(
                    PLAYER_STATS_REQUIRED_COLUMNS | {"recent_team", "week"},
                    season=season,
                    week=1,
                    player_id="00-0000001",
                    recent_team="ARI",
                )
            ]
        ).write_parquet(player_stats)
        assets.append(
            SourceAsset(
                asset_key=f"player_stats_{season}",
                dataset="player_stats",
                season=season,
                url=player_stats.as_uri(),
                cache_path=f"player_stats/stats_player_week_{season}.parquet",
                bronze_path=f"player_stats/season={season}/player_stats.parquet",
                required_columns=tuple(sorted(PLAYER_STATS_REQUIRED_COLUMNS)),
            )
        )
        if season >= 2012:
            snaps = fixtures / f"snap_counts_{season}.parquet"
            pl.DataFrame(
                [
                    _row(
                        SNAP_COUNT_REQUIRED_COLUMNS | {"team", "week"},
                        season=season,
                        week=1,
                        game_id=f"{season}_01_ARI_ATL",
                        team="ARI",
                        pfr_player_id="FixtQB00",
                    )
                ]
            ).write_parquet(snaps)
            assets.append(
                SourceAsset(
                    asset_key=f"snap_counts_{season}",
                    dataset="snap_counts",
                    season=season,
                    url=snaps.as_uri(),
                    cache_path=f"snap_counts/snap_counts_{season}.parquet",
                    bronze_path=f"snap_counts/season={season}/snap_counts.parquet",
                    required_columns=tuple(sorted(SNAP_COUNT_REQUIRED_COLUMNS)),
                )
            )

        injuries = fixtures / f"injuries_{season}.parquet"
        pl.DataFrame(
            [
                _row(
                    INJURY_REQUIRED_COLUMNS,
                    season=season,
                    week=1,
                    team="ARI",
                    gsis_id="00-0000001",
                )
            ]
        ).write_parquet(injuries)
        assets.append(
            SourceAsset(
                asset_key=f"injuries_{season}",
                dataset="injuries",
                season=season,
                url=injuries.as_uri(),
                cache_path=f"injuries/injuries_{season}.parquet",
                bronze_path=f"injuries/season={season}/injuries.parquet",
                required_columns=tuple(sorted(INJURY_REQUIRED_COLUMNS)),
            )
        )

        depth = fixtures / f"depth_charts_{season}.parquet"
        pl.DataFrame(
            [
                _row(
                    DEPTH_CHART_REQUIRED_COLUMNS | {"season", "club_code"},
                    season=season,
                    club_code="ARI",
                    gsis_id="00-0000001",
                )
            ]
        ).write_parquet(depth)
        assets.append(
            SourceAsset(
                asset_key=f"depth_charts_{season}",
                dataset="depth_charts",
                season=season,
                url=depth.as_uri(),
                cache_path=f"depth_charts/depth_charts_{season}.parquet",
                bronze_path=f"depth_charts/season={season}/depth_charts.parquet",
                required_columns=tuple(sorted(DEPTH_CHART_REQUIRED_COLUMNS)),
            )
        )
    return build_historical_source_plan(seasons)[1]


def create_historical_fixtures(
    root: Path,
    seasons: tuple[int, ...] = (2009, 2010, 2012),
) -> tuple[list[SourceAsset], list[CoverageExpectation]]:
    assets = create_fixture_sources(root, seasons=seasons)
    coverage = _add_context_sources(root, assets, seasons)
    return assets, coverage


def _tree_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CheckpointThreePipelineTest(unittest.TestCase):
    def test_checkpoint_reports_and_plan_match_final_boundaries(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        checkpoint_two = (project_root / "docs" / "CHECKPOINT_2_REPORT.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(checkpoint_two.count("Published local data version:"), 1)
        self.assertNotIn("c2-7b086f7e552ec74a", checkpoint_two)
        checkpoint_three = (project_root / "docs" / "CHECKPOINT_3_REPORT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("c3-f6c1aa118ff43b90", checkpoint_three)
        self.assertIn("checkpoint-3.3", checkpoint_three)
        self.assertIn("## Exact next checkpoint", checkpoint_three)
        project_plan = (project_root / "docs" / "PROJECT_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("Checkpoint three — full historical ingestion (complete)", project_plan)
        self.assertIn("Checkpoint four — coaching-data verification", project_plan)

    def test_full_registry_records_expected_historical_gaps(self) -> None:
        assets, coverage = build_historical_source_plan(range(1999, 2026))
        self.assertEqual(len(assets), 140)
        self.assertEqual(len(coverage), 162)
        gaps = {(item.dataset, item.season) for item in coverage if not item.expected_available}
        self.assertIn(("injuries", 1999), gaps)
        self.assertIn(("depth_charts", 2000), gaps)
        self.assertIn(("snap_counts", 2011), gaps)
        self.assertNotIn(("injuries", 2009), gaps)
        self.assertNotIn(("depth_charts", 2001), gaps)
        self.assertNotIn(("snap_counts", 2012), gaps)

    def test_preflight_rejects_insufficient_storage_before_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, _ = create_historical_fixtures(root)
            cache = root / "cache"
            with self.assertRaisesRegex(SourceValidationError, "Insufficient storage"):
                run_historical_preflight(
                    HistoricalPipelineConfig(
                        project_root=root,
                        seasons=(2009, 2010, 2012),
                        cache_dir=cache,
                        output_dir=root / "output",
                        available_bytes=0,
                    ),
                    assets=assets,
                )
            self.assertFalse(cache.exists())

    def test_empty_expected_season_asset_is_recorded_without_fabrication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "snap_counts_2012.parquet"
            pl.DataFrame(
                schema={"season": pl.Int32, "game_id": pl.String, "pfr_player_id": pl.String}
            ).write_parquet(source)
            asset = SourceAsset(
                asset_key="snap_counts_2012",
                dataset="snap_counts",
                season=2012,
                url=source.as_uri(),
                cache_path="snap_counts/snap_counts_2012.parquet",
                bronze_path="snap_counts/season=2012/snap_counts.parquet",
                required_columns=("game_id", "pfr_player_id", "season"),
            )
            _, metadata = SourceCache(root / "cache").materialize(asset)
            self.assertEqual(metadata.row_count, 0)
            self.assertEqual(metadata.validation_status, "passed")

    def test_clean_rebuild_is_byte_identical_and_reports_every_season(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, coverage = create_historical_fixtures(root)
            first_output = root / "output-first"
            second_output = root / "output-second"
            config = HistoricalPipelineConfig(
                project_root=root,
                seasons=(2009, 2010, 2012),
                cache_dir=root / "cache",
                output_dir=first_output,
            )
            first = run_historical_pipeline(config, assets=assets, coverage=coverage)
            first_checksums = json.loads(
                (first.output_path / "OUTPUT_CHECKSUMS.json").read_text(encoding="utf-8")
            )

            summary = pl.read_parquet(first.output_path / "silver" / "season_summary.parquet")
            self.assertEqual(summary.get_column("season").to_list(), [2009, 2010, 2012])
            self.assertEqual(
                summary.get_column("scope").to_list(),
                ["warmup", "analysis", "analysis"],
            )
            self.assertEqual(summary.get_column("quality_failures").to_list(), [0, 0, 0])
            coverage_frame = pl.read_parquet(
                first.output_path / "silver" / "source_coverage.parquet"
            )
            self.assertEqual(
                coverage_frame.filter(
                    (pl.col("dataset") == "snap_counts") & ~pl.col("expected_available")
                ).height,
                2,
            )
            snap_counts = pl.read_parquet(
                first.output_path / "silver" / "snap_counts" / "season=2012" / "data.parquet"
            )
            self.assertEqual(snap_counts.get_column("canonical_player_id").item(), "00-0000001")
            qb_seasons = pl.read_parquet(
                first.output_path / "silver" / "qb_team_season_performance.parquet"
            )
            self.assertEqual(set(qb_seasons.get_column("season")), {2009, 2010, 2012})
            self.assertEqual(
                qb_seasons.filter((pl.col("season") == 2009) & pl.col("qualifies_default")).height,
                0,
            )

            second = run_historical_pipeline(
                HistoricalPipelineConfig(
                    project_root=root,
                    seasons=(2009, 2010, 2012),
                    cache_dir=root / "cache",
                    output_dir=second_output,
                    offline=True,
                ),
                assets=assets,
                coverage=coverage,
            )
            second_checksums = json.loads(
                (second.output_path / "OUTPUT_CHECKSUMS.json").read_text(encoding="utf-8")
            )
            self.assertFalse(first.reused_existing)
            self.assertFalse(second.reused_existing)
            self.assertEqual(first.data_version, second.data_version)
            self.assertEqual(first_checksums, second_checksums)
            self.assertEqual(_tree_digests(first.output_path), _tree_digests(second.output_path))
            self.assertEqual(
                _tree_digests(first_output / "seasons"),
                _tree_digests(second_output / "seasons"),
            )
            first_execution = json.loads(
                (first_output / "EXECUTION_LOG.json").read_text(encoding="utf-8")
            )
            second_execution = json.loads(
                (second_output / "EXECUTION_LOG.json").read_text(encoding="utf-8")
            )
            self.assertGreater(first_execution["preflight"]["download_bytes"], 0)
            self.assertEqual(second_execution["preflight"]["download_bytes"], 0)
            self.assertNotEqual(first_execution, second_execution)
            self.assertFalse((first.output_path / "PREFLIGHT.json").exists())

    def test_null_pbp_game_id_fails_with_season_counts_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, coverage = create_historical_fixtures(root, seasons=(2009,))
            pbp_asset = next(asset for asset in assets if asset.asset_key == "pbp_2009")
            pbp_path = Path(pbp_asset.url.removeprefix("file://"))
            pbp = pl.read_parquet(pbp_path).with_columns(
                pl.when(pl.col("play_id") == 1.0)
                .then(pl.lit(None, dtype=pl.String))
                .otherwise(pl.col("game_id"))
                .alias("game_id")
            )
            pbp.write_parquet(pbp_path)
            with self.assertRaisesRegex(
                DataQualityError,
                r"season=2009; null_game_id_rows=1; null_play_id_rows=0;.*play_id",
            ):
                run_historical_pipeline(
                    HistoricalPipelineConfig(
                        project_root=root,
                        seasons=(2009,),
                        cache_dir=root / "cache",
                        output_dir=root / "output",
                    ),
                    assets=assets,
                    coverage=coverage,
                )

    def test_null_pbp_play_id_fails_with_season_counts_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, coverage = create_historical_fixtures(root, seasons=(2009,))
            pbp_asset = next(asset for asset in assets if asset.asset_key == "pbp_2009")
            pbp_path = Path(pbp_asset.url.removeprefix("file://"))
            pbp = pl.read_parquet(pbp_path).with_columns(
                pl.when(pl.col("play_id") == 1.0)
                .then(pl.lit(None, dtype=pl.Float64))
                .otherwise(pl.col("play_id"))
                .alias("play_id")
            )
            pbp.write_parquet(pbp_path)
            with self.assertRaisesRegex(
                DataQualityError,
                r"season=2009; null_game_id_rows=0; null_play_id_rows=1;.*game_id",
            ):
                run_historical_pipeline(
                    HistoricalPipelineConfig(
                        project_root=root,
                        seasons=(2009,),
                        cache_dir=root / "cache",
                        output_dir=root / "output",
                    ),
                    assets=assets,
                    coverage=coverage,
                )

    def test_duplicate_pbp_composite_key_fails_with_season_counts_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, coverage = create_historical_fixtures(root, seasons=(2009,))
            pbp_asset = next(asset for asset in assets if asset.asset_key == "pbp_2009")
            pbp_path = Path(pbp_asset.url.removeprefix("file://"))
            pbp = pl.read_parquet(pbp_path)
            pl.concat([pbp, pbp.head(1)]).write_parquet(pbp_path)
            with self.assertRaisesRegex(
                DataQualityError,
                r"season=2009; null_game_id_rows=0; null_play_id_rows=0; "
                r"duplicate_excess_rows=1;.*key_row_count",
            ):
                run_historical_pipeline(
                    HistoricalPipelineConfig(
                        project_root=root,
                        seasons=(2009,),
                        cache_dir=root / "cache",
                        output_dir=root / "output",
                    ),
                    assets=assets,
                    coverage=coverage,
                )

    def test_failed_season_preserves_completed_season_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, coverage = create_historical_fixtures(root)
            schedule_asset = next(asset for asset in assets if asset.asset_key == "schedules")
            schedule_path = Path(schedule_asset.url.removeprefix("file://"))
            schedules = pl.read_parquet(schedule_path).with_columns(
                pl.when(pl.col("season") == 2010)
                .then(pl.lit("BUF"))
                .otherwise(pl.col("home_team"))
                .alias("home_team")
            )
            schedules.write_parquet(schedule_path)
            output = root / "output"

            with self.assertRaisesRegex(DataQualityError, "dropbacks_match_schedule_teams"):
                run_historical_pipeline(
                    HistoricalPipelineConfig(
                        project_root=root,
                        seasons=(2009, 2010, 2012),
                        cache_dir=root / "cache",
                        output_dir=output,
                    ),
                    assets=assets,
                    coverage=coverage,
                )
            season_latest = output / "seasons" / "season=2009" / "LATEST"
            self.assertTrue(season_latest.is_file())
            completed = season_latest.read_text(encoding="utf-8").strip()
            self.assertTrue((season_latest.parent / completed).is_dir())
            self.assertFalse((output / "LATEST").exists())


if __name__ == "__main__":
    unittest.main()

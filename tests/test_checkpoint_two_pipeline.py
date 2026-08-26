from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

import polars as pl

from nfl_coaching_impact.constants import (
    CANONICAL_TEAM_IDS,
    PBP_REQUIRED_COLUMNS,
    PLAYER_REQUIRED_COLUMNS,
    ROSTER_REQUIRED_COLUMNS,
    SCHEDULE_REQUIRED_COLUMNS,
    TEAM_REQUIRED_COLUMNS,
    VERTICAL_SLICE_SEASONS,
)
from nfl_coaching_impact.errors import DataQualityError, PipelineError, SourceValidationError
from nfl_coaching_impact.pipeline import PipelineConfig, run_vertical_slice
from nfl_coaching_impact.quality import QualityReport
from nfl_coaching_impact.sources import SourceAsset
from nfl_coaching_impact.transforms import build_games, build_players, build_qb_seasons


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(columns: Iterable[str], **values: object) -> dict[str, object]:
    return {column: values.get(column) for column in sorted(set(columns))}


def create_fixture_sources(
    root: Path,
    *,
    omit_qb_epa: bool = False,
    seasons: Iterable[int] = VERTICAL_SLICE_SEASONS,
) -> list[SourceAsset]:
    fixtures = root / "fixtures"
    fixtures.mkdir(parents=True)
    assets: list[SourceAsset] = []

    season_list = tuple(sorted(set(seasons)))
    for season in season_list:
        game_id = f"{season}_01_ARI_ATL"
        omitted_columns = {"qb_epa"} if omit_qb_epa and season == 2009 else set()
        pbp_columns = PBP_REQUIRED_COLUMNS - omitted_columns
        plays = [
            _row(
                pbp_columns,
                play_id=1.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                pass_attempt=1.0,
                complete_pass=1.0,
                sack=0.0,
                interception=0.0,
                pass_touchdown=1.0,
                first_down_pass=1.0,
                yards_gained=25.0,
                air_yards=15.0,
                qb_epa=0.5,
                wpa=0.02,
                cpoe=5.0,
                passer_player_id="00-0000001",
                passer_player_name="Fixture QB",
                passer_id="00-0000001",
            ),
            _row(
                pbp_columns,
                play_id=2.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                pass_attempt=0.0,
                complete_pass=0.0,
                sack=1.0,
                interception=0.0,
                pass_touchdown=0.0,
                first_down_pass=0.0,
                yards_gained=-7.0,
                qb_epa=-0.7,
                wpa=-0.03,
                passer_player_id="00-0000001",
                passer_player_name="Fixture QB",
                passer_id="00-0000001",
            ),
            _row(
                pbp_columns,
                play_id=3.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=1.0,
                pass_attempt=0.0,
                complete_pass=0.0,
                sack=0.0,
                interception=0.0,
                pass_touchdown=0.0,
                first_down_pass=0.0,
                yards_gained=8.0,
                qb_epa=0.3,
                wpa=0.01,
                rusher_player_id="00-0000001",
                rusher_player_name="Fixture QB",
            ),
            _row(
                pbp_columns,
                play_id=4.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                pass_attempt=1.0,
                complete_pass=0.0,
                sack=0.0,
                interception=0.0,
                pass_touchdown=0.0,
                first_down_pass=0.0,
                yards_gained=0.0,
                qb_epa=-0.2,
                wpa=-0.01,
            ),
            _row(
                pbp_columns,
                play_id=5.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=1.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                qb_epa=100.0,
                passer_player_id="00-0000001",
                passer_id="00-0000001",
            ),
            _row(
                pbp_columns,
                play_id=6.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=1.0,
                qb_scramble=0.0,
                qb_epa=100.0,
                passer_player_id="00-0000001",
                passer_id="00-0000001",
            ),
            _row(
                pbp_columns,
                play_id=7.0,
                game_id=game_id,
                season=season,
                season_type="POST",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                qb_epa=100.0,
                passer_player_id="00-0000001",
                passer_id="00-0000001",
            ),
            _row(
                pbp_columns,
                play_id=8.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                qb_epa=-0.4,
                passer_player_id="00-0000001",
                passer_id="00-0000002",
            ),
            _row(
                pbp_columns,
                play_id=9.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ATL",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=1.0,
                pass_attempt=0.0,
                sack=0.0,
                qb_epa=0.1,
                wpa=0.01,
                rusher_player_id="00-0000002",
                rusher_player_name="Opponent QB",
            ),
            _row(
                pbp_columns,
                play_id=10.0,
                game_id=game_id,
                season=season,
                season_type="REG",
                week=1,
                posteam="ARI",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=1.0,
                qb_kneel=0.0,
                qb_spike=0.0,
                qb_scramble=0.0,
                pass_attempt=1.0,
                complete_pass=0.0,
                sack=0.0,
                interception=0.0,
                pass_touchdown=0.0,
                first_down_pass=0.0,
                yards_gained=0.0,
                air_yards=None,
                qb_epa=0.0,
                wpa=0.0,
                cpoe=None,
                passer_player_id="00-0000001",
                passer_player_name="Fixture QB",
                passer_id="00-0000001",
            ),
        ]
        pbp_path = fixtures / f"pbp_{season}.parquet"
        pbp_frame = pl.DataFrame(plays, infer_schema_length=None)
        pbp_frame.write_parquet(pbp_path)
        assets.append(
            SourceAsset(
                asset_key=f"pbp_{season}",
                dataset="play_by_play",
                season=season,
                url=pbp_path.as_uri(),
                cache_path=f"pbp/play_by_play_{season}.parquet",
                bronze_path=f"play_by_play/season={season}/play_by_play.parquet",
                required_columns=tuple(sorted(PBP_REQUIRED_COLUMNS)),
            )
        )

        roster_path = fixtures / f"roster_{season}.parquet"
        pl.DataFrame(
            [
                _row(
                    ROSTER_REQUIRED_COLUMNS,
                    season=season,
                    team="ARI",
                    position="QB",
                    full_name="Fixture QB",
                    birth_date="1985-01-01",
                    college="Example University",
                    gsis_id="00-0000001",
                )
            ]
        ).write_parquet(roster_path)
        assets.append(
            SourceAsset(
                asset_key=f"roster_{season}",
                dataset="rosters",
                season=season,
                url=roster_path.as_uri(),
                cache_path=f"rosters/roster_{season}.parquet",
                bronze_path=f"rosters/season={season}/roster.parquet",
                required_columns=tuple(sorted(ROSTER_REQUIRED_COLUMNS)),
            )
        )

    schedules_path = fixtures / "games.parquet"
    pl.DataFrame(
        [
            _row(
                SCHEDULE_REQUIRED_COLUMNS,
                game_id=f"{season}_01_ARI_ATL",
                season=season,
                game_type="REG",
                week=1,
                gameday=f"{season}-09-10",
                home_team="ARI",
                away_team="ATL",
                home_score=24,
                away_score=17,
                home_qb_id="00-0000001",
                away_qb_id="00-0000002",
            )
            for season in season_list
        ]
    ).write_parquet(schedules_path)
    assets.append(
        SourceAsset(
            asset_key="schedules",
            dataset="schedules",
            url=schedules_path.as_uri(),
            cache_path="global/games.parquet",
            bronze_path="schedules/games.parquet",
            required_columns=tuple(sorted(SCHEDULE_REQUIRED_COLUMNS)),
        )
    )

    players_path = fixtures / "players.parquet"
    player_columns = set(PLAYER_REQUIRED_COLUMNS) | {"esb_id", "pfr_id"}
    pl.DataFrame(
        [
            _row(
                player_columns,
                gsis_id="00-0000001",
                display_name="Fixture QB",
                birth_date="1985-01-01",
                position="QB",
                college_name="Example University",
                esb_id="fixture-1",
                pfr_id="FixtQB00",
            ),
            _row(
                player_columns,
                gsis_id="00-0000002",
                display_name="Opponent QB",
                birth_date="1986-01-01",
                position="QB",
                college_name="Example State",
                esb_id="fixture-2",
                pfr_id="OppoQB00",
            ),
        ]
    ).write_parquet(players_path)
    assets.append(
        SourceAsset(
            asset_key="players",
            dataset="players",
            url=players_path.as_uri(),
            cache_path="global/players.parquet",
            bronze_path="players/players.parquet",
            required_columns=tuple(sorted(PLAYER_REQUIRED_COLUMNS)),
        )
    )

    teams_path = fixtures / "teams.parquet"
    pl.DataFrame(
        [
            _row(
                TEAM_REQUIRED_COLUMNS,
                team_abbr=abbr,
                team_name=f"{abbr} Fixture Team",
                team_id=index,
            )
            for index, abbr in enumerate(sorted(CANONICAL_TEAM_IDS), start=1)
        ]
    ).write_parquet(teams_path)
    assets.append(
        SourceAsset(
            asset_key="teams",
            dataset="teams",
            url=teams_path.as_uri(),
            cache_path="global/teams.parquet",
            bronze_path="teams/teams_colors_logos.parquet",
            required_columns=tuple(sorted(TEAM_REQUIRED_COLUMNS)),
        )
    )
    return assets


class CheckpointTwoPipelineTest(unittest.TestCase):
    def test_fixture_columns_are_constructed_in_sorted_order(self) -> None:
        self.assertEqual(
            list(_row(["zeta", "alpha", "middle"])),
            ["alpha", "middle", "zeta"],
        )

        with tempfile.TemporaryDirectory() as temporary:
            assets = create_fixture_sources(Path(temporary))
            for asset in assets:
                columns = pl.read_parquet(Path(asset.url.removeprefix("file://"))).columns
                self.assertEqual(columns, sorted(columns), asset.asset_key)

    def test_offline_fixture_pipeline_proves_metrics_lineage_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = create_fixture_sources(root)
            config = PipelineConfig(
                project_root=root,
                cache_dir=root / "cache",
                output_dir=root / "output",
            )
            first = run_vertical_slice(config, assets=assets)

            self.assertFalse(first.reused_existing)
            self.assertTrue((first.output_path / "RUN_MANIFEST.json").is_file())
            self.assertTrue((first.output_path / "OUTPUT_CHECKSUMS.json").is_file())
            self.assertTrue((first.output_path / "DATA_QUALITY_REPORT.md").is_file())
            self.assertEqual((root / "output" / "LATEST").read_text().strip(), first.data_version)

            source_manifest = pl.read_parquet(
                first.output_path / "silver" / "source_manifest.parquet"
            )
            self.assertEqual(source_manifest.height, 13)
            self.assertEqual(set(source_manifest.get_column("validation_status")), {"passed"})
            for asset in assets:
                bronze = first.output_path / "bronze" / asset.bronze_path
                source = Path(asset.url.removeprefix("file://"))
                self.assertEqual(_sha256(bronze), _sha256(source))

            qb_games = pl.read_parquet(first.output_path / "silver" / "qb_game_performance.parquet")
            row = qb_games.filter(
                (pl.col("season") == 2009) & (pl.col("player_id") == "00-0000001")
            ).row(0, named=True)
            self.assertEqual(row["dropbacks"], 4)
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(row["sacks"], 1)
            self.assertEqual(row["scrambles"], 1)
            self.assertAlmostEqual(row["epa_per_dropback"], (0.5 - 0.7 + 0.3) / 4)
            self.assertAlmostEqual(row["success_rate"], 2 / 4)
            self.assertEqual(row["cpoe"], 5.0)
            self.assertEqual(row["explosive_pass_rate"], 0.5)
            self.assertEqual(row["touchdown_rate"], 0.5)
            self.assertEqual(row["interception_rate"], 0.0)
            self.assertAlmostEqual(row["sack_rate"], 1 / 3)
            self.assertEqual(row["air_yards_per_attempt"], 7.5)
            self.assertEqual(row["air_yards_coverage_rate"], 0.5)
            zero_attempt = qb_games.filter(
                (pl.col("season") == 2009) & (pl.col("player_id") == "00-0000002")
            ).row(0, named=True)
            self.assertEqual(zero_attempt["dropbacks"], 1)
            self.assertIsNone(zero_attempt["cpoe"])
            self.assertIsNone(zero_attempt["explosive_pass_rate"])
            self.assertIsNone(zero_attempt["sack_rate"])

            qb_seasons = pl.read_parquet(
                first.output_path / "silver" / "qb_team_season_performance.parquet"
            )
            fixture_qb = pl.col("player_id") == "00-0000001"
            warmup = qb_seasons.filter((pl.col("season") == 2009) & fixture_qb).row(0, named=True)
            current = qb_seasons.filter((pl.col("season") == 2010) & fixture_qb).row(0, named=True)
            boundary = qb_seasons.filter((pl.col("season") == 2016) & fixture_qb).row(0, named=True)
            self.assertEqual(warmup["scope"], "warmup")
            self.assertFalse(warmup["qualifies_default"])
            self.assertEqual(current["prior_season"], 2009)
            self.assertTrue(current["prior_season_available"])
            self.assertIsNone(boundary["prior_season"])

            unresolved = pl.read_parquet(
                first.output_path / "silver" / "unresolved_qb_plays.parquet"
            )
            self.assertEqual(unresolved.height, 10)
            self.assertEqual(
                set(unresolved.get_column("resolution_status")),
                {"missing_id", "conflicting_ids"},
            )

            offline = PipelineConfig(
                project_root=root,
                cache_dir=root / "cache",
                output_dir=root / "output",
                offline=True,
            )
            second = run_vertical_slice(offline, assets=assets)
            self.assertTrue(second.reused_existing)
            self.assertEqual(first.data_version, second.data_version)

            run_manifest = json.loads(
                (first.output_path / "RUN_MANIFEST.json").read_text(encoding="utf-8")
            )
            pipeline_manifest = pl.read_parquet(
                first.output_path / "silver" / "pipeline_manifest.parquet"
            ).row(0, named=True)
            self.assertEqual(
                json.loads(pipeline_manifest["table_counts_json"]),
                run_manifest["table_counts"],
            )

            corrupt = first.output_path / "silver" / "teams.parquet"
            corrupt.write_bytes(b"corrupt")
            with self.assertRaises(PipelineError):
                run_vertical_slice(offline, assets=assets)

    def test_schema_failure_publishes_no_partial_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = create_fixture_sources(root, omit_qb_epa=True)
            output = root / "output"
            with self.assertRaises(SourceValidationError):
                run_vertical_slice(
                    PipelineConfig(
                        project_root=root,
                        cache_dir=root / "cache",
                        output_dir=output,
                    ),
                    assets=assets,
                )
            self.assertFalse((output / "LATEST").exists())
            published = [path for path in output.glob("c2-*") if path.is_dir()]
            self.assertEqual(published, [])

    def test_team_normalization_and_duplicate_game_failure(self) -> None:
        schedule = pl.DataFrame(
            [
                _row(
                    SCHEDULE_REQUIRED_COLUMNS,
                    game_id="2009_01_OAK_SD",
                    season=2009,
                    game_type="REG",
                    week=1,
                    gameday="2009-09-14",
                    home_team="OAK",
                    away_team="SD",
                    home_score=24,
                    away_score=20,
                    home_qb_id="00-0000001",
                    away_qb_id="00-0000002",
                )
            ]
        )
        games = build_games(schedule, (2009,), QualityReport())
        self.assertEqual(games.get_column("home_team_id").item(), "team_lv")
        self.assertEqual(games.get_column("away_team_id").item(), "team_lac")

        with self.assertRaises(DataQualityError):
            build_games(pl.concat([schedule, schedule]), (2009,), QualityReport())

    def test_blank_non_team_aliases_are_treated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = create_fixture_sources(root)
            pbp_asset = next(asset for asset in assets if asset.asset_key == "pbp_2009")
            pbp_path = Path(pbp_asset.url.removeprefix("file://"))
            pbp = pl.read_parquet(pbp_path)
            blank = pbp.row(0, named=True)
            blank.update(
                play_id=999.0,
                posteam="",
                home_team="ARI",
                away_team="ATL",
                qb_dropback=0.0,
            )
            pl.concat([pbp, pl.DataFrame([blank])], how="diagonal_relaxed").write_parquet(pbp_path)
            result = run_vertical_slice(
                PipelineConfig(
                    project_root=root,
                    cache_dir=root / "cache",
                    output_dir=root / "output",
                ),
                assets=assets,
            )
            aliases = pl.read_parquet(result.output_path / "silver" / "team_aliases.parquet")
            self.assertEqual(aliases.filter(pl.col("alias") == "").height, 0)

    def test_invalid_qb_epa_is_quarantined_before_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = create_fixture_sources(root)
            pbp_asset = next(asset for asset in assets if asset.asset_key == "pbp_2009")
            pbp_path = Path(pbp_asset.url.removeprefix("file://"))
            pbp = pl.read_parquet(pbp_path).with_columns(
                pl.when(pl.col("play_id") == 1.0)
                .then(pl.lit(None, dtype=pl.Float64))
                .otherwise(pl.col("qb_epa"))
                .alias("qb_epa")
            )
            pbp.write_parquet(pbp_path)
            result = run_vertical_slice(
                PipelineConfig(
                    project_root=root,
                    cache_dir=root / "cache",
                    output_dir=root / "output",
                ),
                assets=assets,
            )
            unresolved = pl.read_parquet(
                result.output_path / "silver" / "unresolved_qb_plays.parquet"
            )
            self.assertEqual(
                unresolved.filter(pl.col("resolution_status") == "invalid_qb_epa").height,
                1,
            )
            qb_games = pl.read_parquet(
                result.output_path / "silver" / "qb_game_performance.parquet"
            )
            self.assertEqual(
                qb_games.filter((pl.col("season") == 2009) & (pl.col("player_id") == "00-0000001"))
                .get_column("dropbacks")
                .item(),
                3,
            )

    def test_null_game_id_fails_before_uniqueness_check(self) -> None:
        schedule = pl.DataFrame(
            [
                _row(
                    SCHEDULE_REQUIRED_COLUMNS,
                    game_id=None,
                    season=2009,
                    game_type="REG",
                    week=1,
                    gameday="2009-09-14",
                    home_team="OAK",
                    away_team="SD",
                    home_score=24,
                    away_score=20,
                    home_qb_id="00-0000001",
                    away_qb_id="00-0000002",
                )
            ]
        )

        with self.assertRaisesRegex(DataQualityError, "games_have_non_null_ids"):
            build_games(schedule, (2009,), QualityReport())

    def test_mismatched_pbp_and_schedule_teams_fail_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = create_fixture_sources(root)
            schedule_asset = next(asset for asset in assets if asset.asset_key == "schedules")
            schedule_path = Path(schedule_asset.url.removeprefix("file://"))
            schedules = pl.read_parquet(schedule_path).with_columns(
                pl.when(pl.col("season") == 2009)
                .then(pl.lit("BUF"))
                .otherwise(pl.col("home_team"))
                .alias("home_team"),
                pl.when(pl.col("season") == 2009)
                .then(pl.lit("CAR"))
                .otherwise(pl.col("away_team"))
                .alias("away_team"),
            )
            schedules.write_parquet(schedule_path)

            with self.assertRaisesRegex(DataQualityError, "dropbacks_match_schedule_teams"):
                run_vertical_slice(
                    PipelineConfig(
                        project_root=root,
                        cache_dir=root / "cache",
                        output_dir=root / "output",
                    ),
                    assets=assets,
                )

    def test_year_over_year_deltas_are_player_level_and_strictly_lagged(self) -> None:
        rows = []
        for season, total_epa, total_cpoe in ((2009, 20.0, 900.0), (2010, 40.0, 1080.0)):
            rows.append(
                {
                    "game_id": f"{season}_01_ARI_ATL",
                    "season": season,
                    "player_id": "00-0000001",
                    "team_id": "team_ari",
                    "starter": True,
                    "dropbacks": 200,
                    "attempts": 180,
                    "completions": 120,
                    "sacks": 20,
                    "scrambles": 0,
                    "interceptions": 10,
                    "passing_touchdowns": 20,
                    "passing_first_downs": 80,
                    "explosive_completions": 30,
                    "positive_epa_dropbacks": 100,
                    "cpoe_attempts": 180,
                    "wpa_plays": 200,
                    "air_yards_attempts": 180,
                    "total_cpoe": total_cpoe,
                    "total_qb_epa": total_epa,
                    "total_wpa": 2.0,
                    "total_air_yards": 1440.0,
                }
            )
        rows.append(
            {
                "game_id": "2010_01_ATL_ARI",
                "season": 2010,
                "player_id": "00-0000002",
                "team_id": "team_atl",
                "starter": False,
                "dropbacks": 1,
                "attempts": 1,
                "completions": 0,
                "sacks": 0,
                "scrambles": 0,
                "interceptions": 0,
                "passing_touchdowns": 0,
                "passing_first_downs": 0,
                "explosive_completions": 0,
                "positive_epa_dropbacks": 0,
                "cpoe_attempts": 0,
                "wpa_plays": 1,
                "air_yards_attempts": 0,
                "total_cpoe": None,
                "total_qb_epa": 0.0,
                "total_wpa": 0.0,
                "total_air_yards": None,
            }
        )
        seasons = build_qb_seasons(pl.DataFrame(rows), QualityReport())
        current = seasons.filter(
            (pl.col("season") == 2010) & (pl.col("player_id") == "00-0000001")
        ).row(0, named=True)
        self.assertEqual(current["prior_season"], 2009)
        self.assertTrue(current["prior_qualifies_default"])
        self.assertAlmostEqual(current["epa_per_dropback_change"], 0.1)
        self.assertAlmostEqual(current["cpoe_change"], 1.0)
        self.assertEqual(current["dropbacks_change"], 0)
        missing_air = seasons.filter(pl.col("player_id") == "00-0000002").row(0, named=True)
        self.assertIsNone(missing_air["air_yards_per_attempt"])
        self.assertEqual(missing_air["air_yards_coverage_rate"], 0.0)

    def test_players_allow_sources_without_optional_external_ids(self) -> None:
        player_source = pl.DataFrame(
            [
                _row(
                    PLAYER_REQUIRED_COLUMNS,
                    gsis_id="00-0000001",
                    display_name="Fixture QB",
                    birth_date="1985-01-01",
                    position="QB",
                    college_name="Example University",
                )
            ]
        )
        rosters = pl.DataFrame(
            [
                _row(
                    ROSTER_REQUIRED_COLUMNS,
                    season=2009,
                    team="ARI",
                    position="QB",
                    full_name="Fixture QB",
                    birth_date="1985-01-01",
                    college="Example University",
                    gsis_id="00-0000001",
                )
            ]
        )
        resolved = pl.DataFrame({"player_id": ["00-0000001"], "player_name": ["Fixture QB"]})
        players, external_ids, conflicts = build_players(
            player_source, rosters, resolved, QualityReport()
        )
        self.assertEqual(players.height, 1)
        self.assertEqual(external_ids.height, 0)
        self.assertEqual(conflicts.height, 0)


if __name__ == "__main__":
    unittest.main()

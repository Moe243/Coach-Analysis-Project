from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import polars as pl
import pytest

from nfl_coaching_impact.enhancements import (
    EnhancementConfig,
    build_coaching_completeness,
    build_inherited_environment_features,
    build_qb_supplemental_statistics,
    build_team_season_statistics,
    run_enhancement_pipeline,
)

ROOT = Path(__file__).resolve().parents[1]


def _qb_seasons() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "player_id": "00-0000001",
                "team_id": "team_buf",
                "season": 2010,
                "scope": "analysis",
                "games": 2,
                "starts": 1,
                "dropbacks": 40,
                "attempts": 35,
                "completions": 21,
                "sacks": 5,
                "interceptions": 2,
                "epa_per_dropback": 0.1,
                "cpoe": 1.2,
                "success_rate": 0.5,
                "sack_rate": 0.1,
                "touchdown_rate": 0.05,
                "interception_rate": 2 / 35,
                "qualifies_default": False,
            },
            {
                "player_id": "00-0000001",
                "team_id": "team_jax",
                "season": 2010,
                "scope": "analysis",
                "games": 1,
                "starts": 1,
                "dropbacks": 20,
                "attempts": 18,
                "completions": 12,
                "sacks": 2,
                "interceptions": 0,
                "epa_per_dropback": 0.2,
                "cpoe": 2.0,
                "success_rate": 0.55,
                "sack_rate": 0.1,
                "touchdown_rate": 0.1,
                "interception_rate": 0.0,
                "qualifies_default": False,
            },
        ]
    )


def test_supplemental_stats_preserve_multi_team_grain_and_reconcile() -> None:
    qb_games = pl.DataFrame(
        [
            {
                "game_id": "g1",
                "player_id": "00-0000001",
                "team_id": "team_buf",
                "season": 2010,
                "starter": True,
            },
            {
                "game_id": "g2",
                "player_id": "00-0000001",
                "team_id": "team_jax",
                "season": 2010,
                "starter": True,
            },
        ]
    )
    games = pl.DataFrame(
        [
            {
                "game_id": "g1",
                "season": 2010,
                "game_type": "REG",
                "home_team_id": "team_buf",
                "away_team_id": "team_mia",
                "home_score": 24,
                "away_score": 17,
            },
            {
                "game_id": "g2",
                "season": 2010,
                "game_type": "REG",
                "home_team_id": "team_jax",
                "away_team_id": "team_ten",
                "home_score": 10,
                "away_score": 20,
            },
        ]
    )
    stats = pl.DataFrame(
        [
            {
                "source_season": 2010,
                "canonical_player_id": "00-0000001",
                "canonical_team_id": team,
                "season_type": "REG",
                "passing_yards": passing,
                "passing_tds": passing_tds,
                "rushing_yards": rushing,
                "rushing_tds": rushing_tds,
                "fumbles_total": fumbles,
                "fumbles_lost_total": 1,
                "sack_yards_lost": 10,
            }
            for team, passing, passing_tds, rushing, rushing_tds, fumbles in (
                ("team_buf", 300, 2, 20, 1, 2),
                ("team_jax", 150, 1, 30, 0, 1),
            )
        ]
    )
    result = build_qb_supplemental_statistics(_qb_seasons(), qb_games, games, stats)
    assert result.height == 2
    assert result.select("player_id", "team_id", "season").n_unique() == 2
    buffalo = result.filter(pl.col("team_id") == "team_buf").row(0, named=True)
    jacksonville = result.filter(pl.col("team_id") == "team_jax").row(0, named=True)
    assert buffalo["starter_wins"] == 1 and buffalo["starter_losses"] == 0
    assert jacksonville["starter_losses"] == 1
    assert buffalo["total_yards"] == 320
    assert buffalo["total_touchdowns"] == 3
    assert buffalo["completion_percentage"] == 0.6
    assert buffalo["yards_per_attempt"] == pytest.approx(300 / 35)
    assert buffalo["adjusted_net_yards_per_attempt"] == pytest.approx(
        (300 - 10 + 20 * 2 - 45 * 2) / (35 + 5)
    )
    assert buffalo["fumbles_lost"] == 1
    assert buffalo["team_points_scored"] == 24
    assert jacksonville["team_points_scored"] == 10


def test_supplemental_missing_box_score_data_remains_null() -> None:
    stats = pl.DataFrame(
        schema={
            "source_season": pl.Int64,
            "canonical_player_id": pl.String,
            "canonical_team_id": pl.String,
            "season_type": pl.String,
            "passing_yards": pl.Int64,
            "passing_tds": pl.Int64,
            "rushing_yards": pl.Int64,
            "rushing_tds": pl.Int64,
            "fumbles_total": pl.Int64,
            "fumbles_lost_total": pl.Int64,
            "sack_yards_lost": pl.Int64,
        }
    )
    games = pl.DataFrame(
        schema={
            "game_id": pl.String,
            "season": pl.Int64,
            "game_type": pl.String,
            "home_team_id": pl.String,
            "away_team_id": pl.String,
            "home_score": pl.Int64,
            "away_score": pl.Int64,
        }
    )
    qb_games = pl.DataFrame(
        schema={
            "game_id": pl.String,
            "player_id": pl.String,
            "team_id": pl.String,
            "season": pl.Int64,
            "starter": pl.Boolean,
        }
    )
    result = build_qb_supplemental_statistics(_qb_seasons(), qb_games, games, stats)
    assert result["passing_yards"].null_count() == 2
    assert result["total_yards"].null_count() == 2
    assert result["team_points_scored"].null_count() == 2
    assert result["starter_decisions"].to_list() == [0, 0]


def test_coaching_completeness_keeps_missing_and_manual_review_distinct() -> None:
    assignments = [
        {
            "assignment_key": "2010-ARI-head_coach-01-17-a",
            "season": "2010",
            "team_id": "ARI",
            "role": "head_coach",
            "coach_id": "coach-a",
            "start_week": "1",
            "end_week": "17",
            "interval_basis": "observed_game_weeks",
            "verification_status": "verified",
            "confidence_level": "high",
            "is_interim": "false",
            "is_shared": "false",
        }
    ]
    citations = [{"assignment_key": assignments[0]["assignment_key"]}]
    reviews = [
        {
            "review_id": "r1",
            "season": "2010",
            "team_id": "ARI",
            "role": "play_caller",
            "status": "open",
            "issue_type": "explicit_play_caller_evidence_required",
        }
    ]
    result = build_coaching_completeness(assignments, citations, reviews)
    head = result.filter(
        (pl.col("season") == 2010) & (pl.col("team_id") == "ARI") & (pl.col("role") == "head_coach")
    ).row(0, named=True)
    caller = result.filter(
        (pl.col("season") == 2010)
        & (pl.col("team_id") == "ARI")
        & (pl.col("role") == "play_caller")
    ).row(0, named=True)
    assert head["assignment_status"] == "verified"
    assert head["review_status"] == "complete"
    assert json.loads(head["intervals_json"])[0]["coach_id"] == "coach-a"
    assert caller["assignment_status"] == "missing"
    assert caller["review_status"] == "manual_review"
    assert caller["review_issue_types"] == "explicit_play_caller_evidence_required"


def test_inherited_environment_uses_only_target_minus_one_inputs() -> None:
    protection = pl.DataFrame(
        [
            {
                "season": 2009,
                "team_id": "team_ari",
                "prior_protection_dropbacks": 500,
                "prior_pressure_events": 100,
                "prior_pressure_rate": 0.2,
                "prior_protection_score": 0.5,
            }
        ]
    )
    defense = pl.DataFrame(
        [
            {
                "season": 2009,
                "team_id": "team_atl",
                "prior_pass_defense_strength": 0.75,
            }
        ]
    )
    opening = pl.DataFrame(
        [
            {
                "season": 2010,
                "team_id": "team_ari",
                "player_id": "wr-1",
                "position_group": "WR",
            },
            {
                "season": 2010,
                "team_id": "team_ari",
                "player_id": "te-1",
                "position_group": "TE",
            },
            {
                "season": 2010,
                "team_id": "team_ari",
                "player_id": "rb-1",
                "position_group": "RB",
            },
        ]
    )
    production = pl.DataFrame(
        [
            {
                "season": 2009,
                "player_id": player,
                "position_group": position,
                "opportunities": 100,
                "shrunk_production_score": score,
            }
            for player, position, score in (
                ("wr-1", "WR", 0.4),
                ("te-1", "TE", 0.2),
                ("rb-1", "RB", 0.3),
            )
        ]
    )
    games = pl.DataFrame(
        [
            {
                "season": 2010,
                "game_type": "REG",
                "home_team_id": "team_ari",
                "away_team_id": "team_atl",
            }
        ]
    )
    teams = pl.DataFrame({"team_id": ["team_ari", "team_atl"]})
    result = build_inherited_environment_features(
        protection, defense, opening, production, games, teams, seasons=(2010,)
    )
    arizona = result.filter(pl.col("team_id") == "team_ari").row(0, named=True)
    assert arizona["feature_source_max_season"] == 2009
    assert arizona["prior_pressure_rate"] == 0.2
    assert arizona["wr_quality_score"] == 0.4
    assert arizona["te_quality_score"] == 0.2
    assert arizona["receiving_quality_score"] == pytest.approx(0.6)
    assert arizona["run_quality_score"] == 0.3
    assert arizona["sos_pass_defense_strength"] == 0.75


def test_team_statistics_reconcile_results_offense_and_competition_ranks() -> None:
    games = pl.DataFrame(
        [
            {
                "season": 2024,
                "game_type": "REG",
                "home_team_id": "team_ari",
                "away_team_id": "team_atl",
                "home_score": 24,
                "away_score": 17,
            },
            {
                "season": 2024,
                "game_type": "REG",
                "home_team_id": "team_atl",
                "away_team_id": "team_ari",
                "home_score": 20,
                "away_score": 20,
            },
        ]
    )
    pbp = pl.DataFrame(
        [
            {
                "season": 2024,
                "season_type": "REG",
                "posteam": team,
                "pass": is_pass,
                "rush": 1 - is_pass,
                "yards_gained": yards,
                "pass_touchdown": pass_td,
                "rush_touchdown": rush_td,
                "interception": interception,
                "fumble_lost": fumble,
                "fumbled_1_team": team if fumble else None,
                "fumbled_2_team": None,
                "fumble_recovery_1_team": "ARI" if fumble else None,
                "fumble_recovery_2_team": None,
                "sack": sack,
                "qb_kneel": 0,
                "qb_spike": 0,
                "epa": epa,
                "success": success,
                "qb_dropback": is_pass,
                "qb_epa": epa if is_pass else None,
            }
            for (
                team,
                is_pass,
                yards,
                pass_td,
                rush_td,
                interception,
                fumble,
                sack,
                epa,
                success,
            ) in (
                ("ARI", 1, 20.0, 1, 0, 0, 0, 0, 1.2, 1),
                ("ARI", 0, 8.0, 0, 1, 0, 0, 0, 0.4, 1),
                ("ATL", 1, -7.0, 0, 0, 0, 0, 1, -1.0, 0),
                ("ATL", 0, 3.0, 0, 0, 0, 1, 0, -0.2, 0),
                ("ARI", 1, 0.0, 0, 0, 1, 1, 0, -1.5, 0),
            )
        ]
    )
    pbp = pbp.with_columns(
        pl.when((pl.col("posteam") == "ARI") & (pl.col("interception") == 1))
        .then(pl.lit("ATL"))
        .otherwise(pl.col("fumbled_1_team"))
        .alias("fumbled_1_team")
    )
    result = build_team_season_statistics(pbp, games)
    ari = result.filter(pl.col("team_id") == "team_ari").row(0, named=True)
    atl = result.filter(pl.col("team_id") == "team_atl").row(0, named=True)
    assert (ari["team_wins"], ari["team_losses"], ari["team_ties"]) == (1, 0, 1)
    assert ari["team_win_percentage"] == 0.75
    assert ari["team_total_offensive_yards"] == 28
    assert ari["team_offensive_touchdowns"] == 2
    assert ari["team_turnovers"] == 1
    assert atl["team_turnovers"] == 1
    assert atl["team_sacks_allowed"] == 1
    assert ari["team_points_per_game_rank"] == 1


class PostReleaseEnhancementTest(unittest.TestCase):
    def test_clean_stage_one_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = run_enhancement_pipeline(
                EnhancementConfig(project_root=ROOT, output_dir=root / "first")
            )
            second = run_enhancement_pipeline(
                EnhancementConfig(project_root=ROOT, output_dir=root / "second")
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

    def test_supplemental_grain_and_reconciliation(self) -> None:
        test_supplemental_stats_preserve_multi_team_grain_and_reconcile()

    def test_missingness_is_explicit(self) -> None:
        test_supplemental_missing_box_score_data_remains_null()

    def test_coaching_completeness_statuses(self) -> None:
        test_coaching_completeness_keeps_missing_and_manual_review_distinct()

    def test_environment_timing(self) -> None:
        test_inherited_environment_uses_only_target_minus_one_inputs()

    def test_team_statistics(self) -> None:
        test_team_statistics_reconcile_results_offense_and_competition_ranks()

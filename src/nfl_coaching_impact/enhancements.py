"""Additive post-release statistics, coaching completeness, and context artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from .coaching import ROLES
from .constants import ANALYSIS_SEASONS, CANONICAL_TEAM_IDS, TEAM_ALIAS_TO_CANONICAL
from .errors import PipelineError
from .pipeline import _output_checksums, _update_latest, _validate_existing_version, _write_json
from .sources import sha256_file

ENHANCEMENT_PIPELINE_VERSION = "post-release-enhancements-v2"
SUPPLEMENTAL_METRIC_VERSION = "qb-supplemental-v2"
TEAM_METRIC_VERSION = "team-season-statistics-v1"
ENVIRONMENT_FEATURE_VERSION = "inherited-environment-v1"


@dataclass(frozen=True)
class EnhancementConfig:
    project_root: Path
    historical_dir: Path | None = None
    output_dir: Path | None = None

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "data" / "processed" / "enhancements"


@dataclass(frozen=True)
class EnhancementResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    table_counts: dict[str, int]


def _latest(root: Path) -> tuple[str, Path]:
    pointer = root / "LATEST"
    if not pointer.is_file():
        raise PipelineError(f"missing LATEST pointer: {pointer}")
    version = pointer.read_text(encoding="utf-8").strip()
    path = root / version
    _validate_existing_version(path, version)
    return version, path


def _sum_if_observed(column: str, alias: str | None = None) -> pl.Expr:
    return (
        pl.when(pl.col(column).count() > 0)
        .then(pl.col(column).sum())
        .otherwise(None)
        .alias(alias or column)
    )


def _regular_season_team_points(games: pl.DataFrame) -> pl.DataFrame:
    regular = games.filter(pl.col("game_type") == "REG")
    return (
        pl.concat(
            [
                regular.select(
                    "season",
                    pl.col("home_team_id").alias("team_id"),
                    pl.col("home_score").alias("points"),
                ),
                regular.select(
                    "season",
                    pl.col("away_team_id").alias("team_id"),
                    pl.col("away_score").alias("points"),
                ),
            ]
        )
        .group_by("team_id", "season")
        .agg(_sum_if_observed("points", "team_points_scored"))
    )


def _starter_records(qb_games: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    schedule = games.select("game_id", "home_team_id", "away_team_id", "home_score", "away_score")
    starts = qb_games.filter(pl.col("starter") == True).join(  # noqa: E712
        schedule, on="game_id", how="left", validate="m:1"
    )
    starts = starts.with_columns(
        pl.when(pl.col("team_id") == pl.col("home_team_id"))
        .then(pl.col("home_score"))
        .when(pl.col("team_id") == pl.col("away_team_id"))
        .then(pl.col("away_score"))
        .otherwise(None)
        .alias("points_for"),
        pl.when(pl.col("team_id") == pl.col("home_team_id"))
        .then(pl.col("away_score"))
        .when(pl.col("team_id") == pl.col("away_team_id"))
        .then(pl.col("home_score"))
        .otherwise(None)
        .alias("points_against"),
    )
    return starts.group_by("player_id", "team_id", "season").agg(
        (pl.col("points_for") > pl.col("points_against")).sum().alias("starter_wins"),
        (pl.col("points_for") < pl.col("points_against")).sum().alias("starter_losses"),
        (pl.col("points_for") == pl.col("points_against")).sum().alias("starter_ties"),
        pl.col("points_for").is_not_null().sum().alias("starter_decisions"),
    )


def _player_stat_totals(player_stats: pl.DataFrame) -> pl.DataFrame:
    required = {
        "source_season",
        "canonical_player_id",
        "canonical_team_id",
        "season_type",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "fumbles_total",
        "fumbles_lost_total",
        "sack_yards_lost",
    }
    missing = required - set(player_stats.columns)
    if missing:
        raise PipelineError(f"player stats lack supplemental columns: {sorted(missing)}")
    return (
        player_stats.filter(
            (pl.col("season_type") == "REG")
            & pl.col("canonical_player_id").is_not_null()
            & pl.col("canonical_team_id").is_not_null()
        )
        .group_by(
            pl.col("canonical_player_id").alias("player_id"),
            pl.col("canonical_team_id").alias("team_id"),
            pl.col("source_season").alias("season"),
        )
        .agg(
            _sum_if_observed("passing_yards"),
            _sum_if_observed("passing_tds", "passing_touchdowns_box"),
            _sum_if_observed("rushing_yards"),
            _sum_if_observed("rushing_tds", "rushing_touchdowns"),
            _sum_if_observed("fumbles_total", "fumbles"),
            _sum_if_observed("fumbles_lost_total", "fumbles_lost"),
            _sum_if_observed("sack_yards_lost"),
        )
    )


def build_qb_supplemental_statistics(
    qb_seasons: pl.DataFrame,
    qb_games: pl.DataFrame,
    games: pl.DataFrame,
    player_stats: pl.DataFrame,
) -> pl.DataFrame:
    """Build additive results and box-score facts at QB-team-season grain."""

    grain = ["player_id", "team_id", "season"]
    if qb_seasons.select(grain).n_unique() != qb_seasons.height:
        raise PipelineError("QB-season input has duplicate business keys")
    base = qb_seasons.filter(pl.col("scope") == "analysis").select(
        *grain,
        "games",
        "starts",
        "dropbacks",
        "attempts",
        "completions",
        "sacks",
        "interceptions",
        "epa_per_dropback",
        "cpoe",
        "success_rate",
        "sack_rate",
        "touchdown_rate",
        "interception_rate",
        "qualifies_default",
    )
    result = (
        base.join(_player_stat_totals(player_stats), on=grain, how="left", validate="1:1")
        .join(_starter_records(qb_games, games), on=grain, how="left", validate="1:1")
        .join(_regular_season_team_points(games), on=["team_id", "season"], how="left")
        .with_columns(
            pl.when(pl.col("attempts") > 0)
            .then(pl.col("completions") / pl.col("attempts"))
            .otherwise(None)
            .alias("completion_percentage"),
            pl.when(pl.col("attempts") > 0)
            .then(pl.col("passing_yards") / pl.col("attempts"))
            .otherwise(None)
            .alias("yards_per_attempt"),
            pl.when((pl.col("attempts") + pl.col("sacks")) > 0)
            .then(
                (
                    pl.col("passing_yards")
                    - pl.col("sack_yards_lost")
                    + 20 * pl.col("passing_touchdowns_box")
                    - 45 * pl.col("interceptions")
                )
                / (pl.col("attempts") + pl.col("sacks"))
            )
            .otherwise(None)
            .alias("adjusted_net_yards_per_attempt"),
            pl.when(
                pl.col("passing_touchdowns_box").is_not_null()
                & pl.col("rushing_touchdowns").is_not_null()
            )
            .then(pl.col("passing_touchdowns_box") + pl.col("rushing_touchdowns"))
            .otherwise(None)
            .alias("total_touchdowns"),
            pl.when(pl.col("passing_yards").is_not_null() & pl.col("rushing_yards").is_not_null())
            .then(pl.col("passing_yards") + pl.col("rushing_yards"))
            .otherwise(None)
            .alias("total_yards"),
            pl.col("starter_wins").fill_null(0),
            pl.col("starter_losses").fill_null(0),
            pl.col("starter_ties").fill_null(0),
            pl.col("starter_decisions").fill_null(0),
            pl.lit(SUPPLEMENTAL_METRIC_VERSION).alias("supplemental_metric_version"),
            pl.lit("nflverse_player_stats_weekly").alias("box_score_source"),
            pl.lit("nflverse_schedules").alias("result_source"),
        )
        .sort("season", "team_id", "player_id")
    )
    if result.select(grain).n_unique() != result.height:
        raise PipelineError("supplemental QB statistics have duplicate business keys")
    bad_record = result.filter(
        pl.col("starter_wins") + pl.col("starter_losses") + pl.col("starter_ties")
        != pl.col("starter_decisions")
    )
    if bad_record.height:
        raise PipelineError("starter record components do not reconcile")
    return result


def build_team_season_statistics(pbp: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Build schedule results and deterministic PBP offense at team-season grain."""

    regular_games = games.filter(
        (pl.col("game_type") == "REG") & pl.col("season").is_between(2010, 2025)
    )
    results = pl.concat(
        [
            regular_games.select(
                "season",
                pl.col("home_team_id").alias("team_id"),
                pl.col("home_score").alias("points_for"),
                pl.col("away_score").alias("points_against"),
            ),
            regular_games.select(
                "season",
                pl.col("away_team_id").alias("team_id"),
                pl.col("away_score").alias("points_for"),
                pl.col("home_score").alias("points_against"),
            ),
        ]
    )
    results = (
        results.group_by("season", "team_id")
        .agg(
            pl.len().alias("team_games"),
            (pl.col("points_for") > pl.col("points_against")).sum().alias("team_wins"),
            (pl.col("points_for") < pl.col("points_against")).sum().alias("team_losses"),
            (pl.col("points_for") == pl.col("points_against")).sum().alias("team_ties"),
            pl.col("points_for").sum().alias("team_points_scored"),
            pl.col("points_against").sum().alias("team_points_allowed"),
        )
        .with_columns(
            ((pl.col("team_wins") + 0.5 * pl.col("team_ties")) / pl.col("team_games")).alias(
                "team_win_percentage"
            ),
            (pl.col("team_points_scored") / pl.col("team_games")).alias("team_points_per_game"),
        )
    )

    offense = pbp.filter(
        (pl.col("season_type") == "REG")
        & pl.col("season").is_between(2010, 2025)
        & pl.col("posteam").is_not_null()
        & ((pl.col("pass") == 1) | (pl.col("rush") == 1))
    ).with_columns(
        pl.col("posteam")
        .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
        .alias("team_abbr"),
    )
    if offense.filter(pl.col("team_abbr").is_null()).height:
        raise PipelineError("team statistics contain unresolved offensive team aliases")
    offense = offense.with_columns(
        pl.concat_str([pl.lit("team_"), pl.col("team_abbr").str.to_lowercase()]).alias("team_id")
    )
    team_offense = offense.group_by("season", "team_id").agg(
        pl.when(pl.col("pass") == 1)
        .then(pl.col("yards_gained"))
        .otherwise(0)
        .sum()
        .alias("team_passing_yards"),
        pl.when(pl.col("rush") == 1)
        .then(pl.col("yards_gained"))
        .otherwise(0)
        .sum()
        .alias("team_rushing_yards"),
        (pl.col("pass_touchdown").fill_null(0) + pl.col("rush_touchdown").fill_null(0))
        .sum()
        .alias("team_offensive_touchdowns"),
        (
            pl.col("interception").fill_null(0)
            + (
                (pl.col("fumbled_1_team") == pl.col("posteam"))
                & pl.col("fumble_recovery_1_team").is_not_null()
                & (pl.col("fumble_recovery_1_team") != pl.col("posteam"))
            ).cast(pl.Int8)
            + (
                (pl.col("fumbled_2_team") == pl.col("posteam"))
                & pl.col("fumble_recovery_2_team").is_not_null()
                & (pl.col("fumble_recovery_2_team") != pl.col("posteam"))
            ).cast(pl.Int8)
        )
        .sum()
        .alias("team_turnovers"),
        pl.col("sack").fill_null(0).sum().alias("team_sacks_allowed"),
        pl.col("yards_gained").sum().alias("team_total_offensive_yards"),
    )
    analytics = (
        offense.filter(
            (pl.col("qb_kneel").fill_null(0) != 1) & (pl.col("qb_spike").fill_null(0) != 1)
        )
        .group_by("season", "team_id")
        .agg(
            pl.col("epa").mean().alias("team_offensive_epa_per_play"),
            pl.col("success").mean().alias("team_offensive_success_rate"),
            pl.when(pl.col("qb_dropback") == 1)
            .then(pl.col("qb_epa"))
            .otherwise(None)
            .mean()
            .alias("team_passing_epa_per_dropback"),
        )
    )
    result = (
        results.join(team_offense, on=["season", "team_id"], how="left", validate="1:1")
        .join(analytics, on=["season", "team_id"], how="left", validate="1:1")
        .with_columns(
            pl.col("team_points_per_game")
            .rank(method="min", descending=True)
            .over("season")
            .cast(pl.Int16)
            .alias("team_points_per_game_rank"),
            pl.col("team_offensive_epa_per_play")
            .rank(method="min", descending=True)
            .over("season")
            .cast(pl.Int16)
            .alias("team_offensive_epa_per_play_rank"),
            pl.col("team_passing_epa_per_dropback")
            .rank(method="min", descending=True)
            .over("season")
            .cast(pl.Int16)
            .alias("team_passing_epa_per_dropback_rank"),
            pl.lit(TEAM_METRIC_VERSION).alias("team_metric_version"),
        )
        .with_columns(pl.col(pl.Float64).round(12))
        .sort("season", "team_id")
    )
    if result.select("season", "team_id").n_unique() != result.height:
        raise PipelineError("team-season statistics have duplicate business keys")
    return result


def build_coaching_completeness(
    assignments: list[dict[str, str]],
    citations: list[dict[str, str]],
    reviews: list[dict[str, str]],
) -> pl.DataFrame:
    """Return one deterministic coverage row per team-season-role."""

    assignment_groups: dict[tuple[int, str, str], list[dict[str, str]]] = {}
    for row in assignments:
        assignment_groups.setdefault((int(row["season"]), row["team_id"], row["role"]), []).append(
            row
        )
    review_groups: dict[tuple[int, str, str], list[dict[str, str]]] = {}
    for row in reviews:
        if row["status"] == "open":
            review_groups.setdefault((int(row["season"]), row["team_id"], row["role"]), []).append(
                row
            )
    citation_counts: dict[str, int] = {}
    for row in citations:
        citation_counts[row["assignment_key"]] = citation_counts.get(row["assignment_key"], 0) + 1

    records: list[dict[str, Any]] = []
    for season in sorted(ANALYSIS_SEASONS):
        for team in sorted(CANONICAL_TEAM_IDS):
            for role in sorted(ROLES):
                rows = sorted(
                    assignment_groups.get((season, team, role), []),
                    key=lambda row: (
                        int(row["start_week"]),
                        int(row["end_week"]),
                        row["assignment_key"],
                    ),
                )
                queued = sorted(
                    review_groups.get((season, team, role), []), key=lambda row: row["review_id"]
                )
                statuses = {row["verification_status"] for row in rows}
                assignment_status = (
                    "missing"
                    if not rows
                    else "conflicting"
                    if "conflicting" in statuses
                    else "provisional"
                    if statuses - {"verified"}
                    else "verified"
                )
                intervals = [
                    {
                        "assignment_key": row["assignment_key"],
                        "coach_id": row["coach_id"],
                        "start_week": int(row["start_week"]),
                        "end_week": int(row["end_week"]),
                        "interval_basis": row["interval_basis"],
                        "verification_status": row["verification_status"],
                        "confidence_level": row["confidence_level"],
                        "is_interim": row["is_interim"] == "true",
                        "is_shared": row["is_shared"] == "true",
                    }
                    for row in rows
                ]
                records.append(
                    {
                        "season": season,
                        "team_id": team,
                        "role": role,
                        "assignment_status": assignment_status,
                        "review_status": "manual_review" if queued else "complete",
                        "requires_manual_review": bool(queued),
                        "assignment_count": len(rows),
                        "verified_assignment_count": sum(
                            row["verification_status"] == "verified" for row in rows
                        ),
                        "citation_count": sum(
                            citation_counts.get(row["assignment_key"], 0) for row in rows
                        ),
                        "has_in_season_change": len(rows) > 1
                        and any(int(row["start_week"]) > 1 for row in rows),
                        "has_interim": any(row["is_interim"] == "true" for row in rows),
                        "has_shared_duty": any(row["is_shared"] == "true" for row in rows),
                        "has_unclear_interval": any(
                            row["interval_basis"] == "season_designation"
                            or row["verification_status"] != "verified"
                            for row in rows
                        ),
                        "review_issue_types": "|".join(
                            sorted({row["issue_type"] for row in queued})
                        )
                        or None,
                        "intervals_json": json.dumps(intervals, sort_keys=True),
                    }
                )
    result = pl.DataFrame(records).sort("season", "team_id", "role")
    expected = len(ANALYSIS_SEASONS) * len(CANONICAL_TEAM_IDS) * len(ROLES)
    if (
        result.height != expected
        or result.select("season", "team_id", "role").n_unique() != expected
    ):
        raise PipelineError("coaching completeness matrix does not cover every team-season-role")
    unsupported_verified = result.filter(
        (pl.col("verified_assignment_count") > 0) & (pl.col("citation_count") == 0)
    )
    if unsupported_verified.height:
        raise PipelineError("coaching completeness found verified assignments without citations")
    return result


def _position_group(value: object) -> str | None:
    text = str(value or "").upper()
    if text.startswith("WR") or text == "W":
        return "WR"
    if text.startswith("TE"):
        return "TE"
    if text in {"RB", "HB", "FB"} or text.startswith("RB"):
        return "RB"
    return None


def _z_score_by_season(frame: pl.DataFrame, raw: str, output: str) -> pl.DataFrame:
    return frame.with_columns(
        pl.when(pl.col(raw).std().over("season") > 0)
        .then((pl.col(raw) - pl.col(raw).mean().over("season")) / pl.col(raw).std().over("season"))
        .otherwise(0.0)
        .alias(output)
    )


def build_pbp_environment_inputs(pbp: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build prior protection and opponent pass-defense inputs from regular-season PBP."""

    required = {
        "season",
        "season_type",
        "posteam",
        "defteam",
        "qb_dropback",
        "qb_kneel",
        "qb_spike",
        "qb_hit",
        "sack",
        "qb_epa",
        "epa",
        "success",
        "yards_gained",
        "pass",
        "rush",
        "pass_touchdown",
        "rush_touchdown",
        "interception",
        "fumble_lost",
        "fumbled_1_team",
        "fumbled_2_team",
        "fumble_recovery_1_team",
        "fumble_recovery_2_team",
    }
    missing = required - set(pbp.columns)
    if missing:
        raise PipelineError(f"PBP environment input lacks columns: {sorted(missing)}")
    eligible = pbp.filter(
        (pl.col("season_type") == "REG")
        & (pl.col("qb_dropback") == 1)
        & (pl.col("qb_kneel").fill_null(0) != 1)
        & (pl.col("qb_spike").fill_null(0) != 1)
    ).with_columns(
        pl.col("posteam")
        .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
        .alias("offense_abbr"),
        pl.col("defteam")
        .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
        .alias("defense_abbr"),
        ((pl.col("qb_hit").fill_null(0) == 1) | (pl.col("sack").fill_null(0) == 1))
        .cast(pl.Int8)
        .alias("pressure_event"),
    )
    unresolved = eligible.filter(
        pl.col("offense_abbr").is_null() | pl.col("defense_abbr").is_null()
    )
    if unresolved.height:
        raise PipelineError("PBP environment input has unresolved team aliases")
    protection = (
        eligible.group_by("season", "offense_abbr")
        .agg(
            pl.len().alias("prior_protection_dropbacks"),
            pl.col("pressure_event").sum().alias("prior_pressure_events"),
        )
        .with_columns(
            (pl.col("prior_pressure_events") / pl.col("prior_protection_dropbacks")).alias(
                "prior_pressure_rate"
            ),
            pl.concat_str([pl.lit("team_"), pl.col("offense_abbr").str.to_lowercase()]).alias(
                "team_id"
            ),
        )
    )
    protection = _z_score_by_season(
        protection.with_columns((-pl.col("prior_pressure_rate")).alias("_protection_raw")),
        "_protection_raw",
        "prior_protection_score",
    ).drop("_protection_raw", "offense_abbr")
    pass_defense = (
        eligible.filter(pl.col("qb_epa").is_finite())
        .group_by("season", "defense_abbr")
        .agg(
            pl.len().alias("prior_pass_defense_dropbacks"),
            pl.col("qb_epa").mean().alias("prior_pass_defense_epa_allowed"),
        )
        .with_columns(
            pl.concat_str([pl.lit("team_"), pl.col("defense_abbr").str.to_lowercase()]).alias(
                "team_id"
            ),
            (-pl.col("prior_pass_defense_epa_allowed")).alias("_defense_raw"),
        )
    )
    pass_defense = _z_score_by_season(
        pass_defense, "_defense_raw", "prior_pass_defense_strength"
    ).drop("_defense_raw", "defense_abbr")
    return protection, pass_defense


def build_opening_skill_players(depth_charts: pl.DataFrame) -> pl.DataFrame:
    """Select only opening-week WR/TE/RB depth-chart identities."""

    required = {
        "source_season",
        "canonical_player_id",
        "canonical_team_id",
        "week",
        "game_type",
    }
    if not required <= set(depth_charts.columns):
        return pl.DataFrame(
            schema={
                "season": pl.Int32,
                "team_id": pl.String,
                "player_id": pl.String,
                "position_group": pl.String,
            }
        )
    position = (
        pl.coalesce("position", "depth_position")
        if {"position", "depth_position"} <= set(depth_charts.columns)
        else pl.col("position")
        if "position" in depth_charts.columns
        else pl.col("depth_position")
    )
    return (
        depth_charts.filter(
            (pl.col("week") == 1)
            & (pl.col("game_type") == "REG")
            & pl.col("canonical_player_id").is_not_null()
            & pl.col("canonical_team_id").is_not_null()
        )
        .select(
            pl.col("source_season").alias("season"),
            pl.col("canonical_team_id").alias("team_id"),
            pl.col("canonical_player_id").alias("player_id"),
            position.map_elements(_position_group, return_dtype=pl.String).alias("position_group"),
        )
        .filter(pl.col("position_group").is_not_null())
        .unique()
    )


def build_skill_production(player_stats: pl.DataFrame) -> pl.DataFrame:
    """Build season-standardized, opportunity-shrunk prior skill production."""

    stats = (
        player_stats.filter(
            (pl.col("season_type") == "REG") & pl.col("canonical_player_id").is_not_null()
        )
        .with_columns(
            pl.col("position")
            .map_elements(_position_group, return_dtype=pl.String)
            .alias("position_group")
        )
        .filter(pl.col("position_group").is_in(["WR", "TE", "RB"]))
        .group_by(
            pl.col("source_season").alias("season"),
            pl.col("canonical_player_id").alias("player_id"),
            "position_group",
        )
        .agg(
            pl.col("targets").fill_null(0).sum().alias("targets"),
            pl.col("receptions").fill_null(0).sum().alias("receptions"),
            pl.col("receiving_yards").fill_null(0).sum().alias("receiving_yards"),
            pl.col("receiving_tds").fill_null(0).sum().alias("receiving_tds"),
            pl.col("carries").fill_null(0).sum().alias("carries"),
            pl.col("rushing_yards").fill_null(0).sum().alias("rushing_yards"),
            pl.col("rushing_tds").fill_null(0).sum().alias("rushing_tds"),
            pl.col("rushing_first_downs").fill_null(0).sum().alias("rushing_first_downs"),
        )
        .with_columns(
            (
                pl.col("receiving_yards") + 5 * pl.col("receptions") + 20 * pl.col("receiving_tds")
            ).alias("receiving_raw"),
            (
                pl.col("rushing_yards")
                + 20 * pl.col("rushing_tds")
                + 5 * pl.col("rushing_first_downs")
            ).alias("rushing_raw"),
        )
        .with_columns(
            pl.when(pl.col("position_group") == "RB")
            .then(pl.col("rushing_raw"))
            .otherwise(pl.col("receiving_raw"))
            .alias("production_raw"),
            pl.when(pl.col("position_group") == "RB")
            .then(pl.col("carries"))
            .otherwise(pl.col("targets"))
            .alias("opportunities"),
        )
    )
    standardized = stats.with_columns(
        pl.when(pl.col("production_raw").std().over("season", "position_group") > 0)
        .then(
            (
                pl.col("production_raw")
                - pl.col("production_raw").mean().over("season", "position_group")
            )
            / pl.col("production_raw").std().over("season", "position_group")
        )
        .otherwise(0.0)
        .alias("production_z")
    )
    return standardized.with_columns(
        (
            pl.col("production_z")
            * pl.col("opportunities")
            / (
                pl.col("opportunities")
                + pl.when(pl.col("position_group") == "RB").then(50.0).otherwise(25.0)
            )
        ).alias("shrunk_production_score")
    ).select("season", "player_id", "position_group", "opportunities", "shrunk_production_score")


def build_inherited_environment_features(
    protection: pl.DataFrame,
    pass_defense: pl.DataFrame,
    opening_players: pl.DataFrame,
    skill_production: pl.DataFrame,
    games: pl.DataFrame,
    teams: pl.DataFrame,
    seasons: tuple[int, ...] = tuple(range(2009, 2026)),
) -> pl.DataFrame:
    """Build team-season context whose latest source season is target minus one."""

    roster = opening_players.join(
        skill_production.with_columns((pl.col("season") + 1).alias("target_season")).drop("season"),
        left_on=["season", "player_id", "position_group"],
        right_on=["target_season", "player_id", "position_group"],
        how="left",
        validate="m:1",
    )
    roster_rows: list[dict[str, Any]] = []
    for key, group in roster.group_by("season", "team_id"):
        record: dict[str, Any] = {"season": int(key[0]), "team_id": str(key[1])}
        for group_name, prefix in (("WR", "wr"), ("TE", "te"), ("RB", "run")):
            subset = group.filter(pl.col("position_group") == group_name)
            observed = subset.filter(pl.col("shrunk_production_score").is_not_null())
            record[f"{prefix}_opening_players"] = subset.height
            record[f"{prefix}_prior_production_players"] = observed.height
            record[f"{prefix}_missing_prior_production_players"] = subset.height - observed.height
            record[f"{prefix}_prior_production_coverage"] = (
                observed.height / subset.height if subset.height else None
            )
            record[f"{prefix}_quality_score"] = (
                float(observed["shrunk_production_score"].sum()) if subset.height else None
            )
        record["receiving_quality_score"] = (
            record["wr_quality_score"] + record["te_quality_score"]
            if record["wr_quality_score"] is not None and record["te_quality_score"] is not None
            else None
        )
        roster_rows.append(record)
    roster_features = pl.DataFrame(roster_rows, infer_schema_length=None)

    regular = games.filter(pl.col("game_type") == "REG")
    schedule = pl.concat(
        [
            regular.select(
                "season",
                pl.col("home_team_id").alias("team_id"),
                pl.col("away_team_id").alias("opponent_id"),
            ),
            regular.select(
                "season",
                pl.col("away_team_id").alias("team_id"),
                pl.col("home_team_id").alias("opponent_id"),
            ),
        ]
    )
    prior_defense = pass_defense.with_columns((pl.col("season") + 1).alias("target_season")).drop(
        "season"
    )
    schedule = schedule.join(
        prior_defense.select(
            "target_season",
            pl.col("team_id").alias("opponent_id"),
            "prior_pass_defense_strength",
        ),
        left_on=["season", "opponent_id"],
        right_on=["target_season", "opponent_id"],
        how="left",
        validate="m:1",
    )
    sos = (
        schedule.group_by("season", "team_id")
        .agg(
            pl.len().alias("sos_opponents"),
            pl.col("prior_pass_defense_strength").count().alias("sos_covered_opponents"),
            pl.col("prior_pass_defense_strength").mean().alias("sos_pass_defense_strength"),
        )
        .with_columns(
            (pl.col("sos_covered_opponents") / pl.col("sos_opponents")).alias("sos_coverage")
        )
    )
    prior_protection = protection.with_columns((pl.col("season") + 1).alias("target_season")).drop(
        "season"
    )
    grid = pl.DataFrame(
        [
            {"season": season, "team_id": team_id}
            for season in seasons
            for team_id in sorted(teams["team_id"].unique().to_list())
        ]
    )
    result = (
        grid.join(
            prior_protection,
            left_on=["season", "team_id"],
            right_on=["target_season", "team_id"],
            how="left",
            validate="1:1",
        )
        .join(roster_features, on=["season", "team_id"], how="left", validate="1:1")
        .join(sos, on=["season", "team_id"], how="left", validate="1:1")
        .with_columns(
            (pl.col("season") - 1).alias("feature_source_max_season"),
            pl.lit(ENVIRONMENT_FEATURE_VERSION).alias("feature_version"),
            pl.lit("preseason_inherited").alias("timing_label"),
        )
        # Parallel group-by reductions can otherwise differ at the final floating-point bit.
        # This is a content-addressed analytical artifact, so publish a documented stable
        # precision rather than non-reproducible machine-rounding noise.
        .with_columns(pl.col(pl.Float64).round(9))
        .sort("season", "team_id")
    )
    if result.filter(pl.col("feature_source_max_season") >= pl.col("season")).height:
        raise PipelineError("target or future season leaked into inherited environment features")
    return result


def _manual_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _identity(project_root: Path, historical_version: str) -> tuple[str, dict[str, str]]:
    inputs = [
        project_root / "data" / "manual" / name
        for name in (
            "coaching_assignments.csv",
            "coach_assignment_sources.csv",
            "coaching_review_queue.csv",
        )
    ]
    source_hashes = {
        path.relative_to(project_root).as_posix(): sha256_file(path) for path in inputs
    }
    source_hashes["src/nfl_coaching_impact/enhancements.py"] = sha256_file(Path(__file__))
    payload = {
        "pipeline_version": ENHANCEMENT_PIPELINE_VERSION,
        "supplemental_metric_version": SUPPLEMENTAL_METRIC_VERSION,
        "environment_feature_version": ENVIRONMENT_FEATURE_VERSION,
        "team_metric_version": TEAM_METRIC_VERSION,
        "historical_version": historical_version,
        "inputs": source_hashes,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"enh-{digest}", source_hashes


def _read_player_stats(historical: Path) -> pl.DataFrame:
    paths = sorted((historical / "silver" / "player_stats").glob("season=*/data.parquet"))
    if not paths:
        raise PipelineError("historical build has no player-stat partitions")
    return pl.concat([pl.read_parquet(path) for path in paths], how="diagonal_relaxed")


def _read_depth_charts(historical: Path) -> pl.DataFrame:
    paths = sorted((historical / "silver" / "depth_charts").glob("season=*/data.parquet"))
    return pl.concat([pl.read_parquet(path) for path in paths], how="diagonal_relaxed")


def _read_environment_pbp(historical: Path) -> pl.DataFrame:
    columns = [
        "season",
        "season_type",
        "posteam",
        "defteam",
        "qb_dropback",
        "qb_kneel",
        "qb_spike",
        "qb_hit",
        "sack",
        "qb_epa",
        "epa",
        "success",
        "yards_gained",
        "pass",
        "rush",
        "pass_touchdown",
        "rush_touchdown",
        "interception",
        "fumble_lost",
        "fumbled_1_team",
        "fumbled_2_team",
        "fumble_recovery_1_team",
        "fumble_recovery_2_team",
    ]
    paths = [
        historical / "bronze" / "play_by_play" / f"season={season}" / "play_by_play.parquet"
        for season in range(2008, 2026)
    ]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise PipelineError(f"missing PBP environment inputs: {missing[:3]}")
    return pl.concat([pl.read_parquet(path, columns=columns) for path in paths])


def _write_completeness_report(path: Path, completeness: pl.DataFrame) -> None:
    """Write a deterministic role-level audit summary beside its artifact."""

    summary = (
        completeness.group_by("season", "role", "assignment_status", "review_status")
        .len()
        .sort("season", "role", "assignment_status", "review_status")
    )
    rows = "\n".join(
        "| {season} | {role} | {assignment_status} | {review_status} | {count} |".format(
            season=row["season"],
            role=row["role"],
            assignment_status=row["assignment_status"],
            review_status=row["review_status"],
            count=row["len"],
        )
        for row in summary.to_dicts()
    )
    focus = completeness.filter(
        pl.col("requires_manual_review") | pl.col("has_unclear_interval")
    ).height
    path.write_text(
        "# Coaching completeness report\n\n"
        "This deterministic report summarizes the source-backed manual coaching matrix. "
        "It does not infer missing assignments or promote provisional rows.\n\n"
        f"- Matrix cells: {completeness.height}\n"
        f"- Manual-review/uncertain cells: {focus}\n\n"
        "| Season | Role | Assignment status | Review status | Cells |\n"
        "| --- | --- | --- | --- | ---: |\n"
        f"{rows}\n",
        encoding="utf-8",
    )


def run_enhancement_pipeline(config: EnhancementConfig) -> EnhancementResult:
    """Build additive artifacts without mutating checkpoint outputs."""

    historical_version, historical = (
        (config.historical_dir.name, config.historical_dir)
        if config.historical_dir
        else _latest(config.project_root / "data" / "processed" / "historical")
    )
    version, source_hashes = _identity(config.project_root, historical_version)
    output_root = config.resolved_output_dir
    final_path = output_root / version
    if final_path.exists():
        counts = _validate_existing_version(final_path, version)
        _update_latest(output_root, version)
        return EnhancementResult(version, final_path, True, counts)

    silver = historical / "silver"
    player_stats = _read_player_stats(historical)
    qb_stats = (
        build_qb_supplemental_statistics(
            pl.read_parquet(silver / "qb_team_season_performance.parquet"),
            pl.read_parquet(silver / "qb_game_performance.parquet"),
            pl.read_parquet(silver / "games.parquet"),
            player_stats,
        )
        .with_columns(pl.lit(version).alias("data_version"))
        .select("data_version", pl.exclude("data_version"))
    )
    manual = config.project_root / "data" / "manual"
    completeness = (
        build_coaching_completeness(
            _manual_rows(manual / "coaching_assignments.csv"),
            _manual_rows(manual / "coach_assignment_sources.csv"),
            _manual_rows(manual / "coaching_review_queue.csv"),
        )
        .with_columns(pl.lit(version).alias("data_version"))
        .select("data_version", pl.exclude("data_version"))
    )
    review_focus = completeness.filter(
        pl.col("requires_manual_review") | pl.col("has_unclear_interval")
    )
    pbp = _read_environment_pbp(historical)
    protection, pass_defense = build_pbp_environment_inputs(pbp)
    environment = (
        build_inherited_environment_features(
            protection,
            pass_defense,
            build_opening_skill_players(_read_depth_charts(historical)),
            build_skill_production(player_stats),
            pl.read_parquet(silver / "games.parquet"),
            pl.read_parquet(silver / "teams.parquet"),
        )
        .with_columns(pl.lit(version).alias("data_version"))
        .select("data_version", pl.exclude("data_version"))
    )
    coverage = (
        pl.DataFrame(
            [
                {
                    "dataset": "next_gen_stats",
                    "first_season": 2016,
                    "role": "optional_validation_only",
                    "core_dependency": False,
                },
                {
                    "dataset": "ftn_charting",
                    "first_season": 2022,
                    "role": "optional_validation_only",
                    "core_dependency": False,
                },
            ]
        )
        .with_columns(pl.lit(version).alias("data_version"))
        .select("data_version", pl.exclude("data_version"))
    )
    team_statistics = (
        build_team_season_statistics(pbp, pl.read_parquet(silver / "games.parquet"))
        .with_columns(pl.lit(version).alias("data_version"))
        .select("data_version", pl.exclude("data_version"))
    )

    staging = output_root / ".staging" / uuid.uuid4().hex
    try:
        staging.mkdir(parents=True)
        tables = {
            "qb_supplemental_statistics": qb_stats,
            "team_season_statistics": team_statistics,
            "coaching_completeness": completeness,
            "coaching_manual_review_focus": review_focus,
            "inherited_environment_features": environment,
            "modern_validation_coverage": coverage,
        }
        for name, frame in tables.items():
            frame.write_parquet(staging / f"{name}.parquet", compression="zstd")
        _write_completeness_report(staging / "COACHING_COMPLETENESS_REPORT.md", completeness)
        counts = {name: frame.height for name, frame in tables.items()}
        manifest = {
            "data_version": version,
            "pipeline_version": ENHANCEMENT_PIPELINE_VERSION,
            "historical_data_version": historical_version,
            "supplemental_metric_version": SUPPLEMENTAL_METRIC_VERSION,
            "environment_feature_version": ENVIRONMENT_FEATURE_VERSION,
            "team_metric_version": TEAM_METRIC_VERSION,
            "source_hashes": source_hashes,
            "table_counts": counts,
            "status": "succeeded",
        }
        _write_json(staging / "RUN_MANIFEST.json", manifest)
        _write_json(staging / "OUTPUT_CHECKSUMS.json", _output_checksums(staging))
        output_root.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_path)
        _update_latest(output_root, version)
        return EnhancementResult(version, final_path, False, counts)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

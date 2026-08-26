"""Deterministic Bronze-to-Silver transforms for the checkpoint-two slice."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import polars as pl

from .constants import (
    ANALYSIS_SEASONS,
    CANONICAL_TEAM_IDS,
    DEFAULT_MIN_DROPBACKS,
    PLAYER_EXTERNAL_ID_COLUMNS,
    ROSTER_EXTERNAL_ID_COLUMNS,
    TEAM_ALIAS_TO_CANONICAL,
    WARMUP_SEASONS,
)
from .quality import QualityReport


def _canonical_abbr(column: str) -> pl.Expr:
    return pl.col(column).replace_strict(
        TEAM_ALIAS_TO_CANONICAL,
        default=None,
        return_dtype=pl.String,
    )


def _team_id(column: str) -> pl.Expr:
    return pl.concat_str([pl.lit("team_"), _canonical_abbr(column).str.to_lowercase()])


def _rate(numerator: str, denominator: str, name: str) -> pl.Expr:
    return (
        pl.when(pl.col(denominator) > 0)
        .then(pl.col(numerator) / pl.col(denominator))
        .otherwise(None)
        .alias(name)
    )


def read_seasonal_bronze(root: Path, dataset: str, seasons: Iterable[int]) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    filename = "play_by_play.parquet" if dataset == "play_by_play" else "roster.parquet"
    for season in sorted(seasons):
        frames.append(pl.read_parquet(root / dataset / f"season={season}" / filename))
    return pl.concat(frames, how="diagonal_relaxed")


def _assert_known_team_aliases(
    frame: pl.DataFrame,
    columns: Iterable[str],
    quality: QualityReport,
    check_name: str,
) -> None:
    unknown: set[str] = set()
    for column in columns:
        if column not in frame.columns:
            continue
        observed = (
            frame.select(pl.col(column).cast(pl.String).str.strip_chars().alias(column))
            .filter(pl.col(column).is_not_null() & (pl.col(column) != ""))
            .get_column(column)
            .unique()
            .to_list()
        )
        unknown.update(value for value in observed if value not in TEAM_ALIAS_TO_CANONICAL)
    quality.record(
        check_name,
        not unknown,
        failure_count=len(unknown),
        details=f"unknown aliases={sorted(unknown)}",
    )


def build_teams_and_aliases(
    team_source: pl.DataFrame,
    schedules: pl.DataFrame,
    pbp: pl.DataFrame,
    rosters: pl.DataFrame,
    quality: QualityReport,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build stable internal teams and preserve each observed upstream alias."""

    _assert_known_team_aliases(team_source, ["team_abbr"], quality, "known_team_reference_aliases")
    _assert_known_team_aliases(
        schedules, ["home_team", "away_team"], quality, "known_schedule_team_aliases"
    )
    _assert_known_team_aliases(
        pbp, ["posteam", "home_team", "away_team"], quality, "known_pbp_team_aliases"
    )
    _assert_known_team_aliases(rosters, ["team"], quality, "known_roster_team_aliases")

    reference = (
        team_source.with_columns(canonical_abbr=_canonical_abbr("team_abbr"))
        .filter(pl.col("canonical_abbr").is_not_null())
        .with_columns(preferred=(pl.col("team_abbr") == pl.col("canonical_abbr")).cast(pl.Int8))
        .sort(["canonical_abbr", "preferred", "team_abbr"], descending=[False, True, False])
        .group_by("canonical_abbr", maintain_order=True)
        .agg(
            pl.col("team_name").first().alias("team_name"),
            pl.col("team_id").first().cast(pl.String).alias("nflverse_team_id"),
        )
    )
    teams = (
        pl.DataFrame({"team_abbr": sorted(CANONICAL_TEAM_IDS)})
        .join(reference, left_on="team_abbr", right_on="canonical_abbr", how="left", validate="1:1")
        .with_columns(
            pl.concat_str([pl.lit("team_"), pl.col("team_abbr").str.to_lowercase()]).alias(
                "team_id"
            )
        )
        .select("team_id", "team_abbr", "team_name", "nflverse_team_id")
    )
    quality.record(
        "canonical_team_count",
        teams.height == 32 and teams.get_column("team_name").null_count() == 0,
        failure_count=abs(teams.height - 32) + teams.get_column("team_name").null_count(),
        details=f"expected 32 named teams, observed {teams.height}",
    )

    observed: list[pl.DataFrame] = []
    for source_system, frame, columns in (
        ("nflverse_teams", team_source, ("team_abbr",)),
        ("nflverse_schedules", schedules, ("home_team", "away_team")),
        ("nflverse_pbp", pbp, ("posteam", "home_team", "away_team")),
        ("nflverse_rosters", rosters, ("team",)),
    ):
        for column in columns:
            if "season" in frame.columns:
                alias_frame = frame.select(
                    pl.lit(source_system).alias("source_system"),
                    pl.col(column).cast(pl.String).str.strip_chars().alias("alias"),
                    pl.col("season").cast(pl.Int32),
                )
            else:
                alias_frame = frame.select(
                    pl.lit(source_system).alias("source_system"),
                    pl.col(column).cast(pl.String).str.strip_chars().alias("alias"),
                    pl.lit(None, dtype=pl.Int32).alias("season"),
                )
            observed.append(
                alias_frame.filter(pl.col("alias").is_not_null() & (pl.col("alias") != ""))
            )

    aliases = (
        pl.concat(observed)
        .unique()
        .with_columns(
            canonical_abbr=_canonical_abbr("alias"),
            team_id=_team_id("alias"),
        )
        .group_by("source_system", "alias", "canonical_abbr", "team_id")
        .agg(
            pl.col("season").min().alias("first_observed_season"),
            pl.col("season").max().alias("last_observed_season"),
        )
        .sort("source_system", "alias")
    )
    quality.record(
        "team_aliases_resolve",
        aliases.get_column("team_id").null_count() == 0,
        failure_count=aliases.get_column("team_id").null_count(),
        details="every observed alias must resolve to a canonical internal team_id",
    )
    return teams, aliases


def build_games(
    schedules: pl.DataFrame,
    seasons: Iterable[int],
    quality: QualityReport,
) -> pl.DataFrame:
    seasons_set = sorted(set(seasons))
    games = (
        schedules.filter(pl.col("season").is_in(seasons_set))
        .with_columns(
            home_team_id=_team_id("home_team"),
            away_team_id=_team_id("away_team"),
            game_date=pl.col("gameday").cast(pl.String).str.to_date(strict=False),
            scope=pl.when(pl.col("season").is_in(sorted(WARMUP_SEASONS)))
            .then(pl.lit("warmup"))
            .otherwise(pl.lit("analysis")),
        )
        .select(
            "game_id",
            pl.col("season").cast(pl.Int32),
            pl.col("week").cast(pl.Int16),
            pl.col("game_type"),
            "game_date",
            "home_team_id",
            "away_team_id",
            pl.col("home_score").cast(pl.Int16, strict=False),
            pl.col("away_score").cast(pl.Int16, strict=False),
            "home_qb_id",
            "away_qb_id",
            "scope",
        )
        .sort("season", "week", "game_id")
    )
    missing_game_ids = games.get_column("game_id").null_count()
    quality.record(
        "games_have_non_null_ids",
        missing_game_ids == 0,
        failure_count=missing_game_ids,
        details="game_id must be non-null in the selected slice",
    )
    duplicates = games.select(pl.struct("game_id").is_duplicated().sum()).item()
    quality.record(
        "unique_games",
        duplicates == 0,
        failure_count=duplicates,
        details="game_id must be unique in the selected slice",
    )
    missing_teams = games.select(
        (pl.col("home_team_id").is_null() | pl.col("away_team_id").is_null()).sum()
    ).item()
    quality.record(
        "games_have_canonical_teams",
        missing_teams == 0,
        failure_count=missing_teams,
        details="every selected game must resolve both teams",
    )
    return games


def validate_season_pbp_play_keys(
    pbp: pl.DataFrame,
    season: int,
    quality: QualityReport,
) -> None:
    """Reject missing or duplicate source play keys before any football filtering."""

    null_game_ids = pbp.get_column("game_id").null_count()
    null_play_ids = pbp.get_column("play_id").null_count()
    null_key_rows = pbp.filter(pl.col("game_id").is_null() | pl.col("play_id").is_null())
    duplicate_keys = (
        pbp.filter(pl.col("game_id").is_not_null() & pl.col("play_id").is_not_null())
        .group_by("game_id", "play_id")
        .len(name="key_row_count")
        .filter(pl.col("key_row_count") > 1)
        .with_columns((pl.col("key_row_count") - 1).alias("duplicate_excess_rows"))
        .sort("game_id", "play_id")
    )
    duplicate_excess_rows = duplicate_keys.get_column("duplicate_excess_rows").sum() or 0
    null_samples = (
        null_key_rows.select("game_id", "play_id")
        .sort("game_id", "play_id", nulls_last=True)
        .head(5)
        .to_dicts()
    )
    duplicate_samples = (
        duplicate_keys.select("game_id", "play_id", "key_row_count").head(5).to_dicts()
    )
    failure_count = null_key_rows.height + duplicate_excess_rows
    quality.record(
        "season_pbp_play_keys_are_non_null_and_unique",
        failure_count == 0,
        failure_count=failure_count,
        details=(
            f"season={season}; null_game_id_rows={null_game_ids}; "
            f"null_play_id_rows={null_play_ids}; duplicate_excess_rows={duplicate_excess_rows}; "
            f"null_key_samples={json.dumps(null_samples, sort_keys=True)}; "
            f"duplicate_key_samples={json.dumps(duplicate_samples, sort_keys=True)}"
        ),
    )


def resolve_eligible_dropbacks(
    pbp: pl.DataFrame,
    games: pl.DataFrame,
    quality: QualityReport,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply the authoritative filter and resolve QB IDs without name matching."""

    eligible = (
        pbp.filter(
            (pl.col("season_type") == "REG")
            & (pl.col("qb_dropback") == 1)
            & (pl.col("qb_kneel").fill_null(0) != 1)
            & (pl.col("qb_spike").fill_null(0) != 1)
        )
        .with_columns(
            primary_qb_id=pl.coalesce("passer_player_id", "passer_id"),
            scramble_qb_id=pl.when(pl.col("qb_scramble").fill_null(0) == 1)
            .then(pl.col("rusher_player_id"))
            .otherwise(None),
            team_id=_team_id("posteam"),
            pbp_home_team_id=_team_id("home_team"),
            pbp_away_team_id=_team_id("away_team"),
        )
        .with_columns(
            id_conflict=(
                pl.col("passer_player_id").is_not_null()
                & pl.col("passer_id").is_not_null()
                & (pl.col("passer_player_id") != pl.col("passer_id"))
            )
            | (
                pl.col("scramble_qb_id").is_not_null()
                & pl.col("primary_qb_id").is_not_null()
                & (pl.col("scramble_qb_id") != pl.col("primary_qb_id"))
            ),
            candidate_qb_id=pl.coalesce("scramble_qb_id", "primary_qb_id"),
        )
        .with_columns(
            resolution_status=pl.when(pl.col("id_conflict"))
            .then(pl.lit("conflicting_ids"))
            .when(pl.col("qb_epa").is_null() | ~pl.col("qb_epa").is_finite().fill_null(False))
            .then(pl.lit("invalid_qb_epa"))
            .when(pl.col("candidate_qb_id").is_null())
            .then(pl.lit("missing_id"))
            .when(~pl.col("candidate_qb_id").str.contains(r"^00-\d{7}$"))
            .then(pl.lit("invalid_gsis_id"))
            .otherwise(pl.lit("resolved")),
        )
        .with_columns(
            player_id=pl.when(pl.col("resolution_status") == "resolved")
            .then(pl.col("candidate_qb_id"))
            .otherwise(None),
            player_name=pl.when(pl.col("qb_scramble").fill_null(0) == 1)
            .then(pl.coalesce("rusher_player_name", "passer_player_name"))
            .otherwise(pl.col("passer_player_name")),
        )
    )

    invalid_flags = (
        pbp.filter(pl.col("qb_dropback").is_not_null())
        .select((~pl.col("qb_dropback").is_in([0.0, 1.0])).sum())
        .item()
    )
    quality.record(
        "binary_qb_dropback",
        invalid_flags == 0,
        failure_count=invalid_flags,
        details="non-null qb_dropback values must be 0 or 1",
    )
    invalid_epa = eligible.select(
        (pl.col("qb_epa").is_null() | ~pl.col("qb_epa").is_finite()).sum()
    ).item()
    quality.warn(
        "eligible_dropbacks_with_invalid_qb_epa",
        invalid_epa,
        "plays without finite qb_epa are quarantined and excluded from QB metrics",
    )
    invalid_teams = eligible.select(
        (
            pl.col("team_id").is_null()
            | ~(
                (pl.col("team_id") == pl.col("pbp_home_team_id"))
                | (pl.col("team_id") == pl.col("pbp_away_team_id"))
            )
        ).sum()
    ).item()
    quality.record(
        "eligible_dropbacks_have_valid_possession_team",
        invalid_teams == 0,
        failure_count=invalid_teams,
        details="posteam must resolve to home or away team",
    )

    game_lookup = games.select(
        "game_id",
        pl.col("season").alias("schedule_season"),
        "game_date",
        "home_team_id",
        "away_team_id",
        "home_qb_id",
        "away_qb_id",
    )
    eligible = eligible.join(game_lookup, on="game_id", how="left", validate="m:1")
    missing_games = eligible.get_column("schedule_season").null_count()
    mismatched_seasons = eligible.filter(
        pl.col("schedule_season").is_not_null() & (pl.col("season") != pl.col("schedule_season"))
    ).height
    quality.record(
        "dropbacks_match_schedule_games",
        missing_games == 0 and mismatched_seasons == 0,
        failure_count=missing_games + mismatched_seasons,
        details="each eligible play must match one same-season schedule game",
    )
    missing_team = "__missing_team__"
    mismatched_teams = eligible.filter(
        pl.col("schedule_season").is_not_null()
        & (
            (
                pl.col("pbp_home_team_id").fill_null(missing_team)
                != pl.col("home_team_id").fill_null(missing_team)
            )
            | (
                pl.col("pbp_away_team_id").fill_null(missing_team)
                != pl.col("away_team_id").fill_null(missing_team)
            )
        )
    ).height
    quality.record(
        "dropbacks_match_schedule_teams",
        mismatched_teams == 0,
        failure_count=mismatched_teams,
        details="each eligible play's normalized home and away teams must match its schedule game",
    )

    unresolved = (
        eligible.filter(pl.col("resolution_status") != "resolved")
        .select(
            pl.col("game_id"),
            pl.col("play_id"),
            pl.col("season").cast(pl.Int32),
            pl.col("week").cast(pl.Int16),
            "team_id",
            "resolution_status",
            "passer_player_id",
            "passer_id",
            "rusher_player_id",
            "passer_player_name",
            "rusher_player_name",
        )
        .sort("season", "game_id", "play_id")
    )
    quality.warn(
        "unresolved_eligible_dropbacks",
        unresolved.height,
        "unresolved plays are excluded from QB metrics and retained in Silver",
    )

    resolved = eligible.filter(pl.col("resolution_status") == "resolved")
    invalid_resolved_epa = resolved.select(
        (pl.col("qb_epa").is_null() | ~pl.col("qb_epa").is_finite().fill_null(False)).sum()
    ).item()
    quality.record(
        "resolved_dropbacks_have_finite_qb_epa",
        invalid_resolved_epa == 0,
        failure_count=invalid_resolved_epa,
        details="every play entering QB metrics must have finite qb_epa",
    )
    return resolved, unresolved


def build_qb_game_performance(resolved: pl.DataFrame, quality: QualityReport) -> pl.DataFrame:
    plays = resolved.with_columns(
        opponent_team_id=pl.when(pl.col("team_id") == pl.col("home_team_id"))
        .then(pl.col("away_team_id"))
        .otherwise(pl.col("home_team_id")),
        is_attempt=(pl.col("pass_attempt").fill_null(0) == 1).cast(pl.Int32),
        is_completion=(pl.col("complete_pass").fill_null(0) == 1).cast(pl.Int32),
        is_sack=(pl.col("sack").fill_null(0) == 1).cast(pl.Int32),
        is_scramble=(pl.col("qb_scramble").fill_null(0) == 1).cast(pl.Int32),
        is_interception=(pl.col("interception").fill_null(0) == 1).cast(pl.Int32),
        is_pass_td=(pl.col("pass_touchdown").fill_null(0) == 1).cast(pl.Int32),
        is_first_down=(pl.col("first_down_pass").fill_null(0) == 1).cast(pl.Int32),
        is_explosive=(
            (pl.col("complete_pass").fill_null(0) == 1)
            & (pl.col("yards_gained").fill_null(float("-inf")) >= 20)
        ).cast(pl.Int32),
        is_success=(pl.col("qb_epa") > 0).cast(pl.Int32),
        cpoe_value=pl.when(
            (pl.col("pass_attempt").fill_null(0) == 1) & pl.col("cpoe").is_not_null()
        ).then(pl.col("cpoe")),
        air_yards_value=pl.when(pl.col("pass_attempt").fill_null(0) == 1).then(pl.col("air_yards")),
    )
    missing_air_yards = plays.filter(
        (pl.col("is_attempt") == 1) & pl.col("air_yards_value").is_null()
    ).height
    quality.warn(
        "pass_attempts_missing_air_yards",
        missing_air_yards,
        "missing values are not imputed; coverage columns expose partial air-yards data",
    )
    qb_games = (
        plays.group_by(
            "game_id",
            "season",
            "week",
            "game_date",
            "player_id",
            "team_id",
            "opponent_team_id",
        )
        .agg(
            pl.len().cast(pl.Int32).alias("dropbacks"),
            pl.col("is_attempt").sum().cast(pl.Int32).alias("attempts"),
            pl.col("is_completion").sum().cast(pl.Int32).alias("completions"),
            pl.col("is_sack").sum().cast(pl.Int32).alias("sacks"),
            pl.col("is_scramble").sum().cast(pl.Int32).alias("scrambles"),
            pl.col("is_interception").sum().cast(pl.Int32).alias("interceptions"),
            pl.col("is_pass_td").sum().cast(pl.Int32).alias("passing_touchdowns"),
            pl.col("is_first_down").sum().cast(pl.Int32).alias("passing_first_downs"),
            pl.col("is_explosive").sum().cast(pl.Int32).alias("explosive_completions"),
            pl.col("is_success").sum().cast(pl.Int32).alias("positive_epa_dropbacks"),
            pl.col("cpoe_value").count().cast(pl.Int32).alias("cpoe_attempts"),
            pl.col("cpoe_value").sum().alias("total_cpoe"),
            pl.col("qb_epa").sum().alias("total_qb_epa"),
            pl.col("wpa").drop_nulls().sum().alias("total_wpa"),
            pl.col("wpa").count().cast(pl.Int32).alias("wpa_plays"),
            pl.col("air_yards_value").count().cast(pl.Int32).alias("air_yards_attempts"),
            pl.when(pl.col("air_yards_value").count() > 0)
            .then(pl.col("air_yards_value").sum())
            .alias("total_air_yards"),
            pl.col("home_qb_id").first().alias("home_qb_id"),
            pl.col("away_qb_id").first().alias("away_qb_id"),
            pl.col("home_team_id").first().alias("home_team_id"),
        )
        .with_columns(
            starter=pl.when(pl.col("team_id") == pl.col("home_team_id"))
            .then(pl.col("player_id") == pl.col("home_qb_id"))
            .otherwise(pl.col("player_id") == pl.col("away_qb_id")),
        )
        .with_columns(
            _rate("total_qb_epa", "dropbacks", "epa_per_dropback"),
            _rate("total_cpoe", "cpoe_attempts", "cpoe"),
            _rate("positive_epa_dropbacks", "dropbacks", "success_rate"),
            _rate("explosive_completions", "attempts", "explosive_pass_rate"),
            _rate("interceptions", "attempts", "interception_rate"),
            _rate("passing_touchdowns", "attempts", "touchdown_rate"),
            (
                pl.when((pl.col("attempts") + pl.col("sacks")) > 0)
                .then(pl.col("sacks") / (pl.col("attempts") + pl.col("sacks")))
                .otherwise(None)
                .alias("sack_rate")
            ),
            pl.when((pl.col("attempts") > 0) & (pl.col("air_yards_attempts") > 0))
            .then(pl.col("total_air_yards") / pl.col("attempts"))
            .otherwise(None)
            .alias("air_yards_per_attempt"),
            _rate("air_yards_attempts", "attempts", "air_yards_coverage_rate"),
            _rate("passing_first_downs", "dropbacks", "first_down_rate"),
            _rate("total_wpa", "dropbacks", "wpa_per_dropback"),
        )
        .drop("home_qb_id", "away_qb_id", "home_team_id")
        .sort("season", "week", "game_id", "team_id", "player_id")
    )
    duplicates = qb_games.select(
        pl.struct("game_id", "team_id", "player_id").is_duplicated().sum()
    ).item()
    quality.record(
        "unique_qb_team_games",
        duplicates == 0,
        failure_count=duplicates,
        details="QB game output grain is game_id/team_id/player_id",
    )
    quality.record(
        "qb_game_dropbacks_reconcile",
        qb_games.get_column("dropbacks").sum() == resolved.height,
        failure_count=abs(qb_games.get_column("dropbacks").sum() - resolved.height),
        details="aggregated QB-game dropbacks must equal resolved eligible plays",
    )
    return qb_games


def build_qb_seasons(qb_games: pl.DataFrame, quality: QualityReport) -> pl.DataFrame:
    seasons = (
        qb_games.group_by("season", "player_id", "team_id")
        .agg(
            pl.col("game_id").n_unique().cast(pl.Int16).alias("games"),
            pl.col("starter").fill_null(False).sum().cast(pl.Int16).alias("starts"),
            *[
                pl.col(column).sum().alias(column)
                for column in (
                    "dropbacks",
                    "attempts",
                    "completions",
                    "sacks",
                    "scrambles",
                    "interceptions",
                    "passing_touchdowns",
                    "passing_first_downs",
                    "explosive_completions",
                    "positive_epa_dropbacks",
                    "cpoe_attempts",
                    "wpa_plays",
                    "air_yards_attempts",
                    "total_cpoe",
                    "total_qb_epa",
                    "total_wpa",
                    "total_air_yards",
                )
            ],
        )
        .with_columns(
            pl.when(pl.col("season").is_in(sorted(WARMUP_SEASONS)))
            .then(pl.lit("warmup"))
            .otherwise(pl.lit("analysis"))
            .alias("scope")
        )
        .with_columns(
            _rate("total_qb_epa", "dropbacks", "epa_per_dropback"),
            _rate("total_cpoe", "cpoe_attempts", "cpoe"),
            _rate("positive_epa_dropbacks", "dropbacks", "success_rate"),
            _rate("explosive_completions", "attempts", "explosive_pass_rate"),
            _rate("interceptions", "attempts", "interception_rate"),
            _rate("passing_touchdowns", "attempts", "touchdown_rate"),
            (
                pl.when((pl.col("attempts") + pl.col("sacks")) > 0)
                .then(pl.col("sacks") / (pl.col("attempts") + pl.col("sacks")))
                .otherwise(None)
                .alias("sack_rate")
            ),
            pl.when((pl.col("attempts") > 0) & (pl.col("air_yards_attempts") > 0))
            .then(pl.col("total_air_yards") / pl.col("attempts"))
            .otherwise(None)
            .alias("air_yards_per_attempt"),
            _rate("air_yards_attempts", "attempts", "air_yards_coverage_rate"),
            _rate("passing_first_downs", "dropbacks", "first_down_rate"),
            _rate("total_wpa", "dropbacks", "wpa_per_dropback"),
        )
        .with_columns(
            qualifies_default=(
                pl.col("season").is_in(sorted(ANALYSIS_SEASONS))
                & (pl.col("dropbacks") >= DEFAULT_MIN_DROPBACKS)
            )
        )
        .sort("season", "team_id", "player_id")
    )

    prior = (
        seasons.group_by("player_id", "season")
        .agg(
            pl.col("starts").sum().alias("prior_starts"),
            pl.col("dropbacks").sum().alias("prior_dropbacks"),
            pl.col("attempts").sum().alias("prior_attempts"),
            pl.col("sacks").sum().alias("prior_sacks"),
            pl.col("interceptions").sum().alias("prior_interceptions"),
            pl.col("passing_touchdowns").sum().alias("prior_passing_touchdowns"),
            pl.col("passing_first_downs").sum().alias("prior_passing_first_downs"),
            pl.col("explosive_completions").sum().alias("prior_explosive_completions"),
            pl.col("positive_epa_dropbacks").sum().alias("prior_positive_epa_dropbacks"),
            pl.col("total_qb_epa").sum().alias("prior_total_qb_epa"),
            pl.col("total_cpoe").sum().alias("prior_total_cpoe"),
            pl.col("cpoe_attempts").sum().alias("prior_cpoe_attempts"),
            pl.col("total_wpa").sum().alias("prior_total_wpa"),
            pl.col("total_air_yards").sum().alias("prior_total_air_yards"),
            pl.col("air_yards_attempts").sum().alias("prior_air_yards_attempts"),
        )
        .with_columns(prior_qualifies_default=pl.col("prior_dropbacks") >= DEFAULT_MIN_DROPBACKS)
        .with_columns(
            prior_epa_per_dropback=pl.when(pl.col("prior_qualifies_default")).then(
                pl.col("prior_total_qb_epa") / pl.col("prior_dropbacks")
            ),
            prior_cpoe=pl.when(
                pl.col("prior_qualifies_default") & (pl.col("prior_cpoe_attempts") > 0)
            ).then(pl.col("prior_total_cpoe") / pl.col("prior_cpoe_attempts")),
            prior_success_rate=pl.when(pl.col("prior_qualifies_default")).then(
                pl.col("prior_positive_epa_dropbacks") / pl.col("prior_dropbacks")
            ),
            prior_explosive_pass_rate=pl.when(
                pl.col("prior_qualifies_default") & (pl.col("prior_attempts") > 0)
            ).then(pl.col("prior_explosive_completions") / pl.col("prior_attempts")),
            prior_interception_rate=pl.when(
                pl.col("prior_qualifies_default") & (pl.col("prior_attempts") > 0)
            ).then(pl.col("prior_interceptions") / pl.col("prior_attempts")),
            prior_touchdown_rate=pl.when(
                pl.col("prior_qualifies_default") & (pl.col("prior_attempts") > 0)
            ).then(pl.col("prior_passing_touchdowns") / pl.col("prior_attempts")),
            prior_sack_rate=pl.when(
                pl.col("prior_qualifies_default")
                & ((pl.col("prior_attempts") + pl.col("prior_sacks")) > 0)
            ).then(pl.col("prior_sacks") / (pl.col("prior_attempts") + pl.col("prior_sacks"))),
            prior_air_yards_per_attempt=pl.when(
                pl.col("prior_qualifies_default")
                & (pl.col("prior_attempts") > 0)
                & (pl.col("prior_air_yards_attempts") > 0)
            ).then(pl.col("prior_total_air_yards") / pl.col("prior_attempts")),
            prior_air_yards_coverage_rate=pl.when(
                pl.col("prior_qualifies_default") & (pl.col("prior_attempts") > 0)
            ).then(pl.col("prior_air_yards_attempts") / pl.col("prior_attempts")),
            prior_first_down_rate=pl.when(pl.col("prior_qualifies_default")).then(
                pl.col("prior_passing_first_downs") / pl.col("prior_dropbacks")
            ),
            prior_wpa_per_dropback=pl.when(pl.col("prior_qualifies_default")).then(
                pl.col("prior_total_wpa") / pl.col("prior_dropbacks")
            ),
        )
        .select(
            "player_id",
            (pl.col("season") + 1).alias("season"),
            pl.col("season").alias("prior_season"),
            "prior_starts",
            "prior_dropbacks",
            "prior_qualifies_default",
            "prior_epa_per_dropback",
            "prior_cpoe",
            "prior_success_rate",
            "prior_explosive_pass_rate",
            "prior_interception_rate",
            "prior_touchdown_rate",
            "prior_sack_rate",
            "prior_air_yards_per_attempt",
            "prior_air_yards_coverage_rate",
            "prior_first_down_rate",
            "prior_wpa_per_dropback",
        )
    )
    seasons = seasons.join(
        prior, on=["player_id", "season"], how="left", validate="m:1"
    ).with_columns(
        prior_season_available=pl.col("prior_season").is_not_null(),
        starts_change=pl.col("starts") - pl.col("prior_starts"),
        dropbacks_change=pl.col("dropbacks") - pl.col("prior_dropbacks"),
        epa_per_dropback_change=pl.col("epa_per_dropback") - pl.col("prior_epa_per_dropback"),
        cpoe_change=pl.col("cpoe") - pl.col("prior_cpoe"),
        success_rate_change=pl.col("success_rate") - pl.col("prior_success_rate"),
        explosive_pass_rate_change=pl.col("explosive_pass_rate")
        - pl.col("prior_explosive_pass_rate"),
        interception_rate_change=pl.col("interception_rate") - pl.col("prior_interception_rate"),
        touchdown_rate_change=pl.col("touchdown_rate") - pl.col("prior_touchdown_rate"),
        sack_rate_change=pl.col("sack_rate") - pl.col("prior_sack_rate"),
        air_yards_per_attempt_change=pl.col("air_yards_per_attempt")
        - pl.col("prior_air_yards_per_attempt"),
        air_yards_coverage_rate_change=pl.col("air_yards_coverage_rate")
        - pl.col("prior_air_yards_coverage_rate"),
        first_down_rate_change=pl.col("first_down_rate") - pl.col("prior_first_down_rate"),
        wpa_per_dropback_change=pl.col("wpa_per_dropback") - pl.col("prior_wpa_per_dropback"),
    )
    leakage = seasons.filter(
        pl.col("prior_season").is_not_null() & (pl.col("prior_season") >= pl.col("season"))
    ).height
    quality.record(
        "prior_features_are_strictly_lagged",
        leakage == 0,
        failure_count=leakage,
        details="prior features must come from season-1 only",
    )
    duplicates = seasons.select(
        pl.struct("season", "team_id", "player_id").is_duplicated().sum()
    ).item()
    quality.record(
        "unique_qb_team_seasons",
        duplicates == 0,
        failure_count=duplicates,
        details="QB season output grain is season/team_id/player_id",
    )
    return seasons


def build_players(
    player_source: pl.DataFrame,
    rosters: pl.DataFrame,
    resolved: pl.DataFrame,
    quality: QualityReport,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build GSIS-anchored people and long-form external identifiers."""

    rosters = rosters.with_columns(
        gsis_id=pl.when(pl.col("gsis_id").cast(pl.String).str.strip_chars() != "")
        .then(pl.col("gsis_id").cast(pl.String).str.strip_chars())
        .otherwise(None)
    )
    player_source = player_source.with_columns(
        gsis_id=pl.when(pl.col("gsis_id").cast(pl.String).str.strip_chars() != "")
        .then(pl.col("gsis_id").cast(pl.String).str.strip_chars())
        .otherwise(None)
    )
    relevant = (
        pl.concat(
            [
                rosters.select(pl.col("gsis_id").alias("player_id")),
                resolved.select("player_id"),
            ]
        )
        .drop_nulls()
        .unique()
    )
    master = player_source.rename({"gsis_id": "player_id"})
    roster_fallback = (
        rosters.filter(pl.col("gsis_id").is_not_null())
        .sort("season", descending=True)
        .group_by("gsis_id")
        .agg(
            pl.col("full_name").drop_nulls().first().alias("roster_name"),
            pl.col("birth_date").drop_nulls().first().alias("roster_birth_date"),
            pl.col("position").drop_nulls().first().alias("roster_position"),
            pl.col("college").drop_nulls().first().alias("roster_college"),
        )
        .rename({"gsis_id": "player_id"})
    )
    pbp_fallback = (
        resolved.select("player_id", "player_name")
        .drop_nulls("player_id")
        .group_by("player_id")
        .agg(pl.col("player_name").drop_nulls().first().alias("pbp_name"))
    )
    players = (
        relevant.join(master, on="player_id", how="left", validate="1:1")
        .join(roster_fallback, on="player_id", how="left", validate="1:1")
        .join(pbp_fallback, on="player_id", how="left", validate="1:1")
        .select(
            "player_id",
            pl.coalesce("display_name", "roster_name", "pbp_name").alias("display_name"),
            pl.coalesce("birth_date", "roster_birth_date")
            .cast(pl.String)
            .str.to_date(strict=False)
            .alias("birth_date"),
            pl.coalesce("position", "roster_position").alias("position"),
            pl.coalesce("college_name", "roster_college").alias("college"),
        )
        .sort("player_id")
    )
    quality.record(
        "players_have_valid_gsis_ids",
        players.filter(~pl.col("player_id").str.contains(r"^00-\d{7}$")).height == 0,
        failure_count=players.filter(~pl.col("player_id").str.contains(r"^00-\d{7}$")).height,
        details="player_id is always a GSIS identifier",
    )
    missing_names = players.get_column("display_name").null_count()
    quality.warn(
        "players_missing_display_name",
        missing_names,
        "names remain nullable when no ID-anchored source value exists",
    )

    external_frames: list[pl.DataFrame] = []
    for column in PLAYER_EXTERNAL_ID_COLUMNS:
        if column in master.columns:
            external_frames.append(
                master.select(
                    "player_id",
                    pl.lit(f"nflverse_players.{column}").alias("external_system"),
                    pl.col(column).cast(pl.String).str.strip_chars().alias("external_id"),
                )
                .drop_nulls(["player_id", "external_id"])
                .filter(pl.col("external_id") != "")
            )
    for column in ROSTER_EXTERNAL_ID_COLUMNS:
        if column in rosters.columns:
            external_frames.append(
                rosters.select(
                    pl.col("gsis_id").alias("player_id"),
                    pl.lit(f"nflverse_rosters.{column}").alias("external_system"),
                    pl.col(column).cast(pl.String).str.strip_chars().alias("external_id"),
                )
                .drop_nulls(["player_id", "external_id"])
                .filter(pl.col("external_id") != "")
            )
    if external_frames:
        external_ids = (
            pl.concat(external_frames, how="diagonal_relaxed")
            .join(players.select("player_id"), on="player_id", how="semi")
            .unique()
            .sort("player_id", "external_system", "external_id")
        )
    else:
        external_ids = pl.DataFrame(
            schema={
                "player_id": pl.String,
                "external_system": pl.String,
                "external_id": pl.String,
            }
        )
    conflicting_external_ids = (
        external_ids.group_by("external_system", "external_id")
        .agg(
            pl.col("player_id").n_unique().alias("distinct_player_count"),
            pl.col("player_id").unique().sort().alias("player_ids"),
        )
        .filter(pl.col("distinct_player_count") > 1)
        .sort("external_system", "external_id")
    )
    quality.warn(
        "ambiguous_external_ids_excluded",
        conflicting_external_ids.height,
        "upstream system/ID pairs mapped to multiple GSIS players and were excluded",
    )
    external_ids = external_ids.join(
        conflicting_external_ids.select("external_system", "external_id"),
        on=["external_system", "external_id"],
        how="anti",
    )
    return players, external_ids, conflicting_external_ids

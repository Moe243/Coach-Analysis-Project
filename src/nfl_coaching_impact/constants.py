"""Versioned data contracts shared by the ingestion checkpoints."""

from __future__ import annotations

from typing import Final

PIPELINE_VERSION: Final = "checkpoint-2.5"
HISTORICAL_PIPELINE_VERSION: Final = "checkpoint-3.3"
METRIC_VERSION: Final = "qb-dropback-v1"
VERTICAL_SLICE_SEASONS: Final[tuple[int, ...]] = (2009, 2010, 2016, 2022, 2025)
HISTORICAL_SEASONS: Final[tuple[int, ...]] = tuple(range(1999, 2026))
WARMUP_SEASONS: Final[frozenset[int]] = frozenset(range(1999, 2010))
ANALYSIS_SEASONS: Final[frozenset[int]] = frozenset(range(2010, 2026))
DEFAULT_MIN_DROPBACKS: Final = 200


# Canonical franchise identifiers use current nflverse abbreviations. Historical
# source values remain available in the Silver alias table and untouched Bronze files.
TEAM_ALIAS_TO_CANONICAL: Final[dict[str, str]] = {
    "ARI": "ARI",
    "ARZ": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BLT": "BAL",
    "BUF": "BUF",
    "CAR": "CAR",
    "CHI": "CHI",
    "CIN": "CIN",
    "CLE": "CLE",
    "CLV": "CLE",
    "DAL": "DAL",
    "DEN": "DEN",
    "DET": "DET",
    "GB": "GB",
    "HOU": "HOU",
    "HST": "HOU",
    "IND": "IND",
    "JAC": "JAX",
    "JAX": "JAX",
    "KC": "KC",
    "LA": "LA",
    "LAR": "LA",
    "SL": "LA",
    "STL": "LA",
    "LAC": "LAC",
    "SD": "LAC",
    "LV": "LV",
    "OAK": "LV",
    "MIA": "MIA",
    "MIN": "MIN",
    "NE": "NE",
    "NO": "NO",
    "NYG": "NYG",
    "NYJ": "NYJ",
    "PHI": "PHI",
    "PIT": "PIT",
    "SEA": "SEA",
    "SF": "SF",
    "TB": "TB",
    "TEN": "TEN",
    "WAS": "WAS",
    "WSH": "WAS",
}

CANONICAL_TEAM_IDS: Final[frozenset[str]] = frozenset(TEAM_ALIAS_TO_CANONICAL.values())


PBP_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "play_id",
        "game_id",
        "season",
        "season_type",
        "week",
        "posteam",
        "home_team",
        "away_team",
        "qb_dropback",
        "qb_kneel",
        "qb_spike",
        "qb_scramble",
        "pass_attempt",
        "complete_pass",
        "sack",
        "interception",
        "pass_touchdown",
        "first_down_pass",
        "yards_gained",
        "air_yards",
        "qb_epa",
        "wpa",
        "cpoe",
        "passer_player_id",
        "passer_player_name",
        "rusher_player_id",
        "rusher_player_name",
        "passer_id",
    }
)

ROSTER_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "season",
        "team",
        "position",
        "full_name",
        "birth_date",
        "college",
        "gsis_id",
    }
)

SCHEDULE_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "game_id",
        "season",
        "game_type",
        "week",
        "gameday",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "home_qb_id",
        "away_qb_id",
    }
)

PLAYER_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "gsis_id",
        "display_name",
        "birth_date",
        "position",
        "college_name",
    }
)

TEAM_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset({"team_abbr", "team_name", "team_id"})

PLAYER_STATS_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset({"season", "player_id"})
INJURY_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset({"season", "week", "team", "gsis_id"})
DEPTH_CHART_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset({"gsis_id"})
SNAP_COUNT_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"season", "game_id", "pfr_player_id"}
)

PLAYER_EXTERNAL_ID_COLUMNS: Final[tuple[str, ...]] = (
    "esb_id",
    "nfl_id",
    "pfr_id",
    "pff_id",
    "otc_id",
    "espn_id",
    "smart_id",
)

ROSTER_EXTERNAL_ID_COLUMNS: Final[tuple[str, ...]] = (
    "esb_id",
    "espn_id",
    "sportradar_id",
    "yahoo_id",
    "rotowire_id",
    "pff_id",
    "pfr_id",
    "fantasy_data_id",
    "sleeper_id",
    "smart_id",
)

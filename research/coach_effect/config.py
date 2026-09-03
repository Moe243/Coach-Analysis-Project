"""Versioned definitions for the exploratory Coach Effect research program."""

from __future__ import annotations

from pathlib import Path

RESEARCH_VERSION = "coach-effect-research-v1"
RESEARCH_OUTPUT_DIRECTORY = Path("research/coach_effect/outputs")

PAE_FORMULA = "actual_epa_per_dropback - expected_epa_per_dropback"
QB_DEVELOPMENT_SIGNAL_FORMULA = "actual_qb_delta_pae - expected_qb_delta_pae"
CALL_VALUE_FORMULA = "expected_chosen_epa - expected_alternative_epa"
PCAE_FORMULA = "coach_average_call_value - league_average_call_value"

PLAY_CALL_TRAIN_SEASONS = (2022, 2023, 2024)
PLAY_CALL_TEST_SEASON = 2025
PLAY_CALL_ADVANTAGE_THRESHOLDS = (0.05, 0.10, 0.20)
RANDOM_SEED = 20260902

# Checkpoint Eleven keeps the Checkpoint Ten equations fixed while making the
# historical eligibility and temporal-training contracts explicit.
HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION = "pcae-play-eligibility-v2"
HISTORICAL_PCAE_MODEL_VERSION = "pcae-expanding-prior-seasons-v1"
HISTORICAL_PCAE_ANALYSIS_SEASONS = tuple(range(2010, 2026))
HISTORICAL_PCAE_WARMUP_SEASONS = tuple(range(1999, 2010))

PLAY_CALL_FEATURES = (
    "down",
    "ydstogo",
    "yardline_100",
    "game_seconds_remaining",
    "score_differential",
    "posteam_timeouts_remaining",
    "defteam_timeouts_remaining",
    "shotgun",
    "no_huddle",
)

ENVIRONMENT_FEATURES = (
    "prior_team_epa",
    "expected_qb_epa",
    "supporting_cast",
    "opponent_strength",
)

# These names are deliberately symbolic. Checkpoint Ten does not estimate or assign weights.
CONCEPTUAL_COMPONENTS = (
    "unique_qb_development_signal",
    "unique_play_calling_signal",
    "shared_coaching_signal",
)
CONCEPTUAL_WEIGHT_NAMES = ("w_Q", "w_P", "w_S")

PRODUCTION_BLOCKER = (
    "Production Coach Effect implementation is blocked until offensive coordinator, "
    "quarterbacks coach, and play-caller assignments are comprehensively verified. "
    "Play-caller assignments require explicit evidence and weekly or in-season intervals "
    "where applicable."
)

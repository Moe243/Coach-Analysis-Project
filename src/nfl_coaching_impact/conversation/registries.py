"""Declared feature semantics and player/scheme compatibility mappings."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .enums import FeatureCategory

EVIDENCE_REDUCER_VERSION = "ask-v2-evidence-v1"


@dataclass(frozen=True, slots=True)
class PlayerFeatureDefinition:
    category: FeatureCategory
    unit: str


@dataclass(frozen=True, slots=True)
class FeatureCompatibility:
    player_feature: str
    scheme_feature: str
    semantic_label: str
    comparison_unit: str
    higher_higher_is_similar_usage: bool
    reducer_version: str = EVIDENCE_REDUCER_VERSION


_USAGE = FeatureCategory.USAGE
_EFFICIENCY = FeatureCategory.EFFICIENCY
_CONDITIONAL = FeatureCategory.CONTEXTUAL_EFFICIENCY
_STATE = FeatureCategory.STATE
_UNCERTAINTY = FeatureCategory.UNCERTAINTY
_DESCRIPTIVE = FeatureCategory.DESCRIPTIVE_PERFORMANCE

PLAYER_FEATURE_DEFINITIONS = MappingProxyType(
    {
        "career_observed_epa_per_db": PlayerFeatureDefinition(_STATE, "epa_per_dropback"),
        "career_stability_epa_per_db": PlayerFeatureDefinition(_UNCERTAINTY, "epa_per_dropback"),
        "career_trend_epa_per_season": PlayerFeatureDefinition(
            _STATE, "epa_per_dropback_per_season"
        ),
        "preseason_ability_estimate_epa_per_db": PlayerFeatureDefinition(
            _STATE, "epa_per_dropback"
        ),
        "recent_average_air_yards": PlayerFeatureDefinition(_USAGE, "yards_per_attempt"),
        "recent_cpoe": PlayerFeatureDefinition(_EFFICIENCY, "percentage_points"),
        "recent_early_down_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_dropback"),
        "recent_epa_per_dropback": PlayerFeatureDefinition(_EFFICIENCY, "epa_per_dropback"),
        "recent_observed_pae": PlayerFeatureDefinition(_STATE, "epa_per_dropback"),
        "recent_pass_location_left_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_attempt"),
        "recent_pass_location_left_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_pass_location_middle_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_attempt"),
        "recent_pass_location_middle_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_pass_location_right_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_attempt"),
        "recent_pass_location_right_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_red_zone_epa": PlayerFeatureDefinition(_DESCRIPTIVE, "epa_per_dropback"),
        "recent_rushing_tds_per_dropback": PlayerFeatureDefinition(_DESCRIPTIVE, "rate"),
        "recent_rushing_yards_per_dropback": PlayerFeatureDefinition(
            _DESCRIPTIVE, "yards_per_dropback"
        ),
        "recent_sack_rate": PlayerFeatureDefinition(_EFFICIENCY, "rate"),
        "recent_scramble_epa": PlayerFeatureDefinition(_DESCRIPTIVE, "epa_per_scramble"),
        "recent_scramble_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_shotgun_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_dropback"),
        "recent_shotgun_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_success_rate": PlayerFeatureDefinition(_EFFICIENCY, "rate"),
        "recent_target_depth_deep_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_attempt"),
        "recent_target_depth_deep_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_target_depth_intermediate_epa": PlayerFeatureDefinition(
            _CONDITIONAL, "epa_per_attempt"
        ),
        "recent_target_depth_intermediate_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_target_depth_short_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_attempt"),
        "recent_target_depth_short_rate": PlayerFeatureDefinition(_USAGE, "rate"),
        "recent_third_down_epa": PlayerFeatureDefinition(_CONDITIONAL, "epa_per_dropback"),
    }
)

SCHEME_FEATURE_UNITS = MappingProxyType(
    {
        "average_air_yards": "yards_per_attempt",
        "early_down_pass_rate": "rate",
        "expected_pass_rate": "rate",
        "neutral_pass_rate": "rate",
        "no_huddle_rate": "rate",
        "pass_rate": "rate",
        "proe": "rate_difference",
        "scramble_rate": "rate",
        "shotgun_rate": "rate",
        "target_depth_deep_rate": "rate",
        "target_depth_intermediate_rate": "rate",
        "target_depth_short_rate": "rate",
    }
)

FEATURE_COMPATIBILITY = (
    FeatureCompatibility(
        "recent_scramble_rate",
        "scramble_rate",
        "QB scramble usage",
        "rate",
        True,
    ),
    FeatureCompatibility(
        "recent_shotgun_rate",
        "shotgun_rate",
        "shotgun usage",
        "rate",
        True,
    ),
    FeatureCompatibility(
        "recent_average_air_yards",
        "average_air_yards",
        "average target depth",
        "yards_per_attempt",
        True,
    ),
    FeatureCompatibility(
        "recent_target_depth_short_rate",
        "target_depth_short_rate",
        "short-target usage",
        "rate",
        True,
    ),
    FeatureCompatibility(
        "recent_target_depth_intermediate_rate",
        "target_depth_intermediate_rate",
        "intermediate-target usage",
        "rate",
        True,
    ),
    FeatureCompatibility(
        "recent_target_depth_deep_rate",
        "target_depth_deep_rate",
        "deep-target usage",
        "rate",
        True,
    ),
)

FEATURE_COMPATIBILITY_BY_PLAYER = MappingProxyType(
    {definition.player_feature: definition for definition in FEATURE_COMPATIBILITY}
)

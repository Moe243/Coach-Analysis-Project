"""Checkpoint 13 leakage-safe predictive feature and scheme foundation.

The module deliberately publishes deterministic files rather than serving tables.  It converts
the frozen Checkpoint 12 descriptive scheme research into prior-season feature records, rebuilds
expected-pass/PROE with an expanding-history contract, and exposes chronology-enforcing accessors
for later checkpoints.  It does not fit or publish a quarterback prediction model.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final, Literal

import polars as pl

from .constants import TEAM_ALIAS_TO_CANONICAL

CHECKPOINT_13_SPECIFICATION: Final = "checkpoint-13-predictive-foundation-v1"
FEATURE_DEFINITION_VERSION: Final = "predictive-feature-contract-v1"
FEATURE_BUILD_VERSION: Final = "asof-scheme-v1"
EXPECTED_PASS_MODEL_VERSION: Final = "context-beta-trailing-five-v1"
AS_OF_MONTH_DAY: Final = (8, 31)
ANALYSIS_SEASONS: Final = tuple(range(2010, 2026))
TARGET_SEASONS: Final = tuple(range(2011, 2027))
REFERENCE_WINDOW_SEASONS: Final = 5
EXPECTED_PASS_PRIOR_STRENGTH: Final = 50.0
MIN_EXPECTED_PASS_CONTEXT_PLAYS: Final = 1

TimingClass = Literal["HISTORICAL_PRIOR", "PRESEASON_KNOWN", "TARGET_SEASON_FORBIDDEN"]
FeatureStatus = Literal[
    "PREDICTIVE_CORE",
    "PREDICTIVE_CONDITIONAL",
    "DESCRIPTIVE",
    "EXPERIMENTAL",
    "UNAVAILABLE",
]
PredictivePermission = Literal["YES", "NO", "CONDITIONAL"]

TIMING_CLASSES: Final = {
    "HISTORICAL_PRIOR",
    "PRESEASON_KNOWN",
    "TARGET_SEASON_FORBIDDEN",
}
FEATURE_STATUSES: Final = {
    "PREDICTIVE_CORE",
    "PREDICTIVE_CONDITIONAL",
    "DESCRIPTIVE",
    "EXPERIMENTAL",
    "UNAVAILABLE",
}
PREDICTIVE_PERMISSIONS: Final = {"YES", "NO", "CONDITIONAL"}
SUPPORTED_ENTITY_TYPES: Final = {
    "QB",
    "team",
    "team-season",
    "coach",
    "coach-team-season",
    "QB-team-season",
    "scheme-team-season",
}
MISSINGNESS_REASONS: Final = {
    "SOURCE_NOT_AVAILABLE",
    "INSUFFICIENT_SAMPLE",
    "ROLE_NOT_VERIFIED",
    "FEATURE_NOT_SUPPORTED_THAT_SEASON",
    "ENTITY_NOT_PRESENT",
    "NOT_APPLICABLE",
}

CORE_FEATURES: Final = (
    "average_air_yards",
    "early_down_pass_rate",
    "neutral_pass_rate",
    "no_huddle_rate",
    "pass_rate",
    "scramble_rate",
    "shotgun_rate",
    "target_depth_deep_rate",
    "target_depth_intermediate_rate",
    "target_depth_short_rate",
)
PERSONNEL_FAMILY_FEATURES: Final = (
    "personnel_family_11_rate",
    "personnel_family_empty_backfield_rate",
    "personnel_family_heavy_rate",
    "personnel_family_multiple_back_rate",
    "personnel_family_multiple_te_rate",
    "personnel_family_spread_rate",
)
CONDITIONAL_FEATURES: Final = (
    "expected_pass_rate",
    "pcae_verified_play_caller",
    *PERSONNEL_FAMILY_FEATURES,
    "proe",
)
EXPERIMENTAL_FEATURES: Final = (
    "ftn_pistol_rate",
    "ftn_shotgun_rate",
    "ftn_under_center_rate",
    "motion_rate",
    "play_action_rate",
    "q_head_coach",
    "q_offensive_coordinator",
    "q_play_caller",
    "q_quarterbacks_coach",
    "rpo_rate",
    "screen_rate",
)
PERSONNEL_GROUPS: Final = (
    "00",
    "01",
    "02",
    "03",
    "04",
    "10",
    "11",
    "12",
    "13",
    "14",
    "20",
    "21",
    "22",
    "23",
    "30",
    "31",
    "32",
    "40",
    "41",
)

REQUIRED_FEATURE_RECORD_COLUMNS: Final = (
    "entity_type",
    "entity_id",
    "feature_name",
    "feature_value",
    "raw_value",
    "source_season",
    "target_season",
    "as_of_date",
    "source_available_date",
    "source_dataset",
    "source_version",
    "source_hash",
    "intermediate_artifact",
    "intermediate_hash",
    "feature_definition_version",
    "feature_build_version",
    "model_version",
    "sample_size",
    "exposure",
    "missingness_reason",
    "timing_class",
    "feature_status",
    "predictive_permission",
    "standardization_method",
    "standardization_fit_start_season",
    "standardization_fit_end_season",
    "standardization_mean",
    "standardization_std",
)


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    entity_grain: str
    family: str
    description: str
    football_interpretation: str
    source: str
    source_fields: str
    earliest_supported_season: int | None
    latest_supported_season: int | None
    timing_class: TimingClass
    minimum_sample_rule: str
    derivation: str
    status: FeatureStatus
    missing_data_behavior: str
    predictive_permission: PredictivePermission
    research_readiness: str
    definition_version: str = FEATURE_DEFINITION_VERSION


@dataclass(frozen=True)
class PredictiveMatrix:
    frame: pl.DataFrame
    feature_set_version: str
    data_version: str
    maximum_source_season: int
    target_season: int
    feature_names: tuple[str, ...]
    entity_grain: str


@dataclass(frozen=True)
class CheckpointThirteenResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    registered_features: int
    feature_records: int
    scheme_rows: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _canonical_team_expression(column: str = "posteam") -> pl.Expr:
    return pl.col(column).replace_strict(
        TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String
    )


def _description(feature: str) -> str:
    return feature.replace("_", " ").replace("pcae", "PCAE").replace("proe", "PROE")


def _registry_from_checkpoint_twelve(availability: pl.DataFrame) -> tuple[FeatureDefinition, ...]:
    definitions: list[FeatureDefinition] = []
    for row in availability.sort("feature_name").to_dicts():
        original = str(row["feature_name"])
        name = {
            "expected_pass_rate": "expected_pass_rate_descriptive_nflverse",
            "proe_mean": "proe_descriptive_nflverse",
        }.get(original, original)
        family = str(row["profile_family"])
        if name in CORE_FEATURES:
            status: FeatureStatus = "PREDICTIVE_CORE"
            permission: PredictivePermission = "YES"
        elif name in PERSONNEL_FAMILY_FEATURES:
            status = "PREDICTIVE_CONDITIONAL"
            permission = "CONDITIONAL"
        elif name in EXPERIMENTAL_FEATURES:
            status = "EXPERIMENTAL"
            permission = "NO"
        elif name == "designed_qb_run_rate":
            status = "UNAVAILABLE"
            permission = "NO"
        else:
            status = "DESCRIPTIVE"
            permission = "NO"
        timing: TimingClass = "HISTORICAL_PRIOR"
        missing_behavior = "FEATURE_NOT_SUPPORTED_THAT_SEASON outside the source window"
        if original in {"expected_pass_rate", "proe_mean"}:
            timing = "TARGET_SEASON_FORBIDDEN"
            missing_behavior = (
                "Not admitted to prediction: the frozen nflverse model fields lack an "
                "as-of training lineage"
            )
        source = str(row["source_dataset"])
        interpretation = _description(name)
        if family == "outcome":
            interpretation += "; retrospective performance, not a pure scheme tendency"
        if family == "formation":
            interpretation += "; explicit structured alignment only"
        definitions.append(
            FeatureDefinition(
                name=name,
                entity_grain="scheme-team-season",
                family=family,
                description=f"Observed team-season {_description(name)}.",
                football_interpretation=interpretation,
                source=source,
                source_fields=str(row["source_fields"]),
                earliest_supported_season=(
                    int(row["first_season"]) if row["first_season"] is not None else None
                ),
                latest_supported_season=(
                    int(row["last_season"]) if row["last_season"] is not None else None
                ),
                timing_class=timing,
                minimum_sample_rule=(
                    "valid explicit source denominator; exact observed zero remains zero"
                ),
                derivation="derived" if source != "none" else "unavailable",
                status=status,
                missing_data_behavior=missing_behavior,
                predictive_permission=permission,
                research_readiness="NOT_APPLICABLE",
            )
        )
    definitions.extend(
        [
            FeatureDefinition(
                name="expected_pass_rate",
                entity_grain="scheme-team-season",
                family="tendency",
                description=(
                    "Mean expected pass probability from a context model fitted only to the "
                    "preceding five seasons."
                ),
                football_interpretation="Situation-adjusted expected pass tendency.",
                source="nflverse_pbp",
                source_fields=("play_type|down|ydstogo|yardline_100|qtr|score_differential"),
                earliest_supported_season=2010,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="at least one eligible regular-season scrimmage play",
                derivation="model-derived",
                status="PREDICTIVE_CONDITIONAL",
                missing_data_behavior="INSUFFICIENT_SAMPLE or SOURCE_NOT_AVAILABLE",
                predictive_permission="CONDITIONAL",
                research_readiness="EXPANDING_HISTORY_VALIDATED",
            ),
            FeatureDefinition(
                name="proe",
                entity_grain="scheme-team-season",
                family="tendency",
                description="Observed pass rate minus leakage-safe expected pass rate.",
                football_interpretation="Pass tendency over expectation for the situations faced.",
                source="nflverse_pbp",
                source_fields=("play_type|down|ydstogo|yardline_100|qtr|score_differential"),
                earliest_supported_season=2010,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="at least one eligible regular-season scrimmage play",
                derivation="model-derived",
                status="PREDICTIVE_CONDITIONAL",
                missing_data_behavior="INSUFFICIENT_SAMPLE or SOURCE_NOT_AVAILABLE",
                predictive_permission="CONDITIONAL",
                research_readiness="EXPANDING_HISTORY_VALIDATED",
            ),
            FeatureDefinition(
                name="pcae_verified_play_caller",
                entity_grain="coach-team-season",
                family="coach_signal",
                description="Lagged PCAE for explicitly verified, non-shared play-caller work.",
                football_interpretation=(
                    "Research-only prior decision-value signal; not universal Coach Effect."
                ),
                source="checkpoint_12_historical_pcae",
                source_fields="pcae|verification_status|is_shared|assignment interval",
                earliest_supported_season=2010,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="verified play caller, non-shared attributed plays only",
                derivation="model-derived",
                status="PREDICTIVE_CONDITIONAL",
                missing_data_behavior="ROLE_NOT_VERIFIED or INSUFFICIENT_SAMPLE",
                predictive_permission="CONDITIONAL",
                research_readiness="RESEARCH_READY",
            ),
            FeatureDefinition(
                name="preseason_verified_assignment_indicator",
                entity_grain="coach-team-season",
                family="coach_context",
                description=(
                    "Reserved indicator for an assignment captured by a dated preseason snapshot."
                ),
                football_interpretation="Known coaching continuity entering the target season.",
                source="future_dated_preseason_assignment_snapshot",
                source_fields="coach_id|team_id|season|role|source_available_date",
                earliest_supported_season=None,
                latest_supported_season=None,
                timing_class="PRESEASON_KNOWN",
                minimum_sample_rule="explicit source date on or before the preseason cutoff",
                derivation="unavailable",
                status="UNAVAILABLE",
                missing_data_behavior="SOURCE_NOT_AVAILABLE until dated snapshots exist",
                predictive_permission="NO",
                research_readiness="AWAITING_DATED_PRESEASON_SNAPSHOTS",
            ),
        ]
    )
    for role in ("head_coach", "offensive_coordinator", "quarterbacks_coach", "play_caller"):
        definitions.append(
            FeatureDefinition(
                name=f"q_{role}",
                entity_grain="coach-team-season",
                family="coach_signal",
                description=f"Lagged exploratory Q signal for {role.replace('_', ' ')}.",
                football_interpretation="Role-specific exploratory development association.",
                source="checkpoint_12_final_research",
                source_fields="role-specific Q evidence",
                earliest_supported_season=2010,
                latest_supported_season=2025,
                timing_class="HISTORICAL_PRIOR",
                minimum_sample_rule="role-specific verified exposure and prior observed Q",
                derivation="model-derived",
                status="EXPERIMENTAL",
                missing_data_behavior="ROLE_NOT_VERIFIED or INSUFFICIENT_SAMPLE",
                predictive_permission="NO",
                research_readiness="EXPLORATORY_ONLY",
            )
        )
    result = tuple(sorted(definitions, key=lambda item: item.name))
    validate_feature_registry(result)
    return result


def feature_registry_frame(registry: Sequence[FeatureDefinition]) -> pl.DataFrame:
    return pl.DataFrame([asdict(item) for item in registry]).sort("name", "definition_version")


def validate_feature_registry(registry: Sequence[FeatureDefinition]) -> None:
    if not registry:
        raise ValueError("feature registry is empty")
    keys = [(item.name, item.definition_version) for item in registry]
    if len(keys) != len(set(keys)):
        raise ValueError("feature registry contains duplicate feature/version keys")
    for item in registry:
        if item.entity_grain not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"unsupported entity grain for {item.name}: {item.entity_grain}")
        if item.timing_class not in TIMING_CLASSES:
            raise ValueError(f"invalid timing class for {item.name}")
        if item.status not in FEATURE_STATUSES:
            raise ValueError(f"invalid status for {item.name}")
        if item.predictive_permission not in PREDICTIVE_PERMISSIONS:
            raise ValueError(f"missing predictive permission for {item.name}")
        if not all(
            (
                item.description.strip(),
                item.football_interpretation.strip(),
                item.source.strip(),
                item.minimum_sample_rule.strip(),
                item.missing_data_behavior.strip(),
            )
        ):
            raise ValueError(f"incomplete registry entry for {item.name}")
        if (
            item.earliest_supported_season is not None
            and item.latest_supported_season is not None
            and item.earliest_supported_season > item.latest_supported_season
        ):
            raise ValueError(f"invalid source window for {item.name}")
        if item.status == "UNAVAILABLE" and item.predictive_permission != "NO":
            raise ValueError(f"unavailable feature cannot be predictive: {item.name}")


def _record_registry_lookup(registry: Sequence[FeatureDefinition]) -> dict[str, FeatureDefinition]:
    return {item.name: item for item in registry}


def validate_feature_records(
    records: pl.DataFrame,
    registry: Sequence[FeatureDefinition],
    *,
    predictive_only: bool = True,
) -> None:
    """Reject unregistered, ambiguous, future, forbidden, or weak-lineage feature records."""

    missing_columns = sorted(set(REQUIRED_FEATURE_RECORD_COLUMNS) - set(records.columns))
    if missing_columns:
        raise ValueError(f"feature records missing columns: {missing_columns}")
    lookup = _record_registry_lookup(registry)
    unknown = sorted(set(records["feature_name"].drop_nulls().to_list()) - set(lookup))
    if unknown:
        raise ValueError(f"unregistered features requested or materialized: {unknown}")
    if (
        records.select(
            "entity_type", "entity_id", "feature_name", "target_season", "feature_build_version"
        ).n_unique()
        != records.height
    ):
        raise ValueError("duplicate feature-record grain")
    if records.filter(~pl.col("entity_type").is_in(sorted(SUPPORTED_ENTITY_TYPES))).height:
        raise ValueError("feature records contain unsupported entity types")
    for row in records.to_dicts():
        definition = lookup[str(row["feature_name"])]
        if row["entity_type"] != definition.entity_grain:
            raise ValueError(f"entity grain mismatch for {definition.name}")
        if row["timing_class"] != definition.timing_class:
            raise ValueError(f"timing class mismatch for {definition.name}")
        if row["feature_status"] != definition.status:
            raise ValueError(f"feature status mismatch for {definition.name}")
        if row["predictive_permission"] != definition.predictive_permission:
            raise ValueError(f"predictive permission mismatch for {definition.name}")
        if predictive_only and definition.predictive_permission == "NO":
            raise ValueError(f"feature is not admitted to predictive snapshots: {definition.name}")
        source_season = int(row["source_season"])
        target_season = int(row["target_season"])
        if (
            definition.earliest_supported_season is not None
            and source_season < definition.earliest_supported_season
        ) or (
            definition.latest_supported_season is not None
            and source_season > definition.latest_supported_season
        ):
            raise ValueError(
                f"source season {source_season} is outside the registered window for "
                f"{definition.name}"
            )
        if definition.timing_class == "HISTORICAL_PRIOR" and source_season >= target_season:
            raise ValueError(
                f"leakage: {definition.name} source_season={source_season} "
                f"is not before target_season={target_season}"
            )
        if definition.timing_class == "PRESEASON_KNOWN":
            if source_season > target_season:
                raise ValueError(f"future source season for {definition.name}")
            if str(row["source_available_date"]) > str(row["as_of_date"]):
                raise ValueError(f"post-cutoff source date for {definition.name}")
        if definition.timing_class == "TARGET_SEASON_FORBIDDEN" and predictive_only:
            raise ValueError(f"target-season-forbidden feature: {definition.name}")
        fit_end = row["standardization_fit_end_season"]
        if fit_end is not None and int(fit_end) >= target_season:
            raise ValueError(
                f"leakage: {definition.name} standardization fit ends in {fit_end} "
                f"for target season {target_season}"
            )
        if not row["source_dataset"] or not row["source_version"] or not row["source_hash"]:
            raise ValueError(f"incomplete raw lineage for {definition.name}")
        if not row["intermediate_artifact"] or not row["intermediate_hash"]:
            raise ValueError(f"incomplete intermediate lineage for {definition.name}")
        missingness = row["missingness_reason"]
        if missingness is not None and missingness not in MISSINGNESS_REASONS:
            raise ValueError(f"invalid missingness reason for {definition.name}: {missingness}")
        if row["feature_value"] is None and missingness is None:
            raise ValueError(f"null feature lacks missingness reason: {definition.name}")


class HistoricalStandardizer:
    """Fit-only-on-history standardizer used by the as-of build and future checkpoints."""

    def __init__(self) -> None:
        self.mean_: float | None = None
        self.std_: float | None = None
        self.fit_start_season_: int | None = None
        self.fit_end_season_: int | None = None

    def fit(self, frame: pl.DataFrame, *, target_season: int) -> HistoricalStandardizer:
        illegal = frame.filter(pl.col("season") >= target_season)
        if illegal.height:
            raise ValueError(
                f"standardizer leakage: {illegal.height} rows are not before {target_season}"
            )
        finite = frame.filter(pl.col("raw_value").is_not_null() & pl.col("raw_value").is_finite())
        if finite.is_empty():
            raise ValueError("cannot fit standardizer without finite historical values")
        self.mean_ = float(finite["raw_value"].mean())
        self.std_ = float(finite["raw_value"].std(ddof=0) or 0.0)
        self.fit_start_season_ = int(finite["season"].min())
        self.fit_end_season_ = int(finite["season"].max())
        return self

    def transform(self, frame: pl.DataFrame) -> pl.DataFrame:
        if self.mean_ is None or self.std_ is None:
            raise ValueError("standardizer must be fit before transform")
        expression = (
            (pl.col("raw_value") - self.mean_) / self.std_
            if self.std_ > 0
            else pl.lit(None, dtype=pl.Float64)
        )
        return frame.with_columns(expression.alias("standardized_value"))


class AsOfFeatureStore:
    """Chronology-enforcing access to a versioned Checkpoint 13 feature record set."""

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.manifest = json.loads((output_path / "MANIFEST.json").read_text(encoding="utf-8"))
        registry_frame = pl.read_csv(output_path / "feature_registry.csv")
        self.registry = {row["name"]: row for row in registry_frame.to_dicts()}
        self.records = pl.read_csv(output_path / "predictive_feature_records.csv")

    def _validate_request(
        self,
        *,
        feature_names: Sequence[str],
        entity_grain: str,
        allow_conditional: bool,
    ) -> None:
        unknown = sorted(set(feature_names) - set(self.registry))
        if unknown:
            raise ValueError(f"unregistered features requested: {unknown}")
        for name in feature_names:
            definition = self.registry[name]
            if definition["entity_grain"] != entity_grain:
                raise ValueError(f"{name} is not registered at {entity_grain}")
            permission = definition["predictive_permission"]
            if permission == "NO" or (permission == "CONDITIONAL" and not allow_conditional):
                raise ValueError(f"feature is not enabled for this request: {name}")

    def target_matrix(
        self,
        *,
        target_season: int,
        feature_names: Sequence[str],
        entity_grain: str = "scheme-team-season",
        allow_conditional: bool = False,
    ) -> PredictiveMatrix:
        self._validate_request(
            feature_names=feature_names,
            entity_grain=entity_grain,
            allow_conditional=allow_conditional,
        )
        selected = self.records.filter(
            (pl.col("target_season") == target_season)
            & pl.col("feature_name").is_in(list(feature_names))
            & (pl.col("entity_type") == entity_grain)
        )
        if selected.is_empty():
            raise ValueError(f"no feature records for target season {target_season}")
        max_source = int(selected["source_season"].max())
        historical_leakage = selected.filter(
            (pl.col("timing_class") == "HISTORICAL_PRIOR")
            & (pl.col("source_season") >= target_season)
        )
        preseason_leakage = selected.filter(
            (pl.col("timing_class") == "PRESEASON_KNOWN")
            & (
                (pl.col("source_season") > target_season)
                | (pl.col("source_available_date") > pl.col("as_of_date"))
            )
        )
        if historical_leakage.height or preseason_leakage.height:
            raise ValueError("target feature request violated its registered as-of boundary")
        wide = selected.select("entity_id", "feature_name", "feature_value").pivot(
            on="feature_name", index="entity_id", values="feature_value"
        )
        for name in feature_names:
            if name not in wide.columns:
                wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(name))
        wide = wide.select("entity_id", *feature_names).sort("entity_id")
        return PredictiveMatrix(
            frame=wide,
            feature_set_version=str(self.manifest["feature_set_version"]),
            data_version=str(self.manifest["data_version"]),
            maximum_source_season=max_source,
            target_season=target_season,
            feature_names=tuple(feature_names),
            entity_grain=entity_grain,
        )

    def training_matrices(
        self,
        *,
        target_season: int,
        feature_names: Sequence[str],
        entity_grain: str = "scheme-team-season",
        allow_conditional: bool = False,
    ) -> tuple[PredictiveMatrix, ...]:
        seasons = sorted(
            self.records.filter(
                (pl.col("target_season") < target_season)
                & (pl.col("entity_type") == entity_grain)
                & pl.col("feature_name").is_in(list(feature_names))
            )["target_season"]
            .unique()
            .to_list()
        )
        return tuple(
            self.target_matrix(
                target_season=int(season),
                feature_names=feature_names,
                entity_grain=entity_grain,
                allow_conditional=allow_conditional,
            )
            for season in seasons
        )


def _expected_pass_context(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        pl.col("down").fill_null(-1).cast(pl.Int16).alias("context_down"),
        pl.when(pl.col("ydstogo").is_null())
        .then(pl.lit("missing"))
        .when(pl.col("ydstogo") <= 2)
        .then(pl.lit("01_02"))
        .when(pl.col("ydstogo") <= 5)
        .then(pl.lit("03_05"))
        .when(pl.col("ydstogo") <= 10)
        .then(pl.lit("06_10"))
        .otherwise(pl.lit("11_plus"))
        .alias("context_distance"),
        pl.when(pl.col("yardline_100").is_null())
        .then(pl.lit(-1))
        .otherwise((pl.col("yardline_100").clip(0, 99) // 20).cast(pl.Int16))
        .alias("context_field_bin"),
        pl.col("qtr").fill_null(-1).clip(-1, 5).cast(pl.Int16).alias("context_quarter"),
        pl.when(pl.col("score_differential").is_null())
        .then(pl.lit("missing"))
        .when(pl.col("score_differential") < -8)
        .then(pl.lit("trailing"))
        .when(pl.col("score_differential") > 8)
        .then(pl.lit("leading"))
        .otherwise(pl.lit("close"))
        .alias("context_score"),
        (pl.col("play_type") == "pass").cast(pl.Int8).alias("is_pass"),
    )


def build_expected_pass_profiles(
    pbp: pl.DataFrame,
    *,
    source_hashes: dict[int, str],
    source_version: str,
) -> pl.DataFrame:
    """Build expected pass and PROE without target/future seasons in model training."""

    required = {
        "season",
        "season_type",
        "posteam",
        "play_type",
        "two_point_attempt",
        "qb_kneel",
        "down",
        "qtr",
        "ydstogo",
        "yardline_100",
        "score_differential",
    }
    missing = sorted(required - set(pbp.columns))
    if missing:
        raise ValueError(f"expected-pass source missing fields: {missing}")
    eligible = _expected_pass_context(
        pbp.filter(
            (pl.col("season_type") == "REG")
            & pl.col("play_type").is_in(["pass", "run"])
            & (pl.col("two_point_attempt").fill_null(0) != 1)
            & (pl.col("qb_kneel").fill_null(0) != 1)
            & pl.col("posteam").is_not_null()
        ).with_columns(_canonical_team_expression().alias("team_id"))
    ).filter(pl.col("team_id").is_not_null())
    keys = [
        "context_down",
        "context_distance",
        "context_field_bin",
        "context_quarter",
        "context_score",
    ]
    rows: list[pl.DataFrame] = []
    for season in ANALYSIS_SEASONS:
        fit_start = max(int(eligible["season"].min()), season - REFERENCE_WINDOW_SEASONS)
        training = eligible.filter(pl.col("season").is_between(fit_start, season - 1))
        target = eligible.filter(pl.col("season") == season)
        if training.is_empty() or target.is_empty():
            continue
        if int(training["season"].max()) >= season:
            raise ValueError(f"expected-pass leakage for season {season}")
        global_rate = float(training["is_pass"].mean())
        context = training.group_by(keys).agg(
            pl.len().alias("context_plays"), pl.col("is_pass").sum().alias("context_passes")
        )
        scored = target.join(context, on=keys, how="left", validate="m:1").with_columns(
            pl.when(pl.col("context_plays").fill_null(0) >= MIN_EXPECTED_PASS_CONTEXT_PLAYS)
            .then(
                (pl.col("context_passes") + EXPECTED_PASS_PRIOR_STRENGTH * global_rate)
                / (pl.col("context_plays") + EXPECTED_PASS_PRIOR_STRENGTH)
            )
            .otherwise(global_rate)
            .alias("expected_pass_probability")
        )
        aggregate = (
            scored.group_by("team_id")
            .agg(
                pl.len().alias("eligible_plays"),
                pl.col("is_pass").sum().alias("pass_plays"),
                pl.col("expected_pass_probability").mean().alias("expected_pass_rate"),
            )
            .with_columns(
                pl.lit(season).alias("season"),
                (pl.col("pass_plays") / pl.col("eligible_plays")).alias("observed_pass_rate"),
            )
            .with_columns(
                (pl.col("observed_pass_rate") - pl.col("expected_pass_rate")).alias("proe")
            )
        )
        combined_hash = hashlib.sha256(
            "".join(
                f"{value}:{source_hashes[value]}"
                for value in sorted(source_hashes)
                if fit_start <= value <= season
            ).encode()
        ).hexdigest()
        intermediate_hash = hashlib.sha256(
            f"{combined_hash}:{EXPECTED_PASS_MODEL_VERSION}:{season}".encode()
        ).hexdigest()
        for feature in ("expected_pass_rate", "proe"):
            rows.append(
                aggregate.select(
                    "team_id",
                    "season",
                    pl.lit("tendency").alias("profile_family"),
                    pl.lit(feature).alias("feature_name"),
                    (pl.col("expected_pass_rate") * pl.col("eligible_plays"))
                    .round(0)
                    .cast(pl.Int64)
                    .alias("raw_count")
                    if feature == "expected_pass_rate"
                    else pl.col("pass_plays").cast(pl.Int64).alias("raw_count"),
                    pl.col("eligible_plays"),
                    pl.col(feature).alias("raw_value"),
                    pl.lit("nflverse_pbp").alias("source_dataset"),
                    pl.lit(source_version).alias("source_version"),
                    pl.lit(combined_hash).alias("source_hash"),
                    pl.lit("checkpoint_13/expected_pass_profiles").alias("intermediate_artifact"),
                    pl.lit(intermediate_hash).alias("intermediate_hash"),
                    pl.lit(EXPECTED_PASS_MODEL_VERSION).alias("definition_version"),
                    pl.lit(EXPECTED_PASS_MODEL_VERSION).alias("model_version"),
                    pl.lit(fit_start).alias("model_fit_start_season"),
                    pl.lit(season - 1).alias("model_fit_end_season"),
                    pl.lit(None, dtype=pl.String).alias("missingness_reason"),
                )
            )
    return pl.concat(rows, how="vertical_relaxed").sort("season", "team_id", "feature_name")


def load_expected_pass_source(pbp_root: Path) -> tuple[pl.DataFrame, dict[int, str]]:
    columns = [
        "season",
        "season_type",
        "posteam",
        "play_type",
        "two_point_attempt",
        "qb_kneel",
        "down",
        "qtr",
        "ydstogo",
        "yardline_100",
        "score_differential",
    ]
    frames: list[pl.DataFrame] = []
    hashes: dict[int, str] = {}
    for season in range(1999, 2026):
        path = pbp_root / f"season={season}" / "play_by_play.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        hashes[season] = _sha256(path)
        frame = pl.read_parquet(path, columns=columns)
        if frame.filter(pl.col("season") != season).height:
            raise ValueError(f"PBP season mismatch in {path}")
        frames.append(frame)
    return pl.concat(frames, how="vertical_relaxed"), hashes


def _read_profile_files(expansion_path: Path) -> pl.DataFrame:
    files = (
        "tendency_profiles.csv",
        "qb_usage_profiles.csv",
        "situational_profiles.csv",
        "outcome_profiles.csv",
        "personnel_profiles.csv",
        "personnel_family_profiles.csv",
        "formation_profiles.csv",
        "mechanic_profiles.csv",
    )
    frames = [
        pl.read_csv(expansion_path / name).with_columns(
            pl.lit(f"checkpoint_12_data_expansion/{name}").alias("intermediate_artifact"),
            pl.lit(_sha256(expansion_path / name)).alias("intermediate_hash"),
        )
        for name in files
    ]
    profiles = pl.concat(frames, how="diagonal_relaxed")
    profiles = profiles.with_columns(
        pl.col("feature_name").replace(
            {
                "expected_pass_rate": "expected_pass_rate_descriptive_nflverse",
                "proe_mean": "proe_descriptive_nflverse",
            }
        ),
        pl.lit(None, dtype=pl.String).alias("source_version"),
        pl.lit(None, dtype=pl.String).alias("model_version"),
        pl.lit(None, dtype=pl.Int64).alias("model_fit_start_season"),
        pl.lit(None, dtype=pl.Int64).alias("model_fit_end_season"),
    )
    if profiles.select("team_id", "season", "feature_name").n_unique() != profiles.height:
        raise ValueError("Checkpoint 12 profiles contain duplicate team-season-feature keys")
    return profiles


def build_scheme_table(
    profiles: pl.DataFrame,
    expected_pass: pl.DataFrame,
    registry: Sequence[FeatureDefinition],
    *,
    expansion_version: str,
) -> pl.DataFrame:
    lookup = feature_registry_frame(registry).select(
        pl.col("name").alias("feature_name"),
        "status",
        "timing_class",
        "predictive_permission",
    )
    combined = pl.concat([profiles, expected_pass], how="diagonal_relaxed").with_columns(
        pl.col("source_version").fill_null(expansion_version),
        pl.lit("retrospective_same_season_z_display_only").alias(
            "descriptive_standardization_method"
        ),
    )
    combined = combined.with_columns(
        pl.when(pl.col("raw_value").std(ddof=0).over(["season", "feature_name"]) > 0)
        .then(
            (pl.col("raw_value") - pl.col("raw_value").mean().over(["season", "feature_name"]))
            / pl.col("raw_value").std(ddof=0).over(["season", "feature_name"])
        )
        .otherwise(None)
        .alias("descriptive_standardized_value")
    ).join(lookup, on="feature_name", how="left", validate="m:1")
    if combined.filter(pl.col("status").is_null()).height:
        missing = combined.filter(pl.col("status").is_null())["feature_name"].unique().to_list()
        raise ValueError(f"scheme features are not registered: {sorted(missing)}")
    return combined.select(
        "team_id",
        "season",
        "profile_family",
        "feature_name",
        "raw_count",
        pl.col("eligible_plays").alias("eligible_play_count"),
        pl.col("eligible_plays").alias("feature_sample_size"),
        "raw_value",
        "descriptive_standardized_value",
        "descriptive_standardization_method",
        "source_dataset",
        "source_version",
        "source_hash",
        "intermediate_artifact",
        "intermediate_hash",
        pl.col("definition_version").alias("feature_definition_version"),
        "model_version",
        "model_fit_start_season",
        "model_fit_end_season",
        pl.col("status").alias("feature_status"),
        "timing_class",
        "predictive_permission",
        "missingness_reason",
        pl.col("raw_value").is_not_null().alias("source_covered"),
    ).sort("season", "team_id", "profile_family", "feature_name")


def build_predictive_feature_records(
    scheme: pl.DataFrame,
    registry: Sequence[FeatureDefinition],
) -> pl.DataFrame:
    permitted = scheme.filter(
        pl.col("predictive_permission").is_in(["YES", "CONDITIONAL"])
        & (pl.col("timing_class") == "HISTORICAL_PRIOR")
    )
    rows: list[pl.DataFrame] = []
    for target_season in TARGET_SEASONS:
        source_season = target_season - 1
        source = permitted.filter(pl.col("season") == source_season)
        if source.is_empty():
            continue
        window_start = max(int(permitted["season"].min()), source_season - 4)
        feature_parts: list[pl.DataFrame] = []
        for feature in sorted(source["feature_name"].unique().to_list()):
            current = source.filter(pl.col("feature_name") == feature)
            history = permitted.filter(
                (pl.col("feature_name") == feature)
                & pl.col("season").is_between(window_start, source_season)
            ).select("season", "raw_value")
            standardizer = HistoricalStandardizer().fit(history, target_season=target_season)
            transformed = standardizer.transform(current)
            feature_parts.append(
                transformed.with_columns(
                    pl.lit(target_season).alias("target_season"),
                    pl.date(target_season, *AS_OF_MONTH_DAY).cast(pl.String).alias("as_of_date"),
                    pl.date(target_season, *AS_OF_MONTH_DAY)
                    .cast(pl.String)
                    .alias("source_available_date"),
                    pl.concat_str(
                        [
                            pl.lit("team:"),
                            pl.col("team_id"),
                            pl.lit(":season:"),
                            pl.lit(target_season),
                        ]
                    ).alias("entity_id"),
                    pl.lit("scheme-team-season").alias("entity_type"),
                    pl.lit(FEATURE_BUILD_VERSION).alias("feature_build_version"),
                    pl.lit("rolling_prior_five_seasons_zscore").alias("standardization_method"),
                    pl.lit(standardizer.fit_start_season_).alias(
                        "standardization_fit_start_season"
                    ),
                    pl.lit(standardizer.fit_end_season_).alias("standardization_fit_end_season"),
                    pl.lit(standardizer.mean_).alias("standardization_mean"),
                    pl.lit(standardizer.std_).alias("standardization_std"),
                )
            )
        rows.append(pl.concat(feature_parts, how="vertical_relaxed"))
    records = (
        pl.concat(rows, how="vertical_relaxed")
        .select(
            "entity_type",
            "entity_id",
            "feature_name",
            pl.col("standardized_value").alias("feature_value"),
            "raw_value",
            pl.col("season").alias("source_season"),
            "target_season",
            "as_of_date",
            "source_available_date",
            "source_dataset",
            "source_version",
            "source_hash",
            "intermediate_artifact",
            "intermediate_hash",
            "feature_definition_version",
            "feature_build_version",
            "model_version",
            pl.col("feature_sample_size").cast(pl.Float64).alias("sample_size"),
            pl.col("eligible_play_count").cast(pl.Float64).alias("exposure"),
            "missingness_reason",
            "timing_class",
            "feature_status",
            "predictive_permission",
            "standardization_method",
            "standardization_fit_start_season",
            "standardization_fit_end_season",
            "standardization_mean",
            "standardization_std",
        )
        .sort("target_season", "entity_type", "entity_id", "feature_name")
    )
    validate_feature_records(records, registry)
    return records


def build_coach_scheme_associations(expansion_path: Path, scheme: pl.DataFrame) -> pl.DataFrame:
    associations = pl.read_csv(expansion_path / "coach_role_scheme_associations.csv")
    metadata_columns = [
        "assignment_key",
        "season",
        "team_id",
        "coach_id",
        "coach_canonical_name",
        "role",
        "start_week",
        "end_week",
        "start_date",
        "end_date",
        "is_interim",
        "is_shared",
        "is_retained",
        "verification_status",
        "confidence_level",
        "interval_basis",
        "primary_source_url",
    ]
    assignments = associations.select(metadata_columns).unique()
    if assignments.select("assignment_key").n_unique() != assignments.height:
        raise ValueError("assignment keys do not uniquely identify coach intervals")
    return (
        assignments.with_columns(
            (pl.col("end_week") - pl.col("start_week") + 1).alias("assignment_week_exposure")
        )
        .join(scheme, on=["team_id", "season"], how="inner", validate="m:m")
        .with_columns(
            pl.lit("team_season_context").alias("scheme_observation_grain"),
            pl.lit(False).alias("exact_weekly_scheme_ownership"),
            pl.lit("NOT_RELIABLE_AT_INTERVAL_GRAIN").alias("interval_specific_scheme_status"),
            pl.lit(
                "observational association; assignment interval preserved; no causal ownership"
            ).alias("attribution_limitation"),
        )
        .sort("season", "team_id", "assignment_key", "feature_name")
    )


def _coverage_by_season(
    scheme: pl.DataFrame, registry: Sequence[FeatureDefinition]
) -> pl.DataFrame:
    definitions = feature_registry_frame(registry).select(
        pl.col("name").alias("feature_name"),
        "family",
        "earliest_supported_season",
        "latest_supported_season",
        "timing_class",
        "status",
    )
    grid = pl.DataFrame({"season": list(ANALYSIS_SEASONS)}).join(definitions, how="cross")
    observed = scheme.group_by("season", "feature_name").agg(
        pl.col("team_id").n_unique().alias("observed_team_seasons"),
        pl.col("raw_value").is_not_null().sum().alias("non_null_team_seasons"),
        pl.col("eligible_play_count").sum().alias("eligible_plays"),
    )
    return (
        grid.join(observed, on=["season", "feature_name"], how="left", validate="1:1")
        .with_columns(
            pl.col("observed_team_seasons", "non_null_team_seasons", "eligible_plays").fill_null(0),
            (
                pl.col("earliest_supported_season").is_not_null()
                & pl.col("season").is_between(
                    pl.col("earliest_supported_season"), pl.col("latest_supported_season")
                )
            ).alias("source_expected"),
        )
        .with_columns(
            (pl.col("non_null_team_seasons") > 0).alias("available"),
            (pl.col("non_null_team_seasons") / 32).alias("coverage"),
            pl.when(pl.col("status") == "UNAVAILABLE")
            .then(pl.lit("SOURCE_NOT_AVAILABLE"))
            .when(~pl.col("source_expected"))
            .then(pl.lit("FEATURE_NOT_SUPPORTED_THAT_SEASON"))
            .when(pl.col("non_null_team_seasons") == 0)
            .then(pl.lit("ENTITY_NOT_PRESENT"))
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("missingness_reason"),
        )
        .sort("season", "family", "feature_name")
    )


def _availability_by_target(
    records: pl.DataFrame, registry: Sequence[FeatureDefinition]
) -> pl.DataFrame:
    definitions = feature_registry_frame(registry).select(
        pl.col("name").alias("feature_name"),
        "family",
        "entity_grain",
        "timing_class",
        "status",
        "predictive_permission",
        "earliest_supported_season",
        "latest_supported_season",
    )
    grid = pl.DataFrame({"target_season": list(TARGET_SEASONS)}).join(definitions, how="cross")
    observed = records.group_by("target_season", "feature_name").agg(
        pl.len().alias("available_entities"),
        pl.col("feature_value").is_not_null().sum().alias("non_null_entities"),
        pl.col("source_season").max().alias("maximum_source_season"),
    )
    return (
        grid.join(observed, on=["target_season", "feature_name"], how="left", validate="1:1")
        .with_columns(
            pl.col("available_entities", "non_null_entities").fill_null(0),
            (pl.col("non_null_entities") > 0).alias("available"),
            (
                (pl.col("maximum_source_season").is_null())
                | (pl.col("maximum_source_season") < pl.col("target_season"))
            ).alias("as_of_safe"),
            pl.when(pl.col("entity_grain") == "scheme-team-season")
            .then(pl.col("non_null_entities") / 32)
            .otherwise(None)
            .alias("coverage"),
            pl.when(pl.col("status") == "UNAVAILABLE")
            .then(pl.lit("SOURCE_NOT_AVAILABLE"))
            .when(pl.col("predictive_permission") == "NO")
            .then(pl.lit("NOT_APPLICABLE"))
            .when(pl.col("target_season") - 1 < pl.col("earliest_supported_season"))
            .then(pl.lit("FEATURE_NOT_SUPPORTED_THAT_SEASON"))
            .when(pl.col("non_null_entities") == 0)
            .then(
                pl.when(pl.col("family") == "coach_signal")
                .then(pl.lit("ROLE_NOT_VERIFIED"))
                .otherwise(pl.lit("ENTITY_NOT_PRESENT"))
            )
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("missingness_reason"),
        )
        .sort("target_season", "family", "feature_name")
    )


def _feature_stability(scheme: pl.DataFrame) -> pl.DataFrame:
    usable = scheme.filter(pl.col("raw_value").is_not_null()).select(
        "team_id", "season", "feature_name", "raw_value"
    )
    pairs = usable.join(
        usable.with_columns((pl.col("season") + 1).alias("season")).rename(
            {"raw_value": "prior_raw_value"}
        ),
        on=["team_id", "season", "feature_name"],
        how="inner",
        validate="1:1",
    )
    return (
        pairs.group_by("feature_name")
        .agg(
            pl.len().alias("consecutive_team_pairs"),
            pl.corr("prior_raw_value", "raw_value").alias("pearson"),
            pl.col("prior_raw_value").std().alias("prior_std"),
            pl.col("raw_value").std().alias("current_std"),
        )
        .with_columns(pl.lit("same_team_consecutive_seasons").alias("comparison"))
        .sort("feature_name")
    )


def _leakage_audit(records: pl.DataFrame) -> pl.DataFrame:
    return (
        records.group_by("target_season")
        .agg(
            pl.len().alias("feature_rows"),
            pl.col("entity_id").n_unique().alias("entities"),
            pl.col("source_season").min().alias("minimum_source_season"),
            pl.col("source_season").max().alias("maximum_source_season"),
            (pl.col("source_season") >= pl.col("target_season")).sum().alias("illegal_source_rows"),
            (pl.col("standardization_fit_end_season") >= pl.col("target_season"))
            .sum()
            .alias("illegal_standardization_rows"),
        )
        .with_columns(
            (
                (pl.col("illegal_source_rows") == 0) & (pl.col("illegal_standardization_rows") == 0)
            ).alias("passed")
        )
        .sort("target_season")
    )


def _missingness_summary(availability: pl.DataFrame) -> pl.DataFrame:
    return (
        availability.group_by("feature_name", "missingness_reason")
        .agg(
            pl.len().alias("target_seasons"),
            pl.col("target_season").min().alias("first_target_season"),
            pl.col("target_season").max().alias("last_target_season"),
            pl.col("non_null_entities").sum().alias("non_null_entities"),
        )
        .sort("feature_name", "missingness_reason", nulls_last=True)
    )


def _write_csv(frame: pl.DataFrame, path: Path) -> None:
    floats = [name for name, dtype in frame.schema.items() if dtype in {pl.Float32, pl.Float64}]
    deterministic = frame.with_columns(pl.col(floats).round(10)) if floats else frame
    deterministic.write_csv(path, line_terminator="\n")


def _output_checksums(directory: Path, names: Iterable[str]) -> dict[str, str]:
    return {name: _sha256(directory / name) for name in sorted(names)}


def _content_identity(
    *,
    inputs: dict[str, str],
    registry: Sequence[FeatureDefinition],
    code_hash: str,
) -> tuple[str, dict[str, Any]]:
    identity = {
        "specification": CHECKPOINT_13_SPECIFICATION,
        "feature_definition_version": FEATURE_DEFINITION_VERSION,
        "feature_build_version": FEATURE_BUILD_VERSION,
        "expected_pass_model_version": EXPECTED_PASS_MODEL_VERSION,
        "expected_pass_prior_strength": EXPECTED_PASS_PRIOR_STRENGTH,
        "reference_window_seasons": REFERENCE_WINDOW_SEASONS,
        "as_of_month_day": AS_OF_MONTH_DAY,
        "analysis_seasons": ANALYSIS_SEASONS,
        "target_seasons": TARGET_SEASONS,
        "python_version": platform.python_version(),
        "polars_version": pl.__version__,
        "code_hash": code_hash,
        "inputs": dict(sorted(inputs.items())),
        "registry": [asdict(item) for item in registry],
    }
    identity = json.loads(json.dumps(identity, sort_keys=True))
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return f"c13-{digest}", identity


def _resolve_latest(root: Path) -> tuple[str, Path]:
    version = (root / "LATEST").read_text(encoding="utf-8").strip()
    path = root / version
    if not version or not path.is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return version, path


def run_checkpoint_thirteen(
    project_root: Path,
    output_root: Path | None = None,
) -> CheckpointThirteenResult:
    """Build and atomically publish deterministic Checkpoint 13 file artifacts."""

    expansion_version, expansion_path = _resolve_latest(
        project_root / "research/coach_effect/outputs/checkpoint_12_data_expansion"
    )
    if expansion_version != "c12-data-250e540b7de79385":
        raise ValueError(f"unexpected Checkpoint 12 scheme version: {expansion_version}")
    final_version, final_path = _resolve_latest(
        project_root / "research/coach_effect/outputs/checkpoint_12_final_research"
    )
    if final_version != "c12-final-0c746df0290c836c":
        raise ValueError(f"unexpected Checkpoint 12 final version: {final_version}")
    historical_version, historical_path = _resolve_latest(
        project_root / "data/processed/historical"
    )
    availability_path = expansion_path / "scheme_feature_availability.csv"
    registry = _registry_from_checkpoint_twelve(pl.read_csv(availability_path))
    profile_names = (
        "tendency_profiles.csv",
        "qb_usage_profiles.csv",
        "situational_profiles.csv",
        "outcome_profiles.csv",
        "personnel_profiles.csv",
        "personnel_family_profiles.csv",
        "formation_profiles.csv",
        "mechanic_profiles.csv",
        "coach_role_scheme_associations.csv",
        "scheme_feature_stability.csv",
        "scheme_feature_availability.csv",
    )
    inputs = {f"checkpoint12/{name}": _sha256(expansion_path / name) for name in profile_names}
    inputs["checkpoint12_final/MANIFEST.json"] = _sha256(final_path / "MANIFEST.json")
    inputs["historical/RUN_MANIFEST.json"] = _sha256(historical_path / "RUN_MANIFEST.json")
    module_path = Path(__file__)
    code_hash = _sha256(module_path)

    pbp, pbp_hashes = load_expected_pass_source(historical_path / "bronze/play_by_play")
    for season, digest in sorted(pbp_hashes.items()):
        inputs[f"historical/pbp/{season}"] = digest
    data_version, identity = _content_identity(
        inputs=inputs, registry=registry, code_hash=code_hash
    )
    root = output_root or project_root / "data/processed/predictive_foundation"
    destination = root / data_version
    if destination.is_dir():
        manifest = json.loads((destination / "MANIFEST.json").read_text(encoding="utf-8"))
        if manifest["identity"] != identity:
            raise ValueError("existing Checkpoint 13 directory does not match content identity")
        changed = [
            name
            for name, expected in manifest["output_checksums"].items()
            if not (destination / name).is_file() or _sha256(destination / name) != expected
        ]
        if changed:
            raise ValueError(f"existing Checkpoint 13 artifacts failed checksums: {changed}")
        return CheckpointThirteenResult(
            data_version=data_version,
            output_path=destination,
            reused_existing=True,
            registered_features=int(manifest["counts"]["registered_features"]),
            feature_records=int(manifest["counts"]["feature_records"]),
            scheme_rows=int(manifest["counts"]["scheme_rows"]),
        )

    profiles = _read_profile_files(expansion_path)
    expected_pass = build_expected_pass_profiles(
        pbp, source_hashes=pbp_hashes, source_version=historical_version
    )
    scheme = build_scheme_table(
        profiles, expected_pass, registry, expansion_version=expansion_version
    )
    records = build_predictive_feature_records(scheme, registry)
    associations = build_coach_scheme_associations(expansion_path, scheme)
    by_season = _coverage_by_season(scheme, registry)
    by_target = _availability_by_target(records, registry)
    stability = _feature_stability(scheme)
    leakage = _leakage_audit(records)
    if leakage.filter(~pl.col("passed")).height:
        raise ValueError("Checkpoint 13 leakage audit failed")
    coverage = (
        scheme.group_by("profile_family", "feature_name", "feature_status")
        .agg(
            pl.col("season").min().alias("first_season"),
            pl.col("season").max().alias("last_season"),
            pl.len().alias("team_season_rows"),
            pl.col("raw_value").is_not_null().sum().alias("non_null_team_seasons"),
            pl.col("eligible_play_count").median().alias("median_sample_size"),
        )
        .with_columns(
            (pl.col("non_null_team_seasons") / pl.col("team_season_rows")).alias("coverage")
        )
        .sort("profile_family", "feature_name")
    )
    snapshot_summary = (
        records.group_by("target_season")
        .agg(
            pl.len().alias("feature_rows"),
            pl.col("entity_id").n_unique().alias("entities"),
            pl.col("feature_name").n_unique().alias("features"),
            pl.col("source_season").min().alias("minimum_source_season"),
            pl.col("source_season").max().alias("maximum_source_season"),
        )
        .with_columns(pl.lit(f"{AS_OF_MONTH_DAY[0]:02d}-{AS_OF_MONTH_DAY[1]:02d}").alias("cutoff"))
        .sort("target_season")
    )
    status = feature_registry_frame(registry).select(
        "name",
        "family",
        "status",
        "timing_class",
        "predictive_permission",
        "research_readiness",
        "description",
    )
    summary = pl.DataFrame(
        [
            {"gate": "LEAKAGE_FOUNDATION", "status": "PASS", "detail": "zero illegal rows"},
            {"gate": "FEATURE_REGISTRY", "status": "PASS", "detail": "all features registered"},
            {
                "gate": "SCHEME_ENGINE",
                "status": "PASS",
                "detail": "clean team-season-feature grain",
            },
            {"gate": "PREDICTIVE_SNAPSHOTS", "status": "PASS", "detail": "prior-season only"},
            {"gate": "CHECKPOINT_14_INTERFACE", "status": "PASS", "detail": "AsOfFeatureStore"},
        ]
    )
    artifacts: dict[str, pl.DataFrame] = {
        "feature_registry.csv": feature_registry_frame(registry),
        "feature_availability_by_season.csv": by_season,
        "feature_availability_by_target.csv": by_target,
        "scheme_team_season.csv": scheme,
        "scheme_feature_coverage.csv": coverage,
        "scheme_feature_stability.csv": stability,
        "personnel_team_season.csv": scheme.filter(pl.col("profile_family") == "personnel_group"),
        "personnel_family_team_season.csv": scheme.filter(
            pl.col("profile_family") == "personnel_family"
        ),
        "formation_team_season.csv": scheme.filter(pl.col("profile_family") == "formation"),
        "predictive_feature_records.csv": records,
        "predictive_asof_snapshot_summary.csv": snapshot_summary,
        "coach_scheme_associations.csv": associations,
        "leakage_audit.csv": leakage,
        "missingness_summary.csv": _missingness_summary(by_target),
        "feature_status.csv": status,
        "checkpoint_13_summary.csv": summary,
    }
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{data_version}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir()
    try:
        for name, frame in artifacts.items():
            _write_csv(frame, temporary / name)
        checksums = _output_checksums(temporary, artifacts)
        manifest = {
            "data_version": data_version,
            "feature_set_version": FEATURE_BUILD_VERSION,
            "checkpoint_status": "COMPLETE",
            "checkpoint_14_readiness": "READY",
            "identity": identity,
            "counts": {
                "registered_features": len(registry),
                "feature_records": records.height,
                "scheme_rows": scheme.height,
                "coach_scheme_associations": associations.height,
                "target_snapshots": snapshot_summary.height,
            },
            "grains": {
                "scheme_team_season": ["team_id", "season", "feature_name"],
                "feature_record": [
                    "entity_type",
                    "entity_id",
                    "feature_name",
                    "target_season",
                    "feature_build_version",
                ],
                "coach_scheme_association": ["assignment_key", "feature_name"],
            },
            "output_checksums": checksums,
        }
        (temporary / "MANIFEST.json").write_bytes(_json_bytes(manifest))
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    latest_tmp = root / ".LATEST.tmp"
    latest_tmp.write_text(data_version + "\n", encoding="utf-8")
    os.replace(latest_tmp, root / "LATEST")
    return CheckpointThirteenResult(
        data_version=data_version,
        output_path=destination,
        reused_existing=False,
        registered_features=len(registry),
        feature_records=records.height,
        scheme_rows=scheme.height,
    )

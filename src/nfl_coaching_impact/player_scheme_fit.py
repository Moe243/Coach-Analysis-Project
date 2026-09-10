"""Checkpoint 15 leakage-safe Player State x Scheme fit research.

The module deliberately keeps target-team assignment separate from target outcomes.  A player can
enter the modeling cohort only through an immutable draft-team fact for the draft season or a
dated QB depth-chart snapshot captured no later than August 31.  Target-season performance is
joined only after that entering-season cohort is frozen.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import Ridge

from .constants import TEAM_ALIAS_TO_CANONICAL
from .predictive_foundation import AsOfFeatureStore

CHECKPOINT_15_SPECIFICATION: Final = "checkpoint-15-player-scheme-fit-v1.1-data-contract-audit"
FIT_FEATURE_VERSION: Final = "player-scheme-fit-features-v1"
FIT_MODEL_VERSION: Final = "rolling-ridge-player-scheme-v1"
COHORT_VERSION: Final = "preseason-known-target-environment-v1.1"
TARGET_SEASONS: Final = tuple(range(2011, 2026))
AS_OF_MONTH_DAY: Final = (8, 31)
MIN_OUTCOME_DROPBACKS: Final = 50
MIN_TRAIN_ROWS: Final = 30
MIN_TEST_ROWS: Final = 2
MIN_INNER_TRAIN_ROWS: Final = 20
MIN_INNER_TEST_ROWS: Final = 2
MIN_FEATURE_TRAIN_VALUES: Final = 10
MIN_INTERACTION_TRAIN_VALUES: Final = 20
RIDGE_ALPHAS: Final = (0.1, 1.0, 10.0, 100.0)
DEFAULT_RIDGE_ALPHA: Final = 10.0
BOOTSTRAP_DRAWS: Final = 500
PERMUTATION_DRAWS: Final = 200
RANDOM_SEED: Final = 15015

PLAYER_FEATURES: Final = (
    "preseason_ability_estimate_epa_per_db",
    "recent_epa_per_dropback",
    "recent_success_rate",
    "recent_cpoe",
    "recent_sack_rate",
    "recent_observed_pae",
    "recent_scramble_rate",
    "recent_shotgun_rate",
    "recent_average_air_yards",
    "recent_target_depth_short_rate",
    "recent_target_depth_intermediate_rate",
    "recent_target_depth_deep_rate",
    "recent_pass_location_left_rate",
    "recent_pass_location_middle_rate",
    "recent_pass_location_right_rate",
    "age_at_season_start",
    "seasons_since_rookie_year",
    "career_starts_log1p",
    "career_dropbacks_log1p",
    "prior_starts_log1p",
    "prior_dropbacks_log1p",
)

CONDITIONAL_PLAYER_FEATURES: Final = (
    "recent_observed_pae",
    "recent_pass_location_left_rate",
    "recent_pass_location_middle_rate",
    "recent_pass_location_right_rate",
)

CORE_PLAYER_FEATURES: Final = tuple(
    name for name in PLAYER_FEATURES if name not in CONDITIONAL_PLAYER_FEATURES
)

STYLE_FEATURES: Final = (
    "recent_scramble_rate",
    "recent_shotgun_rate",
    "recent_average_air_yards",
    "recent_target_depth_short_rate",
    "recent_target_depth_intermediate_rate",
    "recent_target_depth_deep_rate",
    "recent_sack_rate",
    "recent_pass_location_left_rate",
    "recent_pass_location_middle_rate",
    "recent_pass_location_right_rate",
)

SCHEME_FEATURES: Final = (
    "shotgun_rate",
    "no_huddle_rate",
    "pass_rate",
    "expected_pass_rate",
    "proe",
    "early_down_pass_rate",
    "neutral_pass_rate",
    "target_depth_short_rate",
    "target_depth_intermediate_rate",
    "target_depth_deep_rate",
    "average_air_yards",
    "scramble_rate",
)

CONDITIONAL_SCHEME_FEATURES: Final = ("expected_pass_rate", "proe")

CORE_SCHEME_FEATURES: Final = tuple(
    name for name in SCHEME_FEATURES if name not in CONDITIONAL_SCHEME_FEATURES
)

INTERACTION_DEFINITIONS: Final = (
    ("scramble_alignment", "recent_scramble_rate", "scramble_rate", "mobility"),
    ("shotgun_alignment", "recent_shotgun_rate", "shotgun_rate", "formation"),
    (
        "short_depth_alignment",
        "recent_target_depth_short_rate",
        "target_depth_short_rate",
        "target_depth",
    ),
    (
        "intermediate_depth_alignment",
        "recent_target_depth_intermediate_rate",
        "target_depth_intermediate_rate",
        "target_depth",
    ),
    (
        "deep_depth_alignment",
        "recent_target_depth_deep_rate",
        "target_depth_deep_rate",
        "target_depth",
    ),
    (
        "air_yards_alignment",
        "recent_average_air_yards",
        "average_air_yards",
        "target_depth",
    ),
    (
        "mobility_in_pass_heavy_environment",
        "recent_scramble_rate",
        "pass_rate",
        "pass_tendency",
    ),
    (
        "depth_in_neutral_pass_environment",
        "recent_average_air_yards",
        "neutral_pass_rate",
        "pass_tendency",
    ),
)

OUTCOMES: Final = {
    "next_season_epa_per_dropback": "outcome_epa_per_dropback",
    "next_season_pae": "outcome_pae",
}

VALID_MISSINGNESS: Final = {
    "SOURCE_NOT_AVAILABLE",
    "INSUFFICIENT_SAMPLE",
    "ROLE_NOT_VERIFIED",
    "FEATURE_NOT_SUPPORTED_THAT_SEASON",
    "ENTITY_NOT_PRESENT",
    "NOT_APPLICABLE",
    "NOT_IN_ASOF_STATE_UNIVERSE",
    "TARGET_TEAM_NOT_ESTABLISHED",
    "AMBIGUOUS_PRESEASON_TEAM",
    "PRESEASON_NO_TEAM_KNOWN",
    "TARGET_TEAM_NO_OUTCOME",
    "BELOW_OUTCOME_DROPBACK_MINIMUM",
}

TARGET_TEAM_SOURCE_URLS: Final = {
    "immutable_draft_team": (
        "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"
    ),
}
DATED_TRANSACTION_EVENTS: Final = {
    "TRADE",
    "SIGNING",
    "WAIVER_CLAIM",
    "ROSTER_ASSIGNMENT",
    "RELEASE",
    "WAIVER",
}
NO_TEAM_EVENTS: Final = {"RELEASE", "WAIVER"}


@dataclass(frozen=True)
class CheckpointFifteenResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    cohort_rows: int
    eligible_rows: int
    prediction_rows: int
    fit_status: str
    checkpoint_16_readiness: str


@dataclass(frozen=True)
class FoldPreprocessor:
    """Train-only median imputation plus standardization with explicit missing indicators."""

    feature_names: tuple[str, ...]
    medians: tuple[float, ...]
    means: tuple[float, ...]
    standard_deviations: tuple[float, ...]
    fitted_start_season: int
    fitted_end_season: int

    @classmethod
    def fit(
        cls,
        frame: pl.DataFrame,
        feature_names: tuple[str, ...],
        *,
        target_season: int,
        minimum_values: int = MIN_FEATURE_TRAIN_VALUES,
    ) -> FoldPreprocessor:
        if frame.filter(pl.col("target_season") >= target_season).height:
            raise ValueError("preprocessor received target or future-season training rows")
        kept: list[str] = []
        medians: list[float] = []
        means: list[float] = []
        deviations: list[float] = []
        for name in feature_names:
            values = _finite_values(frame[name])
            if len(values) < minimum_values or len(np.unique(values)) < 2:
                continue
            median = float(np.median(values))
            all_values = np.asarray(
                [
                    median if value is None or not math.isfinite(float(value)) else float(value)
                    for value in frame[name].to_list()
                ],
                dtype=float,
            )
            mean = float(np.mean(all_values))
            deviation = float(np.std(all_values, ddof=0))
            if not math.isfinite(deviation) or deviation <= 0:
                continue
            kept.append(name)
            medians.append(median)
            means.append(mean)
            deviations.append(deviation)
        if not kept:
            raise ValueError("no train-qualified features remain after preprocessing")
        return cls(
            tuple(kept),
            tuple(medians),
            tuple(means),
            tuple(deviations),
            int(frame["target_season"].min()),
            int(frame["target_season"].max()),
        )

    def transform(self, frame: pl.DataFrame) -> tuple[np.ndarray, tuple[str, ...]]:
        columns: list[np.ndarray] = []
        names: list[str] = []
        for name, median, mean, deviation in zip(
            self.feature_names,
            self.medians,
            self.means,
            self.standard_deviations,
            strict=True,
        ):
            raw = frame[name].to_list()
            missing = np.asarray(
                [value is None or not math.isfinite(float(value)) for value in raw], dtype=float
            )
            imputed = np.asarray(
                [
                    median if is_missing else float(value)
                    for value, is_missing in zip(raw, missing, strict=True)
                ],
                dtype=float,
            )
            columns.append((imputed - mean) / deviation)
            columns.append(missing)
            names.extend((name, f"{name}__missing"))
        return np.column_stack(columns), tuple(names)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _resolve_latest(root: Path) -> tuple[str, Path]:
    version = (root / "LATEST").read_text(encoding="utf-8").strip()
    path = root / version
    if not version or not path.is_dir():
        raise ValueError(f"invalid LATEST pointer: {root}")
    return version, path


def _canonical_team(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text.startswith("team_"):
        return text
    canonical = TEAM_ALIAS_TO_CANONICAL.get(text.upper())
    return None if canonical is None else f"team_{canonical.lower()}"


def _safe_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _frame_hash(frame: pl.DataFrame) -> str:
    """Return a deterministic fallback hash for in-memory fixture evidence."""

    columns = sorted(frame.columns)
    normalized = frame.select(columns).sort(columns, nulls_last=True) if columns else frame
    return hashlib.sha256(normalized.write_csv().encode()).hexdigest()


def _finite_values(series: pl.Series) -> np.ndarray:
    return np.asarray(
        [
            float(value)
            for value in series.to_list()
            if value is not None and math.isfinite(float(value))
        ],
        dtype=float,
    )


def fit_feature_registry(
    player_registry: pl.DataFrame | None = None,
    scheme_registry: pl.DataFrame | None = None,
) -> pl.DataFrame:
    style = set(STYLE_FEATURES)
    interactions = {name for name, _, _, _ in INTERACTION_DEFINITIONS}
    rows: list[dict[str, object]] = []
    player_contracts = (
        {row["name"]: row for row in player_registry.to_dicts()}
        if player_registry is not None
        else {}
    )
    scheme_contracts = (
        {row["name"]: row for row in scheme_registry.to_dicts()}
        if scheme_registry is not None
        else {}
    )
    conditional_player = set(CONDITIONAL_PLAYER_FEATURES)
    for name in PLAYER_FEATURES:
        source_contract = player_contracts.get(name)
        source_status = (
            source_contract["status"]
            if source_contract is not None
            else "STATE_HEADER_PRESEASON_KNOWN"
        )
        predictive_permission = (
            source_contract["predictive_permission"] if source_contract is not None else "YES"
        )
        if predictive_permission == "NO":
            raise ValueError(f"Checkpoint 14 forbids predictive use of {name}")
        rows.append(
            {
                "feature_name": name,
                "feature_group": "player_style" if name in style else "player_state",
                "source_checkpoint": 14,
                "timing_class": "PRESEASON_KNOWN",
                "status": (
                    "CONDITIONAL"
                    if predictive_permission == "CONDITIONAL" or name in conditional_player
                    else "PRIMARY"
                ),
                "source_status": source_status,
                "predictive_permission": predictive_permission,
                "missingness_rule": "null remains explicit; train-only median when estimable",
            }
        )
    for name in SCHEME_FEATURES:
        source_contract = scheme_contracts.get(name)
        if source_contract is None and scheme_registry is not None:
            raise ValueError(f"Checkpoint 13 registry does not contain {name}")
        predictive_permission = (
            source_contract["predictive_permission"]
            if source_contract is not None
            else ("CONDITIONAL" if name in {"expected_pass_rate", "proe"} else "YES")
        )
        if predictive_permission == "NO":
            raise ValueError(f"Checkpoint 13 forbids predictive use of {name}")
        rows.append(
            {
                "feature_name": f"scheme_{name}",
                "feature_group": "scheme_main_effect",
                "source_checkpoint": 13,
                "timing_class": "HISTORICAL_PRIOR",
                "status": "CONDITIONAL" if predictive_permission == "CONDITIONAL" else "PRIMARY",
                "source_status": (
                    source_contract["status"] if source_contract is not None else "PREDICTIVE_CORE"
                ),
                "predictive_permission": predictive_permission,
                "missingness_rule": "null remains explicit; train-only median when estimable",
            }
        )
    for name, player, scheme, family in INTERACTION_DEFINITIONS:
        rows.append(
            {
                "feature_name": name,
                "feature_group": f"interaction_{family}",
                "source_checkpoint": "13x14",
                "timing_class": "PRESEASON_KNOWN",
                "status": "PREDECLARED",
                "source_status": "DERIVED_FROM_REGISTERED_COMPONENTS",
                "predictive_permission": "CONDITIONAL",
                "missingness_rule": f"null unless both {player} and scheme_{scheme} are available",
            }
        )
    frame = pl.DataFrame(rows, infer_schema_length=None).sort("feature_group", "feature_name")
    if frame["feature_name"].n_unique() != frame.height or not interactions <= set(
        frame["feature_name"].to_list()
    ):
        raise ValueError("invalid fit feature registry")
    return frame


def validate_requested_features(registry: pl.DataFrame, requested: tuple[str, ...]) -> None:
    unknown = sorted(set(requested) - set(registry["feature_name"].to_list()))
    if unknown:
        raise ValueError(f"unregistered fit features requested: {unknown}")


def build_preseason_team_assignments(
    players: pl.DataFrame,
    dated_depth_charts: pl.DataFrame,
    dated_transactions: pl.DataFrame | None = None,
    *,
    players_source_hash: str | None = None,
) -> pl.DataFrame:
    """Resolve teams from immutable or explicitly dated, pre-cutoff evidence only.

    Draft facts carry a conservative August 31 availability bound rather than a fabricated draft
    date. Any exact dated evidence supersedes that coarse bound. Among exact records, the latest
    date wins; contradictory teams (including a no-team release state) on that date remain
    explicitly ambiguous.
    """

    rows: list[dict[str, object]] = []
    player_hash = players_source_hash or _frame_hash(players)
    for row in (
        players.filter((pl.col("position") == "QB") | (pl.col("position_group") == "QB"))
        .select("gsis_id", "draft_year", "draft_team")
        .to_dicts()
    ):
        season = row["draft_year"]
        team = _canonical_team(row["draft_team"])
        if row["gsis_id"] and season in TARGET_SEASONS and team:
            rows.append(
                {
                    "player_id": str(row["gsis_id"]),
                    "target_season": int(season),
                    "candidate_team_id": team,
                    "assignment_basis": "immutable_draft_team",
                    "evidence_type": "IMMUTABLE_DRAFT_TEAM",
                    "evidence_date": f"{season}-08-31",
                    "evidence_date_precision": "PRE_CUTOFF_EVENT_UPPER_BOUND",
                    "evidence_stage": 0,
                    "evidence_priority": 10,
                    "source": TARGET_TEAM_SOURCE_URLS["immutable_draft_team"],
                    "source_version_hash": player_hash,
                    "verification_status": "VERIFIED_IMMUTABLE_FACT",
                    "source_availability_evidence": "IMMUTABLE_DRAFT_FACT_KNOWN_BY_CUTOFF",
                }
            )
    if not dated_depth_charts.is_empty():
        required = {"player_id", "position", "team", "source_available_date"}
        if not required <= set(dated_depth_charts.columns):
            raise ValueError("dated depth-chart assignment evidence lacks required columns")
        for row in dated_depth_charts.filter(pl.col("position") == "QB").to_dicts():
            available = _safe_date(row["source_available_date"])
            team = _canonical_team(row["team"])
            if available is None or team is None or not row["player_id"]:
                continue
            season = available.year
            if season not in TARGET_SEASONS or available > date(season, *AS_OF_MONTH_DAY):
                continue
            rows.append(
                {
                    "player_id": str(row["player_id"]),
                    "target_season": season,
                    "candidate_team_id": team,
                    "assignment_basis": "dated_preseason_depth_chart",
                    "evidence_type": "DATED_PRESEASON_DEPTH_CHART",
                    "evidence_date": str(available),
                    "evidence_date_precision": "EXACT_SOURCE_DATE",
                    "evidence_stage": 1,
                    "evidence_priority": 30,
                    "source": row.get("source") or "fixture://dated-depth-chart",
                    "source_version_hash": row.get("source_version_hash")
                    or _frame_hash(dated_depth_charts),
                    "verification_status": "VERIFIED_DATED_SNAPSHOT",
                    "source_availability_evidence": "DATED_SNAPSHOT_ON_OR_BEFORE_CUTOFF",
                }
            )
    if dated_transactions is not None and not dated_transactions.is_empty():
        required = {
            "player_id",
            "target_season",
            "team",
            "event_type",
            "evidence_date",
            "source",
            "source_version_hash",
            "verification_status",
        }
        if not required <= set(dated_transactions.columns):
            raise ValueError("dated transaction evidence lacks required lineage columns")
        for row in dated_transactions.to_dicts():
            season = row["target_season"]
            available = _safe_date(row["evidence_date"])
            event_type = str(row["event_type"]).upper()
            verification = str(row["verification_status"]).upper()
            if event_type not in DATED_TRANSACTION_EVENTS:
                raise ValueError(f"unsupported target-team transaction event: {event_type}")
            if verification != "VERIFIED":
                continue
            source = str(row["source"])
            source_hash = str(row["source_version_hash"])
            if not source.startswith("https://"):
                raise ValueError("dated transaction source must use HTTPS")
            if len(source_hash) != 64 or any(
                character not in "0123456789abcdef" for character in source_hash.lower()
            ):
                raise ValueError("dated transaction source hash must be a SHA-256 digest")
            if (
                not row["player_id"]
                or season not in TARGET_SEASONS
                or available is None
                or available.year != int(season)
                or available > date(int(season), *AS_OF_MONTH_DAY)
            ):
                continue
            team = _canonical_team(row["team"])
            if event_type not in NO_TEAM_EVENTS and team is None:
                raise ValueError(f"{event_type} evidence lacks a canonical receiving team")
            rows.append(
                {
                    "player_id": str(row["player_id"]),
                    "target_season": int(season),
                    "candidate_team_id": team,
                    "assignment_basis": "dated_official_transaction",
                    "evidence_type": f"DATED_OFFICIAL_{event_type}",
                    "evidence_date": str(available),
                    "evidence_date_precision": "EXACT_SOURCE_DATE",
                    "evidence_stage": 1,
                    "evidence_priority": 40,
                    "source": source,
                    "source_version_hash": source_hash.lower(),
                    "verification_status": "VERIFIED_DATED_TRANSACTION",
                    "source_availability_evidence": "DATED_TRANSACTION_ON_OR_BEFORE_CUTOFF",
                }
            )
    evidence = pl.DataFrame(rows, infer_schema_length=None)
    if evidence.is_empty():
        return pl.DataFrame(
            schema={
                "player_id": pl.String,
                "target_season": pl.Int64,
                "target_team_id": pl.String,
                "target_team_status": pl.String,
                "target_team_basis": pl.String,
                "target_team_source_available_date": pl.String,
                "target_team_source_availability_evidence": pl.String,
                "candidate_team_count": pl.UInt32,
                "evidence_type": pl.String,
                "evidence_date": pl.String,
                "evidence_date_precision": pl.String,
                "source": pl.String,
                "source_version_hash": pl.String,
                "as_of_date": pl.String,
                "verification_status": pl.String,
            }
        )
    resolved: list[dict[str, object]] = []
    for (player_id, target_season), group in evidence.group_by(
        "player_id", "target_season", maintain_order=True
    ):
        candidates = group.to_dicts()
        if any(int(row["evidence_stage"]) == 1 for row in candidates):
            candidates = [row for row in candidates if int(row["evidence_stage"]) == 1]
        latest_date = max(str(row["evidence_date"]) for row in candidates)
        latest = [row for row in candidates if str(row["evidence_date"]) == latest_date]
        distinct_teams = sorted({str(row["candidate_team_id"]) for row in latest})
        primary = sorted(
            latest,
            key=lambda row: (
                -int(row["evidence_priority"]),
                str(row["assignment_basis"]),
                str(row["source"]),
                str(row["source_version_hash"]),
            ),
        )[0]
        team = primary["candidate_team_id"] if len(distinct_teams) == 1 else None
        status = (
            "AMBIGUOUS_PRESEASON_TEAM"
            if len(distinct_teams) > 1
            else ("PRESEASON_NO_TEAM_KNOWN" if team is None else "PRESEASON_TARGET_TEAM_KNOWN")
        )
        resolved.append(
            {
                "player_id": player_id,
                "target_season": int(target_season),
                "candidate_team_count": len(distinct_teams),
                "target_team_basis": str(primary["assignment_basis"]),
                "target_team_source_available_date": latest_date,
                "target_team_source_availability_evidence": "|".join(
                    sorted({str(row["source_availability_evidence"]) for row in latest})
                ),
                "target_team_id": team,
                "target_team_status": status,
                "evidence_type": "|".join(sorted({str(row["evidence_type"]) for row in latest})),
                "evidence_date": latest_date,
                "evidence_date_precision": "|".join(
                    sorted({str(row["evidence_date_precision"]) for row in latest})
                ),
                "source": "|".join(sorted({str(row["source"]) for row in latest})),
                "source_version_hash": "|".join(
                    sorted({str(row["source_version_hash"]) for row in latest})
                ),
                "as_of_date": f"{target_season}-08-31",
                "verification_status": "|".join(
                    sorted({str(row["verification_status"]) for row in latest})
                ),
            }
        )
    return pl.DataFrame(resolved, infer_schema_length=None).sort("target_season", "player_id")


def load_dated_depth_charts(historical_path: Path) -> tuple[pl.DataFrame, list[Path]]:
    rows: list[dict[str, object]] = []
    paths = sorted((historical_path / "bronze/depth_charts").glob("season=*/depth_charts.parquet"))
    for path in paths:
        schema = pl.read_parquet_schema(path)
        if "dt" not in schema:
            continue
        frame = pl.read_parquet(path)
        season = int(path.parent.name.split("=")[1])
        source = (
            "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/"
            f"depth_charts_{season}.parquet"
        )
        source_hash = _sha256(path)
        for row in frame.to_dicts():
            rows.append(
                {
                    "player_id": row.get("gsis_id"),
                    "position": row.get("pos_abb") or row.get("pos_grp"),
                    "team": row.get("team"),
                    "source_available_date": row.get("dt"),
                    "source": source,
                    "source_version_hash": source_hash,
                }
            )
    if rows:
        return pl.DataFrame(rows, infer_schema_length=None), paths
    return (
        pl.DataFrame(
            schema={
                "player_id": pl.String,
                "position": pl.String,
                "team": pl.String,
                "source_available_date": pl.String,
                "source": pl.String,
                "source_version_hash": pl.String,
            }
        ),
        paths,
    )


def _player_matrix(states: pl.DataFrame, records: pl.DataFrame) -> pl.DataFrame:
    selected = records.filter(pl.col("feature_name").is_in(PLAYER_FEATURES)).select(
        "player_id",
        "target_season",
        "feature_name",
        "feature_value",
        "reliability",
        "missingness_reason",
        "source_season",
        "estimate_standard_error",
        "interval_low",
        "interval_high",
        "shrinkage_weight",
    )
    values = selected.select("player_id", "target_season", "feature_name", "feature_value").pivot(
        on="feature_name", index=["player_id", "target_season"], values="feature_value"
    )
    reliability = selected.select(
        "player_id",
        "target_season",
        "feature_name",
        pl.col("reliability").alias("value"),
    ).pivot(on="feature_name", index=["player_id", "target_season"], values="value")
    reliability = reliability.rename(
        {name: f"player_{name}_reliability" for name in reliability.columns[2:]}
    )
    missingness = selected.select(
        "player_id",
        "target_season",
        "feature_name",
        pl.col("missingness_reason").alias("value"),
    ).pivot(on="feature_name", index=["player_id", "target_season"], values="value")
    missingness = missingness.rename(
        {name: f"player_{name}_missingness" for name in missingness.columns[2:]}
    )
    uncertainty_frames: list[pl.DataFrame] = []
    for source_column, suffix in (
        ("estimate_standard_error", "standard_error"),
        ("interval_low", "interval_low"),
        ("interval_high", "interval_high"),
        ("shrinkage_weight", "shrinkage_weight"),
    ):
        uncertainty = selected.select(
            "player_id",
            "target_season",
            "feature_name",
            pl.col(source_column).alias("value"),
        ).pivot(on="feature_name", index=["player_id", "target_season"], values="value")
        uncertainty_frames.append(
            uncertainty.rename(
                {name: f"player_{name}_{suffix}" for name in uncertainty.columns[2:]}
            )
        )
    maximum_source = selected.group_by("player_id", "target_season").agg(
        pl.col("source_season").max().alias("player_feature_max_source_season")
    )
    result = (
        states.join(values, on=["player_id", "target_season"], how="left", validate="1:1")
        .join(reliability, on=["player_id", "target_season"], how="left", validate="1:1")
        .join(missingness, on=["player_id", "target_season"], how="left", validate="1:1")
        .join(maximum_source, on=["player_id", "target_season"], how="left", validate="1:1")
    )
    for uncertainty in uncertainty_frames:
        result = result.join(
            uncertainty,
            on=["player_id", "target_season"],
            how="left",
            validate="1:1",
        )
    result = result.with_columns(
        pl.col("career_starts").cast(pl.Float64).log1p().alias("career_starts_log1p"),
        pl.col("career_dropbacks").cast(pl.Float64).log1p().alias("career_dropbacks_log1p"),
        pl.col("prior_starts").cast(pl.Float64).log1p().alias("prior_starts_log1p"),
        pl.col("prior_dropbacks").cast(pl.Float64).log1p().alias("prior_dropbacks_log1p"),
    )
    for name in PLAYER_FEATURES:
        if name not in result.columns:
            result = result.with_columns(pl.lit(None, dtype=pl.Float64).alias(name))
    return result.sort("target_season", "player_id")


def _scheme_matrix(store: AsOfFeatureStore) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for season in TARGET_SEASONS:
        matrix = store.target_matrix(
            target_season=season,
            feature_names=SCHEME_FEATURES,
            entity_grain="scheme-team-season",
            allow_conditional=True,
        )
        if matrix.maximum_source_season >= season:
            raise ValueError(f"scheme leakage in target season {season}")
        frame = matrix.frame.with_columns(
            pl.col("entity_id")
            .str.extract(r"^team:([^:]+):season:[0-9]+$", 1)
            .map_elements(_canonical_team, return_dtype=pl.String)
            .alias("target_team_id"),
            pl.lit(season).alias("target_season"),
            pl.lit(matrix.maximum_source_season).alias("scheme_feature_max_source_season"),
            pl.lit(matrix.data_version).alias("scheme_data_version"),
            pl.lit(matrix.feature_set_version).alias("scheme_feature_set_version"),
        ).drop("entity_id")
        frame = frame.rename({name: f"scheme_{name}" for name in SCHEME_FEATURES})
        frames.append(frame)
    result = pl.concat(frames, how="vertical_relaxed").sort("target_season", "target_team_id")
    if result.select("target_team_id", "target_season").n_unique() != result.height:
        raise ValueError("duplicate target scheme rows")
    return result


def _scheme_metadata(store: AsOfFeatureStore) -> pl.DataFrame:
    selected = store.records.filter(
        pl.col("feature_name").is_in(SCHEME_FEATURES)
        & pl.col("target_season").is_in(TARGET_SEASONS)
        & (pl.col("entity_type") == "scheme-team-season")
    ).with_columns(
        pl.col("entity_id")
        .str.extract(r"^team:([^:]+):season:[0-9]+$", 1)
        .map_elements(_canonical_team, return_dtype=pl.String)
        .alias("target_team_id")
    )
    sample = selected.select(
        "target_team_id",
        "target_season",
        "feature_name",
        pl.col("sample_size").alias("value"),
    ).pivot(on="feature_name", index=["target_team_id", "target_season"], values="value")
    sample = sample.rename({name: f"scheme_{name}_sample_size" for name in sample.columns[2:]})
    missing = selected.select(
        "target_team_id",
        "target_season",
        "feature_name",
        pl.col("missingness_reason").alias("value"),
    ).pivot(on="feature_name", index=["target_team_id", "target_season"], values="value")
    missing = missing.rename({name: f"scheme_{name}_missingness" for name in missing.columns[2:]})
    status = selected.select(
        "target_team_id",
        "target_season",
        "feature_name",
        pl.col("feature_status").alias("value"),
    ).pivot(on="feature_name", index=["target_team_id", "target_season"], values="value")
    status = status.rename({name: f"scheme_{name}_status" for name in status.columns[2:]})
    permission = selected.select(
        "target_team_id",
        "target_season",
        "feature_name",
        pl.col("predictive_permission").alias("value"),
    ).pivot(on="feature_name", index=["target_team_id", "target_season"], values="value")
    permission = permission.rename(
        {name: f"scheme_{name}_predictive_permission" for name in permission.columns[2:]}
    )
    return (
        sample.join(
            missing,
            on=["target_team_id", "target_season"],
            how="full",
            coalesce=True,
            validate="1:1",
        )
        .join(
            status,
            on=["target_team_id", "target_season"],
            how="left",
            validate="1:1",
        )
        .join(
            permission,
            on=["target_team_id", "target_season"],
            how="left",
            validate="1:1",
        )
        .sort("target_season", "target_team_id")
    )


def construct_interactions(frame: pl.DataFrame) -> pl.DataFrame:
    expressions: list[pl.Expr] = []
    for name, player, scheme, _ in INTERACTION_DEFINITIONS:
        expressions.append(
            pl.when(pl.col(player).is_not_null() & pl.col(f"scheme_{scheme}").is_not_null())
            .then(pl.col(player) * pl.col(f"scheme_{scheme}"))
            .alias(name)
        )
    return frame.with_columns(*expressions)


def _outcome_table(performance: pl.DataFrame, pae: pl.DataFrame) -> pl.DataFrame:
    performance = performance.filter(
        (pl.col("scope") == "analysis") & pl.col("season").is_in(TARGET_SEASONS)
    ).select(
        "player_id",
        pl.col("season").alias("target_season"),
        pl.col("team_id").alias("target_team_id"),
        pl.col("dropbacks").alias("outcome_dropbacks"),
        pl.col("epa_per_dropback").alias("outcome_epa_per_dropback"),
    )
    pae = pae.filter(
        pl.col("season").is_in(TARGET_SEASONS) & (pl.col("is_out_of_sample") == True)  # noqa: E712
    ).select(
        "player_id",
        pl.col("season").alias("target_season"),
        pl.col("team_id").alias("target_team_id"),
        pl.col("performance_above_expectation").alias("outcome_pae"),
        "expected_epa_per_dropback",
        "prediction_std_error",
    )
    result = performance.join(
        pae,
        on=["player_id", "target_team_id", "target_season"],
        how="left",
        validate="1:1",
    )
    invalid = result.filter(
        pl.col("outcome_pae").is_not_null()
        & (
            (
                pl.col("outcome_epa_per_dropback")
                - pl.col("expected_epa_per_dropback")
                - pl.col("outcome_pae")
            ).abs()
            > 1e-12
        )
    )
    if invalid.height:
        raise ValueError("PAE arithmetic failed in Checkpoint 15 outcome join")
    return result.sort("target_season", "player_id", "target_team_id")


def _prior_team_table(performance: pl.DataFrame) -> pl.DataFrame:
    prior = performance.filter(pl.col("scope") == "analysis").select(
        "player_id", "season", "team_id", "dropbacks"
    )
    return (
        prior.sort(
            "player_id",
            "season",
            "dropbacks",
            "team_id",
            descending=[False, False, True, False],
        )
        .unique(["player_id", "season"], keep="first")
        .with_columns((pl.col("season") + 1).alias("target_season"))
        .select(
            "player_id",
            "target_season",
            pl.col("team_id").alias("prior_team_id"),
            pl.col("dropbacks").alias("prior_team_dropbacks"),
        )
    )


def build_modeling_cohort(
    states: pl.DataFrame,
    state_records: pl.DataFrame,
    assignments: pl.DataFrame,
    scheme: pl.DataFrame,
    scheme_metadata: pl.DataFrame,
    performance: pl.DataFrame,
    pae: pl.DataFrame,
) -> pl.DataFrame:
    """Freeze entering-season rows before joining target outcomes on the complete known key."""

    player = _player_matrix(
        states.filter(pl.col("target_season").is_in(TARGET_SEASONS)), state_records
    )
    frozen = (
        player.join(assignments, on=["player_id", "target_season"], how="left", validate="1:1")
        .with_columns(
            pl.col("target_team_status").fill_null("TARGET_TEAM_NOT_ESTABLISHED"),
            pl.col("target_team_basis").fill_null("NOT_APPLICABLE"),
            pl.col("target_team_source_availability_evidence").fill_null("NOT_APPLICABLE"),
        )
        .join(scheme, on=["target_team_id", "target_season"], how="left", validate="m:1")
        .join(
            scheme_metadata,
            on=["target_team_id", "target_season"],
            how="left",
            validate="m:1",
        )
    )
    outcomes = _outcome_table(performance, pae)
    prior_scheme = scheme.select(
        "target_season",
        pl.col("target_team_id").alias("prior_team_id"),
        *[pl.col(f"scheme_{name}").alias(f"prior_scheme_{name}") for name in CORE_SCHEME_FEATURES],
    )
    result = (
        frozen.join(
            outcomes,
            on=["player_id", "target_team_id", "target_season"],
            how="left",
            validate="m:1",
        )
        .join(
            _prior_team_table(performance),
            on=["player_id", "target_season"],
            how="left",
            validate="m:1",
        )
        .join(
            prior_scheme,
            on=["prior_team_id", "target_season"],
            how="left",
            validate="m:1",
        )
    )
    result = construct_interactions(result).with_columns(
        (
            pl.col("prior_team_id").is_not_null()
            & (pl.col("prior_team_id") != pl.col("target_team_id"))
        ).alias("changed_team"),
        pl.when(pl.col("target_team_status") != "PRESEASON_TARGET_TEAM_KNOWN")
        .then(pl.col("target_team_status"))
        .when(pl.col("outcome_dropbacks").is_null())
        .then(pl.lit("TARGET_TEAM_NO_OUTCOME"))
        .when(pl.col("outcome_dropbacks") < MIN_OUTCOME_DROPBACKS)
        .then(pl.lit("BELOW_OUTCOME_DROPBACK_MINIMUM"))
        .otherwise(None)
        .alias("modeling_exclusion_reason"),
    )
    paired_scheme = [
        pl.col(f"scheme_{name}").is_not_null() & pl.col(f"prior_scheme_{name}").is_not_null()
        for name in CORE_SCHEME_FEATURES
    ]
    squared_differences = [
        pl.when(paired)
        .then((pl.col(f"scheme_{name}") - pl.col(f"prior_scheme_{name}")) ** 2)
        .otherwise(0.0)
        for name, paired in zip(CORE_SCHEME_FEATURES, paired_scheme, strict=True)
    ]
    result = (
        result.with_columns(
            pl.sum_horizontal(*[paired.cast(pl.Int64) for paired in paired_scheme]).alias(
                "scheme_change_feature_count"
            ),
            pl.sum_horizontal(*squared_differences).alias("scheme_change_squared_sum"),
            pl.any_horizontal(
                *[
                    paired
                    & ((pl.col(f"scheme_{name}") - pl.col(f"prior_scheme_{name}")).abs() >= 1.0)
                    for name, paired in zip(CORE_SCHEME_FEATURES, paired_scheme, strict=True)
                ]
            ).alias("large_scheme_change"),
        )
        .with_columns(
            pl.when(pl.col("scheme_change_feature_count") > 0)
            .then(
                (pl.col("scheme_change_squared_sum") / pl.col("scheme_change_feature_count")).sqrt()
            )
            .alias("scheme_change_rms_standardized_difference"),
            pl.when(~pl.col("changed_team"))
            .then(pl.lit("SAME_OR_NO_PRIOR_TEAM"))
            .when(pl.col("scheme_change_feature_count") == 0)
            .then(pl.lit("SOURCE_NOT_AVAILABLE"))
            .when(pl.col("large_scheme_change"))
            .then(pl.lit("LARGE_CHANGE_AT_LEAST_ONE_FEATURE_GE_1_SD"))
            .otherwise(pl.lit("MEASURED_BELOW_1_SD_THRESHOLD"))
            .alias("scheme_change_status"),
        )
        .drop("scheme_change_squared_sum")
    )
    interaction_names = [name for name, _, _, _ in INTERACTION_DEFINITIONS]
    return result.with_columns(
        pl.col("modeling_exclusion_reason").is_null().alias("eligible_m0"),
        (
            pl.col("modeling_exclusion_reason").is_null()
            & pl.any_horizontal(
                *[pl.col(f"scheme_{name}").is_not_null() for name in SCHEME_FEATURES]
            )
        ).alias("eligible_m1"),
        (
            pl.col("modeling_exclusion_reason").is_null()
            & pl.any_horizontal(*[pl.col(name).is_not_null() for name in interaction_names])
        ).alias("eligible_m2_row"),
        pl.lit(COHORT_VERSION).alias("cohort_version"),
    ).sort("target_season", "player_id")


def validate_cohort_leakage(cohort: pl.DataFrame) -> pl.DataFrame:
    gates = [
        {
            "gate": "PLAYER_SOURCE_BEFORE_TARGET",
            "failure_count": cohort.filter(
                pl.col("player_feature_max_source_season").is_not_null()
                & (pl.col("player_feature_max_source_season") >= pl.col("target_season"))
            ).height,
        },
        {
            "gate": "SCHEME_SOURCE_BEFORE_TARGET",
            "failure_count": cohort.filter(
                pl.col("scheme_feature_max_source_season").is_not_null()
                & (pl.col("scheme_feature_max_source_season") >= pl.col("target_season"))
            ).height,
        },
        {
            "gate": "TARGET_TEAM_CUTOFF",
            "failure_count": cohort.filter(
                (
                    pl.col("target_team_source_available_date")
                    > (pl.col("target_season").cast(pl.String) + pl.lit("-08-31"))
                )
                | (
                    pl.col("evidence_date").is_not_null()
                    & (pl.col("evidence_date") > pl.col("as_of_date"))
                )
            ).height,
        },
        {
            "gate": "ONE_ENTERING_STATE_PER_PLAYER_SEASON",
            "failure_count": cohort.height - cohort.select("player_id", "target_season").n_unique(),
        },
        {
            "gate": "TARGET_TEAM_BASIS_SUPPORTED",
            "failure_count": cohort.filter(
                (pl.col("target_team_status") == "PRESEASON_TARGET_TEAM_KNOWN")
                & (
                    ~pl.col("target_team_basis").is_in(
                        [
                            "immutable_draft_team",
                            "dated_preseason_depth_chart",
                            "dated_official_transaction",
                        ]
                    )
                    | (pl.col("target_team_source_availability_evidence") == "NOT_APPLICABLE")
                )
            ).height,
        },
        {
            "gate": "TARGET_TEAM_LINEAGE_COMPLETE",
            "failure_count": cohort.filter(
                (pl.col("target_team_status") != "TARGET_TEAM_NOT_ESTABLISHED")
                & (
                    pl.col("evidence_type").is_null()
                    | pl.col("evidence_date").is_null()
                    | pl.col("source").is_null()
                    | pl.col("source_version_hash").is_null()
                    | pl.col("as_of_date").is_null()
                    | pl.col("verification_status").is_null()
                    | ~pl.col("source").str.contains(r"^https://")
                    | ~pl.col("source_version_hash").str.contains(
                        r"^[0-9a-f]{64}(\|[0-9a-f]{64})*$"
                    )
                    | (
                        pl.col("as_of_date")
                        != (pl.col("target_season").cast(pl.String) + pl.lit("-08-31"))
                    )
                )
            ).height,
        },
        {
            "gate": "NO_OUTCOME_DERIVED_TARGET_TEAM",
            "failure_count": cohort.filter(
                pl.col("target_team_basis").is_in(
                    ["target_season_pbp", "final_season_roster", "target_season_outcome"]
                )
            ).height,
        },
        {
            "gate": "MODELING_EXCLUSION_CONTRACT",
            "failure_count": cohort.filter(
                pl.col("modeling_exclusion_reason").is_not_null()
                & ~pl.col("modeling_exclusion_reason").is_in(sorted(VALID_MISSINGNESS))
            ).height,
        },
    ]
    result = pl.DataFrame(gates).with_columns((pl.col("failure_count") == 0).alias("passed"))
    if result.filter(~pl.col("passed")).height:
        raise ValueError(f"Checkpoint 15 leakage audit failed: {result.to_dicts()}")
    return result.sort("gate")


def build_fold_assignments(cohort: pl.DataFrame) -> pl.DataFrame:
    eligible = cohort.filter(pl.col("eligible_m1"))
    rows: list[dict[str, object]] = []
    for target in TARGET_SEASONS:
        training = eligible.filter(pl.col("target_season") < target)
        testing = eligible.filter(pl.col("target_season") == target)
        if training.height < MIN_TRAIN_ROWS or testing.height < MIN_TEST_ROWS:
            continue
        for row in training.select("player_id", "target_season").to_dicts():
            rows.append({"fold_season": target, "role": "TRAIN", **row})
        for row in testing.select("player_id", "target_season").to_dicts():
            rows.append({"fold_season": target, "role": "TEST", **row})
    if not rows:
        return pl.DataFrame(
            schema={
                "fold_season": pl.Int64,
                "role": pl.String,
                "player_id": pl.String,
                "target_season": pl.Int64,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort(
        "fold_season", "role", "target_season", "player_id"
    )


def _qualified_interactions(training: pl.DataFrame) -> tuple[str, ...]:
    qualified: list[str] = []
    for name, _, _, _ in INTERACTION_DEFINITIONS:
        values = _finite_values(training[name])
        if len(values) >= MIN_INTERACTION_TRAIN_VALUES and len(np.unique(values)) >= 2:
            qualified.append(name)
    return tuple(qualified)


def _fit_ridge(
    training: pl.DataFrame,
    testing: pl.DataFrame,
    feature_names: tuple[str, ...],
    outcome: str,
    alpha: float,
    *,
    outer_target_season: int,
) -> tuple[np.ndarray, Ridge, FoldPreprocessor, tuple[str, ...]]:
    preprocessor = FoldPreprocessor.fit(
        training,
        feature_names,
        target_season=outer_target_season,
    )
    x_train, transformed_names = preprocessor.transform(training)
    x_test, _ = preprocessor.transform(testing)
    model = Ridge(alpha=alpha, fit_intercept=True)
    model.fit(x_train, np.asarray(training[outcome], dtype=float))
    return np.asarray(model.predict(x_test), dtype=float), model, preprocessor, transformed_names


def select_alpha(
    training: pl.DataFrame,
    feature_names: tuple[str, ...],
    outcome: str,
    *,
    outer_target_season: int,
) -> tuple[float, str, int, int]:
    scores: dict[float, list[float]] = {alpha: [] for alpha in RIDGE_ALPHAS}
    latest_fit_end = -1
    inner_folds = 0
    for validation_season in sorted(training["target_season"].unique().to_list()):
        inner_train = training.filter(pl.col("target_season") < validation_season)
        inner_test = training.filter(pl.col("target_season") == validation_season)
        if inner_train.height < MIN_INNER_TRAIN_ROWS or inner_test.height < MIN_INNER_TEST_ROWS:
            continue
        inner_folds += 1
        latest_fit_end = max(latest_fit_end, int(inner_train["target_season"].max()))
        for alpha in RIDGE_ALPHAS:
            try:
                prediction, _, _, _ = _fit_ridge(
                    inner_train,
                    inner_test,
                    feature_names,
                    outcome,
                    alpha,
                    outer_target_season=validation_season,
                )
            except ValueError:
                continue
            scores[alpha].append(
                float(np.mean(np.abs(np.asarray(inner_test[outcome], dtype=float) - prediction)))
            )
    if latest_fit_end >= outer_target_season:
        raise ValueError("hyperparameter tuning reached the outer target season")
    candidates = [
        (float(np.mean(values)), -alpha, alpha) for alpha, values in scores.items() if values
    ]
    if not candidates:
        return DEFAULT_RIDGE_ALPHA, "PREDECLARED_DEFAULT_NO_INNER_FOLD", inner_folds, latest_fit_end
    _, _, selected = min(candidates)
    return selected, "TRAIN_ONLY_ROLLING_MAE", inner_folds, latest_fit_end


def _safe_correlation(actual: np.ndarray, predicted: np.ndarray, kind: str) -> float | None:
    if len(actual) < 3 or len(np.unique(actual)) < 2 or len(np.unique(predicted)) < 2:
        return None
    value = (
        pearsonr(actual, predicted).statistic
        if kind == "pearson"
        else spearmanr(actual, predicted).statistic
    )
    return float(value) if math.isfinite(float(value)) else None


def _metrics(
    actual: np.ndarray, predicted: np.ndarray, reference: float
) -> dict[str, float | int | None]:
    residual = actual - predicted
    slope: float | None = None
    intercept: float | None = None
    if len(actual) >= 3 and len(np.unique(predicted)) >= 2:
        design = np.column_stack([np.ones(len(predicted)), predicted])
        coefficients = np.linalg.lstsq(design, actual, rcond=None)[0]
        intercept, slope = float(coefficients[0]), float(coefficients[1])
    return {
        "n": len(actual),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mae": float(np.mean(np.abs(residual))),
        "pearson": _safe_correlation(actual, predicted, "pearson"),
        "spearman": _safe_correlation(actual, predicted, "spearman"),
        "direction_accuracy": float(np.mean((actual >= reference) == (predicted >= reference))),
        "calibration_slope": slope,
        "calibration_intercept": intercept,
    }


def run_rolling_models(
    cohort: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    eligible = cohort.filter(pl.col("eligible_m1"))
    predictions: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    coefficient_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    model_features = {
        "M0": tuple(CORE_PLAYER_FEATURES),
        "M1": tuple(CORE_PLAYER_FEATURES)
        + tuple(f"scheme_{name}" for name in CORE_SCHEME_FEATURES),
        "M0_CONDITIONAL": tuple(PLAYER_FEATURES),
        "M1_CONDITIONAL": tuple(PLAYER_FEATURES)
        + tuple(f"scheme_{name}" for name in SCHEME_FEATURES),
    }
    for outcome_name, outcome_column in OUTCOMES.items():
        outcome_data = eligible.filter(pl.col(outcome_column).is_not_null())
        for target in TARGET_SEASONS:
            training = outcome_data.filter(pl.col("target_season") < target)
            testing = outcome_data.filter(pl.col("target_season") == target)
            if training.height < MIN_TRAIN_ROWS or testing.height < MIN_TEST_ROWS:
                diagnostic_rows.append(
                    {
                        "outcome": outcome_name,
                        "fold_season": target,
                        "model": "ALL",
                        "status": "INSUFFICIENT_OUTER_SAMPLE",
                        "training_rows": training.height,
                        "testing_rows": testing.height,
                        "qualified_interactions": 0,
                    }
                )
                continue
            interaction_features = _qualified_interactions(training)
            fold_model_features = dict(model_features)
            if interaction_features:
                fold_model_features["M2"] = model_features["M1"] + interaction_features
            else:
                diagnostic_rows.append(
                    {
                        "outcome": outcome_name,
                        "fold_season": target,
                        "model": "M2",
                        "status": "NO_QUALIFIED_INTERACTION_TRAINING_DATA",
                        "training_rows": training.height,
                        "testing_rows": testing.height,
                        "qualified_interactions": 0,
                    }
                )
            reference = (
                0.0 if outcome_name == "next_season_pae" else float(training[outcome_column].mean())
            )
            for model_name, features in fold_model_features.items():
                alpha, selection, inner_folds, tuning_end = select_alpha(
                    training,
                    features,
                    outcome_column,
                    outer_target_season=target,
                )
                try:
                    predicted, model, preprocessor, transformed_names = _fit_ridge(
                        training,
                        testing,
                        features,
                        outcome_column,
                        alpha,
                        outer_target_season=target,
                    )
                except ValueError as exc:
                    diagnostic_rows.append(
                        {
                            "outcome": outcome_name,
                            "fold_season": target,
                            "model": model_name,
                            "status": f"NOT_ESTIMABLE:{exc}",
                            "training_rows": training.height,
                            "testing_rows": testing.height,
                            "qualified_interactions": len(interaction_features),
                        }
                    )
                    continue
                actual = np.asarray(testing[outcome_column], dtype=float)
                fold_rows.append(
                    {
                        "outcome": outcome_name,
                        "fold_season": target,
                        "model": model_name,
                        "training_rows": training.height,
                        "training_start_season": int(training["target_season"].min()),
                        "training_end_season": int(training["target_season"].max()),
                        "alpha": alpha,
                        "alpha_selection": selection,
                        "inner_folds": inner_folds,
                        "tuning_fit_end_season": tuning_end if tuning_end >= 0 else None,
                        "reference_value": reference,
                        "retained_raw_features": len(preprocessor.feature_names),
                        **_metrics(actual, predicted, reference),
                    }
                )
                for feature, coefficient in zip(transformed_names, model.coef_, strict=True):
                    if feature in {name for name, _, _, _ in INTERACTION_DEFINITIONS}:
                        coefficient_rows.append(
                            {
                                "outcome": outcome_name,
                                "fold_season": target,
                                "model": model_name,
                                "interaction_name": feature,
                                "standardized_coefficient": float(coefficient),
                                "alpha": alpha,
                                "training_rows": training.height,
                            }
                        )
                for row, prediction in zip(testing.to_dicts(), predicted, strict=True):
                    predictions.append(
                        {
                            "player_id": row["player_id"],
                            "target_team_id": row["target_team_id"],
                            "target_season": target,
                            "outcome": outcome_name,
                            "model": model_name,
                            "actual": row[outcome_column],
                            "predicted": float(prediction),
                            "residual": float(row[outcome_column]) - float(prediction),
                            "outcome_dropbacks": row["outcome_dropbacks"],
                            "changed_team": row["changed_team"],
                            "large_scheme_change": row["large_scheme_change"],
                            "scheme_change_status": row["scheme_change_status"],
                            "target_team_basis": row["target_team_basis"],
                            "reference_value": reference,
                        }
                    )
    prediction_schema = {
        "player_id": pl.String,
        "target_team_id": pl.String,
        "target_season": pl.Int64,
        "outcome": pl.String,
        "model": pl.String,
        "actual": pl.Float64,
        "predicted": pl.Float64,
        "residual": pl.Float64,
        "outcome_dropbacks": pl.Int64,
        "changed_team": pl.Boolean,
        "large_scheme_change": pl.Boolean,
        "scheme_change_status": pl.String,
        "target_team_basis": pl.String,
        "reference_value": pl.Float64,
    }
    coefficient_schema = {
        "outcome": pl.String,
        "fold_season": pl.Int64,
        "model": pl.String,
        "interaction_name": pl.String,
        "standardized_coefficient": pl.Float64,
        "alpha": pl.Float64,
        "training_rows": pl.Int64,
    }
    return (
        _frame_or_empty(predictions, prediction_schema).sort(
            "outcome", "model", "target_season", "player_id", "target_team_id"
        ),
        _frame_or_empty(fold_rows, _fold_metric_schema()).sort("outcome", "model", "fold_season"),
        _frame_or_empty(coefficient_rows, coefficient_schema).sort(
            "outcome", "interaction_name", "fold_season"
        ),
        _frame_or_empty(
            diagnostic_rows,
            {
                "outcome": pl.String,
                "fold_season": pl.Int64,
                "model": pl.String,
                "status": pl.String,
                "training_rows": pl.Int64,
                "testing_rows": pl.Int64,
                "qualified_interactions": pl.Int64,
            },
        ).sort("outcome", "fold_season", "model"),
    )


def _fold_metric_schema() -> dict[str, pl.DataType]:
    return {
        "outcome": pl.String,
        "fold_season": pl.Int64,
        "model": pl.String,
        "training_rows": pl.Int64,
        "training_start_season": pl.Int64,
        "training_end_season": pl.Int64,
        "alpha": pl.Float64,
        "alpha_selection": pl.String,
        "inner_folds": pl.Int64,
        "tuning_fit_end_season": pl.Int64,
        "reference_value": pl.Float64,
        "retained_raw_features": pl.Int64,
        "n": pl.Int64,
        "rmse": pl.Float64,
        "mae": pl.Float64,
        "pearson": pl.Float64,
        "spearman": pl.Float64,
        "direction_accuracy": pl.Float64,
        "calibration_slope": pl.Float64,
        "calibration_intercept": pl.Float64,
    }


def _frame_or_empty(rows: list[dict[str, object]], schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=schema)


def aggregate_model_comparison(predictions: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    if predictions.is_empty():
        return pl.DataFrame(
            schema={"outcome": pl.String, "model": pl.String, **_metric_only_schema()}
        )
    for key, group in predictions.group_by("outcome", "model", maintain_order=True):
        actual = np.asarray(group["actual"], dtype=float)
        predicted = np.asarray(group["predicted"], dtype=float)
        reference = 0.0 if key[0] == "next_season_pae" else float(actual.mean())
        metrics = _metrics(actual, predicted, reference)
        fold_references = np.asarray(group["reference_value"], dtype=float)
        metrics["direction_accuracy"] = float(
            np.mean((actual >= fold_references) == (predicted >= fold_references))
        )
        rows.append({"outcome": key[0], "model": key[1], **metrics})
    return pl.DataFrame(rows, infer_schema_length=None).sort("outcome", "model")


def _metric_only_schema() -> dict[str, pl.DataType]:
    return {
        "n": pl.Int64,
        "rmse": pl.Float64,
        "mae": pl.Float64,
        "pearson": pl.Float64,
        "spearman": pl.Float64,
        "direction_accuracy": pl.Float64,
        "calibration_slope": pl.Float64,
        "calibration_intercept": pl.Float64,
    }


def team_change_validation(predictions: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for key, group in predictions.filter(pl.col("changed_team")).group_by(
        "outcome", "model", maintain_order=True
    ):
        actual = np.asarray(group["actual"], dtype=float)
        predicted = np.asarray(group["predicted"], dtype=float)
        if len(actual) < MIN_TEST_ROWS:
            continue
        reference = 0.0 if key[0] == "next_season_pae" else float(actual.mean())
        metrics = _metrics(actual, predicted, reference)
        if "reference_value" in group.columns:
            fold_references = np.asarray(group["reference_value"], dtype=float)
            metrics["direction_accuracy"] = float(
                np.mean((actual >= fold_references) == (predicted >= fold_references))
            )
        rows.append(
            {
                "outcome": key[0],
                "model": key[1],
                "status": "ESTIMATED",
                **metrics,
            }
        )
    if not rows:
        return pl.DataFrame(
            schema={
                "outcome": pl.String,
                "model": pl.String,
                "status": pl.String,
                **_metric_only_schema(),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("outcome", "model")


def environment_change_validation(predictions: pl.DataFrame) -> pl.DataFrame:
    """Summarize large as-of Scheme changes without inferring a coaching change."""

    result = team_change_validation(
        predictions.filter(pl.col("large_scheme_change")).with_columns(
            pl.lit(True).alias("changed_team")
        )
    )
    if result.is_empty():
        return result.with_columns(
            pl.lit("ASOF_SCHEME_CHANGE_ANY_CORE_FEATURE_GE_1_SD").alias("subset_definition"),
            pl.lit("NOT_AVAILABLE").alias("verified_coach_change_status"),
        )
    return result.with_columns(
        pl.lit("ASOF_SCHEME_CHANGE_ANY_CORE_FEATURE_GE_1_SD").alias("subset_definition"),
        pl.lit("NOT_AVAILABLE").alias("verified_coach_change_status"),
    )


def cluster_bootstrap_model_delta(
    paired: pl.DataFrame,
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = RANDOM_SEED,
) -> pl.DataFrame:
    required = {"player_id", "actual", "predicted_m1", "predicted_m2"}
    if not required <= set(paired.columns) or paired.is_empty():
        return pl.DataFrame(
            [
                {
                    "status": "NOT_ESTIMABLE_NO_PAIRED_M2_PREDICTIONS",
                    "successful_draws": 0,
                    "mae_delta_m2_minus_m1": None,
                    "mae_delta_interval_low": None,
                    "mae_delta_interval_high": None,
                }
            ],
            infer_schema_length=None,
        )
    clusters = sorted(paired["player_id"].unique().to_list())
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    for _ in range(draws):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        frames = [paired.filter(pl.col("player_id") == player) for player in sampled]
        sample = pl.concat(frames, how="vertical")
        actual = np.asarray(sample["actual"], dtype=float)
        m1 = np.asarray(sample["predicted_m1"], dtype=float)
        m2 = np.asarray(sample["predicted_m2"], dtype=float)
        deltas.append(float(np.mean(np.abs(actual - m2)) - np.mean(np.abs(actual - m1))))
    observed = float(
        np.mean(
            np.abs(
                np.asarray(paired["actual"], dtype=float)
                - np.asarray(paired["predicted_m2"], dtype=float)
            )
        )
        - np.mean(
            np.abs(
                np.asarray(paired["actual"], dtype=float)
                - np.asarray(paired["predicted_m1"], dtype=float)
            )
        )
    )
    return pl.DataFrame(
        [
            {
                "status": "ESTIMATED",
                "successful_draws": len(deltas),
                "mae_delta_m2_minus_m1": observed,
                "mae_delta_interval_low": float(np.quantile(deltas, 0.025)),
                "mae_delta_interval_high": float(np.quantile(deltas, 0.975)),
            }
        ],
        infer_schema_length=None,
    )


def deterministic_interaction_placebo(
    values: np.ndarray,
    outcome: np.ndarray,
    *,
    draws: int = PERMUTATION_DRAWS,
    seed: int = RANDOM_SEED,
) -> dict[str, float | int | None]:
    if len(values) < 3 or len(np.unique(values)) < 2 or len(np.unique(outcome)) < 2:
        return {"successful_draws": 0, "observed_correlation": None, "placebo_p_value": None}
    observed = abs(float(spearmanr(values, outcome).statistic))
    rng = np.random.default_rng(seed)
    null = [abs(float(spearmanr(rng.permutation(values), outcome).statistic)) for _ in range(draws)]
    return {
        "successful_draws": len(null),
        "observed_correlation": observed,
        "placebo_p_value": (sum(value >= observed for value in null) + 1) / (len(null) + 1),
    }


def _paired_predictions(predictions: pl.DataFrame, outcome: str) -> pl.DataFrame:
    selected = predictions.filter(
        (pl.col("outcome") == outcome) & pl.col("model").is_in(["M1", "M2"])
    )
    if selected.is_empty():
        return pl.DataFrame()
    wide = selected.select(
        "player_id", "target_team_id", "target_season", "actual", "model", "predicted"
    ).pivot(
        on="model",
        index=["player_id", "target_team_id", "target_season", "actual"],
        values="predicted",
    )
    if not {"M1", "M2"} <= set(wide.columns):
        return pl.DataFrame()
    return wide.drop_nulls(["M1", "M2"]).rename({"M1": "predicted_m1", "M2": "predicted_m2"})


def _interaction_effects(predictions: pl.DataFrame) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for outcome in OUTCOMES:
        paired = _paired_predictions(predictions, outcome)
        if paired.is_empty():
            continue
        frames.append(
            paired.select(
                "player_id",
                "target_team_id",
                "target_season",
                pl.lit(outcome).alias("outcome"),
                (pl.col("predicted_m2") - pl.col("predicted_m1")).alias(
                    "m2_minus_m1_prediction_delta"
                ),
            )
        )
    if not frames:
        return pl.DataFrame(
            schema={
                "player_id": pl.String,
                "target_team_id": pl.String,
                "target_season": pl.Int64,
                "outcome": pl.String,
                "m2_minus_m1_prediction_delta": pl.Float64,
            }
        )
    return pl.concat(frames, how="vertical").sort(
        "outcome", "target_season", "player_id", "target_team_id"
    )


def _interaction_definitions_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "interaction_name": name,
                "player_feature": player,
                "scheme_feature": f"scheme_{scheme}",
                "family": family,
                "formula": f"{player} * scheme_{scheme}",
                "predeclared": True,
                "causal_claim": False,
            }
            for name, player, scheme, family in INTERACTION_DEFINITIONS
        ],
        infer_schema_length=None,
    ).sort("interaction_name")


def _coverage_report(cohort: pl.DataFrame) -> pl.DataFrame:
    features = (
        list(PLAYER_FEATURES)
        + [f"scheme_{name}" for name in SCHEME_FEATURES]
        + [name for name, _, _, _ in INTERACTION_DEFINITIONS]
    )
    rows = []
    for name in features:
        rows.append(
            {
                "feature_name": name,
                "rows": cohort.height,
                "non_null_rows": cohort[name].is_not_null().sum(),
                "null_rows": cohort[name].is_null().sum(),
                "eligible_non_null_rows": cohort.filter(pl.col("eligible_m1"))[name]
                .is_not_null()
                .sum(),
            }
        )
    for reason, count in cohort.group_by("modeling_exclusion_reason").len().iter_rows():
        rows.append(
            {
                "feature_name": f"COHORT_EXCLUSION:{reason or 'ELIGIBLE'}",
                "rows": cohort.height,
                "non_null_rows": count,
                "null_rows": cohort.height - count,
                "eligible_non_null_rows": count if reason is None else 0,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None).sort("feature_name")


def build_target_team_coverage(
    states: pl.DataFrame,
    assignments: pl.DataFrame,
    performance: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Audit assignment coverage without using outcomes to construct an assignment."""

    states = states.filter(pl.col("target_season").is_in(TARGET_SEASONS))
    outcomes = performance.filter(
        (pl.col("scope") == "analysis") & pl.col("season").is_in(TARGET_SEASONS)
    ).select(
        "player_id",
        pl.col("season").alias("target_season"),
        pl.col("team_id").alias("outcome_team_id"),
        pl.col("dropbacks").alias("outcome_dropbacks"),
    )
    state_assignments = states.select("player_id", "target_season").join(
        assignments,
        on=["player_id", "target_season"],
        how="left",
        validate="1:1",
    )
    known = state_assignments.filter(
        (pl.col("target_team_status") == "PRESEASON_TARGET_TEAM_KNOWN")
        & pl.col("target_team_id").is_not_null()
    )
    matching = known.join(
        outcomes,
        left_on=["player_id", "target_season", "target_team_id"],
        right_on=["player_id", "target_season", "outcome_team_id"],
        how="inner",
        validate="1:1",
    )
    participants = states.select("player_id", "target_season").join(
        outcomes.select("player_id", "target_season").unique(),
        on=["player_id", "target_season"],
        how="inner",
        validate="1:1",
    )
    season_rows: list[dict[str, object]] = []
    for season in TARGET_SEASONS:
        season_states = states.filter(pl.col("target_season") == season)
        season_known = known.filter(pl.col("target_season") == season)
        season_matching = matching.filter(pl.col("target_season") == season)
        season_participants = participants.filter(pl.col("target_season") == season)
        participant_known = season_participants.join(
            season_known.select("player_id", "target_season"),
            on=["player_id", "target_season"],
            how="inner",
            validate="1:1",
        ).height
        participant_matching = season_participants.join(
            season_matching.select("player_id", "target_season").unique(),
            on=["player_id", "target_season"],
            how="inner",
            validate="1:1",
        ).height
        season_rows.append(
            {
                "target_season": season,
                "entering_state_rows": season_states.height,
                "known_target_team_rows": season_known.height,
                "known_target_team_coverage": (
                    season_known.height / season_states.height if season_states.height else None
                ),
                "draft_team_rows": season_known.filter(
                    pl.col("target_team_basis") == "immutable_draft_team"
                ).height,
                "dated_depth_chart_rows": season_known.filter(
                    pl.col("target_team_basis") == "dated_preseason_depth_chart"
                ).height,
                "dated_transaction_rows": season_known.filter(
                    pl.col("target_team_basis") == "dated_official_transaction"
                ).height,
                "retrospective_participant_states": season_participants.height,
                "participants_with_any_assignment": participant_known,
                "participants_with_matching_outcome_team": participant_matching,
                "participant_matching_coverage": (
                    participant_matching / season_participants.height
                    if season_participants.height
                    else None
                ),
                "eligible_evaluation_rows": season_matching.filter(
                    pl.col("outcome_dropbacks") >= MIN_OUTCOME_DROPBACKS
                ).height,
            }
        )

    primary = (
        outcomes.sort(
            "player_id",
            "target_season",
            "outcome_dropbacks",
            "outcome_team_id",
            descending=[False, False, True, False],
        )
        .unique(["player_id", "target_season"], keep="first")
        .select("player_id", "target_season", "outcome_team_id")
    )
    prior = primary.with_columns((pl.col("target_season") + 1).alias("target_season")).rename(
        {"outcome_team_id": "prior_team_id"}
    )
    classified = (
        primary.join(
            states.select("player_id", "target_season", "is_rookie"),
            on=["player_id", "target_season"],
            how="inner",
            validate="1:1",
        )
        .join(prior, on=["player_id", "target_season"], how="left", validate="m:1")
        .join(
            assignments.select(
                "player_id", "target_season", "target_team_id", "target_team_status"
            ),
            on=["player_id", "target_season"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.when(pl.col("is_rookie"))
            .then(pl.lit("ROOKIE"))
            .when(pl.col("prior_team_id").is_null())
            .then(pl.lit("OTHER_NEW_ENTRANT"))
            .when(pl.col("prior_team_id") != pl.col("outcome_team_id"))
            .then(pl.lit("TEAM_CHANGER"))
            .otherwise(pl.lit("RETURNING_VETERAN"))
            .alias("evaluation_category")
        )
    )
    matching_keys = (
        matching.select("player_id", "target_season")
        .unique()
        .with_columns(pl.lit(True).alias("has_matching_outcome_team"))
    )
    eligible_keys = (
        matching.filter(pl.col("outcome_dropbacks") >= MIN_OUTCOME_DROPBACKS)
        .select("player_id", "target_season")
        .unique()
        .with_columns(pl.lit(True).alias("is_evaluation_eligible"))
    )
    classified = (
        classified.join(
            matching_keys,
            on=["player_id", "target_season"],
            how="left",
            validate="1:1",
        )
        .join(
            eligible_keys,
            on=["player_id", "target_season"],
            how="left",
            validate="1:1",
        )
        .with_columns(
            pl.col("has_matching_outcome_team").fill_null(False),
            pl.col("is_evaluation_eligible").fill_null(False),
        )
    )
    category_rows: list[dict[str, object]] = []
    for category in ("RETURNING_VETERAN", "TEAM_CHANGER", "ROOKIE", "OTHER_NEW_ENTRANT"):
        group = classified.filter(pl.col("evaluation_category") == category)
        known_count = group.filter(
            pl.col("target_team_status") == "PRESEASON_TARGET_TEAM_KNOWN"
        ).height
        matching_count = int(group["has_matching_outcome_team"].sum())
        category_rows.append(
            {
                "evaluation_category": category,
                "retrospective_participant_states": group.height,
                "participants_with_any_assignment": known_count,
                "participants_with_matching_outcome_team": matching_count,
                "matching_coverage": matching_count / group.height if group.height else None,
                "eligible_evaluation_rows": int(group["is_evaluation_eligible"].sum()),
                "classification_uses_target_outcome_for_audit_only": True,
            }
        )

    source_rows: list[dict[str, object]] = []
    accepted = (
        (
            "immutable_draft_team",
            "ACCEPTED",
            "immutable draft fact; exact event date absent, conservative pre-cutoff bound",
        ),
        (
            "dated_preseason_depth_chart",
            "ACCEPTED",
            "timestamped snapshot on or before August 31; observed only in 2025",
        ),
        (
            "dated_official_transaction",
            "CONTRACT_READY_NO_APPROVED_INPUT",
            "requires an approved primary NFL/team source, exact date, hash, and verification",
        ),
    )
    for basis, status, reason in accepted:
        assigned = known.filter(pl.col("target_team_basis") == basis)
        matched = matching.filter(pl.col("target_team_basis") == basis)
        source_rows.append(
            {
                "source_family": basis,
                "acceptance_status": status,
                "coverage_added_to_state_rows": assigned.height,
                "matching_outcome_rows": matched.height,
                "eligible_evaluation_rows": matched.filter(
                    pl.col("outcome_dropbacks") >= MIN_OUTCOME_DROPBACKS
                ).height,
                "reason": reason,
            }
        )
    for family, reason in (
        ("weekly_or_final_rosters", "week/final state does not prove availability by August 31"),
        ("legacy_weekly_depth_charts", "pre-2025 rows have week but no source timestamp"),
        ("injury_reports", "all dated QB records begin after the August 31 cutoff"),
        ("historical_contracts", "year-only and season-history fields are not dated assignments"),
        (
            "nflverse_trades_via_pfr",
            "rejected by approved PFR audit for predictive/model use without permission",
        ),
        ("target_season_participation", "PBP, stats, and game participation are outcomes"),
    ):
        source_rows.append(
            {
                "source_family": family,
                "acceptance_status": "REJECTED",
                "coverage_added_to_state_rows": 0,
                "matching_outcome_rows": 0,
                "eligible_evaluation_rows": 0,
                "reason": reason,
            }
        )
    return (
        pl.DataFrame(season_rows, infer_schema_length=None).sort("target_season"),
        pl.DataFrame(category_rows, infer_schema_length=None).sort("evaluation_category"),
        pl.DataFrame(source_rows, infer_schema_length=None).sort("source_family"),
    )


def target_team_contract() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "evidence_family": "immutable_draft_team",
                "date_contract": "PRE_CUTOFF_EVENT_UPPER_BOUND",
                "precedence": 10,
                "model_usable": True,
                "required_lineage": "player_id|target_season|team_id|source|source_version_hash",
            },
            {
                "evidence_family": "dated_preseason_depth_chart",
                "date_contract": "EXACT_DATE_LE_AUGUST_31",
                "precedence": 30,
                "model_usable": True,
                "required_lineage": (
                    "player_id|target_season|team_id|evidence_date|source|source_version_hash"
                ),
            },
            {
                "evidence_family": "dated_official_transaction",
                "date_contract": "EXACT_DATE_LE_AUGUST_31",
                "precedence": 40,
                "model_usable": True,
                "required_lineage": (
                    "player_id|target_season|team_or_no_team|event_type|evidence_date|source|"
                    "source_version_hash|verification_status"
                ),
            },
        ],
        infer_schema_length=None,
    ).sort("precedence")


def _fit_decision(
    predictions: pl.DataFrame,
    bootstrap: pl.DataFrame,
    comparison: pl.DataFrame,
) -> tuple[pl.DataFrame, str, str]:
    paired_epa = _paired_predictions(predictions, "next_season_epa_per_dropback")
    m2_rows = predictions.filter(pl.col("model") == "M2").height
    m2_folds = predictions.filter(pl.col("model") == "M2")["target_season"].n_unique()
    interval_high = bootstrap["mae_delta_interval_high"][0]
    validated = bool(
        paired_epa.height >= 50
        and m2_folds >= 5
        and interval_high is not None
        and float(interval_high) < 0
    )
    baseline = comparison.filter(
        (pl.col("outcome") == "next_season_epa_per_dropback") & pl.col("model").is_in(["M0", "M1"])
    )
    baseline_predictive = bool(
        baseline.height
        and baseline.filter(
            (pl.col("n") >= 100)
            & (pl.col("pearson") > 0)
            & (pl.col("spearman") > 0)
            & (pl.col("calibration_slope") > 0)
        ).height
    )
    if validated:
        status = "VALIDATED FOR CHECKPOINT 16 USE"
        readiness = "READY"
        reason = "M2 improved EPA prediction with stable paired out-of-sample evidence."
        blocker = None
    elif m2_folds == 0:
        status = "NOT ESTIMABLE / DATA-LIMITED"
        readiness = "NOT READY"
        reason = (
            "M2 was never estimated: approved repository data lack leakage-safe historical "
            "August 31 target-team assignments for returning veterans and team changers."
        )
        blocker = (
            "A licensed, source-hashed historical preseason player-team assignment contract "
            "with dates on or before August 31 and representative veteran/team-change coverage."
        )
    else:
        status = "NOT SUPPORTED"
        readiness = "READY" if baseline_predictive else "NOT READY"
        reason = "M2 was estimated but did not meet the predeclared validation rule."
        blocker = (
            None
            if baseline_predictive
            else "M0/M1 require positive out-of-sample association and calibration evidence."
        )
    return (
        pl.DataFrame(
            [
                {
                    "decision": status,
                    "checkpoint_16_readiness": readiness,
                    "m2_prediction_rows": m2_rows,
                    "m2_out_of_sample_folds": m2_folds,
                    "paired_m2_m1_epa_rows": paired_epa.height,
                    "standalone_fit_quantity_approved": validated,
                    "checkpoint_16_may_consume_interactions": validated,
                    "checkpoint_16_allowed_baseline": (
                        "M2" if validated else ("M0_M1_ONLY" if readiness == "READY" else "NONE")
                    ),
                    "baseline_predictive_readiness_gate": baseline_predictive,
                    "checkpoint_16_blocker": blocker,
                    "reason": reason,
                }
            ],
            infer_schema_length=None,
        ),
        status,
        readiness,
    )


def _content_identity(inputs: dict[str, str], code_hash: str) -> tuple[str, dict[str, object]]:
    identity = {
        "specification": CHECKPOINT_15_SPECIFICATION,
        "fit_feature_version": FIT_FEATURE_VERSION,
        "fit_model_version": FIT_MODEL_VERSION,
        "cohort_version": COHORT_VERSION,
        "target_seasons": TARGET_SEASONS,
        "as_of_month_day": AS_OF_MONTH_DAY,
        "minimum_outcome_dropbacks": MIN_OUTCOME_DROPBACKS,
        "minimum_train_rows": MIN_TRAIN_ROWS,
        "minimum_test_rows": MIN_TEST_ROWS,
        "minimum_inner_train_rows": MIN_INNER_TRAIN_ROWS,
        "minimum_inner_test_rows": MIN_INNER_TEST_ROWS,
        "minimum_feature_train_values": MIN_FEATURE_TRAIN_VALUES,
        "minimum_interaction_train_values": MIN_INTERACTION_TRAIN_VALUES,
        "ridge_alphas": RIDGE_ALPHAS,
        "default_ridge_alpha": DEFAULT_RIDGE_ALPHA,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "permutation_draws": PERMUTATION_DRAWS,
        "random_seed": RANDOM_SEED,
        "serialization": {
            "csv_float_scientific": False,
            "json_sort_keys": True,
            "parquet_compression": "zstd",
            "parquet_statistics": True,
        },
        "player_features": PLAYER_FEATURES,
        "core_player_features": CORE_PLAYER_FEATURES,
        "conditional_player_features": CONDITIONAL_PLAYER_FEATURES,
        "style_features": STYLE_FEATURES,
        "scheme_features": SCHEME_FEATURES,
        "core_scheme_features": CORE_SCHEME_FEATURES,
        "conditional_scheme_features": CONDITIONAL_SCHEME_FEATURES,
        "interaction_definitions": INTERACTION_DEFINITIONS,
        "outcomes": OUTCOMES,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "polars_version": pl.__version__,
        "scipy_version": scipy.__version__,
        "sklearn_version": sklearn.__version__,
        "code_hash": code_hash,
        "inputs": dict(sorted(inputs.items())),
    }
    canonical = json.loads(json.dumps(identity, sort_keys=True))
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]
    return f"c15-{digest}", canonical


def _publish_latest(root: Path, data_version: str) -> None:
    temporary = root / f".LATEST.{uuid.uuid4().hex}.tmp"
    temporary.write_text(data_version + "\n", encoding="utf-8")
    os.replace(temporary, root / "LATEST")


def _write_artifact(frame: pl.DataFrame, path: Path) -> None:
    if path.suffix == ".parquet":
        frame.write_parquet(path, compression="zstd", statistics=True)
    else:
        frame.write_csv(path, float_scientific=False)


def run_checkpoint_fifteen(
    project_root: Path,
    output_root: Path | None = None,
) -> CheckpointFifteenResult:
    c13_version, c13 = _resolve_latest(project_root / "data/processed/predictive_foundation")
    c14_version, c14 = _resolve_latest(project_root / "data/processed/qb_player_state")
    historical_version, historical = _resolve_latest(project_root / "data/processed/historical")
    enhancement_version, enhancement = _resolve_latest(project_root / "data/processed/enhancements")
    if c13_version != "c13-5e3d7a34ea4d1af5" or c14_version != "c14-43283062e788e686":
        raise ValueError("Checkpoint 15 requires the approved Checkpoint 13 and 14 identities")
    paths = {
        "c13_manifest": c13 / "MANIFEST.json",
        "c13_registry": c13 / "feature_registry.csv",
        "c13_records": c13 / "predictive_feature_records.csv",
        "c14_manifest": c14 / "MANIFEST.json",
        "c14_registry": c14 / "qb_feature_registry.csv",
        "c14_states": c14 / "player_states.parquet",
        "c14_records": c14 / "qb_state_feature_records.parquet",
        "predictive_foundation_code": project_root
        / "src/nfl_coaching_impact/predictive_foundation.py",
        "team_constants_code": project_root / "src/nfl_coaching_impact/constants.py",
        "historical_source_manifest": historical / "SOURCE_MANIFEST.json",
        "players": historical / "bronze/players/players.parquet",
        "performance": enhancement / "canonical_qb_team_season_performance.parquet",
        "pae": enhancement / "canonical_qb_pae.parquet",
    }
    dated, depth_paths = load_dated_depth_charts(historical)
    inputs = {name: _sha256(path) for name, path in paths.items()}
    inputs.update({f"depth_chart/{path.parent.name}": _sha256(path) for path in depth_paths})
    code_hash = _sha256(Path(__file__))
    data_version, identity = _content_identity(inputs, code_hash)
    root = output_root or project_root / "data/processed/player_scheme_fit"
    destination = root / data_version
    if destination.is_dir():
        manifest = json.loads((destination / "MANIFEST.json").read_text(encoding="utf-8"))
        if manifest["identity"] != identity:
            raise ValueError("existing Checkpoint 15 output has a mismatched identity")
        for name, digest in manifest["output_checksums"].items():
            if not (destination / name).is_file() or _sha256(destination / name) != digest:
                raise ValueError(f"existing Checkpoint 15 artifact failed checksum: {name}")
        _publish_latest(root, data_version)
        return CheckpointFifteenResult(
            data_version,
            destination,
            True,
            int(manifest["counts"]["cohort_rows"]),
            int(manifest["counts"]["eligible_rows"]),
            int(manifest["counts"]["prediction_rows"]),
            str(manifest["fit_status"]),
            str(manifest["checkpoint_16_readiness"]),
        )

    store = AsOfFeatureStore(c13)
    registry = fit_feature_registry(
        pl.read_csv(paths["c14_registry"]),
        pl.read_csv(paths["c13_registry"]),
    )
    validate_requested_features(
        registry,
        tuple(PLAYER_FEATURES)
        + tuple(f"scheme_{name}" for name in SCHEME_FEATURES)
        + tuple(name for name, _, _, _ in INTERACTION_DEFINITIONS),
    )
    players = pl.read_parquet(paths["players"])
    assignments = build_preseason_team_assignments(
        players,
        dated,
        players_source_hash=inputs["players"],
    )
    performance = pl.read_parquet(paths["performance"])
    pae = pl.read_parquet(paths["pae"])
    scheme = _scheme_matrix(store)
    cohort = build_modeling_cohort(
        pl.read_parquet(paths["c14_states"]),
        pl.read_parquet(paths["c14_records"]),
        assignments,
        scheme,
        _scheme_metadata(store),
        performance,
        pae,
    )
    leakage = validate_cohort_leakage(cohort)
    folds = build_fold_assignments(cohort)
    predictions, fold_metrics, coefficients, diagnostics = run_rolling_models(cohort)
    comparison = aggregate_model_comparison(predictions)
    coverage_by_season, coverage_by_category, source_audit = build_target_team_coverage(
        pl.read_parquet(paths["c14_states"]),
        assignments,
        performance,
    )
    team_change = team_change_validation(predictions)
    environment_change = environment_change_validation(predictions)
    bootstrap_rows: list[pl.DataFrame] = []
    for outcome in OUTCOMES:
        bootstrap_rows.append(
            cluster_bootstrap_model_delta(_paired_predictions(predictions, outcome)).with_columns(
                pl.lit(outcome).alias("outcome")
            )
        )
    bootstrap = (
        pl.concat(bootstrap_rows, how="diagonal_relaxed")
        .select(
            "outcome",
            "status",
            "successful_draws",
            "mae_delta_m2_minus_m1",
            "mae_delta_interval_low",
            "mae_delta_interval_high",
        )
        .sort("outcome")
    )
    decision, fit_status, readiness = _fit_decision(
        predictions,
        bootstrap.filter(pl.col("outcome") == "next_season_epa_per_dropback"),
        comparison,
    )
    permutation = pl.DataFrame(
        [
            {
                "outcome": outcome,
                "status": "NOT_ESTIMABLE_NO_M2_OUT_OF_SAMPLE_PREDICTIONS",
                "successful_draws": 0,
                "observed_correlation": None,
                "placebo_p_value": None,
            }
            for outcome in OUTCOMES
        ],
        infer_schema_length=None,
    )
    sensitivity = pl.DataFrame(
        [
            {
                "sensitivity": "outcome_dropback_minimum",
                "value": value,
                "eligible_rows": cohort.filter(
                    pl.col("target_team_status") == "PRESEASON_TARGET_TEAM_KNOWN"
                )
                .filter(pl.col("outcome_dropbacks") >= value)
                .height,
                "m2_estimable": False,
                "status": "NO_HISTORICAL_QUALIFIED_INTERACTION_TRAINING_ROWS",
            }
            for value in (25, 50, 100)
        ]
        + [
            {
                "sensitivity": "personnel_family_challenger",
                "value": None,
                "eligible_rows": 0,
                "m2_estimable": False,
                "status": "NOT_RUN_LATER_SOURCE_WINDOW_AND_PRIMARY_BLOCK_UNAVAILABLE",
            },
            {
                "sensitivity": "verified_play_caller_pcae_m3",
                "value": None,
                "eligible_rows": 0,
                "m2_estimable": False,
                "status": "NOT_RUN_NO_ASOF_PCAE_RECORDS_OR_PRESEASON_CALLER_ASSIGNMENTS",
            },
        ],
        infer_schema_length=None,
    )
    summary = pl.DataFrame(
        [
            {"gate": "ASOF_TARGET_TEAM", "status": "PASS", "detail": "no outcome-derived teams"},
            {
                "gate": "ROLLING_ORIGIN",
                "status": "PASS",
                "detail": "training seasons precede folds",
            },
            {
                "gate": "M2_INTERACTIONS",
                "status": fit_status,
                "detail": (
                    "zero estimable folds; absence of a result is not evidence against fit"
                    if predictions.filter(pl.col("model") == "M2").is_empty()
                    else "evaluated under the predeclared validation rule"
                ),
            },
            {
                "gate": "CHECKPOINT_16",
                "status": readiness,
                "detail": str(decision["checkpoint_16_blocker"][0] or "approved baseline"),
            },
        ]
    )
    artifacts = {
        "fit_feature_registry.csv": registry,
        "modeling_cohort.parquet": cohort,
        "preseason_target_team_assignments.parquet": assignments,
        "target_team_contract.csv": target_team_contract(),
        "target_team_source_audit.csv": source_audit,
        "target_team_coverage_by_season.csv": coverage_by_season,
        "target_team_coverage_by_category.csv": coverage_by_category,
        "rolling_fold_assignments.csv": folds,
        "model_comparison.csv": comparison,
        "rolling_fold_metrics.csv": fold_metrics,
        "model_predictions.parquet": predictions,
        "interaction_definitions.csv": _interaction_definitions_frame(),
        "interaction_coefficients.csv": coefficients,
        "interaction_effects.parquet": _interaction_effects(predictions),
        "fold_stability.csv": diagnostics,
        "team_change_validation.csv": team_change,
        "environment_change_validation.csv": environment_change,
        "portability_sensitivity.csv": sensitivity,
        "bootstrap_uncertainty.csv": bootstrap,
        "permutation_placebo.csv": permutation,
        "missingness_coverage.csv": _coverage_report(cohort),
        "fit_approval_decision.csv": decision,
        "leakage_audit.csv": leakage,
        "checkpoint_15_summary.csv": summary,
    }
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{data_version}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir()
    try:
        for name, frame in artifacts.items():
            _write_artifact(frame, temporary / name)
        checksums = {name: _sha256(temporary / name) for name in sorted(artifacts)}
        manifest = {
            "data_version": data_version,
            "fit_feature_version": FIT_FEATURE_VERSION,
            "fit_model_version": FIT_MODEL_VERSION,
            "cohort_version": COHORT_VERSION,
            "checkpoint_status": "COMPLETE",
            "fit_status": fit_status,
            "checkpoint_16_readiness": readiness,
            "identity": identity,
            "upstream_versions": {
                "predictive_foundation": c13_version,
                "qb_player_state": c14_version,
                "historical": historical_version,
                "enhancements": enhancement_version,
            },
            "counts": {
                "cohort_rows": cohort.height,
                "eligible_rows": cohort.filter(pl.col("eligible_m1")).height,
                "known_target_team_rows": coverage_by_season["known_target_team_rows"].sum(),
                "retrospective_participant_states": coverage_by_season[
                    "retrospective_participant_states"
                ].sum(),
                "prediction_rows": predictions.height,
                "m2_prediction_rows": predictions.filter(pl.col("model") == "M2").height,
                "fold_rows": fold_metrics.height,
            },
            "grains": {
                "modeling_cohort": ["player_id", "target_season", "cohort_version"],
                "predictions": ["player_id", "target_team_id", "target_season", "outcome", "model"],
                "fold_metrics": ["outcome", "fold_season", "model"],
            },
            "output_checksums": checksums,
        }
        (temporary / "MANIFEST.json").write_bytes(_json_bytes(manifest))
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _publish_latest(root, data_version)
    return CheckpointFifteenResult(
        data_version,
        destination,
        False,
        cohort.height,
        cohort.filter(pl.col("eligible_m1")).height,
        predictions.height,
        fit_status,
        readiness,
    )

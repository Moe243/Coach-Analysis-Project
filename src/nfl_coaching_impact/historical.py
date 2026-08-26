"""Checkpoint-three full-history ingestion and season-isolated publishing."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from .constants import (
    ANALYSIS_SEASONS,
    HISTORICAL_PIPELINE_VERSION,
    HISTORICAL_SEASONS,
    METRIC_VERSION,
    TEAM_ALIAS_TO_CANONICAL,
    WARMUP_SEASONS,
)
from .errors import PipelineError
from .pipeline import (
    _output_checksums,
    _update_latest,
    _validate_existing_version,
    _write_json,
    _write_quality_markdown,
)
from .quality import QualityReport
from .sources import (
    AssetMetadata,
    CoverageExpectation,
    SourceAsset,
    SourceCache,
    StoragePreflight,
    build_historical_source_plan,
    copy_to_bronze,
    preflight_sources,
)
from .transforms import (
    build_games,
    build_players,
    build_qb_game_performance,
    build_qb_seasons,
    build_teams_and_aliases,
    resolve_eligible_dropbacks,
    validate_season_pbp_play_keys,
)

CONTEXT_DATASETS = ("player_stats", "injuries", "depth_charts", "snap_counts")


@dataclass(frozen=True)
class HistoricalPipelineConfig:
    project_root: Path
    seasons: tuple[int, ...] = HISTORICAL_SEASONS
    cache_dir: Path | None = None
    output_dir: Path | None = None
    offline: bool = False
    available_bytes: int | None = None

    @property
    def resolved_cache_dir(self) -> Path:
        return self.cache_dir or self.project_root / ".cache" / "nfl_coaching_impact"

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "data" / "processed" / "historical"


@dataclass(frozen=True)
class HistoricalPipelineResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    reused_seasons: tuple[int, ...]
    table_counts: dict[str, int]
    preflight: StoragePreflight


@dataclass(frozen=True)
class _SeasonResult:
    season: int
    version: str
    path: Path
    reused_existing: bool


def _scope(season: int) -> str:
    return "warmup" if season in WARMUP_SEASONS else "analysis"


def _version(
    prefix: str,
    metadata: Iterable[AssetMetadata],
    seasons: Iterable[int],
    coverage: Iterable[CoverageExpectation] = (),
) -> str:
    identity = {
        "pipeline_version": HISTORICAL_PIPELINE_VERSION,
        "metric_version": METRIC_VERSION,
        "seasons": sorted(seasons),
        "sources": [
            {"asset_key": item.asset_key, "sha256": item.sha256}
            for item in sorted(metadata, key=lambda value: value.asset_key)
        ],
        "coverage": [
            {
                "dataset": item.dataset,
                "season": item.season,
                "expected_available": item.expected_available,
                "reason": item.reason,
            }
            for item in sorted(coverage, key=lambda value: (value.season, value.dataset))
        ],
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _lineage(frame: pl.DataFrame, data_version: str, *, metric: bool = False) -> pl.DataFrame:
    expressions = [pl.lit(data_version).alias("data_version")]
    if metric:
        expressions.append(pl.lit(METRIC_VERSION).alias("metric_version"))
    return frame.with_columns(expressions).select(
        "data_version",
        *(["metric_version"] if metric else []),
        pl.exclude("data_version", "metric_version"),
    )


def _deterministic_asset_record(item: AssetMetadata) -> dict[str, object]:
    """Return content/provenance facts that are stable across equivalent executions."""

    return {
        "asset_key": item.asset_key,
        "dataset": item.dataset,
        "season": item.season,
        "source_url": item.source_url,
        "sha256": item.sha256,
        "byte_size": item.byte_size,
        "row_count": item.row_count,
        "column_count": item.column_count,
        "schema": item.schema,
        "required_columns": item.required_columns,
        "missing_required_columns": item.missing_required_columns,
        "validation_status": item.validation_status,
    }


def _deterministic_manifest_frame(metadata: list[AssetMetadata], data_version: str) -> pl.DataFrame:
    records = []
    for item in metadata:
        record = _deterministic_asset_record(item)
        record["data_version"] = data_version
        record["schema_json"] = json.dumps(record.pop("schema"), sort_keys=True)
        record["required_columns_json"] = json.dumps(record.pop("required_columns"))
        record["missing_required_columns_json"] = json.dumps(record.pop("missing_required_columns"))
        records.append(record)
    return (
        pl.DataFrame(records)
        .select("data_version", pl.exclude("data_version"))
        .sort("dataset", "season", nulls_last=True)
    )


def _write_execution_log(
    output_root: Path,
    *,
    data_version: str,
    started_at: datetime,
    completed_at: datetime,
    preflight: StoragePreflight,
    metadata: list[AssetMetadata],
    season_results: list[_SeasonResult],
    reused_existing: bool,
) -> None:
    """Write mutable execution evidence outside the content-addressed version tree."""

    payload = {
        "data_version": data_version,
        "pipeline_version": HISTORICAL_PIPELINE_VERSION,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "reused_existing": reused_existing,
        "reused_seasons": [item.season for item in season_results if item.reused_existing],
        "preflight": preflight.as_record(),
        "assets": [
            item.as_record() for item in sorted(metadata, key=lambda value: value.asset_key)
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / "EXECUTION_LOG.json.part"
    _write_json(temporary, payload)
    os.replace(temporary, output_root / "EXECUTION_LOG.json")


def _asset_path(
    materialized: dict[str, tuple[Path, AssetMetadata]], dataset: str, season: int | None = None
) -> Path:
    matches = [
        path
        for path, metadata in materialized.values()
        if metadata.dataset == dataset and metadata.season == season
    ]
    if len(matches) != 1:
        raise PipelineError(
            f"Expected one materialized {dataset} asset for season={season}, found {len(matches)}"
        )
    return matches[0]


def _context_frame(
    frame: pl.DataFrame,
    dataset: str,
    season: int,
    quality: QualityReport,
) -> pl.DataFrame:
    player_column = next(
        (column for column in ("player_id", "gsis_id") if column in frame.columns), None
    )
    team_column = next(
        (column for column in ("team", "recent_team", "club_code") if column in frame.columns),
        None,
    )
    player_expr = (
        pl.col(player_column).cast(pl.String).str.strip_chars()
        if player_column
        else pl.lit(None, dtype=pl.String)
    )
    team_expr = (
        pl.col(team_column)
        .cast(pl.String)
        .replace_strict(TEAM_ALIAS_TO_CANONICAL, default=None, return_dtype=pl.String)
        if team_column
        else pl.lit(None, dtype=pl.String)
    )
    normalized = frame.with_columns(
        pl.lit(dataset).alias("source_dataset"),
        pl.lit(season, dtype=pl.Int32).alias("source_season"),
        pl.when(player_expr.str.contains(r"^00-\d{7}$"))
        .then(player_expr)
        .otherwise(None)
        .alias("canonical_player_id"),
        pl.when(team_expr.is_not_null())
        .then(pl.concat_str([pl.lit("team_"), team_expr.str.to_lowercase()]))
        .otherwise(None)
        .alias("canonical_team_id"),
    ).select(
        "source_dataset",
        "source_season",
        "canonical_player_id",
        "canonical_team_id",
        pl.exclude(
            "source_dataset",
            "source_season",
            "canonical_player_id",
            "canonical_team_id",
        ),
    )
    observed_players = player_expr.is_not_null()
    invalid_players = normalized.filter(
        observed_players & pl.col("canonical_player_id").is_null()
    ).height
    quality.warn(
        f"{dataset}_rows_without_canonical_gsis_id",
        invalid_players,
        "non-GSIS or missing upstream player identifiers remain null; no name match is attempted",
    )
    observed_teams = frame.get_column(team_column).is_not_null().sum() if team_column else 0
    unmapped_teams = (
        normalized.filter(pl.col("canonical_team_id").is_null()).height if observed_teams else 0
    )
    quality.warn(
        f"{dataset}_rows_without_canonical_team_id",
        unmapped_teams,
        "missing or non-team aggregate labels remain null and upstream values are preserved",
    )
    return normalized


def _season_store_root(output_root: Path, season: int) -> Path:
    return output_root / "seasons" / f"season={season}"


def _process_season(
    season: int,
    season_metadata: list[AssetMetadata],
    global_metadata: list[AssetMetadata],
    materialized: dict[str, tuple[Path, AssetMetadata]],
    schedules: pl.DataFrame,
    player_source: pl.DataFrame,
    team_source: pl.DataFrame,
    output_root: Path,
) -> _SeasonResult:
    version = _version(f"s{season}", [*global_metadata, *season_metadata], (season,))
    season_root = _season_store_root(output_root, season)
    final_path = season_root / version
    if final_path.exists():
        _validate_existing_version(final_path, version)
        _update_latest(season_root, version)
        return _SeasonResult(season, version, final_path, True)

    staging = season_root / ".staging" / uuid.uuid4().hex
    silver = staging / "silver"
    quality = QualityReport()
    try:
        pbp = pl.read_parquet(_asset_path(materialized, "play_by_play", season))
        validate_season_pbp_play_keys(pbp, season, quality)
        rosters = pl.read_parquet(_asset_path(materialized, "rosters", season))
        selected_schedule = schedules.filter(pl.col("season") == season)
        teams, aliases = build_teams_and_aliases(
            team_source,
            selected_schedule,
            pbp,
            rosters,
            quality,
        )
        games = build_games(schedules, (season,), quality)
        resolved, unresolved = resolve_eligible_dropbacks(pbp, games, quality)
        invalid_resolved_ids = resolved.filter(
            ~pl.col("player_id").str.contains(r"^00-\d{7}$")
        ).height
        quality.record(
            "resolved_qb_ids_are_gsis",
            invalid_resolved_ids == 0,
            failure_count=invalid_resolved_ids,
            details="every resolved quarterback identifier must be a GSIS ID",
        )
        qb_games = build_qb_game_performance(resolved, quality)
        qb_seasons = build_qb_seasons(qb_games, quality)
        warmup_qualified = (
            qb_seasons.filter(pl.col("qualifies_default")).height
            if _scope(season) == "warmup"
            else 0
        )
        quality.record(
            "warmup_season_is_not_rank_eligible",
            warmup_qualified == 0,
            failure_count=warmup_qualified,
            details="warm-up seasons may seed lagged fields but cannot qualify for analysis",
        )

        identities = (
            resolved.select("player_id", "player_name")
            .group_by("player_id")
            .agg(pl.col("player_name").drop_nulls().first())
            .sort("player_id")
        )
        silver.mkdir(parents=True, exist_ok=True)
        season_tables = {
            "teams": teams,
            "team_aliases": aliases,
            "games": games,
            "qb_game_performance": qb_games,
            "qb_team_season_performance": qb_seasons,
            "unresolved_qb_plays": unresolved,
            "resolved_qb_identities": identities,
        }
        for name, frame in season_tables.items():
            frame.write_parquet(silver / f"{name}.parquet", compression="zstd")

        context_counts: dict[str, int] = {}
        context_root = silver / "context"
        for dataset in CONTEXT_DATASETS:
            matches = [item for item in season_metadata if item.dataset == dataset]
            if not matches:
                context_counts[dataset] = 0
                continue
            source = pl.read_parquet(_asset_path(materialized, dataset, season))
            quality.warn(
                f"{dataset}_source_is_empty",
                int(source.is_empty()),
                "the official asset exists and passed schema validation but contains zero rows",
            )
            context = _context_frame(source, dataset, season, quality)
            destination = context_root / dataset
            destination.mkdir(parents=True, exist_ok=True)
            context.write_parquet(destination / "data.parquet", compression="zstd")
            context_counts[dataset] = context.height

        quality_frame = quality.frame()
        quality_frame.write_parquet(silver / "data_quality_checks.parquet", compression="zstd")
        table_counts = {name: frame.height for name, frame in season_tables.items()}
        table_counts.update({f"context_{key}": value for key, value in context_counts.items()})
        table_counts["data_quality_checks"] = quality_frame.height
        manifest = {
            "data_version": version,
            "pipeline_version": HISTORICAL_PIPELINE_VERSION,
            "metric_version": METRIC_VERSION,
            "season": season,
            "scope": _scope(season),
            "source_asset_count": len(season_metadata) + len(global_metadata),
            "table_counts": table_counts,
            "status": "succeeded",
        }
        _write_json(staging / "RUN_MANIFEST.json", manifest)
        _write_json(staging / "OUTPUT_CHECKSUMS.json", _output_checksums(staging))
        season_root.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_path)
        _update_latest(season_root, version)
        return _SeasonResult(season, version, final_path, False)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _merge_aliases(season_results: list[_SeasonResult]) -> pl.DataFrame:
    frames = [
        pl.read_parquet(item.path / "silver" / "team_aliases.parquet") for item in season_results
    ]
    return (
        pl.concat(frames, how="diagonal_relaxed")
        .group_by("source_system", "alias", "canonical_abbr", "team_id")
        .agg(
            pl.col("first_observed_season").min(),
            pl.col("last_observed_season").max(),
        )
        .sort("source_system", "alias")
    )


def _coverage_frame(
    coverage: list[CoverageExpectation],
    metadata: list[AssetMetadata],
) -> pl.DataFrame:
    observed = {(item.dataset, item.season): item for item in metadata if item.season is not None}
    return pl.DataFrame(
        [
            {
                "season": item.season,
                "dataset": item.dataset,
                "expected_available": item.expected_available,
                "status": (
                    "ingested_empty"
                    if item.expected_available
                    and observed[(item.dataset, item.season)].row_count == 0
                    else "ingested"
                    if item.expected_available
                    else "expected_gap"
                ),
                "reason": item.reason,
                "row_count": (
                    observed[(item.dataset, item.season)].row_count
                    if item.expected_available
                    else None
                ),
                "byte_size": (
                    observed[(item.dataset, item.season)].byte_size
                    if item.expected_available
                    else None
                ),
            }
            for item in sorted(coverage, key=lambda value: (value.season, value.dataset))
        ]
    )


def _season_summary(
    seasons: tuple[int, ...],
    metadata: list[AssetMetadata],
    coverage: list[CoverageExpectation],
    games: pl.DataFrame,
    qb_games: pl.DataFrame,
    qb_seasons: pl.DataFrame,
    unresolved: pl.DataFrame,
    season_quality: pl.DataFrame,
) -> pl.DataFrame:
    metadata_by_season: dict[int, dict[str, int]] = {}
    for item in metadata:
        if item.season is not None:
            metadata_by_season.setdefault(item.season, {})[item.dataset] = item.row_count
    gap_counts: dict[int, int] = {}
    for item in coverage:
        if not item.expected_available:
            gap_counts[item.season] = gap_counts.get(item.season, 0) + 1

    rows = []
    for season in seasons:
        season_games = games.filter(pl.col("season") == season)
        season_qb_games = qb_games.filter(pl.col("season") == season)
        season_qbs = qb_seasons.filter(pl.col("season") == season)
        season_unresolved = unresolved.filter(pl.col("season") == season)
        checks = season_quality.filter(pl.col("season") == season)
        source_counts = metadata_by_season.get(season, {})
        rows.append(
            {
                "season": season,
                "scope": _scope(season),
                "source_rows_json": json.dumps(source_counts, sort_keys=True),
                "games": season_games.height,
                "qb_team_games": season_qb_games.height,
                "qb_team_seasons": season_qbs.height,
                "qualified_qb_team_seasons": season_qbs.filter(pl.col("qualifies_default")).height,
                "resolved_dropbacks": season_qb_games.get_column("dropbacks").sum(),
                "unresolved_qb_plays": season_unresolved.height,
                "invalid_qb_epa_plays": season_unresolved.filter(
                    pl.col("resolution_status") == "invalid_qb_epa"
                ).height,
                "pass_attempts_missing_air_yards": (
                    season_qb_games.get_column("attempts").sum()
                    - season_qb_games.get_column("air_yards_attempts").sum()
                ),
                "expected_coverage_gaps": gap_counts.get(season, 0),
                "quality_checks": checks.height,
                "quality_failures": checks.filter(pl.col("status") == "fail").height,
                "quality_warnings": checks.filter(pl.col("status") == "warning").height,
            }
        )
    return pl.DataFrame(rows).sort("season")


def run_historical_preflight(
    config: HistoricalPipelineConfig,
    *,
    assets: list[SourceAsset] | None = None,
) -> StoragePreflight:
    seasons = tuple(sorted(set(config.seasons)))
    source_assets = assets or build_historical_source_plan(seasons)[0]
    return preflight_sources(
        source_assets,
        cache_dir=config.resolved_cache_dir,
        output_dir=config.resolved_output_dir,
        offline=config.offline,
        available_bytes=config.available_bytes,
    )


def run_historical_pipeline(
    config: HistoricalPipelineConfig,
    *,
    assets: list[SourceAsset] | None = None,
    coverage: list[CoverageExpectation] | None = None,
) -> HistoricalPipelineResult:
    """Build 1999-2025 independently by season, then atomically publish the whole history."""

    started_at = datetime.now(UTC)
    seasons = tuple(sorted(set(config.seasons)))
    if not seasons:
        raise PipelineError("Historical ingestion requires at least one season")
    if assets is None:
        source_assets, default_coverage = build_historical_source_plan(seasons)
    else:
        source_assets = assets
        default_coverage = [
            CoverageExpectation(item.dataset, item.season, True, "fixture source supplied")
            for item in source_assets
            if item.season is not None
        ]
    coverage_rows = coverage if coverage is not None else default_coverage
    preflight = preflight_sources(
        source_assets,
        cache_dir=config.resolved_cache_dir,
        output_dir=config.resolved_output_dir,
        offline=config.offline,
        available_bytes=config.available_bytes,
    )

    cache = SourceCache(config.resolved_cache_dir)
    materialized: dict[str, tuple[Path, AssetMetadata]] = {}
    global_assets = sorted(
        (asset for asset in source_assets if asset.season is None),
        key=lambda item: item.asset_key,
    )
    seasonal_assets = sorted(
        (asset for asset in source_assets if asset.season is not None),
        key=lambda item: (item.season or 0, item.dataset),
    )
    for asset in global_assets:
        materialized[asset.asset_key] = cache.materialize(asset, offline=config.offline)
    global_metadata = [metadata for _, metadata in materialized.values()]
    schedules = pl.read_parquet(_asset_path(materialized, "schedules"))
    player_source = pl.read_parquet(_asset_path(materialized, "players"))
    team_source = pl.read_parquet(_asset_path(materialized, "teams"))

    season_results: list[_SeasonResult] = []
    for season in seasons:
        assets_for_season = [asset for asset in seasonal_assets if asset.season == season]
        for asset in assets_for_season:
            materialized[asset.asset_key] = cache.materialize(asset, offline=config.offline)
        season_metadata = [materialized[asset.asset_key][1] for asset in assets_for_season]
        result = _process_season(
            season,
            season_metadata,
            global_metadata,
            materialized,
            schedules,
            player_source,
            team_source,
            config.resolved_output_dir,
        )
        season_results.append(result)

    metadata = [metadata for _, metadata in materialized.values()]
    data_version = _version("c3", metadata, seasons, coverage_rows)
    output_root = config.resolved_output_dir
    final_path = output_root / data_version
    if final_path.exists():
        table_counts = _validate_existing_version(final_path, data_version)
        _update_latest(output_root, data_version)
        _write_execution_log(
            output_root,
            data_version=data_version,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            preflight=preflight,
            metadata=metadata,
            season_results=season_results,
            reused_existing=True,
        )
        return HistoricalPipelineResult(
            data_version,
            final_path,
            True,
            tuple(item.season for item in season_results if item.reused_existing),
            table_counts,
            preflight,
        )

    staging = output_root / ".staging" / uuid.uuid4().hex
    bronze = staging / "bronze"
    silver = staging / "silver"
    final_quality = QualityReport()
    try:
        for asset in source_assets:
            source, item_metadata = materialized[asset.asset_key]
            copy_to_bronze(source, bronze / asset.bronze_path, item_metadata.sha256)

        games = pl.concat(
            [pl.read_parquet(item.path / "silver" / "games.parquet") for item in season_results],
            how="diagonal_relaxed",
        ).sort("season", "week", "game_id")
        qb_games = pl.concat(
            [
                pl.read_parquet(item.path / "silver" / "qb_game_performance.parquet")
                for item in season_results
            ],
            how="diagonal_relaxed",
        ).sort("season", "week", "game_id", "team_id", "player_id")
        unresolved = pl.concat(
            [
                pl.read_parquet(item.path / "silver" / "unresolved_qb_plays.parquet")
                for item in season_results
            ],
            how="diagonal_relaxed",
        ).sort("season", "game_id", "play_id")
        identities = (
            pl.concat(
                [
                    pl.read_parquet(item.path / "silver" / "resolved_qb_identities.parquet")
                    for item in season_results
                ],
                how="diagonal_relaxed",
            )
            .group_by("player_id")
            .agg(pl.col("player_name").drop_nulls().first())
        )
        rosters = pl.concat(
            [pl.read_parquet(_asset_path(materialized, "rosters", season)) for season in seasons],
            how="diagonal_relaxed",
        )
        teams = pl.read_parquet(season_results[0].path / "silver" / "teams.parquet")
        aliases = _merge_aliases(season_results)
        qb_seasons = build_qb_seasons(qb_games, final_quality)
        players, external_ids, conflicting_external_ids = build_players(
            player_source,
            rosters,
            identities,
            final_quality,
        )

        observed_seasons = sorted(qb_seasons.get_column("season").unique().to_list())
        final_quality.record(
            "all_requested_seasons_have_qb_metrics",
            observed_seasons == list(seasons),
            failure_count=len(set(seasons).symmetric_difference(observed_seasons)),
            details=f"expected {list(seasons)}, observed {observed_seasons}",
        )
        warmup_rankable = qb_seasons.filter(
            pl.col("season").is_in(sorted(WARMUP_SEASONS)) & pl.col("qualifies_default")
        ).height
        final_quality.record(
            "all_warmup_seasons_are_not_rank_eligible",
            warmup_rankable == 0,
            failure_count=warmup_rankable,
            details="1999-2009 may seed lagged fields but cannot qualify for analysis",
        )
        wrong_scope = qb_seasons.filter(
            (pl.col("season").is_in(sorted(ANALYSIS_SEASONS)) & (pl.col("scope") != "analysis"))
            | (pl.col("season").is_in(sorted(WARMUP_SEASONS)) & (pl.col("scope") != "warmup"))
        ).height
        final_quality.record(
            "season_scopes_match_contract",
            wrong_scope == 0,
            failure_count=wrong_scope,
            details="1999-2009 are warm-up only and 2010-2025 are analysis seasons",
        )

        season_quality = pl.concat(
            [
                pl.read_parquet(item.path / "silver" / "data_quality_checks.parquet").with_columns(
                    pl.lit(item.season, dtype=pl.Int32).alias("season"),
                    pl.lit(_scope(item.season)).alias("scope"),
                )
                for item in season_results
            ],
            how="diagonal_relaxed",
        )
        global_quality = final_quality.frame().with_columns(
            pl.lit(None, dtype=pl.Int32).alias("season"),
            pl.lit("all_seasons").alias("scope"),
        )
        quality = pl.concat([season_quality, global_quality], how="diagonal_relaxed").select(
            "season", "scope", "name", "status", "severity", "failure_count", "details"
        )
        coverage_frame = _coverage_frame(coverage_rows, metadata)
        summary = _season_summary(
            seasons,
            metadata,
            coverage_rows,
            games,
            qb_games,
            qb_seasons,
            unresolved,
            season_quality,
        )

        silver.mkdir(parents=True, exist_ok=True)
        tables = {
            "teams": _lineage(teams, data_version),
            "team_aliases": _lineage(aliases, data_version),
            "players": _lineage(players, data_version),
            "player_external_ids": _lineage(external_ids, data_version),
            "conflicting_player_external_ids": _lineage(conflicting_external_ids, data_version),
            "games": _lineage(games, data_version),
            "qb_game_performance": _lineage(qb_games, data_version, metric=True),
            "qb_team_season_performance": _lineage(qb_seasons, data_version, metric=True),
            "unresolved_qb_plays": _lineage(unresolved, data_version),
            "source_manifest": _deterministic_manifest_frame(metadata, data_version),
            "source_coverage": _lineage(coverage_frame, data_version),
            "season_summary": _lineage(summary, data_version),
            "data_quality_checks": _lineage(quality, data_version),
        }
        for name, frame in tables.items():
            frame.write_parquet(silver / f"{name}.parquet", compression="zstd")

        context_counts: dict[str, int] = {dataset: 0 for dataset in CONTEXT_DATASETS}
        pfr_crosswalk = (
            external_ids.filter(pl.col("external_system").str.ends_with(".pfr_id"))
            .group_by("external_id")
            .agg(
                pl.col("player_id").n_unique().alias("distinct_players"),
                pl.col("player_id").first().alias("crosswalk_player_id"),
            )
            .filter(pl.col("distinct_players") == 1)
            .select("external_id", "crosswalk_player_id")
        )
        for result in season_results:
            for dataset in CONTEXT_DATASETS:
                source = result.path / "silver" / "context" / dataset / "data.parquet"
                if not source.is_file():
                    continue
                frame = pl.read_parquet(source)
                if dataset == "snap_counts" and "pfr_player_id" in frame.columns:
                    frame = (
                        frame.with_columns(
                            pl.col("pfr_player_id")
                            .cast(pl.String)
                            .str.strip_chars()
                            .alias("_pfr_player_id")
                        )
                        .join(
                            pfr_crosswalk,
                            left_on="_pfr_player_id",
                            right_on="external_id",
                            how="left",
                            validate="m:1",
                        )
                        .with_columns(
                            pl.coalesce("canonical_player_id", "crosswalk_player_id").alias(
                                "canonical_player_id"
                            )
                        )
                        .drop("_pfr_player_id", "crosswalk_player_id")
                    )
                frame = _lineage(frame, data_version)
                destination = silver / dataset / f"season={result.season}"
                destination.mkdir(parents=True, exist_ok=True)
                frame.write_parquet(destination / "data.parquet", compression="zstd")
                context_counts[dataset] += frame.height

        _write_quality_markdown(staging / "DATA_QUALITY_REPORT.md", tables["data_quality_checks"])
        _write_json(
            staging / "SOURCE_MANIFEST.json",
            {
                "data_version": data_version,
                "assets": [
                    _deterministic_asset_record(item)
                    for item in sorted(metadata, key=lambda value: value.asset_key)
                ],
            },
        )
        _write_json(
            staging / "SEASON_SUMMARY.json",
            {"data_version": data_version, "seasons": summary.to_dicts()},
        )

        table_counts = {name: frame.height for name, frame in tables.items()}
        table_counts.update({f"{dataset}_rows": count for dataset, count in context_counts.items()})
        table_counts["pipeline_manifest"] = 1
        manifest = {
            "data_version": data_version,
            "pipeline_version": HISTORICAL_PIPELINE_VERSION,
            "metric_version": METRIC_VERSION,
            "seasons": list(seasons),
            "warmup_seasons": [season for season in seasons if season in WARMUP_SEASONS],
            "analysis_seasons": [season for season in seasons if season in ANALYSIS_SEASONS],
            "source_asset_count": len(metadata),
            "season_versions": {str(item.season): item.version for item in season_results},
            "table_counts": table_counts,
            "status": "succeeded",
        }
        pipeline_manifest = pl.DataFrame(
            [
                {
                    "data_version": data_version,
                    "pipeline_version": HISTORICAL_PIPELINE_VERSION,
                    "metric_version": METRIC_VERSION,
                    "seasons_json": json.dumps(list(seasons)),
                    "warmup_seasons_json": json.dumps(manifest["warmup_seasons"]),
                    "analysis_seasons_json": json.dumps(manifest["analysis_seasons"]),
                    "source_asset_count": len(metadata),
                    "season_versions_json": json.dumps(manifest["season_versions"], sort_keys=True),
                    "table_counts_json": json.dumps(table_counts, sort_keys=True),
                    "status": "succeeded",
                }
            ]
        )
        pipeline_manifest.write_parquet(silver / "pipeline_manifest.parquet", compression="zstd")
        _write_json(staging / "RUN_MANIFEST.json", manifest)
        _write_json(staging / "OUTPUT_CHECKSUMS.json", _output_checksums(staging))
        output_root.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final_path)
        _update_latest(output_root, data_version)
        _write_execution_log(
            output_root,
            data_version=data_version,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            preflight=preflight,
            metadata=metadata,
            season_results=season_results,
            reused_existing=False,
        )
        return HistoricalPipelineResult(
            data_version,
            final_path,
            False,
            tuple(item.season for item in season_results if item.reused_existing),
            table_counts,
            preflight,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

"""Atomic checkpoint-two vertical-slice orchestration."""

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

from .constants import METRIC_VERSION, PIPELINE_VERSION, VERTICAL_SLICE_SEASONS
from .errors import PipelineError
from .quality import QualityReport
from .sources import (
    AssetMetadata,
    SourceAsset,
    SourceCache,
    build_source_assets,
    copy_to_bronze,
    sha256_file,
)
from .transforms import (
    build_games,
    build_players,
    build_qb_game_performance,
    build_qb_seasons,
    build_teams_and_aliases,
    read_seasonal_bronze,
    resolve_eligible_dropbacks,
)


@dataclass(frozen=True)
class PipelineConfig:
    project_root: Path
    seasons: tuple[int, ...] = VERTICAL_SLICE_SEASONS
    cache_dir: Path | None = None
    output_dir: Path | None = None
    offline: bool = False

    @property
    def resolved_cache_dir(self) -> Path:
        return self.cache_dir or self.project_root / ".cache" / "nfl_coaching_impact"

    @property
    def resolved_output_dir(self) -> Path:
        return self.output_dir or self.project_root / "data" / "processed" / "vertical_slice"


@dataclass(frozen=True)
class PipelineResult:
    data_version: str
    output_path: Path
    reused_existing: bool
    table_counts: dict[str, int]


def _data_version(metadata: Iterable[AssetMetadata], seasons: Iterable[int]) -> str:
    identity = {
        "pipeline_version": PIPELINE_VERSION,
        "metric_version": METRIC_VERSION,
        "seasons": sorted(seasons),
        "sources": [
            {"asset_key": item.asset_key, "sha256": item.sha256}
            for item in sorted(metadata, key=lambda value: value.asset_key)
        ],
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return f"c2-{digest}"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _manifest_frame(metadata: list[AssetMetadata], data_version: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "data_version": data_version,
                "asset_key": item.asset_key,
                "dataset": item.dataset,
                "season": item.season,
                "source_url": item.source_url,
                "retrieved_at": item.retrieved_at,
                "etag": item.etag,
                "last_modified": item.last_modified,
                "sha256": item.sha256,
                "byte_size": item.byte_size,
                "row_count": item.row_count,
                "column_count": item.column_count,
                "schema_json": json.dumps(item.schema, sort_keys=True),
                "required_columns_json": json.dumps(item.required_columns),
                "missing_required_columns_json": json.dumps(item.missing_required_columns),
                "validation_status": item.validation_status,
                "cache_status": item.cache_status,
            }
            for item in metadata
        ]
    ).sort("dataset", "season", nulls_last=True)


def _with_lineage(frame: pl.DataFrame, data_version: str, *, metric: bool = False) -> pl.DataFrame:
    expressions: list[pl.Expr] = [pl.lit(data_version).alias("data_version")]
    if metric:
        expressions.append(pl.lit(METRIC_VERSION).alias("metric_version"))
    return frame.with_columns(expressions).select(
        "data_version",
        *(["metric_version"] if metric else []),
        pl.exclude("data_version", "metric_version"),
    )


def _write_quality_markdown(path: Path, quality: pl.DataFrame) -> None:
    lines = [
        "# Data quality report",
        "",
        "| Check | Status | Severity | Failures | Details |",
        "|---|---|---|---:|---|",
    ]
    for row in quality.iter_rows(named=True):
        details = str(row["details"]).replace("|", "\\|")
        lines.append(
            f"| `{row['name']}` | {row['status']} | {row['severity']} | "
            f"{row['failure_count']} | {details} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _output_checksums(root: Path) -> dict[str, dict[str, object]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "OUTPUT_CHECKSUMS.json"
    }


def _validate_existing_version(final_path: Path, data_version: str) -> dict[str, int]:
    manifest_path = final_path / "RUN_MANIFEST.json"
    checksums_path = final_path / "OUTPUT_CHECKSUMS.json"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise PipelineError(f"Existing version lacks required manifests: {final_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("data_version") != data_version or manifest.get("status") != "succeeded":
        raise PipelineError(f"Existing version has invalid run lineage: {final_path}")
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    if not isinstance(checksums, dict) or not checksums:
        raise PipelineError(
            f"Existing version has an invalid output checksum manifest: {final_path}"
        )
    for relative, expected in checksums.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PipelineError(f"Unsafe path in output checksum manifest: {relative}")
        path = final_path / relative_path
        if not path.is_file():
            raise PipelineError(f"Existing version is missing output: {relative}")
        if not isinstance(expected, dict):
            raise PipelineError(f"Invalid checksum record for output: {relative}")
        actual_digest = sha256_file(path)
        if actual_digest != expected.get("sha256") or path.stat().st_size != expected.get(
            "byte_size"
        ):
            raise PipelineError(f"Existing version has a corrupt output: {relative}")
    table_counts = manifest.get("table_counts")
    if not isinstance(table_counts, dict) or not all(
        isinstance(name, str) and isinstance(count, int) for name, count in table_counts.items()
    ):
        raise PipelineError(f"Existing version has invalid table counts: {final_path}")
    return table_counts


def _update_latest(output_root: Path, data_version: str) -> None:
    latest_part = output_root / "LATEST.part"
    latest_part.write_text(data_version + "\n", encoding="utf-8")
    os.replace(latest_part, output_root / "LATEST")


def run_vertical_slice(
    config: PipelineConfig,
    *,
    assets: list[SourceAsset] | None = None,
) -> PipelineResult:
    """Build the complete slice, publishing it only after every check passes."""

    started_at = datetime.now(UTC)
    seasons = tuple(sorted(set(config.seasons)))
    source_assets = assets or build_source_assets(seasons)
    cache = SourceCache(config.resolved_cache_dir)
    output_root = config.resolved_output_dir
    staging_root = output_root / ".staging" / uuid.uuid4().hex
    bronze_root = staging_root / "bronze"
    silver_root = staging_root / "silver"
    metadata: list[AssetMetadata] = []
    quality = QualityReport()

    try:
        for asset in source_assets:
            cached_path, item_metadata = cache.materialize(asset, offline=config.offline)
            metadata.append(item_metadata)
            copy_to_bronze(
                cached_path,
                bronze_root / asset.bronze_path,
                item_metadata.sha256,
            )

        expected_assets = len(seasons) * 2 + 3
        quality.record(
            "complete_source_registry",
            len(metadata) == expected_assets,
            failure_count=abs(len(metadata) - expected_assets),
            details=f"expected {expected_assets} assets, observed {len(metadata)}",
        )
        data_version = _data_version(metadata, seasons)
        final_path = output_root / data_version
        if final_path.exists():
            table_counts = _validate_existing_version(final_path, data_version)
            shutil.rmtree(staging_root)
            _update_latest(output_root, data_version)
            return PipelineResult(
                data_version=data_version,
                output_path=final_path,
                reused_existing=True,
                table_counts=table_counts,
            )

        pbp = read_seasonal_bronze(bronze_root, "play_by_play", seasons)
        rosters = read_seasonal_bronze(bronze_root, "rosters", seasons)
        schedules = pl.read_parquet(bronze_root / "schedules" / "games.parquet")
        player_source = pl.read_parquet(bronze_root / "players" / "players.parquet")
        team_source = pl.read_parquet(bronze_root / "teams" / "teams_colors_logos.parquet")

        selected_schedule = schedules.filter(pl.col("season").is_in(seasons))
        teams, team_aliases = build_teams_and_aliases(
            team_source, selected_schedule, pbp, rosters, quality
        )
        games = build_games(schedules, seasons, quality)
        resolved, unresolved = resolve_eligible_dropbacks(pbp, games, quality)
        qb_games = build_qb_game_performance(resolved, quality)
        qb_seasons = build_qb_seasons(qb_games, quality)
        players, external_ids, conflicting_external_ids = build_players(
            player_source, rosters, resolved, quality
        )

        observed_seasons = sorted(qb_seasons.get_column("season").unique().to_list())
        quality.record(
            "all_requested_seasons_have_qb_metrics",
            observed_seasons == list(seasons),
            failure_count=len(set(seasons).symmetric_difference(observed_seasons)),
            details=f"expected {list(seasons)}, observed {observed_seasons}",
        )
        warmup_rankable = qb_seasons.filter(
            (pl.col("season") == 2009) & pl.col("qualifies_default")
        ).height
        quality.record(
            "warmup_season_is_not_rank_eligible",
            warmup_rankable == 0,
            failure_count=warmup_rankable,
            details="2009 may seed lagged features but cannot qualify for analysis",
        )

        silver_root.mkdir(parents=True, exist_ok=True)
        tables = {
            "teams": _with_lineage(teams, data_version),
            "team_aliases": _with_lineage(team_aliases, data_version),
            "players": _with_lineage(players, data_version),
            "player_external_ids": _with_lineage(external_ids, data_version),
            "conflicting_player_external_ids": _with_lineage(
                conflicting_external_ids, data_version
            ),
            "games": _with_lineage(games, data_version),
            "qb_game_performance": _with_lineage(qb_games, data_version, metric=True),
            "qb_team_season_performance": _with_lineage(qb_seasons, data_version, metric=True),
            "unresolved_qb_plays": _with_lineage(unresolved, data_version),
            "source_manifest": _manifest_frame(metadata, data_version),
        }
        for name, frame in tables.items():
            frame.write_parquet(silver_root / f"{name}.parquet", compression="zstd")

        quality_frame = _with_lineage(quality.frame(), data_version)
        quality_frame.write_parquet(silver_root / "data_quality_checks.parquet", compression="zstd")
        _write_quality_markdown(staging_root / "DATA_QUALITY_REPORT.md", quality_frame)
        _write_json(
            staging_root / "SOURCE_MANIFEST.json",
            {
                "data_version": data_version,
                "assets": [item.as_record() for item in metadata],
            },
        )

        table_counts = {name: frame.height for name, frame in tables.items()}
        table_counts["data_quality_checks"] = quality_frame.height
        table_counts["pipeline_manifest"] = 1
        completed_at = datetime.now(UTC)
        pipeline_manifest = pl.DataFrame(
            [
                {
                    "data_version": data_version,
                    "pipeline_version": PIPELINE_VERSION,
                    "metric_version": METRIC_VERSION,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "seasons_json": json.dumps(list(seasons)),
                    "warmup_seasons_json": json.dumps([2009]),
                    "analysis_seasons_json": json.dumps(
                        [season for season in seasons if season != 2009]
                    ),
                    "source_asset_count": len(metadata),
                    "table_counts_json": json.dumps(table_counts, sort_keys=True),
                    "status": "succeeded",
                }
            ]
        )
        pipeline_manifest.write_parquet(
            silver_root / "pipeline_manifest.parquet", compression="zstd"
        )
        manifest = {
            "data_version": data_version,
            "pipeline_version": PIPELINE_VERSION,
            "metric_version": METRIC_VERSION,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "seasons": list(seasons),
            "warmup_seasons": [2009],
            "analysis_seasons": [season for season in seasons if season != 2009],
            "source_asset_count": len(metadata),
            "table_counts": table_counts,
            "status": "succeeded",
        }
        _write_json(staging_root / "RUN_MANIFEST.json", manifest)
        _write_json(staging_root / "OUTPUT_CHECKSUMS.json", _output_checksums(staging_root))

        output_root.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_root, final_path)
        _update_latest(output_root, data_version)
        return PipelineResult(
            data_version=data_version,
            output_path=final_path,
            reused_existing=False,
            table_counts=table_counts,
        )
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise

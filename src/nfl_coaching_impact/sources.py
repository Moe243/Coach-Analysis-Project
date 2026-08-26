"""Source registry, verified cache, and immutable Bronze materialization."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import certifi
import polars as pl

from .constants import (
    DEPTH_CHART_REQUIRED_COLUMNS,
    INJURY_REQUIRED_COLUMNS,
    PBP_REQUIRED_COLUMNS,
    PLAYER_REQUIRED_COLUMNS,
    PLAYER_STATS_REQUIRED_COLUMNS,
    ROSTER_REQUIRED_COLUMNS,
    SCHEDULE_REQUIRED_COLUMNS,
    SNAP_COUNT_REQUIRED_COLUMNS,
    TEAM_REQUIRED_COLUMNS,
)
from .errors import SourceValidationError

RELEASE_ROOT: Final = "https://github.com/nflverse/nflverse-data/releases/download"


@dataclass(frozen=True)
class SourceAsset:
    """One exact upstream object required by a pipeline execution."""

    asset_key: str
    dataset: str
    url: str
    cache_path: str
    bronze_path: str
    required_columns: tuple[str, ...]
    season: int | None = None


@dataclass(frozen=True)
class AssetMetadata:
    """Retrieval and validation facts persisted beside a cached source object."""

    asset_key: str
    dataset: str
    season: int | None
    source_url: str
    retrieved_at: str
    etag: str | None
    last_modified: str | None
    sha256: str
    byte_size: int
    row_count: int
    column_count: int
    schema: dict[str, str]
    required_columns: list[str]
    missing_required_columns: list[str]
    validation_status: str
    cache_status: str

    def as_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageExpectation:
    """Expected availability for one season and source family."""

    dataset: str
    season: int
    expected_available: bool
    reason: str


@dataclass(frozen=True)
class PreflightAsset:
    """Remote or cached size discovered before any downloads begin."""

    asset_key: str
    dataset: str
    season: int | None
    url: str
    byte_size: int
    cache_status: str


@dataclass(frozen=True)
class StoragePreflight:
    """Storage and download estimate proven before source materialization."""

    assets: tuple[PreflightAsset, ...]
    total_source_bytes: int
    download_bytes: int
    required_free_bytes: int
    available_free_bytes: int

    def as_record(self) -> dict[str, object]:
        return {
            "assets": [asdict(asset) for asset in self.assets],
            "total_source_bytes": self.total_source_bytes,
            "download_bytes": self.download_bytes,
            "required_free_bytes": self.required_free_bytes,
            "available_free_bytes": self.available_free_bytes,
        }


def build_source_assets(seasons: Iterable[int]) -> list[SourceAsset]:
    """Return the complete, explicit registry for a vertical-slice run."""

    assets: list[SourceAsset] = []
    for season in sorted(set(seasons)):
        assets.extend(
            [
                SourceAsset(
                    asset_key=f"pbp_{season}",
                    dataset="play_by_play",
                    season=season,
                    url=f"{RELEASE_ROOT}/pbp/play_by_play_{season}.parquet",
                    cache_path=f"pbp/play_by_play_{season}.parquet",
                    bronze_path=f"play_by_play/season={season}/play_by_play.parquet",
                    required_columns=tuple(sorted(PBP_REQUIRED_COLUMNS)),
                ),
                SourceAsset(
                    asset_key=f"roster_{season}",
                    dataset="rosters",
                    season=season,
                    url=f"{RELEASE_ROOT}/rosters/roster_{season}.parquet",
                    cache_path=f"rosters/roster_{season}.parquet",
                    bronze_path=f"rosters/season={season}/roster.parquet",
                    required_columns=tuple(sorted(ROSTER_REQUIRED_COLUMNS)),
                ),
            ]
        )
    assets.extend(
        [
            SourceAsset(
                asset_key="schedules",
                dataset="schedules",
                url=f"{RELEASE_ROOT}/schedules/games.parquet",
                cache_path="global/games.parquet",
                bronze_path="schedules/games.parquet",
                required_columns=tuple(sorted(SCHEDULE_REQUIRED_COLUMNS)),
            ),
            SourceAsset(
                asset_key="players",
                dataset="players",
                url=f"{RELEASE_ROOT}/players/players.parquet",
                cache_path="global/players.parquet",
                bronze_path="players/players.parquet",
                required_columns=tuple(sorted(PLAYER_REQUIRED_COLUMNS)),
            ),
            SourceAsset(
                asset_key="teams",
                dataset="teams",
                url=f"{RELEASE_ROOT}/teams/teams_colors_logos.parquet",
                cache_path="global/teams_colors_logos.parquet",
                bronze_path="teams/teams_colors_logos.parquet",
                required_columns=tuple(sorted(TEAM_REQUIRED_COLUMNS)),
            ),
        ]
    )
    return assets


def build_historical_source_plan(
    seasons: Iterable[int],
) -> tuple[list[SourceAsset], list[CoverageExpectation]]:
    """Build the checkpoint-three registry and explicit historical coverage matrix."""

    season_list = sorted(set(seasons))
    availability_starts = {
        "play_by_play": 1999,
        "rosters": 1999,
        "player_stats": 1999,
        "injuries": 2009,
        "depth_charts": 2001,
        "snap_counts": 2012,
    }
    gap_reasons = {
        "injuries": "official weekly injury reports begin in 2009",
        "depth_charts": "official weekly depth charts begin in 2001",
        "snap_counts": "official snap counts begin in 2012",
    }
    coverage: list[CoverageExpectation] = []
    assets: list[SourceAsset] = []

    for season in season_list:
        for dataset, start in availability_starts.items():
            expected = season >= start
            coverage.append(
                CoverageExpectation(
                    dataset=dataset,
                    season=season,
                    expected_available=expected,
                    reason=(
                        f"official coverage expected from {start} onward"
                        if expected
                        else gap_reasons[dataset]
                    ),
                )
            )
            if not expected:
                continue
            if dataset == "play_by_play":
                filename = f"play_by_play_{season}.parquet"
                release = "pbp"
                required = PBP_REQUIRED_COLUMNS
                cache_path = f"pbp/{filename}"
                bronze_path = f"play_by_play/season={season}/play_by_play.parquet"
            elif dataset == "rosters":
                filename = f"roster_{season}.parquet"
                release = "rosters"
                required = ROSTER_REQUIRED_COLUMNS
                cache_path = f"rosters/{filename}"
                bronze_path = f"rosters/season={season}/roster.parquet"
            elif dataset == "player_stats":
                filename = f"stats_player_week_{season}.parquet"
                release = "stats_player"
                required = PLAYER_STATS_REQUIRED_COLUMNS
                cache_path = f"player_stats/{filename}"
                bronze_path = f"player_stats/season={season}/player_stats.parquet"
            elif dataset == "injuries":
                filename = f"injuries_{season}.parquet"
                release = "injuries"
                required = INJURY_REQUIRED_COLUMNS
                cache_path = f"injuries/{filename}"
                bronze_path = f"injuries/season={season}/injuries.parquet"
            elif dataset == "depth_charts":
                filename = f"depth_charts_{season}.parquet"
                release = "depth_charts"
                required = DEPTH_CHART_REQUIRED_COLUMNS
                cache_path = f"depth_charts/{filename}"
                bronze_path = f"depth_charts/season={season}/depth_charts.parquet"
            else:
                filename = f"snap_counts_{season}.parquet"
                release = "snap_counts"
                required = SNAP_COUNT_REQUIRED_COLUMNS
                cache_path = f"snap_counts/{filename}"
                bronze_path = f"snap_counts/season={season}/snap_counts.parquet"
            assets.append(
                SourceAsset(
                    asset_key=f"{dataset}_{season}",
                    dataset=dataset,
                    season=season,
                    url=f"{RELEASE_ROOT}/{release}/{filename}",
                    cache_path=cache_path,
                    bronze_path=bronze_path,
                    required_columns=tuple(sorted(required)),
                )
            )

    assets.extend(build_source_assets(())[-3:])
    return assets, coverage


def _existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        candidate = candidate.parent
    return candidate


def _preflight_asset(asset: SourceAsset, cache_dir: Path, offline: bool) -> PreflightAsset:
    cached = cache_dir / asset.cache_path
    metadata = cached.with_suffix(cached.suffix + ".metadata.json")
    if cached.is_file() and metadata.is_file():
        return PreflightAsset(
            asset_key=asset.asset_key,
            dataset=asset.dataset,
            season=asset.season,
            url=asset.url,
            byte_size=cached.stat().st_size,
            cache_status="hit",
        )
    if offline:
        raise SourceValidationError(f"Offline preflight cache miss for {asset.asset_key}: {cached}")

    parsed = urllib.parse.urlparse(asset.url)
    if parsed.scheme == "file":
        source = Path(urllib.parse.unquote(parsed.path))
        if not source.is_file():
            raise SourceValidationError(f"Preflight source is missing for {asset.asset_key}")
        size = source.stat().st_size
    else:
        request = urllib.request.Request(
            asset.url,
            method="HEAD",
            headers={"User-Agent": "nfl-coaching-impact-engine/checkpoint-3"},
        )
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                header = response.headers.get("Content-Length")
                if header is None:
                    raise SourceValidationError(f"Preflight size unavailable for {asset.asset_key}")
                size = int(header)
        except SourceValidationError:
            raise
        except Exception as exc:
            raise SourceValidationError(f"Preflight failed for {asset.asset_key}: {exc}") from exc
    return PreflightAsset(
        asset_key=asset.asset_key,
        dataset=asset.dataset,
        season=asset.season,
        url=asset.url,
        byte_size=size,
        cache_status="missing",
    )


def preflight_sources(
    assets: Iterable[SourceAsset],
    *,
    cache_dir: Path,
    output_dir: Path,
    offline: bool = False,
    available_bytes: int | None = None,
) -> StoragePreflight:
    """Resolve every size and prove storage capacity before downloading any source."""

    source_assets = sorted(assets, key=lambda item: item.asset_key)
    if offline:
        results = [_preflight_asset(asset, cache_dir, True) for asset in source_assets]
    else:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda asset: _preflight_asset(asset, cache_dir, False),
                    source_assets,
                )
            )
    results.sort(key=lambda item: item.asset_key)
    total_bytes = sum(item.byte_size for item in results)
    download_bytes = sum(item.byte_size for item in results if item.cache_status == "missing")
    required_bytes = download_bytes + (total_bytes * 2) + (128 * 1024 * 1024)
    free_bytes = (
        available_bytes
        if available_bytes is not None
        else shutil.disk_usage(_existing_parent(output_dir)).free
    )
    if free_bytes < required_bytes:
        raise SourceValidationError(
            "Insufficient storage for historical ingestion preflight: "
            f"required={required_bytes}, available={free_bytes}, download={download_bytes}"
        )
    return StoragePreflight(
        assets=tuple(results),
        total_source_bytes=total_bytes,
        download_bytes=download_bytes,
        required_free_bytes=required_bytes,
        available_free_bytes=free_bytes,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class SourceCache:
    """Fetch exact release files once and prove cache integrity on every reuse."""

    def __init__(self, root: Path, timeout_seconds: int = 180) -> None:
        self.root = root
        self.timeout_seconds = timeout_seconds

    def materialize(
        self, asset: SourceAsset, *, offline: bool = False
    ) -> tuple[Path, AssetMetadata]:
        target = self.root / asset.cache_path
        metadata_path = target.with_suffix(target.suffix + ".metadata.json")
        cache_status = "hit"

        if target.exists() and metadata_path.exists():
            stored = json.loads(metadata_path.read_text(encoding="utf-8"))
            actual_digest = sha256_file(target)
            if stored.get("sha256") != actual_digest:
                raise SourceValidationError(
                    f"Cached checksum mismatch for {asset.asset_key}; remove the corrupt cache file"
                )
            metadata = self._inspect(asset, target, stored, cache_status)
            return target, metadata

        if offline:
            raise SourceValidationError(f"Offline cache miss for {asset.asset_key}: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        request = urllib.request.Request(
            asset.url,
            headers={"User-Agent": "nfl-coaching-impact-engine/checkpoint-2"},
        )
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl_context,
            ) as response:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                headers = {
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise SourceValidationError(f"Unable to fetch {asset.asset_key}: {exc}") from exc

        os.replace(temporary, target)
        cache_status = "downloaded"
        metadata = self._inspect(asset, target, headers, cache_status)
        _atomic_json(metadata_path, metadata.as_record())
        return target, metadata

    @staticmethod
    def _inspect(
        asset: SourceAsset,
        path: Path,
        retrieval: dict[str, object],
        cache_status: str,
    ) -> AssetMetadata:
        try:
            lazy = pl.scan_parquet(path)
            schema = lazy.collect_schema()
            row_count = lazy.select(pl.len()).collect().item()
        except Exception as exc:
            raise SourceValidationError(
                f"Unreadable Parquet asset {asset.asset_key}: {exc}"
            ) from exc

        missing = sorted(set(asset.required_columns) - set(schema.names()))
        if missing:
            raise SourceValidationError(
                f"{asset.asset_key} is missing required columns: {', '.join(missing)}"
            )
        if asset.season is not None and "season" in schema:
            observed = (
                lazy.select(pl.col("season").drop_nulls().unique().sort())
                .collect()
                .to_series()
                .to_list()
            )
            if observed not in ([], [asset.season]):
                raise SourceValidationError(
                    f"{asset.asset_key} contains seasons {observed}, expected only {asset.season}"
                )

        retrieved_at = retrieval.get("retrieved_at")
        if not isinstance(retrieved_at, str):
            raise SourceValidationError(f"Missing retrieval timestamp for {asset.asset_key}")
        return AssetMetadata(
            asset_key=asset.asset_key,
            dataset=asset.dataset,
            season=asset.season,
            source_url=asset.url,
            retrieved_at=retrieved_at,
            etag=_optional_string(retrieval.get("etag")),
            last_modified=_optional_string(retrieval.get("last_modified")),
            sha256=sha256_file(path),
            byte_size=path.stat().st_size,
            row_count=row_count,
            column_count=len(schema),
            schema={name: str(dtype) for name, dtype in schema.items()},
            required_columns=list(asset.required_columns),
            missing_required_columns=missing,
            validation_status="passed",
            cache_status=cache_status,
        )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def copy_to_bronze(source: Path, destination: Path, expected_sha256: str) -> None:
    """Copy an upstream object byte-for-byte and verify the Bronze copy."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    actual = sha256_file(destination)
    if actual != expected_sha256:
        raise SourceValidationError(f"Bronze checksum mismatch for {destination}")

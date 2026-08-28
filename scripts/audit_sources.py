#!/usr/bin/env python3
"""Audit boundary nflverse assets and representative CSV schemas.

The default mode is offline and prints the manifest. Network access is explicit.
Large play-by-play files are checked with HEAD requests. Sample mode streams only
enough play-by-play rows to validate the quarterback-level fields used later.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import ssl
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASE_ROOT: Final = "https://github.com/nflverse/nflverse-data/releases/download"


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    expected_status: int
    reason: str


def release_asset(tag: str, filename: str) -> str:
    return f"{RELEASE_ROOT}/{tag}/{filename}"


def build_ssl_context() -> ssl.SSLContext:
    """Build a verified TLS context, including the standard macOS CA bundle fallback."""
    default_paths = ssl.get_default_verify_paths()
    candidates = (default_paths.cafile, "/etc/ssl/cert.pem", "/opt/anaconda3/ssl/cert.pem")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


ASSETS: Final[tuple[Asset, ...]] = (
    Asset("pbp_2010", release_asset("pbp", "play_by_play_2010.csv"), 200, "analysis start"),
    Asset("pbp_2025", release_asset("pbp", "play_by_play_2025.csv"), 200, "analysis end"),
    Asset(
        "stats_2010",
        release_asset("stats_player", "stats_player_reg_2010.csv"),
        200,
        "analysis start",
    ),
    Asset(
        "stats_2025",
        release_asset("stats_player", "stats_player_reg_2025.csv"),
        200,
        "analysis end and schema sample",
    ),
    Asset("roster_2010", release_asset("rosters", "roster_2010.csv"), 200, "analysis start"),
    Asset("roster_2025", release_asset("rosters", "roster_2025.csv"), 200, "analysis end"),
    Asset("injuries_2010", release_asset("injuries", "injuries_2010.csv"), 200, "analysis start"),
    Asset("injuries_2025", release_asset("injuries", "injuries_2025.csv"), 200, "analysis end"),
    Asset(
        "depth_2010",
        release_asset("depth_charts", "depth_charts_2010.csv"),
        200,
        "analysis start",
    ),
    Asset(
        "depth_2025",
        release_asset("depth_charts", "depth_charts_2025.csv"),
        200,
        "analysis end",
    ),
    Asset(
        "snap_2010",
        release_asset("snap_counts", "snap_counts_2010.csv"),
        404,
        "expected unavailable boundary",
    ),
    Asset(
        "snap_2012",
        release_asset("snap_counts", "snap_counts_2012.csv"),
        200,
        "first available season",
    ),
)


SAMPLE_SCHEMAS: Final[dict[str, tuple[str, frozenset[str]]]] = {
    "stats_2025": (
        "stats_player_reg_2025.csv",
        frozenset(
            {
                "player_id",
                "position",
                "season",
                "attempts",
                "passing_interceptions",
                "sacks_suffered",
                "passing_air_yards",
                "passing_first_downs",
                "passing_epa",
                "passing_cpoe",
            }
        ),
    ),
    "roster_2025": (
        "roster_2025.csv",
        frozenset({"season", "team", "position", "full_name", "gsis_id", "years_exp"}),
    ),
    "injuries_2025": (
        "injuries_2025.csv",
        frozenset(
            {
                "season",
                "team",
                "week",
                "gsis_id",
                "position",
                "report_status",
                "practice_status",
            }
        ),
    ),
}


PBP_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "game_id",
        "play_id",
        "season",
        "season_type",
        "week",
        "posteam",
        "epa",
        "qb_epa",
        "qb_dropback",
        "qb_kneel",
        "qb_spike",
        "qb_scramble",
        "passer_player_id",
        "rusher_player_id",
        "cpoe",
        "sack",
        "interception",
        "pass_attempt",
        "complete_pass",
        "yards_gained",
        "pass_touchdown",
        "air_yards",
        "first_down_pass",
        "wpa",
    }
)

PBP_SAMPLE_ASSETS: Final[tuple[str, ...]] = ("pbp_2010", "pbp_2025")


def probe_status(url: str, timeout: int = 30) -> int:
    request = Request(url, method="HEAD", headers={"User-Agent": "nfl-coaching-impact-audit/0.1"})
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS manifest
            request, timeout=timeout, context=build_ssl_context()
        ) as response:
            return response.status
    except HTTPError as error:
        return error.code


def download_file(url: str, destination: Path, timeout: int = 60) -> None:
    request = Request(url, headers={"User-Agent": "nfl-coaching-impact-audit/0.1"})
    with urlopen(  # noqa: S310 - fixed HTTPS manifest
        request, timeout=timeout, context=build_ssl_context()
    ) as response:
        destination.write_bytes(response.read())


def inspect_csv(path: Path, required_columns: frozenset[str]) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(required_columns - columns)
        row_count = sum(1 for _ in reader)
    return {
        "row_count": row_count,
        "column_count": len(columns),
        "missing_required_columns": missing,
        "passed": not missing and row_count > 0,
    }


def inspect_pbp_rows(
    reader: csv.DictReader,
    minimum_dropbacks: int = 25,
    maximum_rows: int = 5_000,
) -> dict[str, object]:
    """Validate a bounded PBP stream without retaining or downloading the season."""
    columns = set(reader.fieldnames or [])
    missing = sorted(PBP_REQUIRED_COLUMNS - columns)
    rows_scanned = 0
    qb_dropbacks = 0
    qb_epa_values = 0
    resolved_qb_ids = 0

    if not missing:
        for row in reader:
            rows_scanned += 1
            if (
                row.get("qb_dropback") == "1"
                and row.get("qb_kneel") != "1"
                and row.get("qb_spike") != "1"
            ):
                qb_dropbacks += 1
                quarterback_id = row.get("passer_player_id") or (
                    row.get("rusher_player_id") if row.get("qb_scramble") == "1" else None
                )
                if quarterback_id and quarterback_id.startswith("00-"):
                    resolved_qb_ids += 1
                try:
                    if math.isfinite(float(row.get("qb_epa", ""))):
                        qb_epa_values += 1
                except (TypeError, ValueError):
                    pass
            if qb_dropbacks >= minimum_dropbacks or rows_scanned >= maximum_rows:
                break

    return {
        "rows_scanned": rows_scanned,
        "column_count": len(columns),
        "missing_required_columns": missing,
        "qb_dropbacks": qb_dropbacks,
        "qb_epa_values": qb_epa_values,
        "resolved_quarterback_ids": resolved_qb_ids,
        "passed": (
            not missing
            and qb_dropbacks >= minimum_dropbacks
            and qb_epa_values == qb_dropbacks
            and resolved_qb_ids == qb_dropbacks
        ),
    }


def load_pbp_sample(url: str, timeout: int = 60) -> dict[str, object]:
    """Stream a bounded remote play-by-play sample and validate its QB fields."""
    request = Request(url, headers={"User-Agent": "nfl-coaching-impact-audit/0.1"})
    with urlopen(  # noqa: S310 - fixed HTTPS manifest
        request, timeout=timeout, context=build_ssl_context()
    ) as response:
        with io.TextIOWrapper(response, encoding="utf-8", newline="") as handle:
            return inspect_pbp_rows(csv.DictReader(handle))


def audit(network: bool, download_samples: bool) -> dict[str, object]:
    report: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "network_enabled": network,
        "assets": [],
        "samples": {},
    }

    asset_results: list[dict[str, object]] = []
    for asset in ASSETS:
        result = asdict(asset)
        if network:
            try:
                observed = probe_status(asset.url)
                result.update(observed_status=observed, passed=observed == asset.expected_status)
            except (TimeoutError, URLError) as error:
                result.update(observed_status=None, passed=False, error=str(error))
        asset_results.append(result)
    report["assets"] = asset_results

    if download_samples:
        if not network:
            raise ValueError("--download-samples requires --network")
        by_name = {asset.name: asset for asset in ASSETS}
        with tempfile.TemporaryDirectory(prefix="nfl-coaching-audit-") as temporary:
            sample_results: dict[str, object] = {}
            for asset_name, (filename, required) in SAMPLE_SCHEMAS.items():
                destination = Path(temporary) / filename
                try:
                    download_file(by_name[asset_name].url, destination)
                    sample_results[asset_name] = inspect_csv(destination, required)
                except (TimeoutError, HTTPError, URLError) as error:
                    sample_results[asset_name] = {"passed": False, "error": str(error)}
            for asset_name in PBP_SAMPLE_ASSETS:
                try:
                    sample_results[asset_name] = load_pbp_sample(by_name[asset_name].url)
                except (TimeoutError, HTTPError, URLError) as error:
                    sample_results[asset_name] = {"passed": False, "error": str(error)}
            report["samples"] = sample_results
    return report


def report_passed(report: dict[str, object]) -> bool:
    asset_results = report["assets"]
    assert isinstance(asset_results, list)
    for item in asset_results:
        assert isinstance(item, dict)
        if "passed" in item and not item["passed"]:
            return False
    sample_results = report["samples"]
    assert isinstance(sample_results, dict)
    return all(isinstance(item, dict) and item.get("passed") for item in sample_results.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true", help="perform HEAD requests")
    parser.add_argument(
        "--download-samples",
        action="store_true",
        help="validate small 2025 CSVs and bounded 2010/2025 PBP streams",
    )
    parser.add_argument("--output", type=Path, help="optional JSON report destination")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = audit(args.network, args.download_samples)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0 if report_passed(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())

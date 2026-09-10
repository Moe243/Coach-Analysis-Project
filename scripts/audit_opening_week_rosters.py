"""Read-only weekly-roster coverage audit; never publishes target-team assignments.

Release bytes are hashed and parsed in memory, then discarded. Only aggregate audit
results go to stdout. Candidate matching counts are explicitly NOT timing-approved.
No models, state builders, publication routines, or upstream authenticated APIs run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import polars as pl
import requests

from nfl_coaching_impact.player_scheme_fit import (
    TARGET_SEASONS,
    _canonical_team,
    build_target_team_coverage,
)

RELEASE = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/weekly_rosters"
C15 = "c15-c4d7c86f56238a49"
C14 = "c14-43283062e788e686"
ENH = "enh-04254065cafd92ba"
KEY = ["player_id", "target_season"]


def read_candidate(asset: dict) -> tuple[dict, pl.DataFrame]:
    response = requests.get(asset["browser_download_url"], timeout=60)
    response.raise_for_status()
    content = response.content
    digest = hashlib.sha256(content).hexdigest()
    assert len(content) == asset["size"], "source size changed during audit"
    if asset.get("digest"):
        assert asset["digest"] == f"sha256:{digest}", "source hash changed during audit"
    frame = pl.read_parquet(io.BytesIO(content))
    year = int(asset["name"].split("_")[-1].split(".")[0])
    assert frame["season"].drop_nulls().unique().to_list() == [year]
    week = frame.filter((pl.col("game_type") == "REG") & (pl.col("week") == 1))
    qb = week.filter(pl.col("position") == "QB")
    assert not any(
        name in frame.columns
        for name in ("evidence_date", "observed_at", "published_at", "snapshot_timestamp")
    ), "timing fields changed: repeat provenance audit"
    audit = {
        "season": year,
        "source_url": asset["browser_download_url"],
        "source_sha256": digest,
        "bytes": len(content),
        "asset_updated_at": asset["updated_at"],
        "schema": {k: str(v) for k, v in frame.schema.items()},
        "rows": frame.height,
        "week1_rows": week.height,
        "week1_qb_rows": qb.height,
        "week1_qb_teams": qb["team"].n_unique(),
        "null_qb_ids": qb["gsis_id"].null_count(),
        "invalid_qb_ids": qb.filter(
            ~pl.col("gsis_id").str.contains(r"^00-\d{7}$").fill_null(False)
        ).height,
        "status_counts": qb.group_by("status", "status_description_abbr")
        .len()
        .sort("status", "status_description_abbr")
        .to_dicts(),
        "game_types": sorted(frame["game_type"].drop_nulls().unique().to_list()),
        "null_weeks": frame["week"].null_count(),
    }
    return audit, qb.select(
        "gsis_id", "season", "team", "full_name", "status", "status_description_abbr"
    ).with_columns(pl.col("season").cast(pl.Int64))


def summarize(candidates: pl.DataFrame, states: pl.DataFrame, performance: pl.DataFrame) -> dict:
    candidates = candidates.select(
        pl.col("gsis_id").alias("player_id"),
        pl.col("season").alias("target_season"),
        pl.col("team")
        .map_elements(_canonical_team, return_dtype=pl.String)
        .alias("target_team_id"),
    ).unique()
    null_identifiers = candidates.filter(
        pl.col("player_id").is_null() | pl.col("target_team_id").is_null()
    ).height
    candidates = candidates.drop_nulls()
    ambiguous = candidates.group_by(KEY).len().filter(pl.col("len") > 1)
    candidates = candidates.join(ambiguous.select(KEY), on=KEY, how="anti")
    assert candidates.height == candidates.unique(KEY).height
    # The existing helper uses this internal string to count matches. These are only
    # hypothetical count inputs; never written as a source or passed to any model.
    candidates = candidates.with_columns(
        pl.lit("PRESEASON_TARGET_TEAM_KNOWN").alias("target_team_status"),
        pl.lit("UNAPPROVED_WEEKLY_ROSTER_AUDIT_ONLY").alias("target_team_basis"),
    )
    seasons, categories, _ = build_target_team_coverage(states, candidates, performance)
    return {
        "timing_approved": False,
        "null_identifiers": null_identifiers,
        "ambiguous_player_seasons": ambiguous.height,
        "candidate_unique_player_seasons": candidates.height,
        "candidate_state_assignments": int(seasons["known_target_team_rows"].sum()),
        "candidate_participant_matches": int(
            seasons["participants_with_matching_outcome_team"].sum()
        ),
        "candidate_50db_outcome_rows": int(seasons["eligible_evaluation_rows"].sum()),
        "by_season": seasons.to_dicts(),
        "by_category": categories.to_dicts(),
    }


def diagnostic_status_filter() -> pl.Expr:
    """Coverage sensitivity only: these status codes do not prove pregame membership."""
    # Pre-2016 status is overwritten from Shield: inspect original weekly codes.
    old_member = pl.col("status_description_abbr").str.contains(r"^(A|I|P|R)\d{2}$") & (
        pl.col("status_description_abbr") != "R02"
    )
    newer_member = pl.col("status").is_in(["ACT", "INA", "DEV", "RES"])
    return pl.when(pl.col("season") < 2016).then(old_member).otherwise(newer_member)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root / "data/processed"
    manifest = json.loads((root / f"player_scheme_fit/{C15}/MANIFEST.json").read_text())
    paths = {
        "c14_states": root / f"qb_player_state/{C14}/player_states.parquet",
        "performance": root / f"enhancements/{ENH}/canonical_qb_team_season_performance.parquet",
    }
    captured = {name: path.read_bytes() for name, path in paths.items()}
    for name, content in captured.items():
        assert hashlib.sha256(content).hexdigest() == manifest["identity"]["inputs"][name]
    states = pl.read_parquet(io.BytesIO(captured["c14_states"]))
    performance = pl.read_parquet(io.BytesIO(captured["performance"]))
    assignment_bytes = (
        root / f"player_scheme_fit/{C15}/preseason_target_team_assignments.parquet"
    ).read_bytes()
    assert (
        hashlib.sha256(assignment_bytes).hexdigest()
        == manifest["output_checksums"]["preseason_target_team_assignments.parquet"]
    )
    existing = pl.read_parquet(io.BytesIO(assignment_bytes))
    before, before_categories, _ = build_target_team_coverage(states, existing, performance)
    assert before["known_target_team_rows"].sum() == 265
    assert before["eligible_evaluation_rows"].sum() == 130
    response = requests.get(RELEASE, timeout=60)
    response.raise_for_status()
    release = response.json()
    assets = {a["name"]: a for a in release["assets"]}
    selected = [assets[f"roster_weekly_{y}.parquet"] for y in TARGET_SEASONS]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fetched = list(pool.map(read_candidate, selected))
    candidates = pl.concat([f for _, f in fetched])
    status_screen = diagnostic_status_filter()
    variants = {
        "all_week1_qb_records": summarize(candidates, states, performance),
        "status_screen_diagnostic": summarize(
            candidates.filter(status_screen), states, performance
        ),
    }
    # Permuting rows must not alter aggregate results or ambiguity handling.
    assert variants["status_screen_diagnostic"] == summarize(
        candidates.filter(status_screen).reverse(), states, performance
    )
    print(
        json.dumps(
            {
                "audit_only": True,
                "decision": "CONDITIONAL_TIMING_UNPROVEN",
                "raw_data_retained": False,
                "approved_new_assignments": 0,
                "checkpoint_15_rerun_readiness": "NOT READY",
                "checkpoint_16_readiness": "NOT READY",
                "m2_validation_pilot": "NOT RUN: provenance/timing gate not passed",
                "baseline_version": C15,
                "input_hashes": {name: manifest["identity"]["inputs"][name] for name in paths},
                "release_id": release["id"],
                "historical_parquet_seasons": sorted(
                    int(n.split("_")[-1].split(".")[0])
                    for n in assets
                    if n.startswith("roster_weekly_") and n.endswith(".parquet")
                ),
                "source_assets": [a for a, _ in fetched],
                "baseline_seasons": before.to_dicts(),
                "baseline_categories": before_categories.to_dicts(),
                "variants": variants,
                "checks": [
                    "pinned_local_input_hashes",
                    "baseline_counts_reconciled",
                    "source_byte_sizes_and_available_release_digests",
                    "source_seasons",
                    "no_evidence_timestamps",
                    "one_candidate_per_player_season",
                    "multi_team_conflicts_excluded",
                    "row_order_invariance",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Audit mechanics only; passing tests do not approve historical roster timing."""

import hashlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_opening_week_rosters.py"
SPEC = importlib.util.spec_from_file_location("opening_week_audit", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_conflicting_teams_are_not_resolved_using_outcomes_or_backfilled_states():
    states = pl.DataFrame(
        {"player_id": ["00-0000001"], "target_season": [2011], "is_rookie": [False]}
    )
    candidates = pl.DataFrame(
        {
            "gsis_id": ["00-0000001", "00-0000001", "00-0000002"],
            "season": [2011] * 3,
            "team": ["BUF", "JAX", "BUF"],
        }
    )
    performance = pl.DataFrame(
        {
            "player_id": ["00-0000001", "00-0000002"],
            "season": [2011] * 2,
            "team_id": ["team_buf"] * 2,
            "dropbacks": [100] * 2,
            "scope": ["analysis"] * 2,
        }
    )
    result = audit.summarize(candidates, states, performance)
    assert result["ambiguous_player_seasons"] == 1
    assert result["candidate_unique_player_seasons"] == 1
    assert result["candidate_state_assignments"] == 0
    assert result["candidate_participant_matches"] == 0
    assert result == audit.summarize(candidates.reverse(), states, performance)
    assert states.height == 1


def test_duplicate_candidates_count_once_and_outcome_team_cannot_replace_roster_team():
    states = pl.DataFrame(
        {"player_id": ["00-0000001"], "target_season": [2011], "is_rookie": [False]}
    )
    candidates = pl.DataFrame(
        {"gsis_id": ["00-0000001"] * 2, "season": [2011] * 2, "team": ["BUF"] * 2}
    )
    performance = pl.DataFrame(
        {
            "player_id": ["00-0000001"],
            "season": [2011],
            "team_id": ["team_jax"],
            "dropbacks": [100],
            "scope": ["analysis"],
        }
    )
    result = audit.summarize(candidates, states, performance)
    assert result["candidate_state_assignments"] == 1
    assert result["candidate_participant_matches"] == 0
    assert result["candidate_50db_outcome_rows"] == 0
    assert not result["timing_approved"]


def test_status_sensitivity_does_not_treat_shield_final_status_as_weekly_status():
    frame = pl.DataFrame(
        {
            "season": [2011, 2025, 2025, 2011],
            "status": ["CUT", "CUT", "DEV", "ACT"],
            "status_description_abbr": ["A01", "A01", "P01", "R02"],
        }
    )
    screened = frame.filter(audit.diagnostic_status_filter())
    assert screened.select("season", "status").rows() == [(2011, "CUT"), (2025, "DEV")]


def test_source_bytes_hash_week_and_position_filter_and_changed_schema_guard():
    frame = pl.DataFrame(
        {
            "season": [2011] * 4,
            "week": [1, 2, 1, 1],
            "game_type": ["REG", "REG", "REG", "WC"],
            "position": ["QB", "QB", "WR", "QB"],
            "gsis_id": ["00-0000001"] * 4,
            "team": ["BUF"] * 4,
            "full_name": ["Fixture QB"] * 4,
            "status": ["ACT"] * 4,
            "status_description_abbr": ["A01"] * 4,
        }
    )

    def fetch(source, bad_digest=False):
        buffer = io.BytesIO()
        source.write_parquet(buffer)
        content = buffer.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        response = SimpleNamespace(content=content, raise_for_status=lambda: None)
        asset = {
            "browser_download_url": "https://example.test/fixture",
            "size": len(content),
            "digest": "sha256:" + ("0" * 64 if bad_digest else digest),
            "name": "roster_weekly_2011.parquet",
            "updated_at": "2026-09-10T00:00:00Z",
        }
        with patch.object(audit.requests, "get", return_value=response):
            return audit.read_candidate(asset), digest

    (metadata, candidates), digest = fetch(frame)
    assert candidates.height == 1
    assert metadata["source_sha256"] == digest
    with pytest.raises(AssertionError, match="hash changed"):
        fetch(frame, bad_digest=True)
    with pytest.raises(AssertionError, match="timing fields changed"):
        fetch(frame.with_columns(pl.lit("2011-09-01").alias("observed_at")))

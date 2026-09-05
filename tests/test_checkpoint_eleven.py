from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

import polars as pl
import scipy

from nfl_coaching_impact.coaching import validate_coaching_data
from research.coach_effect.checkpoint_eleven import (
    _verify_source_hashes,
    aggregate_historical_pcae,
    attribute_verified_calls,
    build_coaching_coverage,
    fit_historical_models,
    prepare_historical_plays,
)
from research.coach_effect.config import (
    CALL_VALUE_FORMULA,
    HISTORICAL_PCAE_MODEL_VERSION,
    HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION,
    PCAE_FORMULA,
    PLAY_CALL_FEATURES,
)

ROOT = Path(__file__).resolve().parents[1]


def _plays(seasons: tuple[int, ...], rows_per_season: int = 24) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for season in seasons:
        for index in range(rows_per_season):
            is_pass = index % 2 == 0
            row: dict[str, object] = {
                "game_id": f"{season}_01_ARI_ATL",
                "play_id": index + 1,
                "season": season,
                "season_type": "REG",
                "week": 1,
                "posteam": "ARI",
                "play_type": "pass" if is_pass else "run",
                "epa": (0.08 if is_pass else -0.02) + index / 1_000,
                "two_point_attempt": 0,
            }
            row.update(
                {
                    feature: float(index + feature_index + 1)
                    for feature_index, feature in enumerate(PLAY_CALL_FEATURES)
                }
            )
            rows.append(row)
    return pl.DataFrame(rows)


def _assignment(
    key: str,
    coach: str,
    start: int,
    end: int,
    *,
    status: str = "verified",
    shared: bool = False,
    role: str = "play_caller",
) -> dict[str, object]:
    return {
        "assignment_key": key,
        "season": 2020,
        "team_id": "HOU",
        "coach_id": coach,
        "coach_canonical_name": coach,
        "role": role,
        "start_week": start,
        "end_week": end,
        "verification_status": status,
        "confidence_level": "high" if status == "verified" else "medium",
        "interval_basis": ("dated_source_weeks" if status == "verified" else "season_designation"),
        "is_shared": shared,
        "primary_source_url": "https://example.test/source",
    }


class CheckpointElevenTests(unittest.TestCase):
    def test_changed_input_fails_closed_before_research_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "manual.csv"
            source.write_text("first\n", encoding="utf-8")
            expected = {"manual.csv": hashlib.sha256(source.read_bytes()).hexdigest()}
            source.write_text("second\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inputs changed during build"):
                _verify_source_hashes(root, expected)

    def test_scipy_is_part_of_the_historical_model_identity(self) -> None:
        source = (ROOT / "research/coach_effect/checkpoint_eleven.py").read_text(encoding="utf-8")
        self.assertIn('"scipy": scipy.__version__', source)
        self.assertTrue(scipy.__version__)

    def test_complete_coaching_matrix_has_one_explicit_status_per_cell(self) -> None:
        coverage, unresolved = build_coaching_coverage(ROOT)
        self.assertEqual(2_048, coverage.height)
        self.assertEqual(2_048, coverage.select("season", "team_id", "role").n_unique())
        statuses = set(coverage["coverage_status"].unique())
        self.assertTrue(
            statuses
            <= {
                "verified_person",
                "verified_no_designated_role",
                "partial",
                "provisional",
                "conflicting",
                "unresolved",
            }
        )
        self.assertTrue({"verified_person", "provisional", "unresolved"} <= statuses)
        self.assertEqual(
            512,
            coverage.filter(
                (pl.col("role") == "head_coach") & (pl.col("coverage_status") == "verified_person")
            ).height,
        )
        self.assertEqual(512, coverage.filter(pl.col("role") == "play_caller").height)
        self.assertTrue(unresolved.select("season", "team_id", "role").is_duplicated().not_().all())

    def test_new_play_caller_designations_remain_provisional_and_queued(self) -> None:
        validate_coaching_data(ROOT)
        with (ROOT / "data/manual/coaching_assignments.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            assignments = list(csv.DictReader(handle))
        with (ROOT / "data/manual/coaching_review_queue.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            reviews = list(csv.DictReader(handle))
        callers = [
            row
            for row in assignments
            if row["season"] == "2020" and row["role"] == "play_caller" and row["team_id"] != "HOU"
        ]
        self.assertEqual(31, len(callers))
        self.assertEqual({"provisional"}, {row["verification_status"] for row in callers})
        self.assertEqual({"season_designation"}, {row["interval_basis"] for row in callers})
        review_grains = {
            (row["season"], row["team_id"], row["role"], row["issue_type"])
            for row in reviews
            if row["status"] == "open"
        }
        for row in callers:
            self.assertIn(
                (
                    "2020",
                    row["team_id"],
                    "play_caller",
                    "season_interval_verification_required",
                ),
                review_grains,
            )

    def test_exact_historical_count_difference_is_two_point_conversions(self) -> None:
        candidate_count = 134_138
        excluded_count = 502
        raw = pl.DataFrame({"play_id": pl.arange(1, candidate_count + 1, eager=True)}).with_columns(
            pl.lit("fixture-game").alias("game_id"),
            pl.lit(2025).alias("season"),
            pl.lit("REG").alias("season_type"),
            pl.lit(1).alias("week"),
            pl.lit("ARI").alias("posteam"),
            pl.when(pl.col("play_id") % 2 == 0)
            .then(pl.lit("pass"))
            .otherwise(pl.lit("run"))
            .alias("play_type"),
            pl.lit(0.1).alias("epa"),
            (pl.col("play_id") <= excluded_count).cast(pl.Int8).alias("two_point_attempt"),
            pl.when(pl.col("play_id") <= excluded_count)
            .then(pl.lit(None, dtype=pl.Float64))
            .otherwise(pl.lit(1.0))
            .alias("down"),
            *[pl.lit(1.0).alias(feature) for feature in PLAY_CALL_FEATURES if feature != "down"],
        )
        eligible, audit = prepare_historical_plays(raw)
        self.assertEqual(candidate_count, audit["regular_season_run_pass"])
        self.assertEqual(excluded_count, audit["two_point_conversions_excluded"])
        self.assertEqual(133_636, eligible.height)

    def test_eligibility_rejects_null_and_duplicate_play_keys(self) -> None:
        raw = _plays((2020,), rows_per_season=4)
        with self.assertRaisesRegex(ValueError, "null identifiers"):
            prepare_historical_plays(raw.with_columns(pl.lit(None).alias("game_id")))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prepare_historical_plays(pl.concat([raw, raw.head(1)]))

    def test_expanding_model_uses_only_true_prior_seasons(self) -> None:
        training, _ = prepare_historical_plays(_plays((1999, 2000)))
        target, _ = prepare_historical_plays(_plays((2001,)))
        models, scored = fit_historical_models(training, target, 2001)
        self.assertEqual((1999, 2000), models.train_seasons)
        self.assertEqual(2001, models.test_season)
        self.assertEqual({2001}, set(scored["season"].unique()))
        with self.assertRaisesRegex(ValueError, "strictly earlier"):
            fit_historical_models(pl.concat([training, target]), target, 2001)

    def test_weekly_attribution_suppresses_shared_and_provisional_intervals(self) -> None:
        scored = pl.DataFrame(
            {
                "game_id": ["g3", "g4", "g5"],
                "play_id": [1, 1, 1],
                "season": [2020, 2020, 2020],
                "week": [3, 4, 5],
                "team_id": ["HOU", "HOU", "HOU"],
                "call_value": [0.10, 0.20, 0.30],
            }
        )
        assignments = pl.DataFrame(
            [
                _assignment("kelly-1-3", "coach-tim-kelly", 1, 3),
                _assignment("kelly-4", "coach-tim-kelly", 4, 4, shared=True),
                _assignment("obrien-4", "coach-bill-obrien", 4, 4, shared=True),
                _assignment(
                    "kelly-5-17",
                    "coach-tim-kelly",
                    5,
                    17,
                    status="provisional",
                ),
            ]
        )
        attributed, unresolved = attribute_verified_calls(scored, assignments)
        self.assertEqual(["g3"], attributed["game_id"].to_list())
        self.assertEqual(
            {
                "g4": "shared_or_ambiguous_interval",
                "g5": "no_verified_interval",
            },
            dict(zip(unresolved["game_id"], unresolved["reason"], strict=True)),
        )

    def test_unresolved_calls_are_never_defaulted_to_the_oc(self) -> None:
        scored = pl.DataFrame(
            {
                "game_id": ["g"],
                "play_id": [1],
                "season": [2020],
                "week": [1],
                "team_id": ["HOU"],
                "call_value": [0.1],
            }
        )
        attributed, unresolved = attribute_verified_calls(
            scored,
            pl.DataFrame([_assignment("oc", "coach-oc", 1, 17, role="offensive_coordinator")]),
        )
        self.assertTrue(attributed.is_empty())
        self.assertEqual(["no_verified_interval"], unresolved["reason"].to_list())

    def test_historical_pcae_uses_the_unchanged_league_centered_formula(self) -> None:
        attributed = pl.DataFrame(
            {
                "coach_id": ["a", "b"],
                "coach_canonical_name": ["A", "B"],
                "team_id": ["ARI", "ATL"],
                "season": [2020, 2020],
                "start_week": [1, 1],
                "end_week": [17, 17],
                "verification_status": ["verified", "verified"],
                "confidence_level": ["high", "high"],
                "is_shared": [False, False],
                "call_value": [0.2, -0.2],
            }
        )
        result = aggregate_historical_pcae(attributed)
        self.assertEqual([0.2, -0.2], result["pcae"].to_list())
        self.assertEqual("expected_chosen_epa - expected_alternative_epa", CALL_VALUE_FORMULA)
        self.assertEqual("coach_average_call_value - league_average_call_value", PCAE_FORMULA)
        self.assertEqual("pcae-play-eligibility-v2", HISTORICAL_PCAE_PLAY_ELIGIBILITY_VERSION)
        self.assertEqual("pcae-expanding-prior-seasons-v1", HISTORICAL_PCAE_MODEL_VERSION)


if __name__ == "__main__":
    unittest.main()

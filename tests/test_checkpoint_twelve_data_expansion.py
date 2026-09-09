from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

from research.coach_effect.checkpoint_twelve_data_expansion import (
    EXPECTED_STARTING_CALLER_COUNTS,
    OUTPUT_NAMES,
    build_feature_availability,
    build_ftn_profiles,
    build_participation_profiles,
    build_pbp_profiles,
    build_play_caller_coverage,
    build_scheme_fingerprints,
    load_and_validate_play_caller_evidence,
    parse_offense_personnel,
    run_checkpoint_twelve_data_expansion,
)

ROOT = Path(__file__).resolve().parents[1]


def _pbp_fixture() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "game_id": "2022_01_A_B",
                "play_id": 1,
                "season": 2022,
                "season_type": "REG",
                "week": 1,
                "posteam": "ARI",
                "team_id": "ARI",
                "play_type": "pass",
                "two_point_attempt": 0,
                "epa": 1.0,
                "success": 1.0,
                "down": 1,
                "qtr": 1,
                "yardline_100": 50.0,
                "game_seconds_remaining": 3000.0,
                "score_differential": 0.0,
                "pass_attempt": 1,
                "rush_attempt": 0,
                "shotgun": 1,
                "no_huddle": 0,
                "qb_dropback": 1,
                "qb_kneel": 0,
                "qb_spike": 0,
                "qb_scramble": 0,
                "sack": 0,
                "rusher_player_id": None,
                "pass_length": "short",
                "pass_location": "left",
                "air_yards": 7.0,
                "xpass": 0.7,
                "pass_oe": 0.3,
            },
            {
                "game_id": "2022_01_A_B",
                "play_id": 2,
                "season": 2022,
                "season_type": "REG",
                "week": 1,
                "posteam": "ARI",
                "team_id": "ARI",
                "play_type": "run",
                "two_point_attempt": 0,
                "epa": -0.5,
                "success": 0.0,
                "down": 2,
                "qtr": 1,
                "yardline_100": 18.0,
                "game_seconds_remaining": 2900.0,
                "score_differential": 0.0,
                "pass_attempt": 0,
                "rush_attempt": 1,
                "shotgun": 0,
                "no_huddle": 1,
                "qb_dropback": 0,
                "qb_kneel": 0,
                "qb_spike": 0,
                "qb_scramble": 0,
                "sack": 0,
                "rusher_player_id": "00-1",
                "pass_length": None,
                "pass_location": None,
                "air_yards": None,
                "xpass": 0.4,
                "pass_oe": -0.4,
            },
        ]
    )


class PromptEightEvidenceTest(unittest.TestCase):
    def test_exact_coverage_matrix_and_top_25(self) -> None:
        evidence = load_and_validate_play_caller_evidence(ROOT)
        coverage, new_cells, intervals = build_play_caller_coverage(ROOT, evidence)
        self.assertEqual(coverage.height, 512)
        self.assertEqual(coverage.select("season", "team_id").n_unique(), 512)
        self.assertEqual(
            dict(coverage.group_by("starting_status").len().iter_rows()),
            EXPECTED_STARTING_CALLER_COUNTS,
        )
        self.assertEqual(new_cells.height, 25)
        self.assertEqual(intervals["research_assignment_key"].n_unique(), intervals.height)
        self.assertEqual(
            evidence.filter(pl.col("batch") == "top25").select("season", "team_id").n_unique(),
            25,
        )

    def test_title_only_text_cannot_verify_play_calling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "research/coach_effect"
            target.mkdir(parents=True)
            source = ROOT / "research/coach_effect/play_caller_evidence_prompt8.csv"
            with source.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
                fieldnames = list(rows[0])
            first_verified = next(row for row in rows if row["interval_status"] == "verified")
            first_verified["evidence_summary"] = "Offensive Coordinator title only."
            with (target / source.name).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "explicit play-calling"):
                load_and_validate_play_caller_evidence(root)

    def test_shared_and_transition_intervals_are_preserved(self) -> None:
        evidence = load_and_validate_play_caller_evidence(ROOT)
        arizona = evidence.filter((pl.col("season") == 2021) & (pl.col("team_id") == "ARI"))
        self.assertEqual(arizona.select("start_week", "end_week").rows(), [(1, 5), (6, 6), (7, 18)])
        self.assertEqual(
            arizona["interval_status"].to_list(), ["verified", "verified", "provisional"]
        )
        shared = evidence.filter(pl.col("is_shared"))
        self.assertEqual(shared.select("season", "team_id").rows(), [(2021, "KC")])
        self.assertEqual(shared["interval_status"].to_list(), ["unresolved"])


class PromptEightSchemeTest(unittest.TestCase):
    def test_personnel_parser_is_explicit_and_handles_fullbacks(self) -> None:
        self.assertEqual(parse_offense_personnel("1 RB, 1 TE, 3 WR")["personnel_group"], "11")
        parsed = parse_offense_personnel("1 RB, 1 FB, 1 TE, 2 WR, 1 QB, 5 OL")
        self.assertEqual((parsed["running_backs"], parsed["tight_ends"]), (2, 1))
        self.assertEqual(parsed["personnel_group"], "21")
        self.assertIsNone(parse_offense_personnel("1 RB, 2 CB, 8 unknown")["personnel_group"])

    def test_personnel_denominators_and_formation_are_independent(self) -> None:
        pbp = _pbp_fixture()
        participation = pl.DataFrame(
            {
                "nflverse_game_id": ["2022_01_A_B", "2022_01_A_B"],
                "play_id": [1, 2],
                "possession_team": ["ARI", "ARI"],
                "offense_formation": ["SHOTGUN", "UNDER CENTER"],
                "offense_personnel": ["1 RB, 1 TE, 3 WR", "1 RB, 2 TE, 2 WR"],
                "n_offense": [11, 11],
            }
        )
        personnel, families, formations, missingness = build_participation_profiles(
            participation, pbp, "source-hash"
        )
        rates = dict(personnel.select("feature_name", "raw_value").iter_rows())
        self.assertEqual(rates["personnel_11_rate"], 0.5)
        self.assertEqual(rates["personnel_12_rate"], 0.5)
        self.assertTrue((personnel["eligible_plays"] == 2).all())
        self.assertEqual(
            families.filter(pl.col("feature_name") == "personnel_family_multiple_te_rate")[
                "raw_value"
            ].item(),
            0.5,
        )
        formation_rates = dict(formations.select("feature_name", "raw_value").iter_rows())
        self.assertEqual(formation_rates["formation_shotgun_rate"], 0.5)
        self.assertEqual(formation_rates["formation_under_center_rate"], 0.5)
        self.assertEqual(missingness["parsed_personnel_plays"].item(), 2)

    def test_ftn_mechanics_use_only_explicit_fields(self) -> None:
        ftn = pl.DataFrame(
            {
                "nflverse_game_id": ["2022_01_A_B", "2022_01_A_B"],
                "nflverse_play_id": [1, 2],
                "season": [2022, 2022],
                "week": [1, 1],
                "qb_location": ["S", "P"],
                "is_motion": [True, False],
                "is_play_action": [False, True],
                "is_screen_pass": [True, False],
                "is_rpo": [False, True],
            }
        )
        mechanics, formation = build_ftn_profiles(ftn, _pbp_fixture(), "ftn-hash")
        rates = dict(mechanics.select("feature_name", "raw_value").iter_rows())
        self.assertEqual(
            rates,
            {"motion_rate": 0.5, "play_action_rate": 0.5, "rpo_rate": 0.5, "screen_rate": 0.5},
        )
        self.assertEqual(
            formation.filter(pl.col("feature_name") == "ftn_pistol_rate")["raw_value"].item(),
            0.5,
        )

    def test_tendencies_preserve_choices_and_outcomes_separately(self) -> None:
        tendencies, qb_usage, situations, outcomes = build_pbp_profiles(
            _pbp_fixture(), {"fixture": "hash"}
        )
        rates = dict(tendencies.select("feature_name", "raw_value").iter_rows())
        self.assertEqual(rates["pass_rate"], 0.5)
        self.assertEqual(rates["shotgun_rate"], 0.5)
        self.assertEqual(rates["expected_pass_rate"], 0.55)
        self.assertEqual(
            qb_usage.filter(pl.col("feature_name") == "target_depth_short_rate")[
                "raw_value"
            ].item(),
            1.0,
        )
        self.assertIn("early_down_pass_rate", situations["feature_name"].to_list())
        self.assertIn("offensive_epa_per_play", outcomes["feature_name"].to_list())
        self.assertFalse(set(tendencies["feature_name"]) & set(outcomes["feature_name"]))

    def test_standardization_is_within_season_and_raw_values_remain(self) -> None:
        profile = pl.DataFrame(
            {
                "team_id": ["ARI", "ATL"],
                "season": [2022, 2022],
                "profile_family": ["tendency", "tendency"],
                "feature_name": ["pass_rate", "pass_rate"],
                "raw_count": [40, 60],
                "eligible_plays": [100, 100],
                "raw_value": [0.4, 0.6],
                "source_dataset": ["fixture", "fixture"],
                "source_hash": ["hash", "hash"],
                "definition_version": ["v1", "v1"],
                "missingness_reason": [None, None],
            }
        )
        wide, long = build_scheme_fingerprints(profile)
        self.assertEqual(wide.height, 2)
        self.assertEqual(long["raw_value"].to_list(), [0.4, 0.6])
        self.assertAlmostEqual(float(long["standardized_value"].mean()), 0.0)
        self.assertAlmostEqual(float(long["standardized_value"].std(ddof=0)), 1.0)

    def test_unavailable_features_are_not_backfilled(self) -> None:
        profile = pl.DataFrame(
            {
                "team_id": ["ARI"],
                "season": [2022],
                "profile_family": ["tendency"],
                "feature_name": ["pass_rate"],
                "raw_count": [50],
                "eligible_plays": [100],
                "raw_value": [0.5],
                "source_dataset": ["fixture"],
                "source_hash": ["hash"],
                "definition_version": ["v1"],
                "missingness_reason": [None],
            }
        )
        missingness = pl.DataFrame({"matched_plays": [100], "parsed_personnel_plays": [80]})
        availability = build_feature_availability(profile, missingness)
        designed = availability.filter(pl.col("feature_name") == "designed_qb_run_rate")
        self.assertEqual(designed["status"].item(), "UNAVAILABLE")
        self.assertEqual(designed["observed_team_seasons"].item(), 0)


class PromptEightDeterminismTest(unittest.TestCase):
    def test_two_independent_full_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = run_checkpoint_twelve_data_expansion(ROOT, base / "first", allow_network=False)
            second = run_checkpoint_twelve_data_expansion(
                ROOT, base / "second", allow_network=False
            )
            self.assertEqual(first.data_version, second.data_version)
            for name in ("MANIFEST.json", *OUTPUT_NAMES):
                self.assertEqual(
                    (first.output_path / name).read_bytes(),
                    (second.output_path / name).read_bytes(),
                    name,
                )
            manifest = json.loads((first.output_path / "MANIFEST.json").read_text())
            self.assertTrue(manifest["research_only"])
            self.assertFalse(manifest["final_equation_fitted"])
            self.assertFalse(manifest["production_ranking"])
            self.assertEqual(set(manifest["output_checksums"]), set(OUTPUT_NAMES))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from nfl_coaching_impact.serving import _manual_snapshot
from nfl_coaching_impact.serving_completeness import (
    EVIDENCE_VERSION,
    EXPECTED_STATUS_COUNTS,
    NO_ROLE_STATUS,
    build_serving_coaching_completeness,
)

ROOT = Path(__file__).resolve().parents[1]


class ServingCoachingCompletenessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manual = _manual_snapshot(ROOT)
        cls.result = build_serving_coaching_completeness(cls.manual.rows)

    def test_final_role_matrix_matches_checkpoint_eleven_b(self) -> None:
        self.assertEqual(2_048, self.result.height)
        self.assertEqual(
            2_048,
            self.result.select("season", "team_id", "role").n_unique(),
        )
        for role, expected in EXPECTED_STATUS_COUNTS.items():
            rows = self.result.filter(self.result["role"] == role)
            self.assertEqual(512, rows.height)
            self.assertEqual(expected, dict(Counter(rows["assignment_status"].to_list())))

    def test_no_role_is_resolved_sourced_and_person_free(self) -> None:
        no_role = self.result.filter(self.result["assignment_status"] == NO_ROLE_STATUS)
        self.assertEqual(40, no_role.height)
        self.assertTrue((no_role["assignment_count"] == 0).all())
        self.assertTrue((no_role["verified_assignment_count"] == 0).all())
        self.assertTrue(all(row == EVIDENCE_VERSION for row in no_role["evidence_version"]))
        for row in no_role.to_dicts():
            self.assertTrue(row["source_urls"])
            self.assertTrue(row["evidence_intervals"])
            self.assertTrue(all(item["coach_id"] is None for item in row["evidence_intervals"]))

    def test_known_no_role_and_mixed_interval_cells_are_preserved(self) -> None:
        for season, team, role in (
            (2010, "ARI", "offensive_coordinator"),
            (2010, "DET", "quarterbacks_coach"),
        ):
            row = self.result.filter(
                (self.result["season"] == season)
                & (self.result["team_id"] == team)
                & (self.result["role"] == role)
            ).to_dicts()[0]
            self.assertEqual(NO_ROLE_STATUS, row["assignment_status"])
            self.assertEqual(0, row["assignment_count"])

        mixed_keys = {
            (row["season"], row["team_id"], row["role"])
            for row in self.result.to_dicts()
            if {item["evidence_type"] for item in row["evidence_intervals"]}
            == {"person_assignment", NO_ROLE_STATUS}
        }
        self.assertEqual(
            {
                (2016, "JAX", "quarterbacks_coach"),
                (2017, "CIN", "quarterbacks_coach"),
                (2018, "ARI", "quarterbacks_coach"),
            },
            mixed_keys,
        )

    def test_play_caller_status_is_not_inferred_from_oc(self) -> None:
        for row in self.result.filter(self.result["role"] == "play_caller").to_dicts():
            self.assertTrue(
                all(
                    "-play_caller-" in interval["evidence_key"]
                    for interval in row["evidence_intervals"]
                    if interval["evidence_type"] == "person_assignment"
                )
            )

    def test_rebuild_is_byte_identical(self) -> None:
        second = build_serving_coaching_completeness(self.manual.rows)
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.parquet"
            second_path = Path(directory) / "second.parquet"
            self.result.write_parquet(first_path)
            second.write_parquet(second_path)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())


if __name__ == "__main__":
    unittest.main()

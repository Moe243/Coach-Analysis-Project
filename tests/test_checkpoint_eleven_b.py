from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

import polars as pl

from nfl_coaching_impact.coaching import CoachingDataError, validate_coaching_data
from research.coach_effect.checkpoint_eleven_b import (
    build_evidence_coverage,
    run_checkpoint_eleven_b,
    validate_checkpoint_eleven_b_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


class CheckpointElevenBTests(unittest.TestCase):
    @staticmethod
    def _read(name: str) -> list[dict[str, str]]:
        with (ROOT / "data" / "manual" / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _copy_manual(directory: Path) -> Path:
        target = directory / "project" / "data" / "manual"
        target.mkdir(parents=True)
        for path in (ROOT / "data" / "manual").glob("*.csv"):
            shutil.copy2(path, target / path.name)
        return directory / "project"

    @staticmethod
    def _mutate(path: Path, change) -> None:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
            fields = list(rows[0])
        change(rows)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_formal_role_verification_requires_explicit_cited_title_evidence(self) -> None:
        targets = {
            "2010-ATL-offensive_coordinator-01-17-mike-mularkey": "offensive_coordinator",
            "2010-ARI-quarterbacks_coach-01-17-chris-miller": "quarterbacks_coach",
        }
        for assignment_key, role in targets.items():
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = self._copy_manual(Path(directory))
                evidence = root / "data/manual/coaching_evidence_11b.csv"

                def remove_role_evidence(
                    rows: list[dict[str, str]], key: str = assignment_key
                ) -> None:
                    for row in rows:
                        if row["assignment_key"] == key:
                            row["evidence_note"] = "A source exists but contains no role title."

                self._mutate(evidence, remove_role_evidence)
                with self.assertRaisesRegex(ValueError, "explicit title evidence"):
                    validate_checkpoint_eleven_b_evidence(root)

    def test_research_overlay_does_not_promote_frozen_serving_assignments(self) -> None:
        assignment_key = "2010-ATL-offensive_coordinator-01-17-mike-mularkey"
        serving = next(
            row
            for row in self._read("coaching_assignments.csv")
            if row["assignment_key"] == assignment_key
        )
        evidence = next(
            row
            for row in self._read("coaching_evidence_11b.csv")
            if row["assignment_key"] == assignment_key
        )
        self.assertEqual("provisional", serving["verification_status"])
        self.assertEqual("verified", evidence["verification_status"])
        self.assertEqual("season_designation", evidence["interval_basis"])
        self.assertEqual("true", evidence["weekly_review_required"])

    def test_title_only_cannot_verify_play_caller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_manual(Path(directory))
            checks = root / "data/manual/coaching_source_content_checks.csv"
            assignment_key = "2023-ARI-play_caller-01-18-drew-petzing"
            self._mutate(
                checks,
                lambda rows: rows.__setitem__(
                    slice(None),
                    [
                        row
                        for row in rows
                        if assignment_key not in row["assignment_keys"].split("|")
                    ],
                ),
            )
            with self.assertRaisesRegex(CoachingDataError, "content check"):
                validate_coaching_data(root)

    def test_oc_is_never_automatically_populated_as_play_caller(self) -> None:
        assignments = self._read("coaching_assignments.csv")
        self.assertTrue(
            any(
                row["season"] == "2010"
                and row["team_id"] == "ATL"
                and row["role"] == "offensive_coordinator"
                for row in assignments
            )
        )
        self.assertFalse(
            any(
                row["season"] == "2010" and row["team_id"] == "ATL" and row["role"] == "play_caller"
                for row in assignments
            )
        )

    def test_weekly_intervals_cannot_exceed_the_regular_season(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_manual(Path(directory))
            assignments = root / "data/manual/coaching_assignments.csv"

            def extend_past_season(rows: list[dict[str, str]]) -> None:
                next(row for row in rows if row["season"] == "2010")["end_week"] = "18"

            self._mutate(assignments, extend_past_season)
            with self.assertRaisesRegex(CoachingDataError, "invalid week interval"):
                validate_coaching_data(root)

    def test_recent_play_callers_have_complete_verified_weekly_coverage(self) -> None:
        coverage, _ = build_evidence_coverage(ROOT)
        recent = coverage.filter(
            (pl.col("role") == "play_caller") & pl.col("season").is_in([2024, 2025])
        )
        self.assertEqual(64, recent.height)
        self.assertEqual({"verified"}, set(recent["coverage_status"]))

        assignments = self._read("coaching_assignments.csv")
        expected = {
            (2024, "NYJ"): [(1, 5, "Nathaniel Hackett"), (6, 18, "Todd Downing")],
            (2025, "TEN"): [(1, 3, "Brian Callahan"), (4, 18, "Bo Hardegree")],
        }
        for (season, team), intervals in expected.items():
            actual = [
                (int(row["start_week"]), int(row["end_week"]), row["coach_canonical_name"])
                for row in assignments
                if row["season"] == str(season)
                and row["team_id"] == team
                and row["role"] == "play_caller"
            ]
            self.assertEqual(intervals, actual)

    def test_jacksonville_2023_uses_official_press_taylor_evidence(self) -> None:
        row = next(
            row
            for row in self._read("coaching_assignments.csv")
            if row["season"] == "2023" and row["team_id"] == "JAX" and row["role"] == "play_caller"
        )
        self.assertEqual("Press Taylor", row["coach_canonical_name"])
        self.assertEqual(
            ("1", "18", "verified"),
            (row["start_week"], row["end_week"], row["verification_status"]),
        )
        self.assertIn("jaguars.com", row["primary_source_url"])

    def test_coverage_matrix_remains_exactly_512_cells_per_role(self) -> None:
        coverage, _ = build_evidence_coverage(ROOT)
        self.assertEqual(2_048, coverage.height)
        for role in ("head_coach", "offensive_coordinator", "quarterbacks_coach", "play_caller"):
            self.assertEqual(512, coverage.filter(pl.col("role") == role).height)

    def test_clean_historical_rebuilds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            first = run_checkpoint_eleven_b(ROOT, Path(left))
            second = run_checkpoint_eleven_b(ROOT, Path(right))
            self.assertEqual(first["data_version"], second["data_version"])
            left_files = {
                path.relative_to(left): path.read_bytes()
                for path in Path(left).rglob("*")
                if path.is_file()
            }
            right_files = {
                path.relative_to(right): path.read_bytes()
                for path in Path(right).rglob("*")
                if path.is_file()
            }
            self.assertEqual(left_files, right_files)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from nfl_coaching_impact.coaching import CoachingDataError, validate_coaching_data

ROOT = Path(__file__).resolve().parents[1]


class CheckpointFourCoachingTest(unittest.TestCase):
    def test_committed_dataset_passes_all_contracts(self) -> None:
        result = validate_coaching_data(ROOT)
        self.assertEqual(result.covered_team_seasons, 512)
        self.assertEqual(result.assignments, result.citations)
        self.assertEqual(result.role_counts["play_caller"], 0)
        self.assertGreater(result.role_counts["head_coach"], 512)
        self.assertGreater(result.open_reviews, 512)

    def _copy(self, directory: Path) -> Path:
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

    def test_verified_assignment_without_citation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            path = root / "data" / "manual" / "coach_assignment_sources.csv"
            self._mutate(path, lambda rows: rows.pop(0))
            with self.assertRaisesRegex(CoachingDataError, "lacks citation"):
                validate_coaching_data(root)

    def test_overlapping_nonshared_assignment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            path = root / "data" / "manual" / "coaching_assignments.csv"

            def overlap(rows):
                original = next(row for row in rows if row["role"] == "offensive_coordinator")
                duplicate = dict(original)
                duplicate["assignment_key"] += "-conflict"
                duplicate["coach_id"] = rows[-1]["coach_id"]
                duplicate["coach_canonical_name"] = rows[-1]["coach_canonical_name"]
                duplicate["verification_status"] = "provisional"
                rows.append(duplicate)

            self._mutate(path, overlap)
            with self.assertRaisesRegex(CoachingDataError, "overlapping non-shared"):
                validate_coaching_data(root)

    def test_missing_role_must_be_in_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy(Path(tmp))
            assignments = root / "data" / "manual" / "coaching_assignments.csv"
            queue = root / "data" / "manual" / "coaching_review_queue.csv"
            with assignments.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            target = next(row for row in rows if row["role"] == "quarterbacks_coach")
            self._mutate(
                assignments,
                lambda values: values.__setitem__(
                    slice(None),
                    [
                        row
                        for row in values
                        if row["assignment_key"] != target["assignment_key"]
                    ],
                ),
            )
            self._mutate(
                queue,
                lambda values: values.__setitem__(
                    slice(None),
                    [
                        row
                        for row in values
                        if not (
                            row["season"] == target["season"]
                            and row["team_id"] == target["team_id"]
                            and row["role"] == target["role"]
                        )
                    ],
                ),
            )
            with self.assertRaisesRegex(CoachingDataError, "neither assigned nor queued"):
                validate_coaching_data(root)


if __name__ == "__main__":
    unittest.main()

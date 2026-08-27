from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from nfl_coaching_impact.coaching import (
    CoachingDataError,
    validate_coaching_data,
    validate_source_content,
)
from nfl_coaching_impact.coaching_loader import load_coaching_data

ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, value=None):
        self.value = value

    def fetchone(self):
        return None if self.value is None else (self.value,)


class _RecordingConnection:
    def __init__(self):
        self.next_id = 1
        self.assignment_parameters = []

    def execute(self, statement, parameters=()):
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT coach_id FROM coaches"):
            return _Result()
        if normalized.startswith("INSERT INTO coach_assignments"):
            self.assignment_parameters.append(parameters)
        if "RETURNING" in normalized:
            value = self.next_id
            self.next_id += 1
            return _Result(value)
        return _Result()


class CheckpointFourCoachingTest(unittest.TestCase):
    def test_committed_dataset_passes_all_contracts(self) -> None:
        result = validate_coaching_data(ROOT)
        self.assertEqual(result.covered_team_seasons, 512)
        self.assertEqual(result.assignments, result.citations)
        self.assertGreaterEqual(result.role_counts["play_caller"], 8)
        self.assertGreater(result.role_counts["head_coach"], 512)
        self.assertGreater(result.open_reviews, 512)

    @staticmethod
    def _read(name: str) -> list[dict[str, str]]:
        with (ROOT / "data" / "manual" / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_baltimore_2012_coordinator_change_is_split(self) -> None:
        rows = [
            row
            for row in self._read("coaching_assignments.csv")
            if row["season"] == "2012"
            and row["team_id"] == "BAL"
            and row["role"] == "offensive_coordinator"
        ]
        self.assertEqual(
            [(row["coach_canonical_name"], row["start_week"], row["end_week"]) for row in rows],
            [("Cam Cameron", "1", "14"), ("Jim Caldwell", "15", "17")],
        )
        self.assertTrue(all(row["interval_basis"] == "dated_source_weeks" for row in rows))

    def test_tim_kelly_has_explicit_play_caller_and_compound_roles(self) -> None:
        rows = [
            row
            for row in self._read("coaching_assignments.csv")
            if row["season"] == "2020"
            and row["team_id"] == "HOU"
            and row["coach_canonical_name"] == "Tim Kelly"
        ]
        self.assertEqual(
            {row["role"] for row in rows},
            {"offensive_coordinator", "quarterbacks_coach", "play_caller"},
        )
        self.assertTrue(all(row["verification_status"] == "verified" for row in rows))

    def test_spelling_variants_resolve_to_one_canonical_identity(self) -> None:
        coaches = self._read("coaches.csv")
        aliases = self._read("coach_aliases.csv")
        canonical = {row["canonical_name"]: row["coach_id"] for row in coaches}
        expected = {
            "Matt LaFluer": "Matt LaFleur",
            "Matt LeFleur": "Matt LaFleur",
            "Rod Chudzinski": "Rob Chudzinski",
            "Frank Cignetti": "Frank Cignetti Jr",
        }
        alias_map = {row["alias_name"]: row["canonical_name"] for row in aliases}
        self.assertEqual({name: alias_map[name] for name in expected}, expected)
        for target in expected.values():
            self.assertIn(target, canonical)
        variants = set(expected) | {"Matt LaFluer", "Matt LeFleur", "Rod Chudzinski"}
        self.assertFalse(variants & set(canonical))
        assignments = self._read("coaching_assignments.csv")
        self.assertFalse(variants & {row["coach_canonical_name"] for row in assignments})
        for target in set(expected.values()):
            target_rows = [row for row in assignments if row["coach_canonical_name"] == target]
            self.assertGreater(len(target_rows), 1)
            self.assertEqual({row["coach_id"] for row in target_rows}, {canonical[target]})

    def test_all_compound_oc_qb_titles_are_expanded(self) -> None:
        assignments = self._read("coaching_assignments.csv")
        citations = self._read("coach_assignment_sources.csv")
        by_key = {row["assignment_key"]: row for row in assignments}
        grains = {
            (row["season"], row["team_id"], row["coach_id"], row["role"]) for row in assignments
        }
        compounds = [
            by_key[row["assignment_key"]]
            for row in citations
            if "offensive coordinator/quarterbacks" in row["evidence_note"].casefold()
        ]
        self.assertGreaterEqual(len(compounds), 2)
        for row in compounds:
            for role in ("offensive_coordinator", "quarterbacks_coach"):
                self.assertIn((row["season"], row["team_id"], row["coach_id"], role), grains)

    def test_representative_source_content_requires_assignment_terms(self) -> None:
        validate_source_content(
            "Tim Kelly was the offensive coordinator/quarterbacks coach and play-caller in 2020.",
            "Tim Kelly|offensive coordinator|quarterbacks|play-caller",
            "fixture",
        )
        with self.assertRaisesRegex(CoachingDataError, "missing required terms"):
            validate_source_content(
                "Tim Kelly was offensive coordinator.", "quarterbacks", "fixture"
            )

    def test_loading_path_preserves_each_interval_basis(self) -> None:
        connection = _RecordingConnection()
        self.assertEqual(load_coaching_data(connection, ROOT), 1340)
        loaded = {
            (parameters[1], parameters[2], parameters[3]): parameters[13]
            for parameters in connection.assignment_parameters
        }
        self.assertEqual(loaded[("HOU", 2020, "play_caller")], "season_designation")
        self.assertEqual(loaded[("BAL", 2012, "offensive_coordinator")], "dated_source_weeks")
        self.assertEqual(loaded[("BAL", 2012, "head_coach")], "observed_game_weeks")

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
                    [row for row in values if row["assignment_key"] != target["assignment_key"]],
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

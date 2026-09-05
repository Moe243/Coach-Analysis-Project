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
        self.assertEqual({"verified_person"}, set(recent["coverage_status"]))

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

    def test_2017_play_callers_do_not_infer_future_weeks_from_november_source(self) -> None:
        coverage, _ = build_evidence_coverage(ROOT)
        season = coverage.filter((pl.col("role") == "play_caller") & (pl.col("season") == 2017))
        self.assertEqual(32, season.height)
        self.assertEqual(
            {"verified_person": 3, "provisional": 29},
            {
                row["coverage_status"]: row["len"]
                for row in season.group_by("coverage_status").len().to_dicts()
            },
        )

        assignments = self._read("coaching_assignments.csv")
        expected = {
            "CIN": [(1, 2, "Ken Zampese"), (3, 17, "Bill Lazor")],
            "DEN": [(1, 11, "Mike McCoy"), (12, 17, "Bill Musgrave")],
            "KC": [(1, 12, "Andy Reid"), (13, 17, "Matt Nagy")],
            "NYG": [
                (1, 5, "Ben McAdoo", "verified"),
                (6, 10, "Mike Sullivan", "verified"),
                (11, 17, "Mike Sullivan", "provisional"),
            ],
            "ARI": [
                (1, 10, "Bruce Arians", "verified"),
                (11, 17, "Bruce Arians", "provisional"),
            ],
        }
        for team, intervals in expected.items():
            actual = [
                (
                    int(row["start_week"]),
                    int(row["end_week"]),
                    row["coach_canonical_name"],
                    row["verification_status"],
                )
                for row in assignments
                if row["season"] == "2017"
                and row["team_id"] == team
                and row["role"] == "play_caller"
            ]
            if team in {"CIN", "DEN", "KC"}:
                actual = [item[:3] for item in actual]
            self.assertEqual(intervals, actual)

    def test_2018_play_caller_changes_preserve_observed_intervals(self) -> None:
        assignments = self._read("coaching_assignments.csv")
        expected = {
            "ARI": [(1, 7, "Mike McCoy"), (8, 17, "Byron Leftwich")],
            "CLE": [(1, 8, "Todd Haley"), (9, 17, "Freddie Kitchens")],
            "JAX": [(1, 12, "Nathaniel Hackett"), (13, 17, "Scott Milanovich")],
            "MIN": [(1, 14, "John DeFilippo"), (15, 17, "Kevin Stefanski")],
        }
        for team, intervals in expected.items():
            actual = [
                (int(row["start_week"]), int(row["end_week"]), row["coach_canonical_name"])
                for row in assignments
                if row["season"] == "2018"
                and row["team_id"] == team
                and row["role"] == "play_caller"
            ]
            self.assertEqual(intervals, actual)

        stefanski = next(
            row
            for row in assignments
            if row["assignment_key"] == "2018-MIN-play_caller-15-17-kevin-stefanski"
        )
        self.assertEqual("true", stefanski["is_interim"])

    def test_formal_role_sanity_pass_preserves_compound_titles_and_no_role_states(self) -> None:
        evidence = self._read("coaching_evidence_11b.csv")
        no_role_evidence = self._read("coaching_no_role_evidence_11b.csv")
        godsey = next(
            row
            for row in evidence
            if row["assignment_key"] == "2016-HOU-quarterbacks_coach-01-17-george-godsey"
        )
        self.assertIn("offensive coordinator & quarterbacks", godsey["evidence_note"])
        self.assertFalse(
            any(
                row["season"] == "2016"
                and row["team_id"] == "HOU"
                and row["role"] == "play_caller"
                and row["coach_id"] == "coach-george-godsey"
                for row in evidence
            )
        )

        coverage, _ = build_evidence_coverage(ROOT)
        no_role_cells = {
            (2010, "ARI", "offensive_coordinator"),
            (2011, "CLE", "offensive_coordinator"),
            (2023, "ATL", "quarterbacks_coach"),
        }
        actual = {
            (row["season"], row["team_id"], row["role"])
            for row in coverage.filter(
                pl.col("coverage_status") == "verified_no_designated_role"
            ).to_dicts()
        }
        self.assertTrue(no_role_cells.issubset(actual))
        excluded_assistant_titles = {
            (2010, "DET"),
            (2011, "DET"),
            (2012, "MIA"),
            (2016, "KC"),
            (2017, "KC"),
            (2018, "IND"),
            (2021, "LA"),
        }
        self.assertFalse(
            any(
                (int(row["season"]), row["team_id"]) in excluded_assistant_titles
                and row["role"] == "quarterbacks_coach"
                for row in evidence
            )
        )
        self.assertEqual(
            excluded_assistant_titles,
            {
                (int(row["season"]), row["team_id"])
                for row in no_role_evidence
                if (int(row["season"]), row["team_id"]) in excluded_assistant_titles
                and row["role"] == "quarterbacks_coach"
            },
        )
        for season, team in ((2013, "BUF"), (2021, "JAX")):
            status = coverage.filter(
                (pl.col("season") == season)
                & (pl.col("team_id") == team)
                & (pl.col("role") == "quarterbacks_coach")
            )["coverage_status"].item()
            self.assertEqual("verified_person", status)

    def test_no_role_evidence_is_validated_and_cannot_overlap_a_person(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_manual(Path(directory))
            path = root / "data/manual/coaching_no_role_evidence_11b.csv"

            def overlap_person(rows: list[dict[str, str]]) -> None:
                row = next(
                    row
                    for row in rows
                    if row["evidence_key"] == "2010-ARI-offensive_coordinator-no-role-01-17"
                )
                row["team_id"] = "ATL"

            self._mutate(path, overlap_person)
            with self.assertRaisesRegex(ValueError, "overlaps a person assignment"):
                validate_checkpoint_eleven_b_evidence(root)

    def test_oc_and_qb_coach_cells_use_explicit_resolution_states(self) -> None:
        coverage, _ = build_evidence_coverage(ROOT)
        for role in ("offensive_coordinator", "quarterbacks_coach"):
            role_rows = coverage.filter(pl.col("role") == role)
            self.assertEqual(512, role_rows.height)
            self.assertFalse(
                set(role_rows["coverage_status"])
                & {"unresolved", "conflicting", "partial", "provisional"}
            )
        resolved_absences = coverage.filter(
            pl.col("coverage_status") == "verified_no_designated_role"
        )
        self.assertTrue(resolved_absences["source_urls"].is_not_null().all())
        self.assertTrue((resolved_absences["source_urls"].str.len_chars() > 0).all())

    def test_arizona_2018_role_change_does_not_overstate_full_season_titles(self) -> None:
        evidence = self._read("coaching_evidence_11b.csv")
        rows = [row for row in evidence if row["season"] == "2018" and row["team_id"] == "ARI"]
        offensive_coordinators = [
            (int(row["start_week"]), int(row["end_week"]), row["coach_canonical_name"])
            for row in rows
            if row["role"] == "offensive_coordinator"
        ]
        quarterback_coaches = [
            (int(row["start_week"]), int(row["end_week"]), row["coach_canonical_name"])
            for row in rows
            if row["role"] == "quarterbacks_coach"
        ]
        self.assertEqual(
            [(1, 7, "Mike McCoy"), (8, 17, "Byron Leftwich")],
            offensive_coordinators,
        )
        self.assertEqual([(1, 7, "Byron Leftwich")], quarterback_coaches)

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

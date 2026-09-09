from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import polars as pl

from research.coach_effect.checkpoint_eleven import _sha256
from research.coach_effect.checkpoint_twelve_final_play_caller_evidence import (
    EXPECTED_RESEARCH_COUNTS,
    OUTPUT_NAMES,
    PROMPT9_VERSION,
    REQUIRED_OPENING_QUEUE,
    build_assignments,
    build_coverage,
    load_and_validate_prompt10_evidence,
    run_checkpoint_twelve_final_play_caller_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def _mutated_prompt10(mutator: object) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    research = root / "research/coach_effect"
    research.mkdir(parents=True)
    source = ROOT / "research/coach_effect/play_caller_evidence_prompt10.csv"
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    mutator(rows)
    with (research / source.name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    shutil.copy2(
        ROOT / "research/coach_effect/play_caller_sources_prompt10.csv",
        research / "play_caller_sources_prompt10.csv",
    )
    baseline = research / "outputs/checkpoint_12_play_caller_verification"
    version = baseline / PROMPT9_VERSION
    version.mkdir(parents=True)
    shutil.copy2(
        ROOT
        / "research/coach_effect/outputs/checkpoint_12_play_caller_verification"
        / PROMPT9_VERSION
        / "play_caller_completeness.csv",
        version,
    )
    (baseline / "LATEST").write_text(PROMPT9_VERSION + "\n", encoding="utf-8")
    return temporary


class PromptTenEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cells, cls.intervals, cls.lineage = load_and_validate_prompt10_evidence(ROOT)
        cls.coverage = build_coverage(ROOT, cls.cells)

    def test_fixed_tiers_opening_queue_and_dynamic_order(self) -> None:
        self.assertEqual(
            dict(self.cells.group_by("tier").len().iter_rows()), EXPECTED_RESEARCH_COUNTS
        )
        opening = tuple(self.cells.head(5).select("season", "team_id").rows())
        self.assertEqual(opening, REQUIRED_OPENING_QUEUE)
        self.assertEqual(self.cells.head(28)["tier"].unique().to_list(), ["highly_recoverable"])
        self.assertEqual(
            self.cells.slice(28, 27)["tier"].unique().to_list(),
            ["possibly_recoverable"],
        )
        expected_first_sixteen = (
            "IND",
            "DEN",
            "NO",
            "IND",
            "TEN",
            "LV",
            "NYJ",
            "PHI",
            "NYG",
            "NYJ",
            "LV",
            "PIT",
            "HOU",
            "MIA",
            "NE",
            "NYG",
        )
        self.assertEqual(tuple(self.cells.head(16)["team_id"]), expected_first_sixteen)

    def test_provisional_gaps_and_final_counts_are_explicit(self) -> None:
        self.assertFalse(self.cells.filter(pl.col("provisional_gap") == "").height)
        self.assertFalse(
            self.cells.filter(
                (pl.col("ending_status") == "verified") & (pl.col("provisional_gap") != "none")
            ).height
        )
        self.assertEqual(
            dict(self.coverage.group_by("ending_status").len().iter_rows()),
            {"verified": 205, "partial": 37, "provisional": 11, "unresolved": 259},
        )

    def test_cumulative_and_explicit_full_season_evidence_passes(self) -> None:
        full = self.intervals.filter(
            ((pl.col("season") == 2021) & (pl.col("team_id") == "IND"))
            | ((pl.col("season") == 2021) & (pl.col("team_id") == "TEN"))
            | ((pl.col("season") == 2022) & (pl.col("team_id") == "NO"))
            | ((pl.col("season") == 2013) & (pl.col("team_id") == "BUF"))
        )
        self.assertEqual(full.height, 4)
        self.assertTrue((full["start_week"] == 1).all())
        self.assertTrue(
            full.select(
                pl.when(pl.col("season") >= 2021)
                .then(pl.col("end_week") == 18)
                .otherwise(pl.col("end_week") == 17)
                .all()
            ).item()
        )
        self.assertTrue(full["secondary_source_url"].str.starts_with("https://").all())

    def test_bounded_game_evidence_cannot_be_promoted_to_full_season(self) -> None:
        bounded = self.intervals.filter(pl.col("source_code") == "espn17")
        self.assertEqual(bounded["end_week"].max(), 10)
        self.assertTrue((bounded["end_week"] <= 10).all())
        self.assertTrue(
            self.cells.filter(pl.col("evidence_codes") == "espn17")["ending_status"]
            .eq("partial")
            .all()
        )

        def mutate(rows: list[dict[str, str]]) -> None:
            target = next(
                row for row in rows if row["season"] == "2017" and row["team_id"] == "JAX"
            )
            target["ending_status"] = "verified"

        temporary = _mutated_prompt10(mutate)
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(ValueError, "complete non-shared weekly coverage"):
            load_and_validate_prompt10_evidence(Path(temporary.name))

    def test_shared_and_provisional_intervals_cannot_be_individually_attributed(self) -> None:
        houston = self.intervals.filter(
            (pl.col("season") == 2020) & (pl.col("team_id") == "HOU")
        ).sort("start_week", "coach_id")
        self.assertEqual(houston.filter(pl.col("is_shared")).height, 2)
        self.assertEqual(
            set(
                houston.filter(pl.col("is_shared"))
                .select("coach_canonical_name", "start_week", "end_week")
                .rows()
            ),
            {("Bill O'Brien", 4, 4), ("Tim Kelly", 4, 4)},
        )
        assignments = pl.DataFrame(build_assignments(ROOT, self.cells, self.intervals))
        shared = assignments.filter(
            (pl.col("season") == "2020")
            & (pl.col("team_id") == "HOU")
            & (pl.col("is_shared") == "true")
        )
        self.assertEqual(shared.height, 2)


class PromptTenOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_checkpoint_twelve_final_play_caller_evidence(ROOT)
        cls.output = cls.result.output_path

    def read(self, name: str) -> pl.DataFrame:
        return pl.read_csv(self.output / name)

    def test_pcae_uses_only_verified_non_shared_intervals(self) -> None:
        historical = self.read("historical_pcae.csv")
        self.assertFalse(historical.filter(pl.col("verification_status") != "verified").height)
        self.assertFalse(historical.filter(pl.col("is_shared")).height)
        houston = historical.filter((pl.col("season") == 2020) & (pl.col("team_id") == "HOU"))
        self.assertEqual(set(houston.select("start_week", "end_week").rows()), {(1, 3)})
        self.assertFalse(
            historical.filter((pl.col("season") == 2020) & (pl.col("team_id") == "PHI")).height
        )

    def test_dynamic_snapshots_never_cross_all_gates(self) -> None:
        snapshots = self.read("batch_snapshots.csv")
        self.assertEqual(snapshots["research_cutoff"].to_list(), [5, 15, 28, 40, 55, 65, 75])
        self.assertTrue(snapshots["verified_cells"].is_sorted())
        self.assertGreaterEqual(snapshots.head(1)["common_future_qp_rows"].item(), 150)
        self.assertFalse(snapshots["all_gates_pass"].any())
        self.assertEqual(snapshots.tail(1)["common_future_qp_rows"].item(), 165)

    def test_era_coverage_missingness_and_readiness_gates(self) -> None:
        eras = self.read("coverage_by_era.csv").select("era", "cells", "verified")
        self.assertEqual(
            eras.rows(),
            [
                ("2010-2014", 160, 13),
                ("2015-2019", 160, 12),
                ("2020-2022", 96, 84),
                ("2023-2025", 96, 96),
            ],
        )
        diagnostics = self.read("coverage_missingness_diagnostics.csv")
        self.assertIn("offensive_quality_proxy", diagnostics["dimension"].to_list())
        readiness = dict(self.read("readiness_gate_status.csv").select("gate", "result").rows())
        self.assertEqual(readiness["A_verified_play_caller_coverage"], "FAIL")
        self.assertEqual(readiness["B_chronological_target_folds"], "PASS")
        self.assertEqual(readiness["C_common_future_qp_rows"], "PASS")
        self.assertEqual(readiness["D_resampling_feasibility"], "PASS")
        self.assertEqual(readiness["FINAL_COACH_EFFECT_RERUN_READINESS"], "NOT READY")

    def test_research_counts_conversions_and_evidence_ceiling(self) -> None:
        researched = self.read("researched_cells.csv")
        self.assertEqual(researched.height, 75)
        self.assertEqual(self.read("newly_verified_evidence.csv").height, 21)
        self.assertEqual(self.read("provisional_conversions.csv").height, 19)
        self.assertEqual(
            self.read("newly_verified_evidence.csv")
            .filter(pl.col("starting_status") == "unresolved")
            .height,
            2,
        )
        ceiling = self.read("evidence_ceiling.csv").row(0, named=True)
        self.assertEqual(ceiling["estimated_defensible_ceiling"], 221)
        self.assertFalse(ceiling["gate_attainable_with_reasonable_public_effort"])
        self.assertEqual(
            ceiling["recommendation"],
            "STOP HISTORICAL VERIFICATION — EVIDENCE CEILING REACHED",
        )

    def test_deterministic_manifest_and_two_independent_builds(self) -> None:
        with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
            left = run_checkpoint_twelve_final_play_caller_evidence(ROOT, Path(left_dir) / "output")
            right = run_checkpoint_twelve_final_play_caller_evidence(
                ROOT, Path(right_dir) / "output"
            )
            self.assertEqual(left.data_version, right.data_version)
            left_files = sorted(path.name for path in left.output_path.iterdir())
            right_files = sorted(path.name for path in right.output_path.iterdir())
            self.assertEqual(left_files, right_files)
            self.assertEqual(left_files, sorted(["MANIFEST.json", *OUTPUT_NAMES]))
            for name in left_files:
                self.assertEqual(
                    _sha256(left.output_path / name), _sha256(right.output_path / name)
                )
            left_manifest = json.loads((left.output_path / "MANIFEST.json").read_text())
            right_manifest = json.loads((right.output_path / "MANIFEST.json").read_text())
            self.assertEqual(left_manifest, right_manifest)


if __name__ == "__main__":
    unittest.main()

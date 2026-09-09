from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import polars as pl

from research.coach_effect.checkpoint_eleven import _sha256
from research.coach_effect.checkpoint_twelve_play_caller_verification import (
    EXPECTED_STARTING_COUNTS,
    MANDATORY_TOP_TEN,
    OUTPUT_NAMES,
    PROMPT8_VERSION,
    build_assignments,
    build_coverage,
    build_priority_ranking,
    load_and_validate_prompt9_evidence,
    run_checkpoint_twelve_play_caller_verification,
)

ROOT = Path(__file__).resolve().parents[1]
PROMPT8_ROOT = ROOT / "research/coach_effect/outputs/checkpoint_12_data_expansion" / PROMPT8_VERSION


def _mutated_evidence(mutator: object) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    evidence_target = root / "research/coach_effect/play_caller_evidence_prompt9.csv"
    evidence_target.parent.mkdir(parents=True)
    with (ROOT / "research/coach_effect/play_caller_evidence_prompt9.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    mutator(rows)
    with evidence_target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    baseline = root / "research/coach_effect/outputs/checkpoint_12_data_expansion"
    version = baseline / PROMPT8_VERSION
    version.mkdir(parents=True)
    shutil.copy2(PROMPT8_ROOT / "play_caller_completeness.csv", version)
    (baseline / "LATEST").write_text(PROMPT8_VERSION + "\n", encoding="utf-8")
    return temporary


class PromptNineEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = load_and_validate_prompt9_evidence(ROOT)
        cls.coverage = build_coverage(ROOT, cls.evidence)

    def test_exact_matrix_batches_and_status_counts(self) -> None:
        self.assertEqual(self.coverage.height, 512)
        self.assertEqual(self.coverage.select("season", "team_id").n_unique(), 512)
        self.assertEqual(
            dict(self.coverage.group_by("starting_status").len().iter_rows()),
            EXPECTED_STARTING_COUNTS,
        )
        self.assertEqual(
            dict(self.coverage.group_by("ending_status").len().iter_rows()),
            {"verified": 184, "partial": 4, "provisional": 56, "unresolved": 268},
        )
        cells = self.evidence.select("research_order", "batch", "season", "team_id").unique()
        self.assertEqual(cells.height, 50)
        self.assertEqual(
            dict(cells.group_by("batch").len().iter_rows()),
            {"mandatory_top10": 10, "dynamic_batch_1": 20, "dynamic_batch_2": 20},
        )

    def test_mandatory_top_ten_and_results_are_fixed(self) -> None:
        top = (
            self.evidence.filter(pl.col("research_order") <= 10)
            .select("research_order", "season", "team_id", "candidate_coach_name", "ending_status")
            .unique()
            .sort("research_order")
        )
        self.assertEqual(
            tuple(
                (row["season"], row["team_id"], row["candidate_coach_name"])
                for row in top.to_dicts()
            ),
            MANDATORY_TOP_TEN,
        )
        self.assertEqual(top["ending_status"].to_list().count("verified"), 8)
        self.assertEqual(top["ending_status"].to_list().count("partial"), 1)
        self.assertEqual(top["ending_status"].to_list().count("provisional"), 1)

    def test_title_inference_cannot_verify_head_coach_or_coordinator(self) -> None:
        for title in ("Head coach only", "Offensive coordinator only"):
            with self.subTest(title=title):

                def mutate(rows: list[dict[str, str]], replacement: str = title) -> None:
                    target = next(row for row in rows if row["interval_status"] == "verified")
                    target["source_title"] = replacement
                    target["evidence_locator"] = replacement
                    target["evidence_summary"] = replacement

                temporary = _mutated_evidence(mutate)
                self.addCleanup(temporary.cleanup)
                with self.assertRaisesRegex(ValueError, "explicit caller evidence"):
                    load_and_validate_prompt9_evidence(Path(temporary.name))

    def test_canonical_identity_and_interval_overlap_fail_closed(self) -> None:
        def bad_identity(rows: list[dict[str, str]]) -> None:
            rows[0]["coach_id"] = "coach-wrong-person"

        identity_root = _mutated_evidence(bad_identity)
        self.addCleanup(identity_root.cleanup)
        with self.assertRaisesRegex(ValueError, "canonical coach mismatch"):
            load_and_validate_prompt9_evidence(Path(identity_root.name))

        def overlapping(rows: list[dict[str, str]]) -> None:
            chicago = [row for row in rows if row["research_order"] == "1"]
            chicago[1]["start_week"] = "3"

        overlap_root = _mutated_evidence(overlapping)
        self.addCleanup(overlap_root.cleanup)
        with self.assertRaisesRegex(ValueError, "overlapping non-shared"):
            load_and_validate_prompt9_evidence(Path(overlap_root.name))

    def test_transitions_and_shared_intervals_are_preserved(self) -> None:
        expected = {
            (2021, "CHI"): [(1, 3), (4, 14), (15, 15), (16, 18)],
            (2021, "CLE"): [(1, 14), (15, 15), (16, 18)],
            (2021, "NO"): [(1, 14), (15, 15), (16, 18)],
            (2020, "CHI"): [(1, 9), (10, 17)],
            (2021, "JAX"): [(1, 15), (16, 18)],
            (2020, "DET"): [(1, 15), (16, 16), (17, 17)],
        }
        for (season, team), intervals in expected.items():
            observed = (
                self.evidence.filter(
                    (pl.col("season") == season)
                    & (pl.col("team_id") == team)
                    & (pl.col("interval_status") == "verified")
                )
                .select("start_week", "end_week")
                .sort("start_week")
                .rows()
            )
            self.assertEqual(observed, intervals)
        shared = self.evidence.filter(pl.col("is_shared"))
        self.assertEqual(shared.height, 2)
        self.assertEqual(set(shared.select("season", "team_id").rows()), {(2022, "JAX")})
        self.assertTrue(shared["proves_shared_duties"].all())

    def test_partial_intervals_do_not_promote_whole_cells(self) -> None:
        assignments = pl.DataFrame(build_assignments(ROOT, self.evidence), infer_schema_length=None)
        jets = (
            assignments.filter(
                (pl.col("season") == "2020")
                & (pl.col("team_id") == "NYJ")
                & (pl.col("role") == "play_caller")
            )
            .with_columns(pl.col("start_week").cast(pl.Int64))
            .sort("start_week")
        )
        self.assertEqual(
            jets["verification_status"].to_list(), ["verified", "verified", "provisional"]
        )
        self.assertEqual(
            self.coverage.filter((pl.col("season") == 2020) & (pl.col("team_id") == "NYJ"))[
                "ending_status"
            ].item(),
            "partial",
        )

    def test_priority_rebuild_is_lexicographic_and_deterministic(self) -> None:
        first = build_priority_ranking(ROOT, self.evidence)
        second = build_priority_ranking(ROOT, self.evidence)
        self.assertTrue(first.equals(second))
        selected = first.filter(pl.col("selected_research_order").is_not_null())
        self.assertEqual(selected["prompt9_priority_rank"].sort().to_list(), list(range(1, 41)))
        self.assertEqual(selected["selected_research_order"].n_unique(), 40)
        self.assertTrue((selected["priority_tier"] == 1).all())
        self.assertEqual(
            selected["priority_basis"].unique().to_list(),
            ["lexicographic: common/future history; repeat/transition; PCAE volume; coverage"],
        )


class PromptNineOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_checkpoint_twelve_play_caller_verification(ROOT)
        cls.output = cls.result.output_path

    def read(self, name: str) -> pl.DataFrame:
        return pl.read_csv(self.output / name)

    def test_verified_only_pcae_and_shared_exclusion(self) -> None:
        historical = self.read("historical_pcae.csv")
        prompt9_cells = set(self.read("researched_cells.csv").select("season", "team_id").rows())
        prompt9_pcae = historical.filter(
            pl.struct("season", "team_id").map_elements(
                lambda row: (row["season"], row["team_id"]) in prompt9_cells,
                return_dtype=pl.Boolean,
            )
        )
        self.assertFalse(prompt9_pcae.filter(pl.col("is_shared")).height)
        self.assertFalse(prompt9_pcae.filter(pl.col("verification_status") != "verified").height)
        self.assertFalse(
            prompt9_pcae.filter(
                ((pl.col("season") == 2022) & (pl.col("team_id") == "JAX"))
                | ((pl.col("season") == 2021) & (pl.col("team_id") == "MIA"))
            ).height
        )
        jets = prompt9_pcae.filter((pl.col("season") == 2020) & (pl.col("team_id") == "NYJ"))
        self.assertEqual(set(jets.select("start_week", "end_week").rows()), {(1, 6), (7, 9)})

    def test_common_qp_folds_and_gates(self) -> None:
        common = self.read("common_qp_availability.csv")
        folds = self.read("future_fold_matrix.csv")
        readiness = dict(self.read("readiness_gate_status.csv").select("gate", "observed").rows())
        self.assertEqual(common.height, 242)
        self.assertEqual(int(folds["future_target_rows"].sum()), 144)
        self.assertEqual(folds.filter(pl.col("eligible_as_target")).height, 5)
        self.assertEqual(readiness["A_verified_play_caller_coverage"], "184")
        self.assertEqual(readiness["B_chronological_target_folds"], "5")
        self.assertEqual(readiness["C_common_future_qp_rows"], "144")
        self.assertEqual(readiness["FINAL_COACH_EFFECT_RERUN_READINESS"], "one_or_more_failed")

    def test_season_matrix_and_source_records_are_complete(self) -> None:
        matrix = self.read("season_readiness_matrix.csv")
        lineage = self.read("source_lineage.csv")
        self.assertEqual(matrix["season"].to_list(), list(range(2010, 2026)))
        self.assertEqual(lineage.height, 65)
        for name in (
            "source_url",
            "source_title",
            "source_publisher",
            "source_family",
            "evidence_locator",
            "evidence_summary",
            "research_notes",
        ):
            self.assertFalse(lineage.filter(pl.col(name).is_null() | (pl.col(name) == "")).height)

    def test_batch_snapshots_rebuild_availability(self) -> None:
        snapshots = self.read("batch_snapshots.csv")
        self.assertEqual(snapshots["researched_cells"].to_list(), [10, 30, 50])
        self.assertEqual(snapshots["verified_cells"].to_list(), [152, 169, 184])
        self.assertEqual(snapshots["partial_cells"].to_list(), [3, 3, 4])
        self.assertEqual(snapshots["common_future_qp_rows"].to_list(), [109, 128, 144])
        self.assertTrue((snapshots["eligible_target_folds"] == 5).all())

    def test_output_contract_and_manifest(self) -> None:
        self.assertEqual(
            {path.name for path in self.output.iterdir() if path.is_file()},
            {"MANIFEST.json", *OUTPUT_NAMES},
        )
        manifest = json.loads((self.output / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["research_only"])
        self.assertFalse(manifest["final_equation_fitted"])
        self.assertFalse(manifest["scheme_methodology_changed"])
        for name in OUTPUT_NAMES:
            self.assertEqual(manifest["output_checksums"][name], _sha256(self.output / name))

    def test_two_independent_builds_are_byte_identical(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_temp,
            tempfile.TemporaryDirectory() as right_temp,
        ):
            left = run_checkpoint_twelve_play_caller_verification(ROOT, Path(left_temp))
            right = run_checkpoint_twelve_play_caller_verification(ROOT, Path(right_temp))
            self.assertEqual(left.data_version, right.data_version)
            left_files = sorted(path.name for path in left.output_path.iterdir() if path.is_file())
            right_files = sorted(
                path.name for path in right.output_path.iterdir() if path.is_file()
            )
            self.assertEqual(left_files, right_files)
            for name in left_files:
                self.assertEqual(
                    _sha256(left.output_path / name), _sha256(right.output_path / name)
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTest(unittest.TestCase):
    def test_required_checkpoint_files_exist(self) -> None:
        required = {
            "README.md",
            "AGENTS.md",
            "DATA_SOURCES.md",
            "METHODOLOGY.md",
            "LIMITATIONS.md",
            "MODEL_CARD.md",
            "DATA_DICTIONARY.md",
            ".env.example",
            ".gitignore",
            "docs/FEASIBILITY_AUDIT.md",
            "docs/ARCHITECTURE.md",
            "docs/PROJECT_PLAN.md",
            "docs/CHECKPOINT_1_REPORT.md",
            "docs/CHECKPOINT_2_REPORT.md",
            "docs/CHECKPOINT_4_REPORT.md",
            "db/schema.sql",
            "data/manual/coaching_assignments.csv",
            "data/manual/coach_assignment_sources.csv",
            "data/manual/coaching_review_queue.csv",
            "data/manual/coaching_role_definitions.csv",
            "data/manual/coaching_source_registry.csv",
            "scripts/audit_sources.py",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual(missing, [])

    def test_manual_assignments_are_source_backed(self) -> None:
        path = ROOT / "data" / "manual" / "coaching_assignments.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertGreater(len(rows), 1, "checkpoint four must contain verified assignments")
        self.assertIn("verification_status", rows[0])
        self.assertIn("primary_source_url", rows[0])
        self.assertIn("role", rows[0])
        self.assertIn("confidence_level", rows[0])
        self.assertIn("assignment_key", rows[0])

    def test_feasibility_classifications_are_documented(self) -> None:
        text = (ROOT / "docs" / "FEASIBILITY_AUDIT.md").read_text(encoding="utf-8").lower()
        for classification in (
            "direct observations",
            "derivable",
            "manual",
            "deferred",
            "unavailable",
        ):
            self.assertIn(classification, text)


if __name__ == "__main__":
    unittest.main()

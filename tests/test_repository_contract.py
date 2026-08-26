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
            "db/schema.sql",
            "data/manual/coaching_assignments.csv",
            "scripts/audit_sources.py",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual(missing, [])

    def test_manual_template_is_schema_only(self) -> None:
        path = ROOT / "data" / "manual" / "coaching_assignments.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 1, "template must not contain fabricated assignments")
        self.assertIn("verification_status", rows[0])
        self.assertIn("source_url", rows[0])
        self.assertIn("role", rows[0])

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

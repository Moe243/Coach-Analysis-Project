"""Offline release-configuration checks for checkpoint nine."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from nfl_coaching_impact.api import _cors_origins

ROOT = Path(__file__).resolve().parents[1]


class CheckpointNineReleaseTests(unittest.TestCase):
    def test_cors_requires_explicit_origins(self) -> None:
        with patch.dict(os.environ, {"CORS_ORIGINS": "https://example.onrender.com/"}):
            self.assertEqual(_cors_origins(), ["https://example.onrender.com"])
        with patch.dict(os.environ, {"CORS_ORIGINS": "*"}):
            with self.assertRaisesRegex(RuntimeError, "explicit origins"):
                _cors_origins()

    def test_render_blueprint_keeps_secrets_out_of_source(self) -> None:
        blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("DATABASE_URL\n        sync: false", blueprint)
        self.assertIn("CORS_ORIGINS\n        sync: false", blueprint)
        self.assertIn("VITE_API_BASE_URL\n        sync: false", blueprint)
        self.assertNotIn("postgresql://", blueprint)
        self.assertIn("source: /*", blueprint)
        self.assertIn("destination: /index.html", blueprint)

    def test_license_and_third_party_notice_are_present(self) -> None:
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        notice = (ROOT / "THIRD_PARTY_DATA_NOTICE.md").read_text(encoding="utf-8")
        self.assertIn("original providers", notice)
        self.assertIn("PERMISSION REQUIRED BEFORE INGESTION", notice)


if __name__ == "__main__":
    unittest.main()

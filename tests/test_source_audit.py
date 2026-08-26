from __future__ import annotations

import csv
import importlib.util
import io
import ssl
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_sources.py"
SPEC = importlib.util.spec_from_file_location("audit_sources", SCRIPT)
assert SPEC and SPEC.loader
audit_sources = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_sources
SPEC.loader.exec_module(audit_sources)


class SourceAuditContractTest(unittest.TestCase):
    def test_boundary_manifest(self) -> None:
        assets = {asset.name: asset for asset in audit_sources.ASSETS}
        self.assertEqual(assets["pbp_2010"].expected_status, 200)
        self.assertEqual(assets["pbp_2025"].expected_status, 200)
        self.assertEqual(assets["snap_2010"].expected_status, 404)
        self.assertEqual(assets["snap_2012"].expected_status, 200)
        self.assertTrue(
            all(asset.url.startswith("https://github.com/nflverse/") for asset in assets.values())
        )

    def test_offline_audit_does_not_claim_network_results(self) -> None:
        report = audit_sources.audit(network=False, download_samples=False)
        self.assertFalse(report["network_enabled"])
        self.assertTrue(all("observed_status" not in item for item in report["assets"]))
        self.assertTrue(audit_sources.report_passed(report))

    def test_ssl_context_verifies_certificates(self) -> None:
        context = audit_sources.build_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_csv_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.csv"
            required = frozenset({"player_id", "position"})
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["player_id", "position"])
                writer.writeheader()
                writer.writerow({"player_id": "00-0000001", "position": "QB"})
            result = audit_sources.inspect_csv(path, required)
        self.assertTrue(result["passed"])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["missing_required_columns"], [])

    def test_pbp_sample_validates_dropback_epa_and_quarterback_id(self) -> None:
        columns = sorted(audit_sources.PBP_REQUIRED_COLUMNS)
        rows = [dict.fromkeys(columns, "") for _ in range(2)]
        rows[0].update(
            {
                "game_id": "2025_01_TEST_TEST",
                "play_id": "10",
                "qb_dropback": "1",
                "qb_kneel": "0",
                "qb_spike": "0",
                "qb_scramble": "0",
                "qb_epa": "0.25",
                "passer_player_id": "00-0000001",
            }
        )
        rows[1].update(
            {
                "game_id": "2025_01_TEST_TEST",
                "play_id": "11",
                "qb_dropback": "1",
                "qb_kneel": "0",
                "qb_spike": "0",
                "qb_scramble": "1",
                "qb_epa": "-0.10",
                "rusher_player_id": "00-0000001",
            }
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        buffer.seek(0)

        result = audit_sources.inspect_pbp_rows(
            csv.DictReader(buffer), minimum_dropbacks=2, maximum_rows=10
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["qb_dropbacks"], 2)
        self.assertEqual(result["qb_epa_values"], 2)
        self.assertEqual(result["resolved_quarterback_ids"], 2)


if __name__ == "__main__":
    unittest.main()

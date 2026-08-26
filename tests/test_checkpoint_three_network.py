from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from nfl_coaching_impact.historical import HistoricalPipelineConfig, run_historical_preflight
from nfl_coaching_impact.sources import build_historical_source_plan


@unittest.skipUnless(
    os.environ.get("RUN_NETWORK_TESTS") == "1",
    "set RUN_NETWORK_TESTS=1 to run nflverse network integration tests",
)
class CheckpointThreeNetworkTest(unittest.TestCase):
    def test_official_boundary_assets_pass_size_preflight(self) -> None:
        seasons = (1999, 2001, 2009, 2012, 2025)
        assets, _ = build_historical_source_plan(seasons)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_historical_preflight(
                HistoricalPipelineConfig(
                    project_root=root,
                    cache_dir=root / "cache",
                    output_dir=root / "output",
                    seasons=seasons,
                ),
                assets=assets,
            )
        self.assertEqual(len(report.assets), len(assets))
        self.assertGreater(report.total_source_bytes, 0)
        self.assertGreater(report.download_bytes, 0)
        self.assertTrue(all(asset.byte_size > 0 for asset in report.assets))


if __name__ == "__main__":
    unittest.main()

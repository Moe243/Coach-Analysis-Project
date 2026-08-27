from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "network test is opt-in")
class CheckpointFourNetworkTest(unittest.TestCase):
    def test_source_registry_urls_resolve(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_coaching_sources.py")],
            cwd=ROOT,
            check=True,
            timeout=600,
        )


if __name__ == "__main__":
    unittest.main()

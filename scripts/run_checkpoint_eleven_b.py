#!/usr/bin/env python3
"""Build the ignored, research-only Checkpoint Eleven-B artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from research.coach_effect.checkpoint_eleven_b import run_checkpoint_eleven_b

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    result = run_checkpoint_eleven_b(ROOT)
    print(
        json.dumps(
            {
                "data_version": result["data_version"],
                "output_path": str(result["output_path"]),
                "historical_pcae_rows": result["pcae"].height,
            },
            indent=2,
            sort_keys=True,
        )
    )

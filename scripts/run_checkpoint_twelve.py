"""Run the research-only Checkpoint Twelve Coach Effect analysis."""

from __future__ import annotations

import json
from pathlib import Path

from research.coach_effect.checkpoint_twelve import run_checkpoint_twelve

if __name__ == "__main__":
    result = run_checkpoint_twelve(Path(__file__).resolve().parents[1])
    print(json.dumps(result, indent=2, sort_keys=True, default=str))

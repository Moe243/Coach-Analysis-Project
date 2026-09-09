"""Run the independent, research-only Checkpoint Twelve adversarial review."""

from __future__ import annotations

import json
from pathlib import Path

from research.coach_effect.checkpoint_twelve_review import run_checkpoint_twelve_review

if __name__ == "__main__":
    result = run_checkpoint_twelve_review(Path(__file__).resolve().parents[1])
    print(json.dumps(result, indent=2, sort_keys=True))

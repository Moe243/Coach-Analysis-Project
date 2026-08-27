#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Validate the committed checkpoint-four manual coaching dataset."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nfl_coaching_impact.coaching import validate_coaching_data


if __name__ == "__main__":
    print(json.dumps(asdict(validate_coaching_data(ROOT)), indent=2, sort_keys=True))

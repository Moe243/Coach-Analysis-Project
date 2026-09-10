#!/usr/bin/env python3
"""Publish local research-only, team-independent QB projection artifacts."""

import argparse
import json
from pathlib import Path

from nfl_coaching_impact.qb_projection import run_checkpoint_sixteen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_sixteen(args.project_root, args.output_root)
    print(
        json.dumps({key: result[key] for key in ("data_version", "counts", "decisions")}, indent=2)
    )


if __name__ == "__main__":
    main()

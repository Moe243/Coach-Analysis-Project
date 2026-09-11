"""Deterministic research-only C17 build; no database or network access."""

import argparse
import json
from pathlib import Path

from nfl_coaching_impact.qb_scenario import run_checkpoint_seventeen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    manifest = run_checkpoint_seventeen(args.project_root, args.output_root)
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in ("data_version", "scenario_status", "counts", "checkpoint_18_readiness")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

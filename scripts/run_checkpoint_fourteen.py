#!/usr/bin/env python3
"""Build Checkpoint 14 QB Style Profile and Player State artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from nfl_coaching_impact.qb_player_state import run_checkpoint_fourteen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_fourteen(args.project_root, args.output_root)
    print(
        f"Checkpoint 14 {result.data_version}: universe={result.universe_rows}, "
        f"states={result.state_rows}, features={result.state_feature_rows}, "
        f"reused={result.reused_existing}"
    )


if __name__ == "__main__":
    main()

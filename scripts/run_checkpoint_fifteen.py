#!/usr/bin/env python3
"""Build Checkpoint 15 Player x Scheme fit research artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from nfl_coaching_impact.player_scheme_fit import run_checkpoint_fifteen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_fifteen(args.project_root, args.output_root)
    print(
        f"Checkpoint 15 {result.data_version}: cohort={result.cohort_rows}, "
        f"eligible={result.eligible_rows}, predictions={result.prediction_rows}, "
        f"fit={result.fit_status}, checkpoint_16={result.checkpoint_16_readiness}, "
        f"reused={result.reused_existing}"
    )


if __name__ == "__main__":
    main()

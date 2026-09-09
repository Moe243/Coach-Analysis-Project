#!/usr/bin/env python3
"""Run the deterministic Checkpoint 13 predictive data foundation."""

from __future__ import annotations

import argparse
from pathlib import Path

from nfl_coaching_impact.predictive_foundation import run_checkpoint_thirteen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_thirteen(
        args.project_root.resolve(),
        args.output_root.resolve() if args.output_root else None,
    )
    print(f"Checkpoint 13 version: {result.data_version}")
    print(f"Output: {result.output_path}")
    print(f"Reused existing: {result.reused_existing}")
    print(f"Registered features: {result.registered_features}")
    print(f"Predictive feature records: {result.feature_records}")
    print(f"Scheme rows: {result.scheme_rows}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the research-only Prompt 8 evidence and scheme data expansion."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.coach_effect.checkpoint_twelve_data_expansion import (
    run_checkpoint_twelve_data_expansion,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = run_checkpoint_twelve_data_expansion(
        args.project_root.resolve(),
        args.output_root,
        allow_network=not args.offline,
    )
    print(f"Prompt 8 research version: {result.data_version}")
    print(f"Outputs: {result.output_path}")
    print(result.readiness.select("gate", "observed", "result"))


if __name__ == "__main__":
    main()

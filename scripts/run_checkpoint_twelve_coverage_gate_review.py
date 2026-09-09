from __future__ import annotations

import argparse
from pathlib import Path

from research.coach_effect.checkpoint_twelve_coverage_gate_review import (
    run_checkpoint_twelve_coverage_gate_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the research-only Prompt 11 play-caller gate methodology review"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_checkpoint_twelve_coverage_gate_review(args.project_root.resolve())
    print(f"Prompt 11 research version: {result.data_version}")
    print(f"Output: {result.output_path}")
    print(result.decision)


if __name__ == "__main__":
    main()

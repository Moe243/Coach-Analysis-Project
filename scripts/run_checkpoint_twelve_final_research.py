"""Run the final Checkpoint 12 research-only architecture analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.coach_effect.checkpoint_twelve_final_research import (
    run_checkpoint_twelve_final_research,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_twelve_final_research(args.project_root, args.output_root)
    print(f"research_data_version={result.data_version}")
    print(f"architecture={result.architecture}")
    print(f"output_path={result.output_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from research.coach_effect.checkpoint_twelve_final_play_caller_evidence import (
    run_checkpoint_twelve_final_play_caller_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the research-only Prompt 10 final play-caller evidence sprint"
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run_checkpoint_twelve_final_play_caller_evidence(args.project_root.resolve())
    print(f"Prompt 10 research version: {result.data_version}")
    print(f"Output: {result.output_path}")
    print(result.readiness)


if __name__ == "__main__":
    main()

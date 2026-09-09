from __future__ import annotations

import argparse
from pathlib import Path

from research.coach_effect.checkpoint_twelve_play_caller_verification import (
    run_checkpoint_twelve_play_caller_verification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Prompt 9 play-caller evidence outputs")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_checkpoint_twelve_play_caller_verification(
        args.project_root.resolve(), args.output_root
    )
    print(result.data_version)
    print(result.output_path)


if __name__ == "__main__":
    main()

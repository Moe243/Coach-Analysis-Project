#!/usr/bin/env python3
"""Build the ignored Checkpoint Eleven research artifacts."""

from pathlib import Path

from research.coach_effect.checkpoint_eleven import run_checkpoint_eleven


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = run_checkpoint_eleven(root)
    print(result.data_version)
    print(result.output_path)


if __name__ == "__main__":
    main()

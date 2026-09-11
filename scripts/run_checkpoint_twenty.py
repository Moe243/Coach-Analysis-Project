"""Publish the C20 research source-gate and historical rookie cohort audit."""

import argparse
from pathlib import Path

from nfl_coaching_impact.rookie_projection import build_checkpoint_twenty


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or args.project_root / "data/processed/rookie_projection"
    print(build_checkpoint_twenty(args.project_root, output))


if __name__ == "__main__":
    main()

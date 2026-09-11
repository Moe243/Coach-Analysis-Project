"""Build the C19 read-only analytical snapshot from frozen approved artifacts."""

import argparse
from pathlib import Path

from nfl_coaching_impact.ask_data import build_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or args.project_root / "data/processed/ask_anything"
    print(build_bundle(args.project_root, output))


if __name__ == "__main__":
    main()

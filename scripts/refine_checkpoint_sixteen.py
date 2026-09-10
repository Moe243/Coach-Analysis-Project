"""Run the C16 calibration and forward candidate-state research follow-up."""

import argparse
import json
from pathlib import Path

from nfl_coaching_impact.qb_projection_refinement import run_refinement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = run_refinement(args.project_root, args.output_root)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "data_version",
                    "selected_base_models",
                    "selected_calibrators",
                    "decisions",
                    "candidate_states",
                    "forward_projection_rows",
                    "checkpoint_17_readiness",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

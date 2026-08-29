"""Command-line entry points for reproducible local pipelines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .coach_impact import CoachImpactConfig, run_coach_impact_pipeline
from .constants import VERTICAL_SLICE_SEASONS
from .expected_performance import (
    ExpectedPerformanceConfig,
    run_expected_performance_pipeline,
)
from .historical import (
    HistoricalPipelineConfig,
    run_historical_pipeline,
    run_historical_preflight,
)
from .pipeline import PipelineConfig, run_vertical_slice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nfl-coaching-impact")
    subparsers = parser.add_subparsers(dest="command", required=True)
    vertical_slice = subparsers.add_parser(
        "vertical-slice", description="Build the checkpoint-two NFL data vertical slice"
    )
    vertical_slice.add_argument("--project-root", type=Path, default=Path.cwd())
    vertical_slice.add_argument("--cache-dir", type=Path)
    vertical_slice.add_argument("--output-dir", type=Path)
    vertical_slice.add_argument(
        "--offline",
        action="store_true",
        help="Require every official asset to already exist in the verified cache",
    )
    historical = subparsers.add_parser(
        "historical",
        description="Build the checkpoint-three 1999-2025 historical dataset",
    )
    historical.add_argument("--project-root", type=Path, default=Path.cwd())
    historical.add_argument("--cache-dir", type=Path)
    historical.add_argument("--output-dir", type=Path)
    historical.add_argument(
        "--offline",
        action="store_true",
        help="Require every historically expected source to exist in the verified cache",
    )
    historical.add_argument(
        "--preflight-only",
        action="store_true",
        help="Report storage and download size without downloading or transforming",
    )
    expected = subparsers.add_parser(
        "expected-performance",
        description="Build checkpoint-five preseason expectations and PAE outputs",
    )
    expected.add_argument("--project-root", type=Path, default=Path.cwd())
    expected.add_argument("--historical-dir", type=Path)
    expected.add_argument("--output-dir", type=Path)
    coach_impact = subparsers.add_parser(
        "coach-impact",
        description="Build checkpoint-six coach-associated PAE estimates",
    )
    coach_impact.add_argument("--project-root", type=Path, default=Path.cwd())
    coach_impact.add_argument("--historical-dir", type=Path)
    coach_impact.add_argument("--expected-performance-dir", type=Path)
    coach_impact.add_argument("--output-dir", type=Path)
    coach_impact.add_argument("--bootstrap-replicates", type=int, default=200)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "vertical-slice":
        result = run_vertical_slice(
            PipelineConfig(
                project_root=args.project_root.resolve(),
                seasons=VERTICAL_SLICE_SEASONS,
                cache_dir=args.cache_dir,
                output_dir=args.output_dir,
                offline=args.offline,
            )
        )
        print(
            json.dumps(
                {
                    "data_version": result.data_version,
                    "output_path": str(result.output_path),
                    "reused_existing": result.reused_existing,
                    "table_counts": result.table_counts,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "historical":
        config = HistoricalPipelineConfig(
            project_root=args.project_root.resolve(),
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
            offline=args.offline,
        )
        if args.preflight_only:
            preflight = run_historical_preflight(config)
            print(json.dumps(preflight.as_record(), indent=2, sort_keys=True))
            return 0
        result = run_historical_pipeline(config)
        print(
            json.dumps(
                {
                    "data_version": result.data_version,
                    "output_path": str(result.output_path),
                    "reused_existing": result.reused_existing,
                    "reused_seasons": list(result.reused_seasons),
                    "table_counts": result.table_counts,
                    "preflight": {
                        "asset_count": len(result.preflight.assets),
                        "total_source_bytes": result.preflight.total_source_bytes,
                        "download_bytes": result.preflight.download_bytes,
                        "required_free_bytes": result.preflight.required_free_bytes,
                        "available_free_bytes": result.preflight.available_free_bytes,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "expected-performance":
        result = run_expected_performance_pipeline(
            ExpectedPerformanceConfig(
                project_root=args.project_root.resolve(),
                historical_dir=args.historical_dir,
                output_dir=args.output_dir,
            )
        )
        print(
            json.dumps(
                {
                    "data_version": result.data_version,
                    "model_version": result.model_version,
                    "selected_model": result.selected_model,
                    "output_path": str(result.output_path),
                    "reused_existing": result.reused_existing,
                    "table_counts": result.table_counts,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "coach-impact":
        result = run_coach_impact_pipeline(
            CoachImpactConfig(
                project_root=args.project_root.resolve(),
                historical_dir=args.historical_dir,
                expected_performance_dir=args.expected_performance_dir,
                output_dir=args.output_dir,
                bootstrap_replicates=args.bootstrap_replicates,
            )
        )
        print(
            json.dumps(
                {
                    "data_version": result.data_version,
                    "model_version": result.model_version,
                    "output_path": str(result.output_path),
                    "reused_existing": result.reused_existing,
                    "table_counts": result.table_counts,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

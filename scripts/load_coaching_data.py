#!/usr/bin/env python3
"""Load validated checkpoint-four coaching data into PostgreSQL."""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from nfl_coaching_impact.coaching import validate_coaching_data
from nfl_coaching_impact.coaching_loader import load_coaching_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    validate_coaching_data(args.project_root)
    with psycopg.connect(args.database_url) as connection:
        count = load_coaching_data(connection, args.project_root)
    print(f"loaded {count} coaching assignments")


if __name__ == "__main__":
    main()

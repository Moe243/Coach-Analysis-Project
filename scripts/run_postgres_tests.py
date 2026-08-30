#!/usr/bin/env python3
"""Run PostgreSQL tests against an isolated bundled server when no URL is supplied."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    existing = os.environ.get("TEST_DATABASE_URL")
    if existing:
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_postgres_behavior",
                "tests.test_checkpoint_seven",
                "-v",
            ]
        )

    try:
        import fasteners
        from pgserver import PostgresServer
    except ImportError:
        print("Install the dev dependencies (including pgserver) or set TEST_DATABASE_URL.")
        return 2

    runtime = Path(tempfile.gettempdir()) / "python_PostgresServer"
    PostgresServer._lock = fasteners.InterProcessLock(runtime / ".lockfile")
    with tempfile.TemporaryDirectory(prefix="nfl-c7-pg-", dir=tempfile.gettempdir()) as directory:
        with PostgresServer(Path(directory), cleanup_mode="stop") as server:
            environment = os.environ.copy()
            environment["TEST_DATABASE_URL"] = server.get_uri()
            environment["PYTHONPATH"] = "src"
            return subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "tests.test_postgres_behavior",
                    "tests.test_checkpoint_seven",
                    "-v",
                ],
                env=environment,
            )


if __name__ == "__main__":
    raise SystemExit(main())

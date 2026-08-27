"""PostgreSQL loading path for the compact checkpoint-four coaching facts."""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_coaching_data(connection, project_root: Path) -> int:
    """Load validated assignments and citations into an existing project schema.

    Teams must already exist. The caller owns the transaction so verified rows and
    their citations are committed together under the schema's deferred constraint.
    """

    manual = project_root / "data" / "manual"
    coaches = _rows(manual / "coaches.csv")
    aliases = _rows(manual / "coach_aliases.csv")
    assignments = _rows(manual / "coaching_assignments.csv")
    citations = _rows(manual / "coach_assignment_sources.csv")
    citation_by_key: dict[str, list[dict[str, str]]] = {}
    for row in citations:
        citation_by_key.setdefault(row["assignment_key"], []).append(row)

    coach_ids: dict[str, int] = {}
    for row in coaches:
        existing = connection.execute(
            "SELECT coach_id FROM coaches WHERE normalized_name = %s AND birth_date IS NULL",
            (row["normalized_name"],),
        ).fetchone()
        if existing:
            coach_ids[row["coach_id"]] = existing[0]
        else:
            result = connection.execute(
                """
                INSERT INTO coaches (canonical_name, normalized_name)
                VALUES (%s, %s)
                RETURNING coach_id
                """,
                (row["canonical_name"], row["normalized_name"]),
            )
            coach_ids[row["coach_id"]] = result.fetchone()[0]

    for row in aliases:
        connection.execute(
            """
            INSERT INTO coach_aliases (coach_id, alias, source_system)
            VALUES (%s, %s, 'checkpoint_four_manual')
            ON CONFLICT (coach_id, alias, source_system) DO NOTHING
            """,
            (coach_ids[row["coach_id"]], row["alias_name"]),
        )

    for row in assignments:
        assignment_id = connection.execute(
            """
            INSERT INTO coach_assignments
                (coach_id, team_id, season, role, start_week, end_week,
                 start_date, end_date, is_interim, is_shared, is_retained,
                 verification_status, confidence_level, interval_basis, notes)
            VALUES
                (%s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date,
                 NULLIF(%s, '')::date, %s, %s, %s, %s, %s, %s, %s)
            RETURNING assignment_id
            """,
            (
                coach_ids[row["coach_id"]],
                row["team_id"],
                int(row["season"]),
                row["role"],
                int(row["start_week"]),
                int(row["end_week"]),
                row["start_date"],
                row["end_date"],
                row["is_interim"] == "true",
                row["is_shared"] == "true",
                row["is_retained"] == "true",
                row["verification_status"],
                row["confidence_level"],
                row["interval_basis"],
                row["notes"],
            ),
        ).fetchone()[0]
        for citation in citation_by_key.get(row["assignment_key"], []):
            host = urlparse(citation["source_url"]).netloc
            source_id = connection.execute(
                """
                INSERT INTO data_sources
                    (source_name, base_url, collection_method, last_reviewed_at)
                VALUES (%s, %s, 'manual verification', %s)
                ON CONFLICT (source_name) DO UPDATE
                    SET last_reviewed_at = EXCLUDED.last_reviewed_at
                RETURNING data_source_id
                """,
                (f"coaching:{host}", f"https://{host}", citation["source_accessed_at"]),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO coach_assignment_sources
                    (assignment_id, data_source_id, source_url, source_title,
                     accessed_at, evidence_note)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    assignment_id,
                    source_id,
                    citation["source_url"],
                    citation["source_title"],
                    citation["source_accessed_at"],
                    citation["evidence_note"],
                ),
            )
    return len(assignments)

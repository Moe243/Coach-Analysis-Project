"""Create the checkpoint-seven PostgreSQL schema.

Revision ID: 0001_checkpoint7
Revises: None
"""

from pathlib import Path

from alembic import op

revision = "0001_checkpoint7"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_path = Path(__file__).with_name("0001_checkpoint7_schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    statements = sql.replace("BEGIN;", "").replace("COMMIT;", "").replace("%", "%%")
    op.get_bind().exec_driver_sql(statements)


def downgrade() -> None:
    raise RuntimeError(
        "checkpoint-seven downgrade is intentionally unsupported; use an isolated schema"
    )

"""Add bidirectional serving exposure lineage enforcement.

Revision ID: 0002_checkpoint7_integrity
Revises: 0001_checkpoint7
"""

from pathlib import Path

from alembic import op

revision = "0002_checkpoint7_integrity"
down_revision = "0001_checkpoint7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0002_checkpoint7_integrity.sql")
    op.get_bind().exec_driver_sql(sql_path.read_text(encoding="utf-8").replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError(
        "checkpoint-seven downgrade is intentionally unsupported; use an isolated schema"
    )

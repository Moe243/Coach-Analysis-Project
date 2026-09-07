"""Publish final Eleven-B coaching completeness states.

Revision ID: 0005_coaching_completeness
Revises: 0004_stage1_statistics
"""

from pathlib import Path

from alembic import op

revision = "0005_coaching_completeness"
down_revision = "0004_stage1_statistics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0005_coaching_completeness.sql")
    op.get_bind().exec_driver_sql(sql_path.read_text(encoding="utf-8").replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError("serving coaching completeness downgrade is intentionally unsupported")

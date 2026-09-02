"""Add Stage 1 QB and team-season statistics.

Revision ID: 0004_stage1_statistics
Revises: 0003_post_release_enhancements
"""

from pathlib import Path

from alembic import op

revision = "0004_stage1_statistics"
down_revision = "0003_post_release_enhancements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0004_stage1_statistics.sql")
    op.get_bind().exec_driver_sql(sql_path.read_text(encoding="utf-8").replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError("Stage 1 statistics downgrade is intentionally unsupported")

"""Add supplemental QB statistics and audit/context serving tables.

Revision ID: 0003_post_release_enhancements
Revises: 0002_checkpoint7_integrity
"""

from pathlib import Path

from alembic import op

revision = "0003_post_release_enhancements"
down_revision = "0002_checkpoint7_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0003_post_release_enhancements.sql")
    op.get_bind().exec_driver_sql(sql_path.read_text(encoding="utf-8").replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError("post-release enhancement downgrade is intentionally unsupported")

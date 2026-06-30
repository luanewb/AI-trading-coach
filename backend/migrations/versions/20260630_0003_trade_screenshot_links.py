"""add trade screenshot links

Revision ID: 20260630_0003
Revises: 20260630_0002
Create Date: 2026-06-30
"""

from alembic import op


revision = "20260630_0003"
down_revision = "20260630_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS before_entry_image_url TEXT")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS after_exit_image_url TEXT")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS analysis_image_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS analysis_image_url")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS after_exit_image_url")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS before_entry_image_url")

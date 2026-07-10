"""add Notion journal links while preserving legacy screenshot entries

Revision ID: 20260710_0006
Revises: 20260702_0005
Create Date: 2026-07-10
"""

from alembic import op


revision = "20260710_0006"
down_revision = "20260702_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS journal_link TEXT")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS journal_entry_mode VARCHAR(16)")
    op.execute("UPDATE trades SET journal_entry_mode = 'screenshots' WHERE journal_entry_mode IS NULL")
    op.execute("ALTER TABLE trades ALTER COLUMN journal_entry_mode SET DEFAULT 'notion'")
    op.execute("ALTER TABLE trades ALTER COLUMN journal_entry_mode SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS journal_entry_mode")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS journal_link")

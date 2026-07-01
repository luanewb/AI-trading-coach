"""add deterministic daily review coach fields

Revision ID: 20260701_0004
Revises: 20260630_0003
Create Date: 2026-07-01
"""

from alembic import op


revision = "20260701_0004"
down_revision = "20260630_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS discipline_score INTEGER NOT NULL DEFAULT 100")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS discipline_breakdown JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS deterministic_findings JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS ai_narrative TEXT")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS model_metadata JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute(
        """
        DELETE FROM daily_reviews older
        USING daily_reviews newer
        WHERE older.account_id = newer.account_id
          AND older.review_date = newer.review_date
          AND older.id < newer.id
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_reviews_account_date ON daily_reviews(account_id, review_date)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_daily_reviews_account_date'
            ) THEN
                ALTER TABLE daily_reviews
                ADD CONSTRAINT uq_daily_reviews_account_date UNIQUE (account_id, review_date);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE daily_reviews DROP CONSTRAINT IF EXISTS uq_daily_reviews_account_date")
    op.execute("DROP INDEX IF EXISTS idx_daily_reviews_account_date")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS generated_at")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS model_metadata")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS ai_narrative")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS deterministic_findings")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS discipline_breakdown")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS discipline_score")
    op.execute("ALTER TABLE daily_reviews DROP COLUMN IF EXISTS metrics_snapshot")

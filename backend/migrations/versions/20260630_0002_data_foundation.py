"""add data foundation tables and indexes

Revision ID: 20260630_0002
Revises: 20260630_0001
Create Date: 2026-06-30
"""

from alembic import op


revision = "20260630_0002"
down_revision = "20260630_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS deal_id VARCHAR(64)")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS position_id VARCHAR(64)")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'mt5'")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy VARCHAR(128)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            balance NUMERIC(18,2) NOT NULL DEFAULT 0,
            equity NUMERIC(18,2) NOT NULL DEFAULT 0,
            margin NUMERIC(18,2) NOT NULL DEFAULT 0,
            free_margin NUMERIC(18,2) NOT NULL DEFAULT 0,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            source VARCHAR(32) NOT NULL DEFAULT 'mt5',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_events (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            trade_id INTEGER REFERENCES trades(id) ON DELETE SET NULL,
            event_key VARCHAR(255) UNIQUE NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            ticket VARCHAR(64) NOT NULL,
            deal_id VARCHAR(64),
            position_id VARCHAR(64),
            symbol VARCHAR(32) NOT NULL,
            order_type VARCHAR(32) NOT NULL,
            lot NUMERIC(12,2) NOT NULL,
            entry_price NUMERIC(18,5),
            sl NUMERIC(18,5),
            tp NUMERIC(18,5),
            close_price NUMERIC(18,5),
            profit NUMERIC(18,2) NOT NULL DEFAULT 0,
            commission NUMERIC(18,2) NOT NULL DEFAULT 0,
            swap NUMERIC(18,2) NOT NULL DEFAULT 0,
            open_time TIMESTAMPTZ,
            close_time TIMESTAMPTZ,
            event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            summary_date DATE NOT NULL,
            start_of_day_balance NUMERIC(18,2),
            start_of_day_equity NUMERIC(18,2),
            end_balance NUMERIC(18,2),
            end_equity NUMERIC(18,2),
            realized_pnl NUMERIC(18,2) NOT NULL DEFAULT 0,
            trade_count INTEGER NOT NULL DEFAULT 0,
            violation_count INTEGER NOT NULL DEFAULT 0,
            max_daily_loss_amount NUMERIC(18,2),
            max_daily_loss_percent NUMERIC(8,2),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_daily_summaries_account_date UNIQUE (account_id, summary_date)
        )
        """
    )

    op.execute("ALTER TABLE rule_violations ADD COLUMN IF NOT EXISTS is_resolved BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE rule_violations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
    op.execute("ALTER TABLE rule_violations ADD COLUMN IF NOT EXISTS resolution_note TEXT")

    op.execute("CREATE INDEX IF NOT EXISTS idx_accounts_account_number ON accounts(account_number)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_account_open_time ON trades(account_id, open_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_account_close_time ON trades(account_id, close_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(ticket)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_deal_id ON trades(deal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trades_position_id ON trades(position_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_account_snapshots_account_timestamp ON account_snapshots(account_id, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_events_account_event_time ON trade_events(account_id, event_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_events_ticket ON trade_events(ticket)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_events_deal_id ON trade_events(deal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_events_position_id ON trade_events(position_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rule_evaluations_checked_at ON rule_evaluations(checked_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pre_trade_checks_account_created_at ON pre_trade_checks(account_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_summaries_account_date ON daily_summaries(account_id, summary_date)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rule_violations_unresolved "
        "ON rule_violations(account_id, created_at) WHERE is_resolved = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rule_violations_unresolved")
    op.execute("DROP TABLE IF EXISTS daily_summaries")
    op.execute("DROP TABLE IF EXISTS trade_events")
    op.execute("DROP TABLE IF EXISTS account_snapshots")
    op.execute("ALTER TABLE rule_violations DROP COLUMN IF EXISTS resolution_note")
    op.execute("ALTER TABLE rule_violations DROP COLUMN IF EXISTS resolved_at")
    op.execute("ALTER TABLE rule_violations DROP COLUMN IF EXISTS is_resolved")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS strategy")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS position_id")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS deal_id")

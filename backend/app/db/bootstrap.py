import logging

from sqlalchemy import Engine, text

from app.services.rule_engine import DEFAULT_RULES

logger = logging.getLogger(__name__)


SCHEMA_STATEMENTS = [
    "ALTER TABLE risk_rules ADD COLUMN IF NOT EXISTS max_risk_per_trade_percent NUMERIC(8,2) NOT NULL DEFAULT 1",
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS before_entry_image_url TEXT",
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS after_exit_image_url TEXT",
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS analysis_image_url TEXT",
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS rule_codes JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS discipline_score INTEGER NOT NULL DEFAULT 100",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS discipline_breakdown JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS deterministic_findings JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS ai_narrative TEXT",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS model_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE daily_reviews ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    """
    DELETE FROM daily_reviews older
    USING daily_reviews newer
    WHERE older.account_id = newer.account_id
      AND older.review_date = newer.review_date
      AND older.id < newer.id
    """,
    """
    CREATE TABLE IF NOT EXISTS rules (
        id SERIAL PRIMARY KEY,
        name VARCHAR(128) NOT NULL,
        code VARCHAR(64) UNIQUE NOT NULL,
        description TEXT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT true,
        severity VARCHAR(16) NOT NULL DEFAULT 'warning',
        action VARCHAR(16) NOT NULL DEFAULT 'block',
        category VARCHAR(32) NOT NULL DEFAULT 'risk',
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        message TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rule_evaluations (
        id SERIAL PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        context VARCHAR(32) NOT NULL,
        allowed BOOLEAN NOT NULL,
        blocked BOOLEAN NOT NULL,
        status VARCHAR(32) NOT NULL,
        decision VARCHAR(16) NOT NULL,
        reason TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rule_violations (
        id SERIAL PRIMARY KEY,
        evaluation_id INTEGER NOT NULL REFERENCES rule_evaluations(id) ON DELETE CASCADE,
        rule_id INTEGER REFERENCES rules(id) ON DELETE SET NULL,
        account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        rule_code VARCHAR(64) NOT NULL,
        severity VARCHAR(16) NOT NULL,
        action VARCHAR(16) NOT NULL,
        message TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_restriction_settings (
        id SERIAL PRIMARY KEY,
        account_type VARCHAR(32) NOT NULL DEFAULT 'standard_funded',
        enforcement_mode VARCHAR(32) NOT NULL DEFAULT 'block_actions',
        minutes_before INTEGER NOT NULL DEFAULT 2,
        minutes_after INTEGER NOT NULL DEFAULT 2,
        apply_usd_only BOOLEAN NOT NULL DEFAULT true,
        blocked_actions JSONB NOT NULL DEFAULT '["new_order","manual_close","modify_sl_tp","pending_order"]'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_restricted_events (
        id SERIAL PRIMARY KEY,
        source VARCHAR(64) NOT NULL,
        source_event_id VARCHAR(128) NOT NULL,
        title VARCHAR(255) NOT NULL,
        normalized_title VARCHAR(128) NOT NULL,
        currency VARCHAR(8) NOT NULL,
        country VARCHAR(64),
        scheduled_at TIMESTAMPTZ NOT NULL,
        impact VARCHAR(16),
        actual VARCHAR(128),
        forecast VARCHAR(128),
        previous VARCHAR(128),
        is_restricted BOOLEAN NOT NULL DEFAULT false,
        restriction_reason TEXT,
        raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_news_restricted_events_source_event UNIQUE (source, source_event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_restriction_events (
        id SERIAL PRIMARY KEY,
        account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
        account_number VARCHAR(64),
        symbol VARCHAR(32) NOT NULL,
        action VARCHAR(32) NOT NULL,
        mode VARCHAR(32) NOT NULL,
        blocked BOOLEAN NOT NULL DEFAULT false,
        news_event_id INTEGER REFERENCES news_restricted_events(id) ON DELETE SET NULL,
        event_title VARCHAR(255),
        restricted_until TIMESTAMPTZ,
        context JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_news_restricted_events_currency_scheduled_at ON news_restricted_events(currency, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS idx_news_restricted_events_restricted_scheduled_at ON news_restricted_events(is_restricted, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS idx_trade_restriction_events_account_created_at ON trade_restriction_events(account_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_trade_restriction_events_symbol_created_at ON trade_restriction_events(symbol, created_at)",
    """
    INSERT INTO news_restriction_settings (id, account_type, enforcement_mode, minutes_before, minutes_after, apply_usd_only, blocked_actions)
    VALUES (1, 'standard_funded', 'block_actions', 2, 2, true, '["new_order","manual_close","modify_sl_tp","pending_order"]'::jsonb)
    ON CONFLICT (id) DO NOTHING
    """,
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS rule_evaluation_id INTEGER REFERENCES rule_evaluations(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_rules_code ON rules(code)",
    "CREATE INDEX IF NOT EXISTS idx_rule_evaluations_account_checked_at ON rule_evaluations(account_id, checked_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rule_violations_rule_code ON rule_violations(rule_code)",
    "CREATE INDEX IF NOT EXISTS idx_daily_reviews_account_date ON daily_reviews(account_id, review_date)",
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
    """,
]


def bootstrap_database(engine: Engine) -> None:
    logger.info("Bootstrapping Rule Engine database schema")
    with engine.begin() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(text(statement))

        for rule in DEFAULT_RULES:
            connection.execute(
                text(
                    """
                    INSERT INTO rules (name, code, description, enabled, severity, action, category, config, message)
                    VALUES (:name, :code, :description, true, :severity, :action, :category, CAST(:config AS jsonb), :message)
                    ON CONFLICT (code) DO NOTHING
                    """
                ),
                {
                    "name": rule.name,
                    "code": rule.code,
                    "description": rule.description,
                    "severity": rule.severity,
                    "action": rule.action,
                    "category": rule.category,
                    "config": "{}",
                    "message": rule.message,
                },
            )
    logger.info("Rule Engine database schema is ready")

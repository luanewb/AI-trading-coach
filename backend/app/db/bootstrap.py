import logging

from sqlalchemy import Engine, text

from app.services.rule_engine import DEFAULT_RULES

logger = logging.getLogger(__name__)


SCHEMA_STATEMENTS = [
    "ALTER TABLE risk_rules ADD COLUMN IF NOT EXISTS max_risk_per_trade_percent NUMERIC(8,2) NOT NULL DEFAULT 1",
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS rule_codes JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb",
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
    "ALTER TABLE pre_trade_checks ADD COLUMN IF NOT EXISTS rule_evaluation_id INTEGER REFERENCES rule_evaluations(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_rules_code ON rules(code)",
    "CREATE INDEX IF NOT EXISTS idx_rule_evaluations_account_checked_at ON rule_evaluations(account_id, checked_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_rule_violations_rule_code ON rule_violations(rule_code)",
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

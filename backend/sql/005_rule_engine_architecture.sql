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
);

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
);

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
);

ALTER TABLE pre_trade_checks
ADD COLUMN IF NOT EXISTS rule_evaluation_id INTEGER REFERENCES rule_evaluations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_rules_code ON rules(code);
CREATE INDEX IF NOT EXISTS idx_rule_evaluations_account_checked_at ON rule_evaluations(account_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_rule_violations_rule_code ON rule_violations(rule_code);

INSERT INTO rules (name, code, description, enabled, severity, action, category, config, message)
VALUES
('Platform trading allowed', 'PLATFORM_TRADING_ALLOWED', 'Blocks all new trades when platform-level trading is disabled.', true, 'critical', 'block', 'execution', '{}'::jsonb, 'Trading is disabled by risk rule configuration.'),
('No stop loss', 'NO_STOP_LOSS', 'Blocks planned or open trades that do not have a stop loss.', true, 'critical', 'block', 'risk', '{}'::jsonb, 'Trade blocked because stop loss is missing.'),
('Max trades per day', 'MAX_TRADES_PER_DAY', 'Warns or blocks when trades opened today reach the configured limit.', true, 'warning', 'block', 'behavior', '{}'::jsonb, 'Trade blocked because the max trades per day limit was reached.'),
('Max daily loss', 'MAX_DAILY_LOSS', 'Blocks or locks trading when daily closed loss reaches the configured percentage.', true, 'critical', 'lock', 'ftmo', '{}'::jsonb, 'Trading locked because the daily loss limit was reached.'),
('Max total loss', 'MAX_TOTAL_LOSS', 'Blocks or locks trading when account loss versus balance reaches the configured percentage.', true, 'critical', 'lock', 'ftmo', '{}'::jsonb, 'Trading locked because the total account loss limit was reached.'),
('Max drawdown', 'MAX_DRAWDOWN_LIMIT', 'Blocks or locks trading when realized drawdown reaches the configured maximum loss percentage.', true, 'critical', 'lock', 'risk', '{}'::jsonb, 'Trading locked because realized drawdown reached the maximum loss limit.'),
('Max consecutive losses', 'MAX_CONSECUTIVE_LOSSES', 'Warns or blocks after the configured number of consecutive losing trades.', true, 'warning', 'block', 'psychology', '{}'::jsonb, 'Trade blocked because the consecutive loss limit was reached.'),
('Cooldown after loss', 'COOLDOWN_AFTER_LOSS', 'Blocks new trades for the configured minutes after a losing trade.', true, 'warning', 'block', 'psychology', '{}'::jsonb, 'Trade blocked because post-loss cooldown is active.'),
('Max lot size', 'MAX_LOT_SIZE', 'Blocks planned trades with lot size above the configured limit.', true, 'warning', 'block', 'execution', '{}'::jsonb, 'Trade blocked because lot size exceeds the configured maximum.'),
('Risk per trade', 'RISK_PER_TRADE', 'Warns or blocks when planned risk exceeds the configured percentage of equity.', true, 'critical', 'block', 'risk', '{}'::jsonb, 'Trade blocked because planned risk per trade is too high.'),
('Revenge trading', 'REVENGE_TRADING', 'Detects same-symbol or larger-lot trades shortly after a loss.', true, 'critical', 'block', 'psychology', '{}'::jsonb, 'Trade blocked because it looks like revenge trading after a recent loss.')
ON CONFLICT (code) DO NOTHING;

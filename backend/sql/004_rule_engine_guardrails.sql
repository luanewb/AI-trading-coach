ALTER TABLE risk_rules
ADD COLUMN IF NOT EXISTS max_risk_per_trade_percent NUMERIC(8,2) NOT NULL DEFAULT 1;

ALTER TABLE pre_trade_checks
ADD COLUMN IF NOT EXISTS rule_codes JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE pre_trade_checks
ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb;

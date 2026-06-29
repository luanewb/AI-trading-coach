CREATE TABLE IF NOT EXISTS pre_trade_checks (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol VARCHAR(32) NOT NULL,
    order_type VARCHAR(8) NOT NULL,
    lot NUMERIC(12,2) NOT NULL,
    entry_price NUMERIC(18,5),
    sl NUMERIC(18,5),
    tp NUMERIC(18,5),
    allowed BOOLEAN NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pre_trade_checks_created_at ON pre_trade_checks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pre_trade_checks_allowed ON pre_trade_checks(allowed);

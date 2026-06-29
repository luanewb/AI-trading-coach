CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    account_number VARCHAR(64) UNIQUE NOT NULL,
    broker VARCHAR(128) NOT NULL,
    server VARCHAR(128) NOT NULL,
    balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    equity NUMERIC(18,2) NOT NULL DEFAULT 0,
    margin NUMERIC(18,2) NOT NULL DEFAULT 0,
    free_margin NUMERIC(18,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    ticket VARCHAR(64) NOT NULL,
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
    r_multiple NUMERIC(10,2),
    status VARCHAR(24) NOT NULL DEFAULT 'open',
    open_time TIMESTAMPTZ,
    close_time TIMESTAMPTZ,
    setup_name VARCHAR(128),
    emotion VARCHAR(64),
    mistake_tags VARCHAR[] DEFAULT '{}',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(account_id, ticket)
);

CREATE TABLE IF NOT EXISTS risk_rules (
    id SERIAL PRIMARY KEY,
    account_id INTEGER UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    max_trades_per_day INTEGER NOT NULL DEFAULT 5,
    max_daily_loss_percent NUMERIC(8,2) NOT NULL DEFAULT 5,
    max_total_loss_percent NUMERIC(8,2) NOT NULL DEFAULT 10,
    max_consecutive_losses INTEGER NOT NULL DEFAULT 3,
    cooldown_minutes_after_loss INTEGER NOT NULL DEFAULT 30,
    max_lot NUMERIC(12,2) NOT NULL DEFAULT 1,
    allow_trading BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    severity VARCHAR(16) NOT NULL,
    type VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    is_resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_reviews (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    review_date DATE NOT NULL,
    pnl NUMERIC(18,2) NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    win_rate NUMERIC(8,2) NOT NULL DEFAULT 0,
    ai_summary TEXT,
    mistakes TEXT,
    best_trade TEXT,
    worst_trade TEXT,
    action_plan TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

CREATE INDEX IF NOT EXISTS idx_trades_account_status ON trades(account_id, status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_close_time ON trades(close_time);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pre_trade_checks_created_at ON pre_trade_checks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pre_trade_checks_allowed ON pre_trade_checks(allowed);

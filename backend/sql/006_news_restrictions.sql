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
);

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
);

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
);

CREATE INDEX IF NOT EXISTS idx_news_restricted_events_currency_scheduled_at ON news_restricted_events(currency, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_news_restricted_events_restricted_scheduled_at ON news_restricted_events(is_restricted, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_trade_restriction_events_account_created_at ON trade_restriction_events(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_restriction_events_symbol_created_at ON trade_restriction_events(symbol, created_at);

INSERT INTO news_restriction_settings (id, account_type, enforcement_mode, minutes_before, minutes_after, apply_usd_only, blocked_actions)
VALUES (1, 'standard_funded', 'block_actions', 2, 2, true, '["new_order","manual_close","modify_sl_tp","pending_order"]'::jsonb)
ON CONFLICT (id) DO NOTHING;

INSERT INTO accounts (account_number, broker, server, balance, equity, margin, free_margin)
VALUES ('100001', 'Demo Broker', 'Demo-FTMO', 100000.00, 99850.00, 1200.00, 98650.00)
ON CONFLICT (account_number) DO NOTHING;

INSERT INTO risk_rules (
    account_id,
    max_trades_per_day,
    max_daily_loss_percent,
    max_total_loss_percent,
    max_consecutive_losses,
    cooldown_minutes_after_loss,
    max_lot,
    allow_trading
)
SELECT id, 5, 5.00, 10.00, 3, 30, 2.00, true
FROM accounts
WHERE account_number = '100001'
ON CONFLICT (account_id) DO NOTHING;

INSERT INTO trades (
    account_id, ticket, symbol, order_type, lot, entry_price, sl, tp, close_price, profit,
    commission, swap, r_multiple, status, open_time, close_time, setup_name, emotion, mistake_tags, notes
)
SELECT id, '900001', 'XAUUSD', 'buy', 0.50, 2320.50000, 2312.50000, 2338.50000, 2332.50000, 450.00,
       -3.50, 0.00, 1.50, 'closed', now() - interval '6 hours', now() - interval '5 hours',
       'London breakout', 'calm', ARRAY['none'], 'Followed plan.'
FROM accounts
WHERE account_number = '100001'
ON CONFLICT (account_id, ticket) DO NOTHING;

INSERT INTO trades (
    account_id, ticket, symbol, order_type, lot, entry_price, sl, tp, close_price, profit,
    commission, swap, r_multiple, status, open_time, close_time, setup_name, emotion, mistake_tags, notes
)
SELECT id, '900002', 'EURUSD', 'sell', 1.00, 1.08450, 1.08750, 1.07850, 1.08750, -300.00,
       -5.00, 0.00, -1.00, 'closed', now() - interval '3 hours', now() - interval '2 hours',
       'NY reversal', 'frustrated', ARRAY['early-entry'], 'Entered before confirmation.'
FROM accounts
WHERE account_number = '100001'
ON CONFLICT (account_id, ticket) DO NOTHING;

INSERT INTO alerts (account_id, severity, type, message)
SELECT id, 'warning', 'SAMPLE_ALERT', 'Seed alert: review risk rules before trading live.'
FROM accounts
WHERE account_number = '100001';

INSERT INTO pre_trade_checks (account_id, symbol, order_type, lot, entry_price, sl, tp, allowed, reason)
SELECT id, 'XAUUSD', 'BUY', 3.00, 2335.50000, NULL, 2350.00000, false, 'Stop loss is required before sending an order. Lot 3.00 exceeds max lot 2.00.'
FROM accounts
WHERE account_number = '100001';

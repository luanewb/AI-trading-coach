# AI Trading Coach MVP

AI Trading Coach is a local-first MVP for MT5 trade journaling, FTMO-style risk monitoring, alerts, daily trading reviews, and a guarded MT5 trade panel.

Version 2 adds a chart trade panel. The EA starts with `SafeMode=true`, so panel orders are simulated by default. Only set `SafeMode=false` on a demo account after you confirm backend rules are working.

## Stack

- Backend: FastAPI, PostgreSQL, Redis
- Frontend: Next.js, TailwindCSS
- MT5 connector: MQL5 Expert Advisor
- Alerts: Telegram Bot, optional
- AI review: OpenAI API, optional via `ENABLE_AI`

## Run With Docker

1. Copy `.env.example` to `.env`.
2. Change `API_KEY` to a private value.
3. Optionally set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENAI_API_KEY`, and `ENABLE_AI=true`.
4. Start the stack:

```bash
docker compose up --build
```

5. Open the dashboard at `http://localhost:3000`.
6. Backend health check is `http://localhost:8000/health`.

PostgreSQL is initialized with schema and sample seed data from `backend/sql`.

## Configure MT5

1. Open MetaTrader 5.
2. Open MetaEditor.
3. Copy or open `mt5-ea/AITradingCoachConnector.mq5`.
4. Compile the EA.
5. In MT5, go to `Tools -> Options -> Expert Advisors`.
6. Enable WebRequest and add your backend base URL, for example `http://127.0.0.1:8000`.
7. Attach the EA to a demo chart.
8. Set:
   - `BackendURL`: `http://127.0.0.1:8000`
   - `ApiKey`: the same value as `.env API_KEY`
   - `SendIntervalSeconds`: for example `10`
   - `SafeMode`: `true` for simulation, `false` for real demo orders after backend approval
   - `AllowCloseAll`: `false` by default
   - `UseRiskPositionSizing`: `true` to auto-calculate lot from Risk % and SL distance
   - `AutoTPByRR`: `true` to auto-place TP from Entry, SL, and RR
   - `DefaultRiskPercent`: default risk per trade shown in the panel
   - `DefaultRR`: default reward-to-risk used for the TP line
   - `OrderHotkey`: default `t`, sends the current panel plan through the same pre-trade check

## Test Heartbeat

After the EA is attached, check the MT5 Experts tab for successful heartbeat logs. You can also test by HTTP:

```bash
curl -X POST http://localhost:8000/api/mt5/heartbeat \
  -H "Content-Type: application/json" \
  -H "x-api-key: change-me" \
  -d '{"account_number":"100002","broker":"Demo","server":"Demo-Server","balance":100000,"equity":100000,"margin":0,"free_margin":100000,"timestamp":"2026-06-29T00:00:00Z"}'
```

## Test Trade Event On Demo

Use a demo account only. Open and close a small test trade, then verify:

- Journal page shows the trade.
- Stats update.
- Alerts page shows any rule violations.
- Rules page can re-evaluate current risk.
- Daily Review page can generate a deterministic review when AI is disabled.

## Test Version 2 MT5 Trade Panel On Demo

Use a demo account first.

1. Start Docker and open `http://localhost:3000`.
2. Attach `AITradingCoachConnector.mq5` to a demo chart.
3. Keep `SafeMode=true`.
4. Drag the `ATC Entry`, `ATC Stop Loss`, and `ATC Take Profit` horizontal lines on the chart.
5. Keep `AUTO TP ON` if you want TP to move automatically from Entry, SL, and RR. With Auto TP on, SL below Entry is treated as BUY, and SL above Entry is treated as SELL. Turn it off when you want to place TP manually.
6. Adjust `Risk %` or `RR` in the panel if needed. For example, with RR `3`, moving Entry or SL recalculates TP at 3R when Auto TP is on.
7. The panel auto-calculates `Lot` from account equity, Risk %, and the Entry-to-SL distance when `UseRiskPositionSizing=true`.
8. Click `BUY` or `SELL`, or press the configured `OrderHotkey` (`t` by default) to send the current plan direction.
9. The EA sends `POST /api/rules/pre-trade-check` with the planned Entry, SL, TP, and calculated Lot.
10. If allowed, the chart shows a SafeMode simulation message and no real order is sent.
11. If blocked, the chart shows the backend reason.
12. Open `Pre-trade Rules` in the dashboard to see allowed and blocked pre-trade checks.

To test real demo orders, set `SafeMode=false` in the EA inputs. With SafeMode off, the EA can send a market order when Entry is near current price, or a pending `BUY LIMIT`, `BUY STOP`, `SELL LIMIT`, or `SELL STOP` when Entry is away from current price. Every request still goes through backend approval first. Test on demo before any live account.

`Close All` is disabled unless `AllowCloseAll=true`. When `SafeMode=true`, Close All is simulated.

## Rule Engine Architecture

The backend Rule Engine is the MVP guardrail system. It runs on MT5 heartbeats, MT5 trade events, manual `POST /api/rules/evaluate`, and every `POST /api/rules/pre-trade-check`.

The existing `risk_rules` table remains the dashboard-compatible account settings layer. `GET /api/rules` and `PUT /api/rules` still load and save:

- `allow_trading`
- `max_trades_per_day`
- `max_daily_loss_percent`
- `max_total_loss_percent`
- `max_consecutive_losses`
- `cooldown_minutes_after_loss`
- `max_lot`
- `max_risk_per_trade_percent`

The extensible rule catalog lives in the new `rules` table. Each rule has:

- `id`, `name`, `code`, `description`
- `enabled`
- `severity`: `info`, `warning`, `critical`
- `action`: `allow`, `warn`, `block`, `lock`
- `category`: `risk`, `behavior`, `ftmo`, `execution`, `psychology`
- `config`, `message`, `created_at`, `updated_at`

Catalog endpoints:

- `GET /api/rules/catalog`
- `POST /api/rules/catalog`
- `PUT /api/rules/catalog/{code}`

Every engine run writes a `rule_evaluations` row. Every warning/block/lock writes a `rule_violations` row. Every pre-trade check is also stored in `pre_trade_checks` with legacy `reason`, machine-readable `rule_codes`, structured `details`, and `rule_evaluation_id`.

The Rules dashboard also supports adding custom catalog rules. Custom pre-trade rules can evaluate a simple JSON condition:

```json
{
  "scope": "pre_trade",
  "field": "symbol",
  "operator": "eq",
  "value": "XAUUSD"
}
```

Supported fields are `symbol`, `order_type`, `lot`, `entry_price`, `sl`, `tp`, `risk_percent`, and `risk_amount`. Supported operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `exists`, and `missing`.

Custom close checks use `scope: "pre_close"` and run when the MT5 panel closes positions through `Close All`. The EA sends `ticket`, `symbol`, `position_type`, `lot`, `entry_price`, `current_price`, `profit`, `sl`, `tp`, `candle_close`, `ema34`, `ema89`, and `close_reason`.

Example warning for closing a BUY early while the last closed candle is still at or above EMA89:

```json
{
  "scope": "pre_close",
  "logic": "all",
  "conditions": [
    { "field": "position_type", "operator": "eq", "value": "BUY" },
    { "field": "candle_close", "operator": "gte", "value_from": "ema89" }
  ]
}
```

Example warning for closing a SELL early while the last closed candle is still at or below EMA89:

```json
{
  "scope": "pre_close",
  "logic": "all",
  "conditions": [
    { "field": "position_type", "operator": "eq", "value": "SELL" },
    { "field": "candle_close", "operator": "lte", "value_from": "ema89" }
  ]
}
```

Set `action` to `warn` to show an MT5 confirmation dialog before close. Set `action` to `block` to prevent the close.

Available rule codes:

- `PLATFORM_TRADING_ALLOWED`: blocks all new trades when platform trading is disabled.
- `NO_STOP_LOSS`: blocks planned trades without SL and alerts on open trades reported without SL.
- `MAX_TRADES_PER_DAY`: warns or blocks when trades opened today reach `max_trades_per_day`.
- `MAX_DAILY_LOSS`: locks/blocks when closed PnL for the current FTMO day reaches the daily loss limit.
- `MAX_TOTAL_LOSS`: locks/blocks when current equity loss versus balance reaches the maximum loss limit.
- `MAX_DRAWDOWN_LIMIT`: locks/blocks when realized max drawdown reaches the configured maximum loss limit.
- `MAX_CONSECUTIVE_LOSSES`: warns or blocks after the configured loss streak.
- `COOLDOWN_AFTER_LOSS`: blocks new trades during the post-loss cooldown window.
- `MAX_LOT_SIZE`: blocks lot size above `max_lot`.
- `RISK_PER_TRADE`: blocks planned trade risk above `max_risk_per_trade_percent`.
- `REVENGE_TRADING`: blocks same-symbol or larger-lot trade attempts shortly after a loss.

The MT5 EA remains compatible with the original pre-trade payload:

```json
{
  "account_number": "100002",
  "symbol": "XAUUSD",
  "order_type": "BUY",
  "lot": 0.5,
  "entry_price": 2335.5,
  "sl": 2325.5,
  "tp": 2365.5
}
```

API clients may also send optional `risk_percent` or `risk_amount` for more accurate risk-per-trade validation. If omitted, the backend estimates risk from entry, SL, lot, and account equity.

Every pre-trade check is stored in `pre_trade_checks` with the human-readable `reason`, machine-readable `rule_codes`, and structured `details`. Existing consumers can keep using `allowed`, `reason`, and `alerts` from the response.

The richer pre-trade response includes `status`, `decision`, `message`, `violations`, `warnings`, `checked_at`, and `rule_evaluation_id`. The MT5 EA remains compatible because `allowed`, `reason`, and `alerts` are still returned.

For an existing local Postgres volume, rebuild and restart the backend so startup bootstrapping applies the idempotent schema updates:

```bash
docker compose up --build -d
docker compose logs --tail=120 backend
```

If you manage the database manually, apply `backend/sql/004_rule_engine_guardrails.sql` and `backend/sql/005_rule_engine_architecture.sql`, or recreate the database volume so the new rule columns and tables exist.

## Key API Endpoints

- `POST /api/mt5/heartbeat`
- `POST /api/mt5/trade-event`
- `GET /api/journal/trades`
- `PATCH /api/journal/trades/{trade_id}`
- `GET /api/journal/stats`
- `GET /api/rules`
- `PUT /api/rules`
- `GET /api/rules/catalog`
- `POST /api/rules/catalog`
- `PUT /api/rules/catalog/{code}`
- `POST /api/rules/evaluate`
- `POST /api/rules/pre-trade-check`
- `GET /api/rules/pre-trade-checks`
- `GET /api/alerts`
- `GET /api/ai/daily-review`
- `POST /api/ai/daily-review`

## Backend Tests

Run the rule engine unit tests from the repository root:

```bash
python -m pytest backend/tests
```

To smoke test the pre-trade guardrail locally after a heartbeat, send a planned order without an SL:

```bash
curl -X POST http://localhost:8000/api/rules/pre-trade-check \
  -H "Content-Type: application/json" \
  -H "x-api-key: change-me" \
  -d '{"account_number":"100002","symbol":"XAUUSD","order_type":"BUY","lot":0.5,"entry_price":2335.5,"tp":2365.5}'
```

Expected result: `allowed=false`, `decision=BLOCK`, `reason=NO_STOP_LOSS`, and one `NO_STOP_LOSS` violation. In the dashboard, open `Rules` to change account thresholds, use `Evaluate Now` to create a manual evaluation, then open `Pre-trade Rules` to inspect stored blocked checks. In MT5, every panel order still calls `POST /api/rules/pre-trade-check`; if the backend blocks it, the EA displays the returned `reason`.

Regression verification commands:

```bash
docker compose up --build -d
curl http://localhost:8000/health
curl http://localhost:8000/api/rules
curl -X POST http://localhost:8000/api/rules/evaluate
curl -X POST http://localhost:8000/api/rules/pre-trade-check \
  -H "Content-Type: application/json" \
  -H "x-api-key: change-me" \
  -d '{"account_number":"<your-mt5-account>","symbol":"XAUUSD","order_type":"BUY","lot":0.5,"entry_price":2335.5,"tp":2365.5}'
curl -X POST http://localhost:8000/api/rules/pre-close-check \
  -H "Content-Type: application/json" \
  -H "x-api-key: change-me" \
  -d '{"account_number":"<your-mt5-account>","ticket":"123","symbol":"XAUUSD","position_type":"BUY","lot":0.5,"entry_price":2335.5,"current_price":2340.0,"profit":120,"candle_close":2334.0,"ema34":2335.0,"ema89":2332.0,"close_reason":"close_all"}'
```

The Rules dashboard uses `NEXT_PUBLIC_API_BASE_URL` in `.env` for browser calls and `INTERNAL_API_BASE_URL` for server-side frontend calls. The default Docker values are `http://localhost:8000` and `http://backend:8000`. CORS defaults allow `http://localhost:3000` and `http://127.0.0.1:3000`.

## TODO

- Add user authentication and account ownership.
- Add migrations with Alembic for production schema changes.
- Add richer FTMO start-of-day equity snapshots.
- Add integration tests.
- Add stronger order panel confirmation flows before live use.
- Add alert resolve endpoints and notification deduplication.
- Add deployment hardening for public hosting.

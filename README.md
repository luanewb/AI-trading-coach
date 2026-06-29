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
4. Enter Lot, SL, and TP in the panel.
5. Click `BUY` or `SELL`.
6. The EA sends `POST /api/rules/pre-trade-check`.
7. If allowed, the chart shows a SafeMode simulation message and no real order is sent.
8. If blocked, the chart shows the backend reason.
9. Open `Pre-trade Rules` in the dashboard to see blocked attempts.

To test real demo orders, set `SafeMode=false` in the EA inputs. With SafeMode off, the EA calls `CTrade.Buy` or `CTrade.Sell` only after backend approval. Test on demo before any live account.

`Close All` is disabled unless `AllowCloseAll=true`. When `SafeMode=true`, Close All is simulated.

## Key API Endpoints

- `POST /api/mt5/heartbeat`
- `POST /api/mt5/trade-event`
- `GET /api/journal/trades`
- `PATCH /api/journal/trades/{trade_id}`
- `GET /api/journal/stats`
- `GET /api/rules`
- `PUT /api/rules`
- `POST /api/rules/evaluate`
- `POST /api/rules/pre-trade-check`
- `GET /api/rules/pre-trade-checks`
- `GET /api/alerts`
- `GET /api/ai/daily-review`
- `POST /api/ai/daily-review`

## TODO

- Add user authentication and account ownership.
- Add migrations with Alembic for production schema changes.
- Add stronger order panel confirmation flows before live use.
- Add richer FTMO start-of-day equity snapshots.
- Add unit and integration tests.
- Add alert resolve endpoints and notification deduplication.
- Add deployment hardening for public hosting.

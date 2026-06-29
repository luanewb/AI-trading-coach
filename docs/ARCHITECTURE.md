# AI Trading Coach Architecture

## Scope

This MVP records MT5 account and trade events, evaluates risk rules, stores journal data, sends optional Telegram alerts, generates daily reviews, and provides a Version 2 MT5 trade panel. The panel calls the backend before sending orders. It runs with `SafeMode=true` by default, so orders are simulated unless the user explicitly disables SafeMode.

## Flow

1. MT5 runs `AITradingCoachConnector.mq5`.
2. The EA sends heartbeat data to `POST /api/mt5/heartbeat` with `x-api-key`.
3. The EA sends trade changes to `POST /api/mt5/trade-event` with `x-api-key`.
4. FastAPI validates payloads with Pydantic and writes PostgreSQL rows.
5. The rule engine evaluates configured limits and creates alerts.
6. Telegram is called only when bot credentials are configured.
7. The Next.js dashboard reads journal, stats, alerts, rules, and daily reviews.
8. The Version 2 MT5 panel calls `POST /api/rules/pre-trade-check` before BUY/SELL.
9. If the backend blocks the order, the EA does not call `OrderSend`.
10. OpenAI daily review runs only when `ENABLE_AI=true` and `OPENAI_API_KEY` is set.

## FTMO Logic

- Daily loss uses equity impact, not balance-only PnL.
- Daily windows use `FTMO_TIMEZONE`, defaulting to `Europe/Prague`.
- FTMO limits are not hardcoded. The `risk_rules` table stores user-configurable thresholds.

## Pre-Trade Safety

- `pre_trade_checks` stores every panel check.
- `SafeMode=true` in the EA simulates allowed orders and does not send live orders.
- `SafeMode=false` allows `CTrade.Buy` and `CTrade.Sell` only after backend approval.
- `Close All` requires `AllowCloseAll=true`; in SafeMode it is simulated.
- The backend blocks disabled trading, missing SL, lot above configured max, max trades/day, cooldown after loss, daily loss limit, and active critical alerts.

## Security Notes

- `/api/mt5/*` and `POST /api/rules/pre-trade-check` require `x-api-key`.
- Secrets live in `.env`, never in source code.
- This MVP assumes the dashboard runs on a trusted local network. Add user auth before exposing it publicly.

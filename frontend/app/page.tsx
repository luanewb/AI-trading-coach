import { Activity, CircleAlert, LineChart, RefreshCw } from "lucide-react";
import { Metric } from "@/components/Metric";
import { PUBLIC_API_BASE_URL, api } from "@/lib/api";
import type { Trade } from "@/lib/types";

const DAY_MS = 24 * 60 * 60 * 1000;

function money(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function compactMoney(value: number) {
  const sign = value < 0 ? "-" : "";
  return `${sign}${money(Math.abs(value))}`;
}

function tradeDate(trade: Trade) {
  const raw = trade.close_time || trade.open_time;
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default async function OverviewPage() {
  const [account, stats, alerts, trades] = await Promise.allSettled([api.account(), api.stats(), api.alerts(), api.trades()]);
  const accountData = account.status === "fulfilled" ? account.value : null;
  const statsData = stats.status === "fulfilled" ? stats.value : null;
  const alertData = alerts.status === "fulfilled" ? alerts.value : [];
  const tradeData = trades.status === "fulfilled" ? trades.value : [];
  const critical = alertData.some((alert) => alert.severity === "critical");
  const status = critical ? "Blocked" : alertData.length ? "Warning" : "OK";

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">MT5 Risk Dashboard</p>
          <h2 className="page-title">Trading journal and FTMO guardrails</h2>
        </div>
        <div className="panel-soft flex items-center gap-2 px-3 py-2 text-sm text-zinc-400">
          <RefreshCw size={16} aria-hidden />
          Backend: {PUBLIC_API_BASE_URL}
        </div>
      </header>

      <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Balance" value={money(accountData?.balance)} />
        <Metric label="Equity" value={money(accountData?.equity)} tone={Number(accountData?.equity || 0) >= Number(accountData?.balance || 0) ? "good" : "warn"} />
        <Metric label="Daily PnL" value={money(statsData?.daily_pnl)} tone={Number(statsData?.daily_pnl || 0) >= 0 ? "good" : "bad"} />
        <Metric label="Trades Today" value={String(statsData?.trades_today ?? 0)} tone={(statsData?.trades_today ?? 0) >= 5 ? "warn" : "neutral"} />
        <Metric label="Win Rate" value={`${(statsData?.win_rate ?? 0).toFixed(1)}%`} />
        <Metric label="Profit Factor" value={(statsData?.profit_factor ?? 0).toFixed(2)} />
        <Metric label="Max Drawdown" value={money(statsData?.max_drawdown)} tone="warn" />
        <Metric label="Consecutive Losses" value={String(statsData?.consecutive_losses ?? 0)} tone={(statsData?.consecutive_losses ?? 0) >= 3 ? "bad" : "neutral"} />
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-[1fr_420px]">
        <div className="panel p-5">
          <div className="flex items-center gap-2">
            <Activity className="text-accent" size={18} aria-hidden />
            <h3 className="text-lg font-semibold text-zinc-50">Connected Account</h3>
          </div>
          {accountData ? (
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="panel-soft p-3">
                <dt className="kicker">Account</dt>
                <dd className="mt-2 font-medium text-zinc-100">{accountData.account_number}</dd>
              </div>
              <div className="panel-soft p-3">
                <dt className="kicker">Server</dt>
                <dd className="mt-2 font-medium text-zinc-100">{accountData.broker} / {accountData.server}</dd>
              </div>
              <div className="panel-soft p-3">
                <dt className="kicker">Margin</dt>
                <dd className="mt-2 font-medium tabular-nums text-zinc-100">{money(accountData.margin)}</dd>
              </div>
              <div className="panel-soft p-3">
                <dt className="kicker">Free Margin</dt>
                <dd className="mt-2 font-medium tabular-nums text-zinc-100">{money(accountData.free_margin)}</dd>
              </div>
            </dl>
          ) : (
            <p className="muted-copy mt-4">No MT5 heartbeat yet. Seed data appears after Postgres init, or connect the EA.</p>
          )}
        </div>

        <div className="panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CircleAlert className={critical ? "text-bad" : alertData.length ? "text-warn" : "text-good"} size={18} aria-hidden />
              <h3 className="text-lg font-semibold text-zinc-50">Current Risk Status</h3>
            </div>
            <span className={`status-pill ${critical ? "bg-red-500/15 text-bad" : alertData.length ? "bg-amber-400/15 text-warn" : "bg-emerald-400/15 text-good"}`}>{status}</span>
          </div>
          <div className="mt-4 space-y-3">
            {alertData.slice(0, 4).map((alert) => (
              <div key={alert.id} className="rounded-xl border border-line bg-elevated p-3">
                <p className="text-sm font-semibold text-zinc-100">{alert.type}</p>
                <p className="mt-1 text-sm text-zinc-400">{alert.message}</p>
              </div>
            ))}
            {!alertData.length && <p className="muted-copy">No active alerts.</p>}
          </div>
        </div>
      </section>

      <CumulativePnlChart trades={tradeData} accountLabel={accountData?.account_number || "Demo Account"} />
    </div>
  );
}

function CumulativePnlChart({ trades, accountLabel }: { trades: Trade[]; accountLabel: string }) {
  const datedTrades = trades
    .map((trade) => {
      const date = tradeDate(trade);
      return date ? { date: startOfDay(date), profit: Number(trade.profit || 0) } : null;
    })
    .filter((trade): trade is { date: Date; profit: number } => Boolean(trade));
  const endDate = datedTrades.length ? datedTrades.reduce((latest, trade) => (trade.date.getTime() > latest.getTime() ? trade.date : latest), datedTrades[0].date) : startOfDay(new Date());
  const startDate = new Date(endDate.getTime() - 29 * DAY_MS);
  const daily = new Map<string, number>();
  datedTrades.forEach((trade) => {
    if (trade.date < startDate || trade.date > endDate) return;
    const key = dateKey(trade.date);
    daily.set(key, (daily.get(key) || 0) + trade.profit);
  });

  let cumulative = 0;
  const series = Array.from({ length: 30 }, (_, index) => {
    const date = new Date(startDate.getTime() + index * DAY_MS);
    cumulative += daily.get(dateKey(date)) || 0;
    return { date, value: cumulative };
  });

  const width = 1040;
  const height = 300;
  const padding = { top: 28, right: 24, bottom: 44, left: 64 };
  const values = series.map((point) => point.value);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const x = (index: number) => padding.left + (index / Math.max(series.length - 1, 1)) * (width - padding.left - padding.right);
  const y = (value: number) => padding.top + ((maxValue - value) / range) * (height - padding.top - padding.bottom);
  const linePath = series.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(2)} ${y(point.value).toFixed(2)}`).join(" ");
  const areaPath = `${linePath} L ${x(series.length - 1).toFixed(2)} ${height - padding.bottom} L ${padding.left} ${height - padding.bottom} Z`;
  const ticks = Array.from({ length: 5 }, (_, index) => minValue + (range / 4) * index).reverse();
  const dateLabels = series.filter((_, index) => index % 5 === 0 || index === series.length - 1);

  return (
    <section className="panel mt-6 overflow-hidden">
      <div className="flex items-start gap-3 border-b border-line p-5">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent/15 text-accent">
          <LineChart size={18} aria-hidden />
        </div>
        <div>
          <h3 className="font-semibold text-zinc-50">Cumulative P&L by Account</h3>
          <p className="mt-1 text-sm text-zinc-400">Showing P&L performance for last 30 days - {accountLabel}</p>
        </div>
      </div>
      <div className="overflow-x-auto p-4">
        <svg className="min-w-[1040px]" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Cumulative P&L by Account chart">
          <defs>
            <linearGradient id="pnlArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#2DD4BF" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#2DD4BF" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={padding.left} x2={width - padding.right} y1={y(tick)} y2={y(tick)} stroke="#263142" strokeWidth="1" />
              <text x={padding.left - 12} y={y(tick) + 4} textAnchor="end" className="fill-zinc-500 text-xs">
                {compactMoney(tick)}
              </text>
            </g>
          ))}
          <path d={areaPath} fill="url(#pnlArea)" />
          <path d={linePath} fill="none" stroke="#2DD4BF" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
          {dateLabels.map((point, index) => (
            <text key={dateKey(point.date)} x={x(series.indexOf(point))} y={height - 16} textAnchor={index === 0 ? "start" : "middle"} className="fill-zinc-500 text-xs">
              {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(point.date)}
            </text>
          ))}
        </svg>
      </div>
    </section>
  );
}

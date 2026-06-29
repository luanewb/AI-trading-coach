import { Activity, CircleAlert, RefreshCw } from "lucide-react";
import { Metric } from "@/components/Metric";
import { PUBLIC_API_BASE_URL, api } from "@/lib/api";

function money(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

export default async function OverviewPage() {
  const [account, stats, alerts] = await Promise.allSettled([api.account(), api.stats(), api.alerts()]);
  const accountData = account.status === "fulfilled" ? account.value : null;
  const statsData = stats.status === "fulfilled" ? stats.value : null;
  const alertData = alerts.status === "fulfilled" ? alerts.value : [];
  const critical = alertData.some((alert) => alert.severity === "critical");
  const status = critical ? "Blocked" : alertData.length ? "Warning" : "OK";

  return (
    <div className="pb-20">
      <header className="flex flex-col gap-3 border-b border-line pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">MT5 Risk Dashboard</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-normal">Trading journal and FTMO guardrails</h2>
        </div>
        <div className="flex items-center gap-2 text-sm text-zinc-600">
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
        <div className="border border-line bg-white p-5">
          <div className="flex items-center gap-2">
            <Activity size={18} aria-hidden />
            <h3 className="text-lg font-semibold">Connected Account</h3>
          </div>
          {accountData ? (
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-zinc-500">Account</dt>
                <dd className="mt-1 font-medium">{accountData.account_number}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-zinc-500">Server</dt>
                <dd className="mt-1 font-medium">{accountData.broker} / {accountData.server}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-zinc-500">Margin</dt>
                <dd className="mt-1 font-medium">{money(accountData.margin)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-zinc-500">Free Margin</dt>
                <dd className="mt-1 font-medium">{money(accountData.free_margin)}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-4 text-sm text-zinc-600">No MT5 heartbeat yet. Seed data appears after Postgres init, or connect the EA.</p>
          )}
        </div>

        <div className="border border-line bg-white p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CircleAlert size={18} aria-hidden />
              <h3 className="text-lg font-semibold">Current Risk Status</h3>
            </div>
            <span className={`rounded px-2 py-1 text-xs font-semibold ${critical ? "bg-red-100 text-bad" : alertData.length ? "bg-amber-100 text-warn" : "bg-green-100 text-good"}`}>{status}</span>
          </div>
          <div className="mt-4 space-y-3">
            {alertData.slice(0, 4).map((alert) => (
              <div key={alert.id} className="border-l-4 border-zinc-300 pl-3">
                <p className="text-sm font-semibold">{alert.type}</p>
                <p className="mt-1 text-sm text-zinc-600">{alert.message}</p>
              </div>
            ))}
            {!alertData.length && <p className="text-sm text-zinc-600">No active alerts.</p>}
          </div>
        </div>
      </section>
    </div>
  );
}

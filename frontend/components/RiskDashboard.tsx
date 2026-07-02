"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Gauge,
  LineChart,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TrendingDown
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api, PUBLIC_API_BASE_URL } from "@/lib/api";
import type {
  Account,
  AccountSnapshotPoint,
  CountBudget,
  PreTradeHistoryItem,
  RiskActivityFilter,
  RiskActivityItem,
  RiskBudget,
  RiskSummary,
  SnapshotRange
} from "@/lib/types";

type OverviewData = {
  account: Account | null;
  summary: RiskSummary | null;
  activity: RiskActivityItem[];
  snapshots: AccountSnapshotPoint[];
  preTradeHistory: PreTradeHistoryItem[];
  errors: string[];
};

const activityFilters: RiskActivityFilter[] = ["all", "warning", "blocked", "locked", "resolved"];
const snapshotRanges: SnapshotRange[] = ["24h", "7d", "30d"];
const displayTimeZone = "Asia/Bangkok";

function money(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function numberText(value: number | string | null | undefined, digits = 0) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(amount);
}

function dateTime(value: string | null | undefined) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: displayTimeZone }).format(date);
}

function statusTone(status: RiskSummary["trading_status"] | string) {
  if (status === "allowed") return "good";
  if (status === "warning") return "warn";
  return "bad";
}

function toneClasses(tone: "good" | "warn" | "bad" | "neutral") {
  return {
    good: "border-emerald-400/25 bg-emerald-400/10 text-good",
    warn: "border-amber-400/25 bg-amber-400/10 text-warn",
    bad: "border-red-400/25 bg-red-500/10 text-bad",
    neutral: "border-line bg-elevated text-zinc-300"
  }[tone];
}

function budgetTone(percentUsed: number) {
  if (percentUsed >= 100) return "bad";
  if (percentUsed >= 80) return "warn";
  return "good";
}

function statusIcon(status: RiskSummary["trading_status"]) {
  if (status === "allowed") return CheckCircle2;
  if (status === "warning") return AlertTriangle;
  if (status === "locked") return LockKeyhole;
  return Ban;
}

function progressColor(tone: "good" | "warn" | "bad" | "neutral") {
  return {
    good: "bg-good",
    warn: "bg-warn",
    bad: "bg-bad",
    neutral: "bg-zinc-500"
  }[tone];
}

function filterActivity(items: RiskActivityItem[], filter: RiskActivityFilter) {
  return items.filter((item) => {
    if (filter === "all") return true;
    if (filter === "resolved") return item.status === "resolved";
    if (filter === "warning") return item.action === "warn" || item.severity === "warning";
    if (filter === "blocked") return item.action === "block" || item.decision === "BLOCK";
    return item.action === "lock" || item.decision === "LOCK";
  });
}

export function RiskDashboard({ initialData }: { initialData: OverviewData }) {
  const [activityFilter, setActivityFilter] = useState<RiskActivityFilter>("all");
  const [snapshots, setSnapshots] = useState(initialData.snapshots);
  const [snapshotRange, setSnapshotRange] = useState<SnapshotRange>("7d");
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [expandedCheck, setExpandedCheck] = useState<number | null>(null);
  const accountId = initialData.account?.id ?? initialData.summary?.account_id ?? null;

  useEffect(() => {
    setSnapshots(initialData.snapshots);
  }, [accountId, initialData.snapshots]);

  useEffect(() => {
    let mounted = true;
    setSnapshotLoading(true);
    setSnapshotError(null);
    api.accountSnapshots(snapshotRange, accountId)
      .then((points) => {
        if (mounted) setSnapshots(points);
      })
      .catch(() => {
        if (mounted) setSnapshotError("Snapshot history could not be loaded. The dashboard is still showing the latest available data.");
      })
      .finally(() => {
        if (mounted) setSnapshotLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [snapshotRange, accountId]);

  const filteredActivity = useMemo(() => filterActivity(initialData.activity, activityFilter), [initialData.activity, activityFilter]);
  const summary = initialData.summary;

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

      {initialData.errors.length > 0 && (
        <div className="mt-5 rounded-lg border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-warn">
          Some dashboard data is unavailable: {initialData.errors.join(" ")}
        </div>
      )}

      {initialData.account && summary ? (
        <>
          <section className="panel mt-6 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="kicker">Connected MT5 Account</p>
                <h3 className="mt-2 text-xl font-semibold text-zinc-50">{initialData.account.account_number}</h3>
              </div>
              <div className="text-sm text-zinc-400">
                {initialData.account.broker} / {initialData.account.server}
              </div>
            </div>
          </section>

          <section className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Balance" value={money(initialData.account.balance)} />
            <MetricCard
              label="Equity"
              value={money(initialData.account.equity)}
              tone={Number(initialData.account.equity || 0) >= Number(initialData.account.balance || 0) ? "good" : "warn"}
            />
            <MetricCard label="Daily PnL" value={money(summary.current_daily_pnl)} tone={Number(summary.current_daily_pnl || 0) >= 0 ? "good" : "bad"} />
            <MetricCard label="Trades Today" value={String(summary.trades_today.current)} tone={budgetTone(summary.trades_today.percent_used)} />
          </section>
        </>
      ) : (
        <section className="panel mt-6 p-5">
          <div className="flex items-center gap-2 text-zinc-100">
            <ShieldAlert className="text-warn" size={18} aria-hidden />
            <h3 className="font-semibold">No real MT5 account connected</h3>
          </div>
          <p className="muted-copy mt-3">Waiting for a live MT5 heartbeat. Seed/demo account data is hidden from this dashboard.</p>
        </section>
      )}

      {summary ? (
        <>
          <RiskStatusSection summary={summary} />
          <RiskBudgetGrid summary={summary} />
        </>
      ) : (
        <section className="panel mt-6 p-5">
          <div className="flex items-center gap-2 text-zinc-100">
            <ShieldAlert className="text-warn" size={18} aria-hidden />
            <h3 className="font-semibold">Risk Status</h3>
          </div>
          <p className="muted-copy mt-3">Connect an MT5 account to calculate live risk limits.</p>
        </section>
      )}

      <section className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_460px]">
        <SnapshotChart points={snapshots} range={snapshotRange} onRangeChange={setSnapshotRange} loading={snapshotLoading} error={snapshotError} />
        <RecentRiskActivity items={filteredActivity} selectedFilter={activityFilter} onFilterChange={setActivityFilter} />
      </section>

      <PreTradeHistoryPanel items={initialData.preTradeHistory} expandedCheck={expandedCheck} onToggle={setExpandedCheck} />
    </div>
  );
}

function MetricCard({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const textClass = {
    neutral: "text-zinc-50",
    good: "text-good",
    warn: "text-warn",
    bad: "text-bad"
  }[tone];

  return (
    <div className="panel p-4">
      <p className="kicker">{label}</p>
      <p className={`mt-3 text-2xl font-semibold tabular-nums ${textClass}`}>{value}</p>
    </div>
  );
}

function RiskStatusSection({ summary }: { summary: RiskSummary }) {
  const StatusIcon = statusIcon(summary.trading_status);
  const tone = statusTone(summary.trading_status);

  return (
    <section className="panel mt-6 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <StatusIcon className={tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : "text-bad"} size={20} aria-hidden />
            <h3 className="text-lg font-semibold text-zinc-50">Risk Status</h3>
          </div>
          <p className="mt-2 text-sm text-zinc-400">{summary.status_reason}</p>
        </div>
        <span className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold ${toneClasses(tone)}`}>
          <StatusIcon size={16} aria-hidden />
          {summary.status_label}
        </span>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatusDatum label="Daily PnL" value={money(summary.current_daily_pnl)} detail={`${numberText(summary.daily_loss.percent_used, 1)}% loss limit used`} tone={budgetTone(summary.daily_loss.percent_used)} />
        <StatusDatum label="Drawdown" value={money(summary.total_drawdown.used)} detail={`${money(summary.total_drawdown.remaining)} remaining`} tone={budgetTone(summary.total_drawdown.percent_used)} />
        <StatusDatum label="Cooldown" value={summary.cooldown.active ? "Active" : "Inactive"} detail={summary.cooldown.active ? `${Math.ceil(summary.cooldown.remaining_seconds / 60)} minutes left` : "No post-loss lockout"} tone={summary.cooldown.active ? "bad" : "good"} />
        <StatusDatum label="Max Lot" value={summary.max_lot.planned_lot ? numberText(summary.max_lot.planned_lot, 2) : "No plan"} detail={`${numberText(summary.max_lot.configured_max_lot, 2)} configured max`} tone={summary.max_lot.planned_lot && Number(summary.max_lot.planned_lot) > Number(summary.max_lot.configured_max_lot) ? "bad" : "neutral"} />
      </div>

      {summary.active_restrictions.length > 0 && (
        <div className="mt-5 grid gap-2">
          {summary.active_restrictions.slice(0, 4).map((item) => (
            <div key={`${item.rule_code}-${item.created_at}`} className="rounded-lg border border-line bg-elevated p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-zinc-100">{item.rule_code}</span>
                <span className={`status-pill ${toneClasses(item.action === "warn" ? "warn" : "bad")}`}>{item.action}</span>
                <span className="text-xs text-zinc-500">{dateTime(item.created_at)}</span>
              </div>
              <p className="mt-1 text-zinc-400">{item.message}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function StatusDatum({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className="panel-soft p-3">
      <p className="kicker">{label}</p>
      <p className={`mt-2 text-xl font-semibold tabular-nums ${tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "text-zinc-100"}`}>{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{detail}</p>
    </div>
  );
}

function RiskBudgetGrid({ summary }: { summary: RiskSummary }) {
  return (
    <section className="mt-6 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
      <RiskBudgetCard title="Daily Loss Budget" icon={TrendingDown} budget={summary.daily_loss} usedText={`${money(summary.daily_loss.used)} used / ${money(summary.daily_loss.limit)} limit`} />
      <RiskBudgetCard title="Total Drawdown Budget" icon={Gauge} budget={summary.total_drawdown} usedText={`${money(summary.total_drawdown.used)} used / ${money(summary.total_drawdown.limit)} limit`} />
      <CountBudgetCard title="Trade Count Budget" icon={ShieldCheck} budget={summary.trades_today} usedText={`${summary.trades_today.current} used / ${summary.trades_today.limit} limit`} />
      <CountBudgetCard title="Consecutive Loss Budget" icon={ShieldAlert} budget={summary.consecutive_losses} usedText={`${summary.consecutive_losses.current} losses / ${summary.consecutive_losses.limit} limit`} />
    </section>
  );
}

function RiskBudgetCard({ title, icon: Icon, budget, usedText }: { title: string; icon: LucideIcon; budget: RiskBudget; usedText: string }) {
  const tone = budgetTone(budget.percent_used);
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon size={17} className={tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : "text-bad"} aria-hidden />
          <h3 className="font-semibold text-zinc-100">{title}</h3>
        </div>
        <span className={`status-pill ${toneClasses(tone)}`}>{numberText(budget.percent_remaining, 0)}% left</span>
      </div>
      <p className="mt-4 text-sm text-zinc-400">{usedText}</p>
      <Progress percent={budget.percent_used} tone={tone} />
      <p className="mt-2 text-xs text-zinc-500">{money(budget.remaining)} remaining</p>
    </div>
  );
}

function CountBudgetCard({ title, icon: Icon, budget, usedText }: { title: string; icon: LucideIcon; budget: CountBudget; usedText: string }) {
  const tone = budgetTone(budget.percent_used);
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon size={17} className={tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : "text-bad"} aria-hidden />
          <h3 className="font-semibold text-zinc-100">{title}</h3>
        </div>
        <span className={`status-pill ${toneClasses(tone)}`}>{budget.remaining} left</span>
      </div>
      <p className="mt-4 text-sm text-zinc-400">{usedText}</p>
      <Progress percent={budget.percent_used} tone={tone} />
      <p className="mt-2 text-xs text-zinc-500">{numberText(budget.percent_remaining, 0)}% remaining</p>
    </div>
  );
}

function Progress({ percent, tone }: { percent: number; tone: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-800" aria-label={`${numberText(percent, 0)} percent used`}>
      <div className={`h-full rounded-full ${progressColor(tone)}`} style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
    </div>
  );
}

function RecentRiskActivity({ items, selectedFilter, onFilterChange }: { items: RiskActivityItem[]; selectedFilter: RiskActivityFilter; onFilterChange: (filter: RiskActivityFilter) => void }) {
  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-line p-5">
        <div className="flex items-center gap-2">
          <Clock3 size={18} className="text-accent" aria-hidden />
          <h3 className="font-semibold text-zinc-50">Recent Risk Activity</h3>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {activityFilters.map((filter) => (
            <button
              key={filter}
              className={`h-9 rounded-lg border px-3 text-xs font-semibold capitalize ${selectedFilter === filter ? "border-accent bg-accent text-slate-950" : "border-line bg-elevated text-zinc-300 hover:border-accent hover:text-accent"}`}
              onClick={() => onFilterChange(filter)}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>
      <div className="max-h-[520px] overflow-y-auto p-4">
        {items.length > 0 ? (
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="rounded-lg border border-line bg-elevated p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-zinc-100">{item.rule_code}</span>
                  <span className={`status-pill ${toneClasses(item.action === "warn" ? "warn" : item.status === "resolved" ? "neutral" : "bad")}`}>{item.status === "resolved" ? "resolved" : item.action}</span>
                  <span className="text-xs text-zinc-500">{dateTime(item.timestamp)}</span>
                </div>
                <p className="mt-2 text-sm text-zinc-400">{item.message}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span>{item.source.replaceAll("_", " ")}</span>
                  {item.decision && <span>Decision: {item.decision}</span>}
                  {item.symbol && <span>Symbol: {item.symbol}</span>}
                  {item.ticket && <span>Ticket: {item.ticket}</span>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted-copy">No activity matches this filter.</p>
        )}
      </div>
    </section>
  );
}

function SnapshotChart({
  points,
  range,
  onRangeChange,
  loading,
  error
}: {
  points: AccountSnapshotPoint[];
  range: SnapshotRange;
  onRangeChange: (range: SnapshotRange) => void;
  loading: boolean;
  error: string | null;
}) {
  const width = 840;
  const height = 320;
  const padding = { top: 26, right: 24, bottom: 42, left: 112 };
  const values = points.flatMap((point) => [Number(point.balance), Number(point.equity)]);
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 1;
  const rangeValue = maxValue - minValue || 1;
  const x = (index: number) => padding.left + (index / Math.max(points.length - 1, 1)) * (width - padding.left - padding.right);
  const y = (value: number) => padding.top + ((maxValue - value) / rangeValue) * (height - padding.top - padding.bottom);
  const path = (key: "balance" | "equity") => points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(2)} ${y(Number(point[key])).toFixed(2)}`).join(" ");
  const ticks = Array.from({ length: 4 }, (_, index) => minValue + (rangeValue / 3) * index).reverse();

  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <LineChart size={18} className="text-accent" aria-hidden />
          <h3 className="font-semibold text-zinc-50">Account Snapshot / Equity</h3>
        </div>
        <div className="flex gap-2">
          {snapshotRanges.map((option) => (
            <button
              key={option}
              className={`h-9 rounded-lg border px-3 text-xs font-semibold uppercase ${range === option ? "border-accent bg-accent text-slate-950" : "border-line bg-elevated text-zinc-300 hover:border-accent hover:text-accent"}`}
              onClick={() => onRangeChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="p-4">
        {loading && <p className="mb-3 text-sm text-zinc-400">Loading snapshot history...</p>}
        {error && <p className="mb-3 rounded-lg border border-amber-400/25 bg-amber-400/10 p-3 text-sm text-warn">{error}</p>}
        {points.length > 1 ? (
          <div className="w-full">
            <svg className="h-auto w-full" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Balance and equity chart">
              {ticks.map((tick) => (
                <g key={tick}>
                  <line x1={padding.left} x2={width - padding.right} y1={y(tick)} y2={y(tick)} stroke="#263142" strokeWidth="1" />
                  <text x={padding.left - 12} y={y(tick) + 4} textAnchor="end" className="fill-zinc-500 text-xs">
                    {money(tick)}
                  </text>
                </g>
              ))}
              <path d={path("balance")} fill="none" stroke="#38BDF8" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />
              <path d={path("equity")} fill="none" stroke="#2DD4BF" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
              {points.filter((_, index) => index === 0 || index === points.length - 1 || index % Math.ceil(points.length / 4) === 0).map((point) => {
                const pointIndex = points.indexOf(point);
                const anchor = pointIndex === 0 ? "start" : pointIndex === points.length - 1 ? "end" : "middle";
                return (
                  <text key={`${point.id}-${point.timestamp}`} x={x(pointIndex)} y={height - 16} textAnchor={anchor} className="fill-zinc-500 text-xs">
                    {dateTime(point.timestamp)}
                  </text>
                );
              })}
            </svg>
          </div>
        ) : (
          <p className="muted-copy">No account snapshots are available for this range.</p>
        )}
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-400">
          <span className="inline-flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-sky-400" />Balance</span>
          <span className="inline-flex items-center gap-2"><span className="h-2 w-5 rounded-full bg-accent" />Equity</span>
        </div>
      </div>
    </section>
  );
}

function PreTradeHistoryPanel({ items, expandedCheck, onToggle }: { items: PreTradeHistoryItem[]; expandedCheck: number | null; onToggle: (id: number | null) => void }) {
  return (
    <section className="panel mt-6 overflow-hidden">
      <div className="border-b border-line p-5">
        <div className="flex items-center gap-2">
          <ShieldCheck size={18} className="text-accent" aria-hidden />
          <h3 className="font-semibold text-zinc-50">Pre-trade Check History</h3>
        </div>
      </div>
      <div className="overflow-x-auto">
        {items.length > 0 ? (
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-elevated text-xs uppercase tracking-[0.12em] text-zinc-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3">Lot</th>
                <th className="px-4 py-3">Entry / SL / TP</th>
                <th className="px-4 py-3">Decision</th>
                <th className="px-4 py-3">Reason</th>
                <th className="px-4 py-3">Alerts</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const expanded = expandedCheck === item.id;
                return (
                  <Fragment key={item.id}>
                    <tr className="border-t border-line">
                      <td className="px-4 py-3 text-zinc-400">{dateTime(item.timestamp)}</td>
                      <td className="px-4 py-3 font-semibold text-zinc-100">{item.symbol}</td>
                      <td className="px-4 py-3 text-zinc-300">{item.side}</td>
                      <td className="px-4 py-3 tabular-nums text-zinc-300">{numberText(item.lot, 2)}</td>
                      <td className="px-4 py-3 tabular-nums text-zinc-400">{numberText(item.entry_price, 2)} / {item.sl ? numberText(item.sl, 2) : "-"} / {item.tp ? numberText(item.tp, 2) : "-"}</td>
                      <td className="px-4 py-3"><span className={`status-pill ${toneClasses(item.allowed ? "good" : item.decision === "WARN" ? "warn" : "bad")}`}>{item.decision}</span></td>
                      <td className="px-4 py-3 text-zinc-300">{item.reason}</td>
                      <td className="px-4 py-3 text-zinc-400">{item.warning_count} warnings, {item.violation_count} violations</td>
                      <td className="px-4 py-3">
                        <button className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-elevated text-zinc-300 hover:border-accent hover:text-accent" onClick={() => onToggle(expanded ? null : item.id)} aria-label={`Toggle details for ${item.symbol}`}>
                          {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
                        </button>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-t border-line bg-elevated/60">
                        <td colSpan={9} className="px-4 py-3">
                          <pre className="max-h-72 overflow-auto rounded-lg border border-line bg-paper p-3 text-xs leading-5 text-zinc-300">{JSON.stringify(item.details, null, 2)}</pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="muted-copy p-5">No pre-trade checks have been recorded yet.</p>
        )}
      </div>
    </section>
  );
}

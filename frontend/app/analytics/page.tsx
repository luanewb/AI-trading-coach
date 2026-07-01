"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, BarChart3, CalendarDays, LineChart, TrendingDown, TrendingUp } from "lucide-react";
import { Metric } from "@/components/Metric";
import { useSelectedAccount } from "@/components/AccountContext";
import { api } from "@/lib/api";
import type { AnalyticsBreakdown, AnalyticsBreakdownRow, AnalyticsDateRangeQuery, AnalyticsInsight, AnalyticsMetrics, AnalyticsOverview } from "@/lib/types";

const groups = [
  { key: "symbol", label: "Symbol" },
  { key: "setup", label: "Setup" },
  { key: "direction", label: "Direction" },
  { key: "session", label: "Session" },
  { key: "hour", label: "Hour" },
  { key: "weekday", label: "Weekday" },
  { key: "emotion", label: "Emotion" },
  { key: "mistake", label: "Mistake" },
  { key: "rule_violation", label: "Rule Code" }
];

const presets = [
  { key: "7d", label: "7d", days: 7 },
  { key: "30d", label: "30d", days: 30 },
  { key: "90d", label: "90d", days: 90 },
  { key: "all", label: "All", days: null },
  { key: "custom", label: "Custom", days: null }
] as const;

type PresetKey = (typeof presets)[number]["key"];

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function presetRange(key: PresetKey): AnalyticsDateRangeQuery {
  const preset = presets.find((item) => item.key === key);
  if (!preset || preset.days === null) return {};
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - preset.days + 1);
  return { start_date: isoDate(start), end_date: isoDate(end) };
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function numberText(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "N/A";
  return `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}${suffix}`;
}

function holdingTime(minutes: number | null) {
  if (minutes === null) return "N/A";
  if (minutes < 90) return `${numberText(minutes)}m`;
  return `${numberText(minutes / 60)}h`;
}

function profitFactor(value: number | null) {
  return value === null ? "No losses" : numberText(value);
}

function confidenceClass(code: AnalyticsMetrics["confidence"]["code"]) {
  if (code === "meaningful_sample") return "border-good/30 bg-good/10 text-good";
  if (code === "early_signal") return "border-warn/30 bg-warn/10 text-warn";
  return "border-line bg-elevated text-zinc-400";
}

function toneClass(tone: AnalyticsInsight["tone"]) {
  if (tone === "edge") return "border-good/30 bg-good/10 text-good";
  if (tone === "leak") return "border-bad/30 bg-bad/10 text-bad";
  return "border-line bg-elevated text-zinc-400";
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-elevated/40 p-5">
      <p className="text-sm font-semibold text-zinc-100">{title}</p>
      <p className="mt-2 text-sm leading-6 text-zinc-400">{body}</p>
    </div>
  );
}

export default function AnalyticsPage() {
  const { selectedAccountId, selectedAccount, loading: accountLoading } = useSelectedAccount();
  const [preset, setPreset] = useState<PresetKey>("30d");
  const [range, setRange] = useState<AnalyticsDateRangeQuery>(() => presetRange("30d"));
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [breakdowns, setBreakdowns] = useState<Record<string, AnalyticsBreakdown>>({});
  const [insights, setInsights] = useState<AnalyticsInsight[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function choosePreset(next: PresetKey) {
    setPreset(next);
    if (next !== "custom") {
      setRange(presetRange(next));
    }
  }

  useEffect(() => {
    if (!selectedAccountId) {
      setOverview(null);
      setBreakdowns({});
      setInsights([]);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([
      api.analyticsOverview(selectedAccountId, range),
      api.analyticsInsights(selectedAccountId, range),
      Promise.all(groups.map((group) => api.analyticsBreakdown(group.key, selectedAccountId, range)))
    ])
      .then(([overviewData, insightData, breakdownData]) => {
        if (!active) return;
        setOverview(overviewData);
        setInsights(insightData.insights);
        setBreakdowns(Object.fromEntries(breakdownData.map((item) => [item.group_by, item])));
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load analytics");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedAccountId, range.start_date, range.end_date]);

  const metrics = overview?.metrics;
  const edgeInsights = insights.filter((item) => item.tone === "edge" && item.supported);
  const leakInsights = insights.filter((item) => item.tone === "leak" && item.supported);
  const infoInsights = insights.filter((item) => !item.supported);
  const rangeLabel = useMemo(() => {
    if (!range.start_date && !range.end_date) return "All time";
    return `${range.start_date || "Start"} to ${range.end_date || "Today"}`;
  }, [range.start_date, range.end_date]);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Performance Analytics</p>
          <h2 className="page-title">Trading edge map</h2>
          {selectedAccount && <p className="mt-2 text-sm text-zinc-400">Account {selectedAccount.account_number} · {rangeLabel}</p>}
        </div>
        <div className="flex flex-col gap-3 sm:items-end">
          <div className="inline-grid grid-cols-5 rounded-lg border border-line bg-elevated p-1">
            {presets.map((item) => (
              <button
                key={item.key}
                className={`h-9 rounded-md px-3 text-xs font-semibold transition ${preset === item.key ? "bg-accent text-slate-950" : "text-zinc-400 hover:text-zinc-100"}`}
                onClick={() => choosePreset(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {preset === "custom" && (
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} aria-hidden />
                <input className="input-field w-full pl-9" type="date" value={range.start_date || ""} onChange={(event) => setRange((current) => ({ ...current, start_date: event.target.value || null }))} />
              </label>
              <label className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} aria-hidden />
                <input className="input-field w-full pl-9" type="date" value={range.end_date || ""} onChange={(event) => setRange((current) => ({ ...current, end_date: event.target.value || null }))} />
              </label>
            </div>
          )}
        </div>
      </header>

      {error && <p className="mt-4 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-bad">{error}</p>}
      {!accountLoading && !selectedAccountId && <EmptyState title="No account connected" body="Analytics appears after a real MT5 account has synced closed trades." />}
      {selectedAccountId && loading && <p className="mt-4 text-sm text-zinc-400">Loading analytics...</p>}

      {selectedAccountId && overview && (
        <>
          {overview.no_data ? (
            <section className="mt-5">
              <EmptyState title="No closed trades in this range" body="Closed MT5 trades are required before performance analytics can calculate edge and leak observations." />
            </section>
          ) : (
            <>
              <section className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <Metric label="Closed Trades" value={String(metrics?.total_closed_trades ?? 0)} />
                <Metric label="Wins / Losses" value={`${metrics?.wins ?? 0} / ${metrics?.losses ?? 0}`} />
                <Metric label="Win Rate" value={numberText(metrics?.win_rate, "%")} tone={(metrics?.win_rate || 0) >= 50 ? "good" : "warn"} />
                <Metric label="Realized PnL" value={money(metrics?.total_realized_pnl)} tone={(metrics?.total_realized_pnl || 0) >= 0 ? "good" : "bad"} />
                <Metric label="Profit Factor" value={profitFactor(metrics?.profit_factor ?? null)} />
                <Metric label="Expectancy" value={money(metrics?.expectancy)} tone={(metrics?.expectancy || 0) >= 0 ? "good" : "bad"} />
                <Metric label="Average R" value={numberText(metrics?.average_r_multiple)} />
                <Metric label="Avg Hold" value={holdingTime(metrics?.average_holding_minutes ?? null)} />
              </section>

              <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                <div className="panel p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="kicker">Performance Curve</p>
                      <h3 className="mt-2 text-lg font-semibold text-zinc-50">Cumulative realized PnL</h3>
                    </div>
                    <LineChart className="text-accent" size={20} aria-hidden />
                  </div>
                  {overview.equity_curve.length > 1 ? <PerformanceCurve points={overview.equity_curve} /> : <EmptyState title="Curve waiting for more days" body="A curve appears after closed trades land on more than one date." />}
                </div>
                <div className="panel p-5">
                  <p className="kicker">Sample Quality</p>
                  {metrics && (
                    <>
                      <span className={`mt-4 inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${confidenceClass(metrics.confidence.code)}`}>{metrics.confidence.label} · {metrics.confidence.sample_size} trades</span>
                      <div className="mt-5 grid gap-3 text-sm">
                        <MetricLine label="Gross Profit" value={money(metrics.gross_profit)} />
                        <MetricLine label="Gross Loss" value={money(metrics.gross_loss)} />
                        <MetricLine label="Avg Winner" value={money(metrics.average_winner)} />
                        <MetricLine label="Avg Loser" value={money(metrics.average_loser)} />
                        <MetricLine label="Best / Worst R" value={`${numberText(metrics.best_r_multiple)} / ${numberText(metrics.worst_r_multiple)}`} />
                        <MetricLine label="Max Win / Loss Streak" value={`${metrics.max_consecutive_wins} / ${metrics.max_consecutive_losses}`} />
                      </div>
                    </>
                  )}
                </div>
              </section>
            </>
          )}

          <section className="mt-4 grid gap-4 xl:grid-cols-2">
            <InsightPanel title="Your Edge" icon={<TrendingUp size={18} aria-hidden />} insights={edgeInsights} fallback={infoInsights[0]} />
            <InsightPanel title="Your Leaks" icon={<TrendingDown size={18} aria-hidden />} insights={leakInsights} fallback={infoInsights[0]} />
          </section>

          <section className="mt-4 grid gap-4">
            {groups.map((group) => (
              <BreakdownTable key={group.key} title={group.label} breakdown={breakdowns[group.key]} />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line/70 pb-3 last:border-b-0 last:pb-0">
      <span className="text-zinc-500">{label}</span>
      <span className="font-semibold tabular-nums text-zinc-100">{value}</span>
    </div>
  );
}

function InsightPanel({ title, icon, insights, fallback }: { title: string; icon: React.ReactNode; insights: AnalyticsInsight[]; fallback?: AnalyticsInsight }) {
  return (
    <div className="panel p-5">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent">{icon}</div>
        <h3 className="text-lg font-semibold text-zinc-50">{title}</h3>
      </div>
      <div className="mt-4 space-y-3">
        {(insights.length ? insights : fallback ? [fallback] : []).map((insight) => (
          <div key={`${insight.title}-${insight.key || "none"}`} className="rounded-xl border border-line bg-elevated p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClass(insight.tone)}`}>{insight.supported ? insight.tone : "info"}</span>
              {insight.confidence && <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${confidenceClass(insight.confidence.code)}`}>{insight.confidence.label} · {insight.sample_size}</span>}
            </div>
            <p className="mt-3 text-sm font-semibold text-zinc-100">{insight.title}</p>
            <p className="mt-2 text-sm leading-6 text-zinc-400">{insight.observation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function BreakdownTable({ title, breakdown }: { title: string; breakdown?: AnalyticsBreakdown }) {
  const rows = breakdown?.rows || [];
  const emptyCopy = title === "Setup" || title === "Emotion" || title === "Mistake"
    ? `No ${title.toLowerCase()} journal data in this range.`
    : "No rows in this range.";

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-line p-5">
        <div>
          <p className="kicker">Breakdown</p>
          <h3 className="mt-2 text-lg font-semibold text-zinc-50">{title}</h3>
        </div>
        <BarChart3 className="text-zinc-500" size={18} aria-hidden />
      </div>
      {rows.length === 0 ? (
        <div className="p-5">
          <EmptyState title={emptyCopy} body={breakdown?.missing_journal_count ? `${breakdown.missing_journal_count} closed trade(s) had no value for this journal field.` : "Closed trades with this grouping value will appear here."} />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-elevated text-xs uppercase tracking-[0.14em] text-zinc-500">
              <tr>
                <th className="px-5 py-3 font-semibold">{title}</th>
                <th className="px-4 py-3 font-semibold">Trades</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Win Rate</th>
                <th className="px-4 py-3 font-semibold">PnL</th>
                <th className="px-4 py-3 font-semibold">PF</th>
                <th className="px-4 py-3 font-semibold">Expectancy</th>
                <th className="px-4 py-3 font-semibold">Avg R</th>
                <th className="px-4 py-3 font-semibold">Avg Win / Loss</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.slice(0, 10).map((row) => (
                <BreakdownRow key={`${row.group_by}-${row.key}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BreakdownRow({ row }: { row: AnalyticsBreakdownRow }) {
  const metrics = row.metrics;
  return (
    <tr className="text-zinc-300">
      <td className="px-5 py-4 font-semibold text-zinc-100">{row.label}</td>
      <td className="px-4 py-4 tabular-nums">{metrics.total_closed_trades}</td>
      <td className="px-4 py-4">
        <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${confidenceClass(metrics.confidence.code)}`}>{metrics.confidence.label}</span>
      </td>
      <td className="px-4 py-4 tabular-nums">{numberText(metrics.win_rate, "%")}</td>
      <td className={`px-4 py-4 tabular-nums ${(metrics.total_realized_pnl || 0) >= 0 ? "text-good" : "text-bad"}`}>{money(metrics.total_realized_pnl)}</td>
      <td className="px-4 py-4 tabular-nums">{profitFactor(metrics.profit_factor)}</td>
      <td className={`px-4 py-4 tabular-nums ${(metrics.expectancy || 0) >= 0 ? "text-good" : "text-bad"}`}>{money(metrics.expectancy)}</td>
      <td className="px-4 py-4 tabular-nums">{numberText(metrics.average_r_multiple)}</td>
      <td className="px-4 py-4 tabular-nums">{money(metrics.average_winner)} / {money(metrics.average_loser)}</td>
    </tr>
  );
}

function PerformanceCurve({ points }: { points: AnalyticsOverview["equity_curve"] }) {
  const width = 720;
  const height = 220;
  const values = points.map((point) => point.cumulative_pnl);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const span = max - min || 1;
  const plotted = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - ((point.cumulative_pnl - min) / span) * height;
    return `${x},${y}`;
  });
  const last = points[points.length - 1];
  const zeroY = height - ((0 - min) / span) * height;

  return (
    <div className="mt-5">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full overflow-visible">
        <line x1="0" x2={width} y1={zeroY} y2={zeroY} stroke="rgba(248,250,252,0.16)" strokeDasharray="6 6" />
        <polyline fill="none" stroke="#2DD4BF" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" points={plotted.join(" ")} />
      </svg>
      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>{points[0]?.date}</span>
        <span className="flex items-center gap-2 text-zinc-300"><Activity size={14} aria-hidden /> {money(last?.cumulative_pnl)}</span>
        <span>{last?.date}</span>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Bot, CalendarDays, CheckCircle2, ListRestart, RefreshCw, ShieldCheck, TrendingUp } from "lucide-react";
import { useSelectedAccount } from "@/components/AccountContext";
import { api } from "@/lib/api";
import type { DailyReview } from "@/lib/types";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function numberText(value: number | string | null | undefined, suffix = "") {
  if (value === null || value === undefined || value === "") return "N/A";
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? `${parsed.toFixed(2)}${suffix}` : `${value}${suffix}`;
}

function listText(items: Array<{ name: string; count: number }> | undefined) {
  if (!items || items.length === 0) return "No data";
  return items.map((item) => `${item.name} (${item.count})`).join(", ");
}

export default function DailyReviewPage() {
  const { selectedAccountId, selectedAccount, loading: accountLoading } = useSelectedAccount();
  const [review, setReview] = useState<DailyReview | null>(null);
  const [history, setHistory] = useState<DailyReview[]>([]);
  const [selectedDate, setSelectedDate] = useState(todayIso());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const metrics = review?.metrics_snapshot;
  const findings = review?.deterministic_findings;
  const aiFallbackReason = review?.model_metadata?.ai_enabled === false ? review.model_metadata.fallback_reason : null;
  const aiProvider = review?.model_metadata?.provider || "AI";

  const journalMissing = useMemo(() => {
    const missing = metrics?.journal?.missing;
    if (!missing) return [];
    return Object.entries(missing).filter(([, count]) => count > 0);
  }, [metrics]);

  async function load(dateValue = selectedDate) {
    if (!selectedAccountId) return;
    try {
      setError(null);
      const [currentReview, reviewHistory] = await Promise.all([
        api.dailyReview(selectedAccountId, dateValue),
        api.dailyReviewHistory(selectedAccountId)
      ]);
      setReview(currentReview);
      setHistory(reviewHistory);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review");
    }
  }

  async function generate(regenerate = false) {
    if (!selectedAccountId) return;
    setLoading(true);
    setError(null);
    try {
      const nextReview = regenerate
        ? await api.regenerateDailyReview(selectedAccountId, selectedDate)
        : await api.createDailyReview(selectedAccountId, selectedDate);
      setReview(nextReview);
      setHistory(await api.dailyReviewHistory(selectedAccountId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create review");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(selectedDate);
  }, [selectedAccountId, selectedDate]);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Daily Review</p>
          <h2 className="page-title">Coach report</h2>
          {selectedAccount && <p className="mt-2 text-sm text-zinc-400">Account {selectedAccount.account_number}</p>}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative">
            <CalendarDays className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} aria-hidden />
            <input className="input-field w-full pl-9 sm:w-44" type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
          </label>
          <button className="secondary-action" onClick={() => generate(true)} disabled={loading || !selectedAccountId}>
            <ListRestart size={16} aria-hidden />
            Regenerate
          </button>
          <button className="primary-action" onClick={() => generate(false)} disabled={loading || !selectedAccountId}>
            <RefreshCw size={16} aria-hidden />
            Generate
          </button>
        </div>
      </header>

      {error && <p className="mt-4 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-bad">{error}</p>}

      {!accountLoading && !selectedAccountId && (
        <EmptyState title="No account connected" body="Daily reviews need a persisted MT5 account, synced trades, and rule data before a report can be generated." />
      )}

      {selectedAccountId && !review && (
        <EmptyState title="No review for this date" body="Generate a review after trades, journal fields, and rule checks are synced. If there were no trades, the report will still record a no-trade day." />
      )}

      {review && (
        <>
          <section className="mt-5 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div className="panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="kicker">Discipline Score</p>
                  <p className="mt-3 text-5xl font-semibold text-zinc-50">{review.discipline_score}</p>
                </div>
                <div className="grid h-12 w-12 place-items-center rounded-xl bg-accent/15 text-accent">
                  <ShieldCheck size={22} aria-hidden />
                </div>
              </div>
              <p className="mt-4 text-sm text-zinc-400">{findings?.score_interpretation || "Score calculated from stored rule and journal data."}</p>
              {aiFallbackReason && (
                <p className="mt-4 rounded-lg border border-amber-300/20 bg-amber-400/10 p-3 text-sm text-warn">
                  {aiFallbackReason === "ENABLE_AI=false"
                    ? "AI disabled. Deterministic review is active."
                    : `${aiProvider} fallback: ${aiFallbackReason}. Deterministic review is active.`}
                </p>
              )}
            </div>

            <div className="panel grid gap-4 p-5 md:grid-cols-4">
              <Metric label="PnL" value={metrics?.realized_pnl || review.pnl} />
              <Metric label="Trades" value={String(metrics?.total_trades ?? review.trade_count)} />
              <Metric label="Wins / Losses" value={`${metrics?.wins ?? 0} / ${metrics?.losses ?? 0}`} />
              <Metric label="Win Rate" value={numberText(metrics?.win_rate ?? review.win_rate, "%")} />
              <Metric label="Avg Winner" value={metrics?.average_winner || "N/A"} />
              <Metric label="Avg Loser" value={metrics?.average_loser || "N/A"} />
              <Metric label="Profit Factor" value={numberText(metrics?.profit_factor)} />
              <Metric label="Avg R" value={numberText(metrics?.average_r_multiple)} />
            </div>
          </section>

          <section className="mt-4 grid gap-4 lg:grid-cols-3">
            <ReviewCard
              icon={<CheckCircle2 size={18} aria-hidden />}
              title="Strongest positive behavior"
              body={findings?.strongest_positive_behavior || "No positive behavior detected from stored data."}
            />
            <ReviewCard
              icon={<AlertTriangle size={18} aria-hidden />}
              title="Biggest risk pattern"
              body={findings?.biggest_mistake_or_risk_pattern || "No major risk pattern was detected from stored data."}
            />
            <ReviewCard
              icon={<TrendingUp size={18} aria-hidden />}
              title="Symbols / setups / emotions"
              body={[
                `Symbols: ${listText(metrics?.most_traded_symbols)}`,
                `Setups: ${listText(metrics?.setups_used)}`,
                `Emotions: ${listText(metrics?.emotions)}`
              ].join("\n")}
            />
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="panel p-5">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent">
                  <Bot size={18} aria-hidden />
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-50">Review for {review.review_date}</h3>
                  <p className="text-sm text-zinc-400">Generated {review.generated_at ? new Date(review.generated_at).toLocaleString() : "recently"}</p>
                </div>
              </div>
              <p className="mt-5 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{review.ai_narrative || review.ai_summary || "No narrative generated."}</p>
            </div>

            <div className="space-y-4">
              <div className="panel p-5">
                <p className="kicker">Tomorrow's plan</p>
                <div className="mt-4 space-y-3">
                  {(findings?.tomorrows_plan || []).slice(0, 3).map((item) => (
                    <p key={item} className="rounded-lg border border-line bg-elevated p-3 text-sm leading-6 text-zinc-300">{item}</p>
                  ))}
                </div>
              </div>
              <div className="panel p-5">
                <p className="kicker">Rule checks</p>
                <p className="mt-3 text-sm text-zinc-300">
                  {metrics?.rule_violations?.total ?? 0} violation(s), {metrics?.blocked_pre_trade_attempts ?? 0} blocked pre-trade attempt(s).
                </p>
                <p className="mt-3 text-sm text-zinc-400">{listText(metrics?.rule_violations?.by_code)}</p>
              </div>
              <div className="panel p-5">
                <p className="kicker">Journal status</p>
                {journalMissing.length === 0 ? (
                  <p className="mt-3 text-sm text-zinc-300">Journal fields are complete for reviewed trades.</p>
                ) : (
                  <p className="mt-3 text-sm text-zinc-300">
                    Journal incomplete: {journalMissing.map(([field, count]) => `${field} (${count})`).join(", ")}.
                  </p>
                )}
              </div>
            </div>
          </section>

          <section className="mt-4 panel p-5">
            <p className="kicker">Score breakdown</p>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {review.discipline_breakdown.map((factor) => (
                <div key={factor.code} className="panel-soft p-4">
                  <div className="flex items-start justify-between gap-3">
                    <h4 className="text-sm font-semibold text-zinc-100">{factor.label}</h4>
                    <span className="rounded bg-red-500/10 px-2 py-1 text-xs font-semibold text-bad">-{factor.penalty}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">{factor.reason}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      <section className="mt-4 panel p-5">
        <p className="kicker">Review history</p>
        {history.length === 0 ? (
          <p className="muted-copy mt-3">No saved daily reviews yet.</p>
        ) : (
          <div className="mt-4 grid gap-2">
            {history.map((item) => (
              <button
                key={item.id}
                className="panel-soft flex items-center justify-between gap-3 p-3 text-left hover:border-accent"
                onClick={() => setSelectedDate(item.review_date)}
              >
                <span>
                  <span className="block text-sm font-semibold text-zinc-100">{item.review_date}</span>
                  <span className="text-xs text-zinc-500">Trades {item.trade_count} | PnL {item.pnl}</span>
                </span>
                <span className="rounded-lg bg-accent/10 px-2.5 py-1 text-sm font-semibold text-accent">{item.discipline_score}</span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-soft p-4">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-zinc-50">{value}</p>
    </div>
  );
}

function ReviewCard({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="panel p-5">
      <div className="flex items-center gap-2 text-accent">
        {icon}
        <p className="kicker">{title}</p>
      </div>
      <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{body}</p>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <section className="panel mt-5 p-5">
      <h3 className="font-semibold text-zinc-50">{title}</h3>
      <p className="muted-copy mt-2">{body}</p>
    </section>
  );
}

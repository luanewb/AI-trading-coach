"use client";

import { useEffect, useState } from "react";
import { Bot, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { DailyReview } from "@/lib/types";

export default function DailyReviewPage() {
  const [review, setReview] = useState<DailyReview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      setReview(await api.dailyReview());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review");
    }
  }

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setReview(await api.createDailyReview());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create review");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="pb-20">
      <header className="flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Daily Review</p>
          <h2 className="mt-1 text-3xl font-semibold">Coach report</h2>
        </div>
        <button className="flex h-10 items-center gap-2 bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50" onClick={generate} disabled={loading}>
          <RefreshCw size={16} aria-hidden />
          Generate
        </button>
      </header>

      {error && <p className="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-bad">{error}</p>}

      <section className="mt-5 border border-line bg-white p-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded bg-ink text-white">
            <Bot size={18} aria-hidden />
          </div>
          <div>
            <h3 className="font-semibold">{review ? `Review for ${review.review_date}` : "No review yet"}</h3>
            {review && <p className="text-sm text-zinc-600">PnL {review.pnl} | Trades {review.trade_count} | Win rate {Number(review.win_rate).toFixed(1)}%</p>}
          </div>
        </div>

        {review ? (
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <ReviewBlock title="AI Summary" body={review.ai_summary} />
            <ReviewBlock title="Mistakes" body={review.mistakes} />
            <ReviewBlock title="Best Trade" body={review.best_trade} />
            <ReviewBlock title="Worst Trade" body={review.worst_trade} />
            <div className="lg:col-span-2">
              <ReviewBlock title="Action Plan" body={review.action_plan} />
            </div>
          </div>
        ) : (
          <p className="mt-5 text-sm text-zinc-600">Generate a review after trades are synced from MT5.</p>
        )}
      </section>
    </div>
  );
}

function ReviewBlock({ title, body }: { title: string; body: string | null }) {
  return (
    <div className="border border-line p-4">
      <h4 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h4>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{body || "-"}</p>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Bot, RefreshCw } from "lucide-react";
import { useSelectedAccount } from "@/components/AccountContext";
import { api } from "@/lib/api";
import type { DailyReview } from "@/lib/types";

export default function DailyReviewPage() {
  const { selectedAccountId, selectedAccount } = useSelectedAccount();
  const [review, setReview] = useState<DailyReview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      setReview(await api.dailyReview(selectedAccountId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review");
    }
  }

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setReview(await api.createDailyReview(selectedAccountId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create review");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [selectedAccountId]);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Daily Review</p>
          <h2 className="page-title">Coach report</h2>
          {selectedAccount && <p className="mt-2 text-sm text-zinc-400">Account {selectedAccount.account_number}</p>}
        </div>
        <button className="primary-action" onClick={generate} disabled={loading}>
          <RefreshCw size={16} aria-hidden />
          Generate
        </button>
      </header>

      {error && <p className="mt-4 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-bad">{error}</p>}

      <section className="panel mt-5 p-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent">
            <Bot size={18} aria-hidden />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-50">{review ? `Review for ${review.review_date}` : "No review yet"}</h3>
            {review && <p className="text-sm text-zinc-400">PnL {review.pnl} | Trades {review.trade_count} | Win rate {Number(review.win_rate).toFixed(1)}%</p>}
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
          <p className="muted-copy mt-5">Generate a review after trades are synced from MT5.</p>
        )}
      </section>
    </div>
  );
}

function ReviewBlock({ title, body }: { title: string; body: string | null }) {
  return (
    <div className="panel-soft p-4">
      <h4 className="kicker">{title}</h4>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{body || "-"}</p>
    </div>
  );
}

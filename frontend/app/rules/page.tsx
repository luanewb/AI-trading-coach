"use client";

import { useEffect, useState } from "react";
import { PlayCircle, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { RiskRule } from "@/lib/types";

const emptyRule: Omit<RiskRule, "id" | "account_id"> = {
  max_trades_per_day: 5,
  max_daily_loss_percent: "5",
  max_total_loss_percent: "10",
  max_consecutive_losses: 3,
  cooldown_minutes_after_loss: 30,
  max_lot: "1",
  allow_trading: true
};

export default function RulesPage() {
  const [rule, setRule] = useState(emptyRule);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.rules()
      .then(({ id, account_id, ...data }) => setRule(data))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load rules"));
  }, []);

  async function save() {
    setStatus(null);
    setError(null);
    try {
      await api.updateRules(rule);
      setStatus("Rules saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save rules");
    }
  }

  async function evaluate() {
    setStatus(null);
    setError(null);
    try {
      const result = await api.evaluateRules();
      setStatus(`Evaluation: ${result.status}. Alerts: ${result.alerts_created.join(", ") || "none"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to evaluate rules");
    }
  }

  return (
    <div className="pb-20">
      <header className="border-b border-line pb-5">
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Rules</p>
        <h2 className="mt-1 text-3xl font-semibold">Risk configuration</h2>
      </header>

      <section className="mt-5 grid gap-4 border border-line bg-white p-5 md:grid-cols-2 xl:grid-cols-3">
        <label className="space-y-2 text-sm font-medium">
          <span>Max trades/day</span>
          <input className="h-11 w-full border border-line px-3" type="number" min={1} value={rule.max_trades_per_day} onChange={(event) => setRule({ ...rule, max_trades_per_day: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium">
          <span>Max daily loss %</span>
          <input className="h-11 w-full border border-line px-3" type="number" step="0.1" value={rule.max_daily_loss_percent} onChange={(event) => setRule({ ...rule, max_daily_loss_percent: event.target.value })} />
        </label>
        <label className="space-y-2 text-sm font-medium">
          <span>Max total loss %</span>
          <input className="h-11 w-full border border-line px-3" type="number" step="0.1" value={rule.max_total_loss_percent} onChange={(event) => setRule({ ...rule, max_total_loss_percent: event.target.value })} />
        </label>
        <label className="space-y-2 text-sm font-medium">
          <span>Max consecutive losses</span>
          <input className="h-11 w-full border border-line px-3" type="number" min={1} value={rule.max_consecutive_losses} onChange={(event) => setRule({ ...rule, max_consecutive_losses: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium">
          <span>Cooldown minutes</span>
          <input className="h-11 w-full border border-line px-3" type="number" min={0} value={rule.cooldown_minutes_after_loss} onChange={(event) => setRule({ ...rule, cooldown_minutes_after_loss: Number(event.target.value) })} />
        </label>
        <label className="space-y-2 text-sm font-medium">
          <span>Max lot</span>
          <input className="h-11 w-full border border-line px-3" type="number" step="0.01" value={rule.max_lot} onChange={(event) => setRule({ ...rule, max_lot: event.target.value })} />
        </label>
        <label className="flex h-11 items-center gap-3 text-sm font-medium">
          <input className="h-5 w-5 accent-ink" type="checkbox" checked={rule.allow_trading} onChange={(event) => setRule({ ...rule, allow_trading: event.target.checked })} />
          Allow trading at platform level
        </label>
      </section>

      <div className="mt-5 flex flex-wrap gap-3">
        <button className="flex h-10 items-center gap-2 bg-ink px-4 text-sm font-semibold text-white" onClick={save}>
          <Save size={16} aria-hidden />
          Save Rules
        </button>
        <button className="flex h-10 items-center gap-2 border border-line bg-white px-4 text-sm font-semibold" onClick={evaluate}>
          <PlayCircle size={16} aria-hidden />
          Evaluate Now
        </button>
      </div>
      {status && <p className="mt-4 border border-green-200 bg-green-50 p-3 text-sm text-good">{status}</p>}
      {error && <p className="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-bad">{error}</p>}
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { Save, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/types";

function formatMoney(value: string | number | null) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
}

export default function JournalPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filters, setFilters] = useState({ symbol: "", setup: "", result: "", trade_date: "" });
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const text = params.toString();
    return text ? `?${text}` : "";
  }, [filters]);

  async function load() {
    try {
      setError(null);
      setTrades(await api.trades(query));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trades");
    }
  }

  useEffect(() => {
    void load();
  }, [query]);

  async function save(trade: Trade) {
    setSavingId(trade.id);
    try {
      await api.updateTrade(trade.id, {
        setup_name: trade.setup_name,
        emotion: trade.emotion,
        mistake_tags: trade.mistake_tags,
        notes: trade.notes
      } as Partial<Trade>);
      await load();
    } finally {
      setSavingId(null);
    }
  }

  function updateTrade(id: number, patch: Partial<Trade>) {
    setTrades((current) => current.map((trade) => (trade.id === id ? { ...trade, ...patch } : trade)));
  }

  return (
    <div className="pb-20">
      <header className="border-b border-line pb-5">
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Journal</p>
        <h2 className="mt-1 text-3xl font-semibold">Trades and notes</h2>
      </header>

      <section className="mt-5 grid gap-3 border border-line bg-white p-4 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
        <input className="h-10 border border-line px-3" placeholder="Symbol" value={filters.symbol} onChange={(event) => setFilters({ ...filters, symbol: event.target.value })} />
        <input className="h-10 border border-line px-3" placeholder="Setup" value={filters.setup} onChange={(event) => setFilters({ ...filters, setup: event.target.value })} />
        <select className="h-10 border border-line px-3" value={filters.result} onChange={(event) => setFilters({ ...filters, result: event.target.value })}>
          <option value="">Win/Loss</option>
          <option value="win">Win</option>
          <option value="loss">Loss</option>
        </select>
        <input className="h-10 border border-line px-3" type="date" value={filters.trade_date} onChange={(event) => setFilters({ ...filters, trade_date: event.target.value })} />
        <button className="flex h-10 items-center justify-center gap-2 bg-ink px-4 text-sm font-semibold text-white" onClick={load}>
          <Search size={16} aria-hidden />
          Apply
        </button>
      </section>

      {error && <p className="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-bad">{error}</p>}

      <section className="mt-5 overflow-x-auto border border-line bg-white">
        <table className="min-w-[1100px] w-full border-collapse text-sm">
          <thead className="bg-paper text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="p-3">Ticket</th>
              <th className="p-3">Symbol</th>
              <th className="p-3">Type</th>
              <th className="p-3">Lot</th>
              <th className="p-3">PnL</th>
              <th className="p-3">R</th>
              <th className="p-3">Setup</th>
              <th className="p-3">Emotion</th>
              <th className="p-3">Mistakes</th>
              <th className="p-3">Notes</th>
              <th className="p-3">Save</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr key={trade.id} className="border-t border-line align-top">
                <td className="p-3 font-medium">{trade.ticket}</td>
                <td className="p-3">{trade.symbol}</td>
                <td className="p-3">{trade.order_type}</td>
                <td className="p-3">{trade.lot}</td>
                <td className={`p-3 font-semibold ${Number(trade.profit) >= 0 ? "text-good" : "text-bad"}`}>{formatMoney(trade.profit)}</td>
                <td className="p-3">{trade.r_multiple ?? "-"}</td>
                <td className="p-3"><input className="h-9 w-36 border border-line px-2" value={trade.setup_name ?? ""} onChange={(event) => updateTrade(trade.id, { setup_name: event.target.value })} /></td>
                <td className="p-3"><input className="h-9 w-32 border border-line px-2" value={trade.emotion ?? ""} onChange={(event) => updateTrade(trade.id, { emotion: event.target.value })} /></td>
                <td className="p-3">
                  <input
                    className="h-9 w-44 border border-line px-2"
                    value={(trade.mistake_tags || []).join(", ")}
                    onChange={(event) => updateTrade(trade.id, { mistake_tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean) })}
                  />
                </td>
                <td className="p-3"><textarea className="h-16 w-56 resize-none border border-line p-2" value={trade.notes ?? ""} onChange={(event) => updateTrade(trade.id, { notes: event.target.value })} /></td>
                <td className="p-3">
                  <button className="grid h-9 w-9 place-items-center bg-ink text-white disabled:opacity-50" onClick={() => save(trade)} disabled={savingId === trade.id} aria-label="Save trade">
                    <Save size={16} aria-hidden />
                  </button>
                </td>
              </tr>
            ))}
            {!trades.length && (
              <tr>
                <td className="p-6 text-zinc-600" colSpan={11}>No trades match the current filters.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

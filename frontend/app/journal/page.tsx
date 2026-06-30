"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, Save, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/types";

const PAGE_SIZE = 20;

function formatMoney(value: string | number | null) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
}

function formatOrderType(value: string) {
  const normalized = value.toUpperCase();
  if (normalized === "ORDER_TYPE_BUY" || normalized === "BUY") return "Buy";
  if (normalized === "ORDER_TYPE_SELL" || normalized === "SELL") return "Sell";
  return value.replace(/^ORDER_TYPE_/i, "").toLowerCase().replace(/^\w/, (letter) => letter.toUpperCase());
}

function normalizeScreenshotUrl(value: string | null | undefined) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

export default function JournalPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filters, setFilters] = useState({ symbol: "", setup: "", result: "", trade_date: "" });
  const [page, setPage] = useState(1);
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
    setPage(1);
    void load();
  }, [query]);

  async function save(trade: Trade) {
    setSavingId(trade.id);
    try {
      await api.updateTrade(trade.id, {
        setup_name: trade.setup_name,
        emotion: trade.emotion,
        mistake_tags: trade.mistake_tags,
        notes: trade.notes,
        before_entry_image_url: trade.before_entry_image_url,
        after_exit_image_url: trade.after_exit_image_url,
        analysis_image_url: trade.analysis_image_url
      } as Partial<Trade>);
      await load();
    } finally {
      setSavingId(null);
    }
  }

  function updateTrade(id: number, patch: Partial<Trade>) {
    setTrades((current) => current.map((trade) => (trade.id === id ? { ...trade, ...patch } : trade)));
  }

  const pageCount = Math.max(1, Math.ceil(trades.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visibleTrades = trades.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const firstRow = trades.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0;
  const lastRow = Math.min(currentPage * PAGE_SIZE, trades.length);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Journal</p>
          <h2 className="page-title">Trades and notes</h2>
        </div>
      </header>

      <section className="panel mt-5 grid gap-3 p-4 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
        <input className="input-field" placeholder="Symbol" value={filters.symbol} onChange={(event) => setFilters({ ...filters, symbol: event.target.value })} />
        <input className="input-field" placeholder="Setup" value={filters.setup} onChange={(event) => setFilters({ ...filters, setup: event.target.value })} />
        <select className="input-field" value={filters.result} onChange={(event) => setFilters({ ...filters, result: event.target.value })}>
          <option value="">Win/Loss</option>
          <option value="win">Win</option>
          <option value="loss">Loss</option>
        </select>
        <input className="input-field" type="date" value={filters.trade_date} onChange={(event) => setFilters({ ...filters, trade_date: event.target.value })} />
        <button className="primary-action" onClick={load}>
          <Search size={16} aria-hidden />
          Apply
        </button>
      </section>

      {error && <p className="mt-4 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-bad">{error}</p>}

      <section className="panel mt-5 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="min-w-[1420px] w-full border-collapse text-sm">
          <thead className="bg-paper text-left text-xs uppercase tracking-[0.14em] text-zinc-500">
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
              <th className="p-3">Screenshots</th>
              <th className="p-3">Save</th>
            </tr>
          </thead>
          <tbody>
            {visibleTrades.map((trade) => (
              <tr key={trade.id} className="border-t border-line align-top text-zinc-300 hover:bg-elevated/60">
                <td className="p-3 font-medium text-zinc-100">{trade.ticket}</td>
                <td className="p-3 font-semibold text-zinc-50">{trade.symbol}</td>
                <td className="p-3">{formatOrderType(trade.order_type)}</td>
                <td className="p-3 tabular-nums">{trade.lot}</td>
                <td className={`p-3 font-semibold ${Number(trade.profit) >= 0 ? "text-good" : "text-bad"}`}>{formatMoney(trade.profit)}</td>
                <td className="p-3 tabular-nums">{trade.r_multiple ?? "-"}</td>
                <td className="p-3"><input className="input-field h-9 w-36" value={trade.setup_name ?? ""} onChange={(event) => updateTrade(trade.id, { setup_name: event.target.value })} /></td>
                <td className="p-3"><input className="input-field h-9 w-32" value={trade.emotion ?? ""} onChange={(event) => updateTrade(trade.id, { emotion: event.target.value })} /></td>
                <td className="p-3">
                  <input
                    className="input-field h-9 w-44"
                    value={(trade.mistake_tags || []).join(", ")}
                    onChange={(event) => updateTrade(trade.id, { mistake_tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean) })}
                  />
                </td>
                <td className="p-3"><textarea className="textarea-field h-16 w-56 resize-none" value={trade.notes ?? ""} onChange={(event) => updateTrade(trade.id, { notes: event.target.value })} /></td>
                <td className="p-3">
                  <ScreenshotLinks trade={trade} onChange={(patch) => updateTrade(trade.id, patch)} />
                </td>
                <td className="p-3">
                  <button className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-slate-950 disabled:opacity-50" onClick={() => save(trade)} disabled={savingId === trade.id} aria-label="Save trade">
                    <Save size={16} aria-hidden />
                  </button>
                </td>
              </tr>
            ))}
            {!trades.length && (
              <tr>
                <td className="p-6 text-zinc-400" colSpan={12}>No trades match the current filters.</td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
        {trades.length > 0 && (
          <div className="flex flex-col gap-3 border-t border-line p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-zinc-400">
              Showing {firstRow}-{lastRow} of {trades.length} trades · {PAGE_SIZE} per page
            </p>
            <div className="flex items-center gap-2">
              <button
                className="secondary-action h-9 px-3"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={currentPage === 1}
              >
                <ChevronLeft size={16} aria-hidden />
                Prev
              </button>
              <span className="rounded-lg border border-line bg-elevated px-3 py-2 text-sm font-semibold text-zinc-200">
                Page {currentPage} / {pageCount}
              </span>
              <button
                className="secondary-action h-9 px-3"
                onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
                disabled={currentPage === pageCount}
              >
                Next
                <ChevronRight size={16} aria-hidden />
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ScreenshotLinks({ trade, onChange }: { trade: Trade; onChange: (patch: Partial<Trade>) => void }) {
  return (
    <div className="grid w-64 gap-2">
      <ScreenshotLinkInput
        label="Before entry"
        value={trade.before_entry_image_url}
        onChange={(value) => onChange({ before_entry_image_url: value })}
      />
      <ScreenshotLinkInput
        label="After exit"
        value={trade.after_exit_image_url}
        onChange={(value) => onChange({ after_exit_image_url: value })}
      />
      <ScreenshotLinkInput
        label="Analysis"
        value={trade.analysis_image_url}
        onChange={(value) => onChange({ analysis_image_url: value })}
      />
    </div>
  );
}

function ScreenshotLinkInput({ label, value, onChange }: { label: string; value: string | null; onChange: (value: string) => void }) {
  const url = normalizeScreenshotUrl(value);
  return (
    <label className="grid grid-cols-[76px_1fr_32px] items-center gap-2 text-[11px] text-zinc-500">
      <span className="whitespace-nowrap">{label}</span>
      <input
        className="input-field h-8 min-w-0 px-2 text-xs"
        placeholder="tradingview.com/x/..."
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
      <a
        className={`grid h-8 w-8 place-items-center rounded-lg border border-line bg-elevated text-zinc-300 transition hover:border-accent hover:text-accent ${url ? "" : "pointer-events-none opacity-35"}`}
        href={url || undefined}
        target="_blank"
        rel="noreferrer"
        aria-label={`Open ${label} screenshot`}
        title={`Open ${label}`}
      >
        <ExternalLink size={14} aria-hidden />
      </a>
    </label>
  );
}

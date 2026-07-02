"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CalendarClock, RefreshCcw, Save, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { NewsRestrictionSettings, NewsRestrictionStatus, NewsRestrictedEvent, NewsTradeAction, TradeRestrictionLog } from "@/lib/types";

const actions: Array<{ value: NewsTradeAction; label: string }> = [
  { value: "new_order", label: "New orders" },
  { value: "manual_close", label: "Manual closes" },
  { value: "modify_sl_tp", label: "SL/TP changes" },
  { value: "pending_order", label: "Pending orders" }
];

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short"
  }).format(new Date(value));
}

function duration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "-";
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes}m ${remainder}s`;
}

function windowText(event: NewsRestrictedEvent) {
  return `${formatDate(event.window_start)} - ${formatDate(event.window_end)}`;
}

function statusTone(status: NewsRestrictionStatus | null) {
  if (!status) return "bg-elevated text-zinc-300";
  if (status.should_block) return "bg-red-500/15 text-bad";
  if (status.should_warn) return "bg-amber-400/15 text-warn";
  return "bg-emerald-400/15 text-good";
}

export default function NewsRestrictionsPage() {
  const [settings, setSettings] = useState<NewsRestrictionSettings | null>(null);
  const [draft, setDraft] = useState<NewsRestrictionSettings | null>(null);
  const [status, setStatus] = useState<NewsRestrictionStatus | null>(null);
  const [events, setEvents] = useState<NewsRestrictedEvent[]>([]);
  const [logs, setLogs] = useState<TradeRestrictionLog[]>([]);
  const [symbol, setSymbol] = useState("XAUUSD");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  async function load(nextSymbol = symbol) {
    setLoading(true);
    setError(null);
    try {
      const [nextSettings, nextStatus, nextEvents, nextLogs] = await Promise.all([
        api.newsSettings(),
        api.newsRestrictionStatus(nextSymbol),
        api.upcomingRestrictedNewsEvents(),
        api.newsRestrictionLogs()
      ]);
      setSettings(nextSettings);
      setDraft(nextSettings);
      setStatus(nextStatus);
      setEvents(nextEvents);
      setLogs(nextLogs);
    } catch {
      setError("News restriction data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const countdown = useMemo(() => {
    if (!status) return "-";
    const base = status.is_restricted_now ? status.seconds_until_restriction_end : status.seconds_until_event;
    return duration(base === null ? null : Math.max(0, base - tick));
  }, [status, tick]);

  async function saveSettings() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateNewsSettings(draft);
      setSettings(updated);
      setDraft(updated);
      await load(symbol);
    } catch {
      setError("Settings could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  function toggleAction(action: NewsTradeAction) {
    if (!draft) return;
    const current = new Set(draft.blocked_actions);
    if (current.has(action)) current.delete(action);
    else current.add(action);
    setDraft({ ...draft, blocked_actions: Array.from(current) as NewsTradeAction[] });
  }

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">News Restrictions</p>
          <h2 className="page-title">FTMO restricted news guard</h2>
        </div>
        <button className="secondary-action" type="button" onClick={() => load(symbol)} disabled={loading}>
          <RefreshCcw size={16} aria-hidden />
          Refresh
        </button>
      </header>

      {error && (
        <div className="mt-5 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-bad">
          {error}
        </div>
      )}

      <section className="panel mt-5 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <div className={`grid h-11 w-11 place-items-center rounded-xl ${status?.should_block ? "bg-red-500/15 text-bad" : "bg-accent/15 text-accent"}`}>
              {status?.is_restricted_now ? <ShieldAlert size={20} aria-hidden /> : <ShieldCheck size={20} aria-hidden />}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-zinc-50">{status?.is_restricted_now ? "Restricted now" : "Trading allowed"}</h3>
              <p className="mt-1 text-sm text-zinc-400">
                {status?.current_event?.title || status?.upcoming_event?.title || "No restricted USD event in the loaded window."}
              </p>
            </div>
          </div>
          <span className={`status-pill ${statusTone(status)}`}>
            {status?.should_block ? "Blocking" : status?.should_warn ? "Warning" : "Allowed"} · {countdown}
          </span>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <label className="grid gap-2 text-sm">
            <span className="text-zinc-400">Symbol</span>
            <input className="input-field" value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} onBlur={() => load(symbol)} />
          </label>
          <div className="panel-soft p-3">
            <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Current mode</p>
            <p className="mt-2 font-semibold text-zinc-50">{status?.effective_mode || settings?.enforcement_mode || "-"}</p>
          </div>
          <div className="panel-soft p-3">
            <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Restricted until</p>
            <p className="mt-2 font-semibold text-zinc-50">{formatDate(status?.restricted_until)}</p>
          </div>
        </div>
      </section>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="panel overflow-hidden">
          <div className="flex items-center gap-3 border-b border-line p-4">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent">
              <CalendarClock size={18} aria-hidden />
            </div>
            <div>
              <h3 className="font-semibold text-zinc-50">Upcoming USD restricted events</h3>
              <p className="text-sm text-zinc-400">Times are displayed in your local timezone.</p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full border-collapse text-sm">
              <thead className="bg-paper text-left text-xs uppercase tracking-[0.14em] text-zinc-500">
                <tr>
                  <th className="p-3">Event</th>
                  <th className="p-3">Time</th>
                  <th className="p-3">Window</th>
                  <th className="p-3">Impact</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="border-t border-line text-zinc-300">
                    <td className="p-3 font-semibold text-zinc-50">{event.title}</td>
                    <td className="p-3 whitespace-nowrap">{formatDate(event.scheduled_at)}</td>
                    <td className="p-3">{windowText(event)}</td>
                    <td className="p-3"><span className="status-pill bg-amber-400/15 text-warn">{event.impact || "restricted"}</span></td>
                  </tr>
                ))}
                {!events.length && (
                  <tr>
                    <td className="p-6 text-zinc-400" colSpan={4}>No upcoming restricted USD events loaded.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-zinc-50">Settings</h3>
              <p className="text-sm text-zinc-400">Default window is 2 minutes before and after the event.</p>
            </div>
            <button className="primary-action" type="button" onClick={saveSettings} disabled={!draft || saving}>
              <Save size={16} aria-hidden />
              Save
            </button>
          </div>

          {draft && (
            <div className="mt-5 grid gap-4">
              <label className="grid gap-2 text-sm">
                <span className="text-zinc-400">Account type</span>
                <select className="input-field" value={draft.account_type} onChange={(event) => setDraft({ ...draft, account_type: event.target.value as NewsRestrictionSettings["account_type"] })}>
                  <option value="standard_funded">Standard funded</option>
                  <option value="swing">Swing</option>
                  <option value="evaluation">Evaluation</option>
                </select>
              </label>
              <label className="grid gap-2 text-sm">
                <span className="text-zinc-400">Enforcement mode</span>
                <select className="input-field" value={draft.enforcement_mode} onChange={(event) => setDraft({ ...draft, enforcement_mode: event.target.value as NewsRestrictionSettings["enforcement_mode"] })}>
                  <option value="block_actions">Block actions</option>
                  <option value="warn_only">Warn only</option>
                  <option value="disabled">Disabled</option>
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="grid gap-2 text-sm">
                  <span className="text-zinc-400">Minutes before</span>
                  <input className="input-field" type="number" min={0} max={120} value={draft.minutes_before} onChange={(event) => setDraft({ ...draft, minutes_before: Number(event.target.value) })} />
                </label>
                <label className="grid gap-2 text-sm">
                  <span className="text-zinc-400">Minutes after</span>
                  <input className="input-field" type="number" min={0} max={120} value={draft.minutes_after} onChange={(event) => setDraft({ ...draft, minutes_after: Number(event.target.value) })} />
                </label>
              </div>
              <label className="flex items-center gap-3 text-sm text-zinc-300">
                <input className="h-4 w-4 accent-teal-300" type="checkbox" checked={draft.apply_usd_only} onChange={(event) => setDraft({ ...draft, apply_usd_only: event.target.checked })} />
                Apply USD-sensitive symbol mapping
              </label>
              <div className="grid gap-2">
                <p className="text-sm text-zinc-400">Blocked actions</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {actions.map((action) => (
                    <label key={action.value} className="flex items-center gap-2 rounded-lg border border-line bg-elevated p-3 text-sm text-zinc-300">
                      <input className="h-4 w-4 accent-teal-300" type="checkbox" checked={draft.blocked_actions.includes(action.value)} onChange={() => toggleAction(action.value)} />
                      {action.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="panel mt-5 overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line p-4">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-amber-400/15 text-warn">
            <AlertTriangle size={18} aria-hidden />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-50">Restriction logs</h3>
            <p className="text-sm text-zinc-400">Warnings and blocks recorded by backend trade guard checks.</p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[820px] w-full border-collapse text-sm">
            <thead className="bg-paper text-left text-xs uppercase tracking-[0.14em] text-zinc-500">
              <tr>
                <th className="p-3">Time</th>
                <th className="p-3">Symbol</th>
                <th className="p-3">Action</th>
                <th className="p-3">Mode</th>
                <th className="p-3">Event</th>
                <th className="p-3">Result</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-t border-line text-zinc-300">
                  <td className="p-3 whitespace-nowrap">{formatDate(log.created_at)}</td>
                  <td className="p-3 font-semibold text-zinc-50">{log.symbol}</td>
                  <td className="p-3">{log.action}</td>
                  <td className="p-3">{log.mode}</td>
                  <td className="p-3">{log.event_title || "-"}</td>
                  <td className="p-3"><span className={`status-pill ${log.blocked ? "bg-red-500/15 text-bad" : "bg-amber-400/15 text-warn"}`}>{log.blocked ? "Blocked" : "Warned"}</span></td>
                </tr>
              ))}
              {!logs.length && (
                <tr>
                  <td className="p-6 text-zinc-400" colSpan={6}>No news restriction logs yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

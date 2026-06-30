import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import type { Trade } from "@/lib/types";

function money(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function compactMoney(value: number) {
  const sign = value < 0 ? "-" : "";
  return `${sign}${money(Math.abs(value))}`;
}

function tradeDate(trade: Trade) {
  const raw = trade.close_time || trade.open_time;
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function addMonths(date: Date, offset: number) {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

export function parseCalendarMonth(value: string | string[] | undefined, fallback: Date) {
  const month = Array.isArray(value) ? value[0] : value;
  const match = month?.match(/^(\d{4})-(\d{2})$/);
  if (!match) return new Date(fallback.getFullYear(), fallback.getMonth(), 1);
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return new Date(fallback.getFullYear(), fallback.getMonth(), 1);
  return new Date(year, monthIndex, 1);
}

export function latestTradeDate(trades: Trade[]) {
  const dates = trades.map(tradeDate).filter((date): date is Date => Boolean(date));
  if (!dates.length) return new Date();
  return dates.reduce((latest, date) => (date.getTime() > latest.getTime() ? date : latest), dates[0]);
}

function summarizeTradesByDay(trades: Trade[]) {
  const summaries = new Map<string, { pnl: number; trades: number }>();
  trades.forEach((trade) => {
    const date = tradeDate(trade);
    if (!date) return;
    const key = dateKey(date);
    const current = summaries.get(key) || { pnl: 0, trades: 0 };
    current.pnl += Number(trade.profit || 0);
    current.trades += 1;
    summaries.set(key, current);
  });
  return summaries;
}

export function TradingCalendar({ trades, activeMonth, basePath = "/calendar" }: { trades: Trade[]; activeMonth: Date; basePath?: string }) {
  const daily = summarizeTradesByDay(trades);
  const monthStart = new Date(activeMonth.getFullYear(), activeMonth.getMonth(), 1);
  const firstGridDate = new Date(monthStart);
  firstGridDate.setDate(1 - monthStart.getDay());
  const monthEnd = new Date(activeMonth.getFullYear(), activeMonth.getMonth() + 1, 0);
  const gridDays = Math.ceil((monthEnd.getDate() + monthStart.getDay()) / 7) * 7;
  const days = Array.from({ length: gridDays }, (_, index) => {
    const day = new Date(firstGridDate);
    day.setDate(firstGridDate.getDate() + index);
    return day;
  });
  const monthDays = days.filter((day) => day.getMonth() === activeMonth.getMonth());
  const monthPnl = monthDays.reduce((sum, day) => sum + (daily.get(dateKey(day))?.pnl || 0), 0);
  const tradingDays = monthDays.filter((day) => (daily.get(dateKey(day))?.trades || 0) > 0).length;
  const label = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(monthStart);

  return (
    <section className="panel overflow-hidden p-4">
      <div className="flex flex-col gap-4 border-b border-line pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Link className="secondary-action h-10 w-10 px-0" href={`${basePath}?month=${monthKey(addMonths(activeMonth, -1))}`} aria-label="Previous month">
            <ChevronLeft size={17} aria-hidden />
          </Link>
          <Link className="secondary-action h-10 px-4" href={`${basePath}?month=${monthKey(new Date())}`}>
            Today
          </Link>
          <Link className="secondary-action h-10 w-10 px-0" href={`${basePath}?month=${monthKey(addMonths(activeMonth, 1))}`} aria-label="Next month">
            <ChevronRight size={17} aria-hidden />
          </Link>
          <div className="ml-0 flex items-center gap-2 text-lg font-semibold text-zinc-50 sm:ml-4">
            <CalendarDays className="text-accent" size={19} aria-hidden />
            {label}
          </div>
        </div>
        <p className="text-sm text-zinc-400">
          <span className={monthPnl >= 0 ? "font-semibold text-good" : "font-semibold text-bad"}>{compactMoney(monthPnl)}</span> from {tradingDays} trading days this month
        </p>
      </div>

      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[1080px]">
          <div className="grid grid-cols-[repeat(7,minmax(0,1fr))_180px] gap-3 px-1 pb-3 text-center text-sm font-semibold text-zinc-300">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Week"].map((day) => (
              <div key={day}>{day}</div>
            ))}
          </div>
          <div className="grid grid-cols-[repeat(7,minmax(0,1fr))_180px] gap-3">
            {Array.from({ length: days.length / 7 }, (_, weekIndex) => {
              const weekDays = days.slice(weekIndex * 7, weekIndex * 7 + 7);
              const weekPnl = weekDays.reduce((sum, day) => sum + (daily.get(dateKey(day))?.pnl || 0), 0);
              const weekTradeDays = weekDays.filter((day) => (daily.get(dateKey(day))?.trades || 0) > 0).length;
              return (
                <div className="contents" key={weekIndex}>
                  {weekDays.map((day) => (
                    <CalendarDayCell key={dateKey(day)} day={day} activeMonth={activeMonth} summary={daily.get(dateKey(day))} />
                  ))}
                  <WeekCell weekIndex={weekIndex} pnl={weekPnl} tradingDays={weekTradeDays} />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function CalendarDayCell({ day, activeMonth, summary }: { day: Date; activeMonth: Date; summary?: { pnl: number; trades: number } }) {
  const isCurrentMonth = day.getMonth() === activeMonth.getMonth();
  const pnl = summary?.pnl || 0;
  const tone = pnl > 0 ? "border-emerald-400/20 bg-emerald-400/10" : pnl < 0 ? "border-red-400/20 bg-red-500/10" : "border-line bg-elevated/45";
  const valueClass = pnl > 0 ? "text-good" : pnl < 0 ? "text-bad" : "text-zinc-500";

  return (
    <div className={`min-h-32 rounded-xl border p-3 shadow-sm ${tone} ${isCurrentMonth ? "" : "opacity-45"}`}>
      <div className="text-right text-xs tabular-nums text-zinc-500">{day.getDate()}</div>
      {summary ? (
        <div className="mt-3">
          <p className={`text-sm font-semibold tabular-nums ${valueClass}`}>{compactMoney(pnl)}</p>
          <p className="mt-1 text-xs text-zinc-400">{summary.trades} {summary.trades === 1 ? "trade" : "trades"}</p>
        </div>
      ) : null}
    </div>
  );
}

function WeekCell({ weekIndex, pnl, tradingDays }: { weekIndex: number; pnl: number; tradingDays: number }) {
  const tone = pnl > 0 ? "border-l-good bg-emerald-400/10 text-good" : pnl < 0 ? "border-l-bad bg-red-500/10 text-bad" : "border-l-zinc-600 bg-elevated/45 text-zinc-500";

  return (
    <div className={`min-h-32 rounded-xl border border-line border-l-4 p-3 ${tone}`}>
      <div className="text-right text-xs font-semibold text-zinc-300">W{weekIndex + 1}</div>
      <p className="mt-3 text-sm font-semibold tabular-nums">{compactMoney(pnl)}</p>
      <p className="mt-1 text-xs text-zinc-400">{tradingDays} {tradingDays === 1 ? "day" : "days"}</p>
    </div>
  );
}

import { CalendarDays } from "lucide-react";
import { api } from "@/lib/api";
import { latestTradeDate, parseCalendarMonth, TradingCalendar } from "@/components/TradingCalendar";

type CalendarSearchParams = Promise<{ month?: string | string[] }>;

export default async function CalendarPage({ searchParams }: { searchParams?: CalendarSearchParams }) {
  const trades = await api.trades();
  const params = searchParams ? await searchParams : {};
  const activeMonth = parseCalendarMonth(params.month, latestTradeDate(trades));

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Trading Calendar</p>
          <h2 className="page-title">Monthly trading performance</h2>
        </div>
        <div className="panel-soft flex items-center gap-2 px-3 py-2 text-sm text-zinc-400">
          <CalendarDays size={16} aria-hidden />
          Daily and weekly P&L
        </div>
      </header>

      <section className="mt-6">
        <TradingCalendar trades={trades} activeMonth={activeMonth} />
      </section>
    </div>
  );
}

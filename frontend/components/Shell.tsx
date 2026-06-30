"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertTriangle, BookOpen, Bot, CalendarDays, ClipboardCheck, Gauge, ListChecks, ShieldCheck } from "lucide-react";

const nav = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/journal", label: "Journal", icon: BookOpen },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/rules", label: "Rules", icon: ShieldCheck },
  { href: "/pre-trade-rules", label: "Pre-trade", icon: ClipboardCheck },
  { href: "/alerts", label: "Alerts", icon: AlertTriangle },
  { href: "/daily-review", label: "Daily Review", icon: ListChecks }
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-[100dvh]">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-line bg-paper/95 px-4 py-5 backdrop-blur lg:block">
        <div className="flex items-center gap-3 px-2">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent text-slate-950">
            <Bot size={20} aria-hidden />
          </div>
          <div>
            <p className="kicker">AI Trading</p>
            <h1 className="text-lg font-semibold text-zinc-50">Coach</h1>
          </div>
        </div>
        <div className="mx-2 mt-6 rounded-xl border border-line bg-elevated p-3">
          <p className="text-xs font-medium text-zinc-500">Session focus</p>
          <p className="mt-1 text-sm font-semibold text-zinc-100">Protect capital before opportunity.</p>
        </div>
        <nav className="mt-6 space-y-1">
          {nav.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition ${
                  active ? "bg-accent text-slate-950" : "text-zinc-400 hover:bg-elevated hover:text-zinc-50"
                }`}
              >
                <item.icon size={18} aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="lg:pl-72">
        <div className="mx-auto w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">{children}</div>
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-7 border-t border-line bg-paper/95 backdrop-blur lg:hidden">
        {nav.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex h-16 flex-col items-center justify-center gap-1 text-[10px] font-semibold transition ${active ? "text-accent" : "text-zinc-500"}`}
            >
              <item.icon size={17} aria-hidden />
              <span className="max-w-full truncate px-1">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

import Link from "next/link";
import { AlertTriangle, BookOpen, Bot, ClipboardCheck, Gauge, ListChecks, ShieldCheck } from "lucide-react";

const nav = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/journal", label: "Journal", icon: BookOpen },
  { href: "/rules", label: "Rules", icon: ShieldCheck },
  { href: "/pre-trade-rules", label: "Pre-trade", icon: ClipboardCheck },
  { href: "/alerts", label: "Alerts", icon: AlertTriangle },
  { href: "/daily-review", label: "Daily Review", icon: ListChecks }
];

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-white px-4 py-5 lg:block">
        <div className="flex items-center gap-3 px-2">
          <div className="grid h-10 w-10 place-items-center rounded bg-ink text-white">
            <Bot size={20} aria-hidden />
          </div>
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">AI Trading</p>
            <h1 className="text-lg font-semibold">Coach</h1>
          </div>
        </div>
        <nav className="mt-8 space-y-1">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="flex h-10 items-center gap-3 rounded px-3 text-sm font-medium text-zinc-700 hover:bg-paper hover:text-ink">
              <item.icon size={18} aria-hidden />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="lg:pl-64">
        <div className="mx-auto w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">{children}</div>
      </main>
      <nav className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-6 border-t border-line bg-white lg:hidden">
        {nav.map((item) => (
          <Link key={item.href} href={item.href} className="flex h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium text-zinc-700">
            <item.icon size={17} aria-hidden />
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

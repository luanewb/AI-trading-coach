import { Ban, CheckCircle2, ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";

const displayTimeZone = "Asia/Bangkok";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: displayTimeZone
  }).format(new Date(value));
}

type PreTradeSearchParams = Promise<{ account_id?: string | string[] }>;

function parseAccountId(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export default async function PreTradeRulesPage({ searchParams }: { searchParams?: PreTradeSearchParams }) {
  const params = searchParams ? await searchParams : {};
  const accountId = parseAccountId(params.account_id);
  const checks = await api.preTradeChecks(false, accountId).catch(() => []);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Pre-trade Rules</p>
          <h2 className="page-title">Order pre-check history</h2>
        </div>
      </header>

      <section className="panel mt-5 overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line p-4">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-accent">
            <ClipboardCheck size={18} aria-hidden />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-50">Panel pre-check history</h3>
            <p className="text-sm text-zinc-400">These rows are recorded before the MT5 panel sends or simulates an order.</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full border-collapse text-sm">
            <thead className="bg-paper text-left text-xs uppercase tracking-[0.14em] text-zinc-500">
              <tr>
                <th className="p-3">Time</th>
                <th className="p-3">Symbol</th>
                <th className="p-3">Type</th>
                <th className="p-3">Lot</th>
                <th className="p-3">Entry</th>
                <th className="p-3">SL</th>
                <th className="p-3">TP</th>
                <th className="p-3">Status</th>
                <th className="p-3">Reason</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr key={check.id} className="border-t border-line align-top text-zinc-300 hover:bg-elevated/60">
                  <td className="p-3 whitespace-nowrap text-zinc-400">{formatDate(check.created_at)}</td>
                  <td className="p-3 font-semibold text-zinc-50">{check.symbol}</td>
                  <td className="p-3">{check.order_type}</td>
                  <td className="p-3 tabular-nums">{check.lot}</td>
                  <td className="p-3 tabular-nums">{check.entry_price ?? "-"}</td>
                  <td className="p-3 tabular-nums">{check.sl ?? "-"}</td>
                  <td className="p-3 tabular-nums">{check.tp ?? "-"}</td>
                  <td className="p-3">
                    <span className={`status-pill ${check.allowed ? "bg-emerald-400/15 text-good" : "bg-red-500/15 text-bad"}`}>
                      {check.allowed ? "Allowed" : "Blocked"}
                    </span>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      {check.allowed ? (
                        <CheckCircle2 className="mt-0.5 shrink-0 text-good" size={16} aria-hidden />
                      ) : (
                        <Ban className="mt-0.5 shrink-0 text-bad" size={16} aria-hidden />
                      )}
                      <span className="text-zinc-300">{check.reason}</span>
                    </div>
                  </td>
                </tr>
              ))}
              {!checks.length && (
                <tr>
                  <td className="p-6 text-zinc-400" colSpan={9}>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 size={18} aria-hidden />
                      No pre-trade checks yet.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

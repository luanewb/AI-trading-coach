import { Ban, CheckCircle2, ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export default async function PreTradeRulesPage() {
  const checks = await api.preTradeChecks(false).catch(() => []);

  return (
    <div className="pb-20">
      <header className="border-b border-line pb-5">
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Pre-trade Rules</p>
        <h2 className="mt-1 text-3xl font-semibold">Order pre-check history</h2>
      </header>

      <section className="mt-5 border border-line bg-white">
        <div className="flex items-center gap-3 border-b border-line p-4">
          <div className="grid h-10 w-10 place-items-center rounded bg-paper">
            <ClipboardCheck size={18} aria-hidden />
          </div>
          <div>
            <h3 className="font-semibold">Panel pre-check history</h3>
            <p className="text-sm text-zinc-600">These rows are recorded before the MT5 panel sends or simulates an order.</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-[900px] w-full border-collapse text-sm">
            <thead className="bg-paper text-left text-xs uppercase tracking-wide text-zinc-500">
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
                <tr key={check.id} className="border-t border-line align-top">
                  <td className="p-3 whitespace-nowrap">{formatDate(check.created_at)}</td>
                  <td className="p-3 font-semibold">{check.symbol}</td>
                  <td className="p-3">{check.order_type}</td>
                  <td className="p-3">{check.lot}</td>
                  <td className="p-3">{check.entry_price ?? "-"}</td>
                  <td className="p-3">{check.sl ?? "-"}</td>
                  <td className="p-3">{check.tp ?? "-"}</td>
                  <td className="p-3">
                    <span className={`rounded px-2 py-1 text-xs font-semibold ${check.allowed ? "bg-green-100 text-good" : "bg-red-100 text-bad"}`}>
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
                      <span className="text-zinc-700">{check.reason}</span>
                    </div>
                  </td>
                </tr>
              ))}
              {!checks.length && (
                <tr>
                  <td className="p-6 text-zinc-600" colSpan={9}>
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

import { AlertOctagon, Bell } from "lucide-react";
import { api } from "@/lib/api";

function severityClass(severity: string) {
  if (severity === "critical") return "bg-red-100 text-bad";
  if (severity === "warning") return "bg-amber-100 text-warn";
  return "bg-zinc-100 text-zinc-700";
}

export default async function AlertsPage() {
  const alerts = await api.alerts().catch(() => []);

  return (
    <div className="pb-20">
      <header className="border-b border-line pb-5">
        <p className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Alerts</p>
        <h2 className="mt-1 text-3xl font-semibold">Risk and behavior alerts</h2>
      </header>

      <section className="mt-5 space-y-3">
        {alerts.map((alert) => (
          <article key={alert.id} className="border border-line bg-white p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded bg-paper">
                  {alert.severity === "critical" ? <AlertOctagon size={18} aria-hidden /> : <Bell size={18} aria-hidden />}
                </div>
                <div>
                  <h3 className="font-semibold">{alert.type}</h3>
                  <p className="mt-1 text-sm text-zinc-600">{alert.message}</p>
                </div>
              </div>
              <span className={`w-fit rounded px-2 py-1 text-xs font-semibold ${severityClass(alert.severity)}`}>{alert.severity}</span>
            </div>
          </article>
        ))}
        {!alerts.length && <p className="border border-line bg-white p-5 text-sm text-zinc-600">No active alerts.</p>}
      </section>
    </div>
  );
}

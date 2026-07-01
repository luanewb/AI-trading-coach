import { AlertOctagon, Bell } from "lucide-react";
import { api } from "@/lib/api";

function severityClass(severity: string) {
  if (severity === "critical") return "bg-red-500/15 text-bad";
  if (severity === "warning") return "bg-amber-400/15 text-warn";
  return "bg-zinc-700/60 text-zinc-300";
}

type AlertsSearchParams = Promise<{ account_id?: string | string[] }>;

function parseAccountId(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export default async function AlertsPage({ searchParams }: { searchParams?: AlertsSearchParams }) {
  const params = searchParams ? await searchParams : {};
  const accountId = parseAccountId(params.account_id);
  const alerts = await api.alerts(accountId).catch(() => []);

  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">Alerts</p>
          <h2 className="page-title">Risk and behavior alerts</h2>
        </div>
      </header>

      <section className="mt-5 space-y-3">
        {alerts.map((alert) => (
          <article key={alert.id} className="panel p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex gap-3">
                <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${alert.severity === "critical" ? "bg-red-500/15 text-bad" : "bg-amber-400/15 text-warn"}`}>
                  {alert.severity === "critical" ? <AlertOctagon size={18} aria-hidden /> : <Bell size={18} aria-hidden />}
                </div>
                <div>
                  <h3 className="font-semibold text-zinc-50">{alert.type}</h3>
                  <p className="mt-1 text-sm text-zinc-400">{alert.message}</p>
                </div>
              </div>
              <span className={`status-pill ${severityClass(alert.severity)}`}>{alert.severity}</span>
            </div>
          </article>
        ))}
        {!alerts.length && <p className="panel p-5 text-sm text-zinc-400">No active alerts.</p>}
      </section>
    </div>
  );
}

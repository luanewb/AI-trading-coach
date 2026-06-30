import { RiskDashboard } from "@/components/RiskDashboard";
import { api } from "@/lib/api";

function errorMessage(label: string, result: PromiseSettledResult<unknown>) {
  if (result.status === "fulfilled") return null;
  return `${label} could not be loaded.`;
}

export default async function OverviewPage() {
  const [account, summary, activity, snapshots, preTradeHistory] = await Promise.allSettled([
    api.account(),
    api.riskSummary(),
    api.riskActivity("all"),
    api.accountSnapshots("7d"),
    api.preTradeHistory()
  ]);

  const errors = [
    errorMessage("Account", account),
    errorMessage("Risk summary", summary),
    errorMessage("Risk activity", activity),
    errorMessage("Account snapshots", snapshots),
    errorMessage("Pre-trade history", preTradeHistory)
  ].filter((message): message is string => Boolean(message));

  return (
    <RiskDashboard
      initialData={{
        account: account.status === "fulfilled" ? account.value : null,
        summary: summary.status === "fulfilled" ? summary.value : null,
        activity: activity.status === "fulfilled" ? activity.value : [],
        snapshots: snapshots.status === "fulfilled" ? snapshots.value : [],
        preTradeHistory: preTradeHistory.status === "fulfilled" ? preTradeHistory.value : [],
        errors
      }}
    />
  );
}

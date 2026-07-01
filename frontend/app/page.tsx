import { RiskDashboard } from "@/components/RiskDashboard";
import { api } from "@/lib/api";

type OverviewSearchParams = Promise<{ account_id?: string | string[] }>;

function errorMessage(label: string, result: PromiseSettledResult<unknown>) {
  if (result.status === "fulfilled") return null;
  return `${label} could not be loaded.`;
}

function parseAccountId(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export default async function OverviewPage({ searchParams }: { searchParams?: OverviewSearchParams }) {
  const params = searchParams ? await searchParams : {};
  const accountId = parseAccountId(params.account_id);
  const [accounts, summary, activity, snapshots, preTradeHistory] = await Promise.allSettled([
    api.accounts(),
    api.riskSummary(accountId),
    api.riskActivity("all", accountId),
    api.accountSnapshots("7d", accountId),
    api.preTradeHistory(accountId)
  ]);

  const errors = [
    errorMessage("Accounts", accounts),
    errorMessage("Risk summary", summary),
    errorMessage("Risk activity", activity),
    errorMessage("Account snapshots", snapshots),
    errorMessage("Pre-trade history", preTradeHistory)
  ].filter((message): message is string => Boolean(message));
  const accountList = accounts.status === "fulfilled" ? accounts.value : [];
  const selectedAccount = accountId
    ? accountList.find((account) => account.id === accountId) || null
    : accountList[0] || null;

  return (
    <RiskDashboard
      initialData={{
        account: selectedAccount,
        summary: summary.status === "fulfilled" ? summary.value : null,
        activity: activity.status === "fulfilled" ? activity.value : [],
        snapshots: snapshots.status === "fulfilled" ? snapshots.value : [],
        preTradeHistory: preTradeHistory.status === "fulfilled" ? preTradeHistory.value : [],
        errors
      }}
    />
  );
}

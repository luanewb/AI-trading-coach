import type {
  Account,
  AccountSnapshotPoint,
  AnalyticsBreakdown,
  AnalyticsDateRangeQuery,
  AnalyticsInsights,
  AnalyticsOverview,
  Alert,
  DailyReview,
  PreTradeCheck,
  PreTradeHistoryItem,
  RiskActivityFilter,
  RiskActivityItem,
  RiskRule,
  RiskSummary,
  RuleCatalog,
  RuleCatalogCreate,
  RuleIndicator,
  SnapshotRange,
  Stats,
  Trade
} from "./types";

const PUBLIC_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const API_BASE_URL = typeof window === "undefined"
  ? process.env.INTERNAL_API_BASE_URL || PUBLIC_API_BASE_URL
  : PUBLIC_API_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });

  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

function accountQuery(accountId?: number | null) {
  return queryString({ account_id: accountId });
}

function analyticsQuery(accountId?: number | null, range?: AnalyticsDateRangeQuery, extra?: Record<string, string | number | boolean | null | undefined>) {
  return queryString({
    account_id: accountId,
    start_date: range?.start_date,
    end_date: range?.end_date,
    ...(extra || {})
  });
}

export const api = {
  accounts: () => request<Account[]>("/api/accounts"),
  account: () => request<Account>("/api/accounts/current"),
  stats: (accountId?: number | null) => request<Stats>(`/api/journal/stats${accountQuery(accountId)}`),
  trades: (query = "", accountId?: number | null) => {
    const params = new URLSearchParams(query.startsWith("?") ? query.slice(1) : query);
    if (accountId !== null && accountId !== undefined) params.set("account_id", String(accountId));
    const text = params.toString();
    return request<Trade[]>(`/api/journal/trades${text ? `?${text}` : ""}`);
  },
  updateTrade: (id: number, payload: Partial<Trade>, accountId?: number | null) =>
    request<Trade>(`/api/journal/trades/${id}${accountQuery(accountId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  alerts: (accountId?: number | null) => request<Alert[]>(`/api/alerts${accountQuery(accountId)}`),
  rules: (accountId?: number | null) => request<RiskRule>(`/api/rules${accountQuery(accountId)}`),
  updateRules: (payload: Omit<RiskRule, "id" | "account_id">, accountId?: number | null) =>
    request<RiskRule>(`/api/rules${accountQuery(accountId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  ruleCatalog: () => request<RuleCatalog[]>("/api/rules/catalog"),
  createRule: (payload: RuleCatalogCreate) =>
    request<RuleCatalog>("/api/rules/catalog", { method: "POST", body: JSON.stringify(payload) }),
  updateRuleCatalog: (code: string, payload: Partial<RuleCatalogCreate>) =>
    request<RuleCatalog>(`/api/rules/catalog/${code}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteRuleCatalog: (code: string) =>
    request<void>(`/api/rules/catalog/${code}`, { method: "DELETE" }),
  evaluateRules: (accountId?: number | null) =>
    request<{ status: string; allow_trading: boolean; alerts_created: string[] }>(`/api/rules/evaluate${accountQuery(accountId)}`, { method: "POST" }),
  preTradeChecks: (blockedOnly = true, accountId?: number | null) =>
    request<PreTradeCheck[]>(`/api/rules/pre-trade-checks${queryString({ blocked_only: blockedOnly, account_id: accountId })}`),
  riskSummary: (accountId?: number | null) => request<RiskSummary>(`/api/dashboard/risk-summary${accountQuery(accountId)}`),
  riskActivity: (filter: RiskActivityFilter = "all", accountId?: number | null) =>
    request<RiskActivityItem[]>(`/api/dashboard/risk-activity${queryString({ filter, account_id: accountId })}`),
  accountSnapshots: (range: SnapshotRange = "7d", accountId?: number | null) =>
    request<AccountSnapshotPoint[]>(`/api/dashboard/account-snapshots${queryString({ range, account_id: accountId })}`),
  preTradeHistory: (accountId?: number | null) => request<PreTradeHistoryItem[]>(`/api/dashboard/pre-trade-history${accountQuery(accountId)}`),
  ruleIndicators: (accountId?: number | null) => request<RuleIndicator[]>(`/api/dashboard/rule-indicators${accountQuery(accountId)}`),
  dailyReview: (accountId?: number | null, reviewDate?: string | null) =>
    request<DailyReview | null>(`/api/ai/daily-review${queryString({ account_id: accountId, review_date: reviewDate })}`),
  dailyReviewHistory: (accountId?: number | null) =>
    request<DailyReview[]>(`/api/ai/daily-review/history${accountQuery(accountId)}`),
  createDailyReview: (accountId?: number | null, reviewDate?: string | null) =>
    request<DailyReview>(`/api/ai/daily-review${accountQuery(accountId)}`, { method: "POST", body: JSON.stringify({ review_date: reviewDate }) }),
  regenerateDailyReview: (accountId?: number | null, reviewDate?: string | null) =>
    request<DailyReview>(`/api/ai/daily-review/regenerate${accountQuery(accountId)}`, { method: "POST", body: JSON.stringify({ review_date: reviewDate }) }),
  analyticsOverview: (accountId?: number | null, range?: AnalyticsDateRangeQuery) =>
    request<AnalyticsOverview>(`/api/analytics/overview${analyticsQuery(accountId, range)}`),
  analyticsBreakdown: (groupBy: string, accountId?: number | null, range?: AnalyticsDateRangeQuery) =>
    request<AnalyticsBreakdown>(`/api/analytics/breakdown${analyticsQuery(accountId, range, { group_by: groupBy })}`),
  analyticsInsights: (accountId?: number | null, range?: AnalyticsDateRangeQuery) =>
    request<AnalyticsInsights>(`/api/analytics/insights${analyticsQuery(accountId, range)}`)
};

export { API_BASE_URL, PUBLIC_API_BASE_URL };

import type { Account, Alert, DailyReview, PreTradeCheck, RiskRule, RuleCatalog, RuleCatalogCreate, Stats, Trade } from "./types";

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

export const api = {
  account: () => request<Account>("/api/accounts/current"),
  stats: () => request<Stats>("/api/journal/stats"),
  trades: (query = "") => request<Trade[]>(`/api/journal/trades${query}`),
  updateTrade: (id: number, payload: Partial<Trade>) =>
    request<Trade>(`/api/journal/trades/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  alerts: () => request<Alert[]>("/api/alerts"),
  rules: () => request<RiskRule>("/api/rules"),
  updateRules: (payload: Omit<RiskRule, "id" | "account_id">) =>
    request<RiskRule>("/api/rules", { method: "PUT", body: JSON.stringify(payload) }),
  ruleCatalog: () => request<RuleCatalog[]>("/api/rules/catalog"),
  createRule: (payload: RuleCatalogCreate) =>
    request<RuleCatalog>("/api/rules/catalog", { method: "POST", body: JSON.stringify(payload) }),
  updateRuleCatalog: (code: string, payload: Partial<RuleCatalogCreate>) =>
    request<RuleCatalog>(`/api/rules/catalog/${code}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteRuleCatalog: (code: string) =>
    request<void>(`/api/rules/catalog/${code}`, { method: "DELETE" }),
  evaluateRules: () => request<{ status: string; allow_trading: boolean; alerts_created: string[] }>("/api/rules/evaluate", { method: "POST" }),
  preTradeChecks: (blockedOnly = true) => request<PreTradeCheck[]>(`/api/rules/pre-trade-checks?blocked_only=${blockedOnly}`),
  dailyReview: () => request<DailyReview | null>("/api/ai/daily-review"),
  createDailyReview: () => request<DailyReview>("/api/ai/daily-review", { method: "POST", body: JSON.stringify({}) })
};

export { API_BASE_URL, PUBLIC_API_BASE_URL };

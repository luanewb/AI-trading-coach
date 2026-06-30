export type Account = {
  id: number;
  account_number: string;
  broker: string;
  server: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
};

export type Stats = {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  average_r: number;
  max_drawdown: number;
  trades_today: number;
  daily_pnl: number;
  consecutive_losses: number;
};

export type Trade = {
  id: number;
  ticket: string;
  symbol: string;
  order_type: string;
  lot: string;
  entry_price: string | null;
  sl: string | null;
  tp: string | null;
  close_price: string | null;
  profit: string;
  r_multiple: string | null;
  status: string;
  open_time: string | null;
  close_time: string | null;
  setup_name: string | null;
  emotion: string | null;
  mistake_tags: string[] | null;
  notes: string | null;
};

export type Alert = {
  id: number;
  account_id: number | null;
  severity: "info" | "warning" | "critical" | string;
  type: string;
  message: string;
  is_resolved: boolean;
  created_at: string;
};

export type RiskRule = {
  id: number;
  account_id: number;
  max_trades_per_day: number;
  max_daily_loss_percent: string;
  max_total_loss_percent: string;
  max_consecutive_losses: number;
  cooldown_minutes_after_loss: number;
  max_lot: string;
  max_risk_per_trade_percent: string;
  allow_trading: boolean;
};

export type RuleCatalog = {
  id: number;
  name: string;
  code: string;
  description: string;
  enabled: boolean;
  severity: "info" | "warning" | "critical";
  action: "allow" | "warn" | "block" | "lock";
  category: "risk" | "behavior" | "ftmo" | "execution" | "psychology";
  config: Record<string, unknown>;
  message: string;
  created_at: string;
  updated_at: string;
};

export type RuleCatalogCreate = Omit<RuleCatalog, "id" | "created_at" | "updated_at">;

export type DailyReview = {
  id: number;
  account_id: number;
  review_date: string;
  pnl: string;
  trade_count: number;
  win_rate: string;
  ai_summary: string | null;
  mistakes: string | null;
  best_trade: string | null;
  worst_trade: string | null;
  action_plan: string | null;
};

export type PreTradeCheck = {
  id: number;
  account_id: number;
  symbol: string;
  order_type: string;
  lot: string;
  entry_price: string | null;
  sl: string | null;
  tp: string | null;
  allowed: boolean;
  reason: string;
  created_at: string;
};

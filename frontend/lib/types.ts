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

export type AnalyticsDateRangeQuery = {
  start_date?: string | null;
  end_date?: string | null;
};

export type AnalyticsConfidence = {
  code: "insufficient_sample" | "early_signal" | "meaningful_sample";
  label: string;
  sample_size: number;
};

export type AnalyticsMetrics = {
  total_closed_trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: number;
  total_realized_pnl: number;
  gross_profit: number;
  gross_loss: number;
  profit_factor: number | null;
  expectancy: number;
  average_winner: number | null;
  average_loser: number | null;
  average_r_multiple: number | null;
  r_multiple_count: number;
  best_r_multiple: number | null;
  worst_r_multiple: number | null;
  average_holding_minutes: number | null;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  confidence: AnalyticsConfidence;
};

export type EquityCurvePoint = {
  date: string;
  cumulative_pnl: number;
  trade_count: number;
};

export type AnalyticsOverview = {
  account_id: number | null;
  start_date: string | null;
  end_date: string | null;
  no_data: boolean;
  metrics: AnalyticsMetrics;
  equity_curve: EquityCurvePoint[];
};

export type AnalyticsBreakdownRow = {
  group_by: string;
  key: string;
  label: string;
  metrics: AnalyticsMetrics;
};

export type AnalyticsBreakdown = {
  account_id: number | null;
  start_date: string | null;
  end_date: string | null;
  group_by: string;
  rows: AnalyticsBreakdownRow[];
  missing_journal_count: number;
};

export type AnalyticsInsight = {
  tone: "edge" | "leak" | "info";
  title: string;
  observation: string;
  group_by: string | null;
  key: string | null;
  sample_size: number;
  confidence: AnalyticsConfidence | null;
  metric_name: string | null;
  metric_value: number | null;
  supported: boolean;
};

export type AnalyticsInsights = {
  account_id: number | null;
  start_date: string | null;
  end_date: string | null;
  insights: AnalyticsInsight[];
};

export type Trade = {
  id: number;
  ticket: string;
  deal_id: string | null;
  position_id: string | null;
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
  source: string;
  strategy: string | null;
  setup_name: string | null;
  emotion: string | null;
  mistake_tags: string[] | null;
  notes: string | null;
  before_entry_image_url: string | null;
  after_exit_image_url: string | null;
  analysis_image_url: string | null;
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
  metrics_snapshot: {
    total_trades?: number;
    wins?: number;
    losses?: number;
    win_rate?: number;
    realized_pnl?: string;
    average_winner?: string | null;
    average_loser?: string | null;
    profit_factor?: number | null;
    average_r_multiple?: number | null;
    max_consecutive_losses?: number;
    rule_violations?: {
      total?: number;
      by_code?: Array<{ name: string; count: number }>;
      items?: Array<{ rule_code: string; severity: string; action: string; message: string; created_at: string | null }>;
    };
    blocked_pre_trade_attempts?: number;
    pre_trade_attempts?: number;
    most_traded_symbols?: Array<{ name: string; count: number }>;
    setups_used?: Array<{ name: string; count: number }>;
    emotions?: Array<{ name: string; count: number }>;
    mistakes?: Array<{ name: string; count: number }>;
    journal?: {
      missing?: Record<string, number>;
      incomplete_trade_count?: number;
    };
  };
  discipline_score: number;
  discipline_breakdown: Array<{ code: string; label: string; observed: number; penalty: number; reason: string }>;
  deterministic_findings: {
    facts?: string[];
    positive_behaviors?: string[];
    risk_patterns?: string[];
    tomorrows_plan?: string[];
    strongest_positive_behavior?: string;
    biggest_mistake_or_risk_pattern?: string;
    score_interpretation?: string;
    disclaimer?: string;
  };
  ai_narrative: string | null;
  model_metadata: {
    ai_enabled?: boolean;
    model?: string;
    provider?: string;
    fallback_reason?: string;
  };
  generated_at: string | null;
  created_at: string;
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

export type RiskBudget = {
  current: string;
  used: string;
  limit: string;
  remaining: string;
  percent_used: number;
  percent_remaining: number;
};

export type CountBudget = {
  current: number;
  limit: number;
  remaining: number;
  percent_used: number;
  percent_remaining: number;
};

export type RiskSummary = {
  account_id: number;
  account_number: string;
  trading_status: "allowed" | "warning" | "blocked" | "locked";
  status_label: string;
  status_reason: string;
  current_daily_pnl: string;
  daily_loss: RiskBudget;
  total_drawdown: RiskBudget;
  trades_today: CountBudget;
  consecutive_losses: CountBudget;
  cooldown: {
    active: boolean;
    cooldown_until: string | null;
    remaining_seconds: number;
  };
  max_lot: {
    planned_lot: string | null;
    configured_max_lot: string;
  };
  active_restrictions: Array<{
    rule_code: string;
    severity: string;
    action: string;
    message: string;
    created_at: string;
  }>;
  checked_at: string;
};

export type RiskActivityFilter = "all" | "warning" | "blocked" | "locked" | "resolved";

export type RiskActivityItem = {
  id: string;
  timestamp: string;
  rule_code: string;
  severity: string;
  action: string;
  message: string;
  source: "rule_violation" | "pre_trade_check";
  decision: string | null;
  symbol: string | null;
  ticket: string | null;
  status: "active" | "resolved";
};

export type SnapshotRange = "24h" | "7d" | "30d";

export type AccountSnapshotPoint = {
  id: number;
  timestamp: string;
  balance: string;
  equity: string;
  drawdown: string;
  drawdown_percent: number;
};

export type PreTradeHistoryItem = {
  id: number;
  timestamp: string;
  symbol: string;
  side: string;
  lot: string;
  entry_price: string | null;
  sl: string | null;
  tp: string | null;
  decision: string;
  allowed: boolean;
  reason: string;
  warning_count: number;
  violation_count: number;
  rule_codes: string[];
  details: Record<string, unknown>;
};

export type RuleIndicator = {
  rule_code: string;
  enabled: boolean;
  latest_trigger_time: string | null;
  trigger_count_today: number;
  latest_action_taken: string | null;
  current_active_state: string;
};

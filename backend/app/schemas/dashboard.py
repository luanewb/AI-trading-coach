from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


TradingStatus = Literal["allowed", "warning", "blocked", "locked"]
ActivityFilter = Literal["all", "warning", "blocked", "locked", "resolved"]
SnapshotRange = Literal["24h", "7d", "30d"]


class RiskBudgetOut(BaseModel):
    current: Decimal
    used: Decimal
    limit: Decimal
    remaining: Decimal
    percent_used: float
    percent_remaining: float


class CountBudgetOut(BaseModel):
    current: int
    limit: int
    remaining: int
    percent_used: float
    percent_remaining: float


class CooldownStatusOut(BaseModel):
    active: bool
    cooldown_until: datetime | None = None
    remaining_seconds: int = 0


class MaxLotStatusOut(BaseModel):
    planned_lot: Decimal | None = None
    configured_max_lot: Decimal


class ActiveRestrictionOut(BaseModel):
    rule_code: str
    severity: str
    action: str
    message: str
    created_at: datetime


class RiskSummaryOut(BaseModel):
    account_id: int
    account_number: str
    trading_status: TradingStatus
    status_label: str
    status_reason: str
    current_daily_pnl: Decimal
    daily_loss: RiskBudgetOut
    total_drawdown: RiskBudgetOut
    trades_today: CountBudgetOut
    consecutive_losses: CountBudgetOut
    cooldown: CooldownStatusOut
    max_lot: MaxLotStatusOut
    active_restrictions: list[ActiveRestrictionOut] = Field(default_factory=list)
    checked_at: datetime


class RiskActivityItemOut(BaseModel):
    id: str
    timestamp: datetime
    rule_code: str
    severity: str
    action: str
    message: str
    source: Literal["rule_violation", "pre_trade_check"]
    decision: str | None = None
    symbol: str | None = None
    ticket: str | None = None
    status: Literal["active", "resolved"]


class AccountSnapshotPointOut(BaseModel):
    id: int
    timestamp: datetime
    balance: Decimal
    equity: Decimal
    drawdown: Decimal
    drawdown_percent: float


class PreTradeHistoryItemOut(BaseModel):
    id: int
    timestamp: datetime
    symbol: str
    side: str
    lot: Decimal
    entry_price: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    decision: str
    allowed: bool
    reason: str
    warning_count: int
    violation_count: int
    rule_codes: list[str]
    details: dict[str, object]


class RuleIndicatorOut(BaseModel):
    rule_code: str
    enabled: bool
    latest_trigger_time: datetime | None = None
    trigger_count_today: int
    latest_action_taken: str | None = None
    current_active_state: str

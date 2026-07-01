from datetime import date
from typing import Literal

from pydantic import BaseModel


ConfidenceCode = Literal["insufficient_sample", "early_signal", "meaningful_sample"]
InsightTone = Literal["edge", "leak", "info"]


class ConfidenceOut(BaseModel):
    code: ConfidenceCode
    label: str
    sample_size: int


class AnalyticsMetricsOut(BaseModel):
    total_closed_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    total_realized_pnl: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    expectancy: float
    average_winner: float | None
    average_loser: float | None
    average_r_multiple: float | None
    r_multiple_count: int
    best_r_multiple: float | None
    worst_r_multiple: float | None
    average_holding_minutes: float | None
    max_consecutive_wins: int
    max_consecutive_losses: int
    confidence: ConfidenceOut


class EquityCurvePointOut(BaseModel):
    date: date
    cumulative_pnl: float
    trade_count: int


class AnalyticsOverviewOut(BaseModel):
    account_id: int | None
    start_date: date | None
    end_date: date | None
    no_data: bool
    metrics: AnalyticsMetricsOut
    equity_curve: list[EquityCurvePointOut]


class BreakdownRowOut(BaseModel):
    group_by: str
    key: str
    label: str
    metrics: AnalyticsMetricsOut


class AnalyticsBreakdownOut(BaseModel):
    account_id: int | None
    start_date: date | None
    end_date: date | None
    group_by: str
    rows: list[BreakdownRowOut]
    missing_journal_count: int = 0


class AnalyticsInsightOut(BaseModel):
    tone: InsightTone
    title: str
    observation: str
    group_by: str | None = None
    key: str | None = None
    sample_size: int = 0
    confidence: ConfidenceOut | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    supported: bool = True


class AnalyticsInsightsOut(BaseModel):
    account_id: int | None
    start_date: date | None
    end_date: date | None
    insights: list[AnalyticsInsightOut]

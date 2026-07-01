from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class DailyReviewRequest(BaseModel):
    account_id: int | None = None
    review_date: date | None = None


class DailyReviewOut(BaseModel):
    id: int
    account_id: int
    review_date: date
    pnl: Decimal
    trade_count: int
    win_rate: Decimal
    ai_summary: str | None
    mistakes: str | None
    best_trade: str | None
    worst_trade: str | None
    action_plan: str | None
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    discipline_score: int = 100
    discipline_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_findings: dict[str, Any] = Field(default_factory=dict)
    ai_narrative: str | None = None
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyReviewDraft(BaseModel):
    ai_summary: str = Field(default="")
    mistakes: str = Field(default="")
    best_trade: str = Field(default="")
    worst_trade: str = Field(default="")
    action_plan: str = Field(default="")

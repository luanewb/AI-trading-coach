from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.rules import RuleViolationOut


class PreTradeCheckIn(BaseModel):
    account_number: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    order_type: Literal["BUY", "SELL"]
    lot: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    sl: Decimal | None = None
    tp: Decimal | None = None
    risk_percent: Decimal | None = Field(default=None, ge=0)
    risk_amount: Decimal | None = Field(default=None, ge=0)


class PreTradeCheckOut(BaseModel):
    allowed: bool
    reason: str
    alerts: list[str]
    status: str = "allowed"
    decision: str = "ALLOW"
    message: str = "Allowed"
    violations: list[RuleViolationOut] = Field(default_factory=list)
    warnings: list[RuleViolationOut] = Field(default_factory=list)
    checked_at: datetime | None = None
    rule_evaluation_id: int | None = None


class PreCloseCheckIn(BaseModel):
    account_number: str = Field(min_length=1, max_length=64)
    ticket: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    position_type: Literal["BUY", "SELL"]
    lot: Decimal = Field(gt=0)
    entry_price: Decimal | None = None
    current_price: Decimal | None = None
    profit: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    candle_close: Decimal | None = None
    ema34: Decimal | None = None
    ema89: Decimal | None = None
    close_reason: str | None = Field(default=None, max_length=64)


class PreCloseCheckOut(PreTradeCheckOut):
    pass


class PreTradeCheckHistoryOut(BaseModel):
    id: int
    account_id: int
    symbol: str
    order_type: str
    lot: Decimal
    entry_price: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    allowed: bool
    reason: str
    rule_codes: list[str]
    details: dict[str, object]
    rule_evaluation_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}

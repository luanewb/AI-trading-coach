from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PreTradeCheckIn(BaseModel):
    account_number: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=32)
    order_type: Literal["BUY", "SELL"]
    lot: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    sl: Decimal | None = None
    tp: Decimal | None = None


class PreTradeCheckOut(BaseModel):
    allowed: bool
    reason: str
    alerts: list[str]


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
    created_at: datetime

    model_config = {"from_attributes": True}

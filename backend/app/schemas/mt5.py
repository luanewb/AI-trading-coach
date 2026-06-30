from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class HeartbeatIn(BaseModel):
    account_number: str = Field(min_length=1, max_length=64)
    broker: str = Field(min_length=1, max_length=128)
    server: str = Field(min_length=1, max_length=128)
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeEventIn(BaseModel):
    account_number: str | None = Field(default=None, max_length=64)
    event_type: Literal["order_opened", "order_modified", "order_closed", "position_updated"]
    symbol: str = Field(min_length=1, max_length=32)
    ticket: str = Field(min_length=1, max_length=64)
    deal_id: str | None = Field(default=None, max_length=64)
    position_id: str | None = Field(default=None, max_length=64)
    order_type: str = Field(min_length=1, max_length=32)
    lot: Decimal = Field(ge=0)
    entry_price: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    close_price: Decimal | None = None
    profit: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    swap: Decimal = Decimal("0")
    open_time: datetime | None = None
    close_time: datetime | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="mt5", max_length=32)
    strategy: str | None = Field(default=None, max_length=128)

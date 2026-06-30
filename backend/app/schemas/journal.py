from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TradeOut(BaseModel):
    id: int
    account_id: int
    ticket: str
    deal_id: str | None
    position_id: str | None
    symbol: str
    order_type: str
    lot: Decimal
    entry_price: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    close_price: Decimal | None
    profit: Decimal
    commission: Decimal
    swap: Decimal
    r_multiple: Decimal | None
    status: str
    open_time: datetime | None
    close_time: datetime | None
    source: str
    strategy: str | None
    setup_name: str | None
    emotion: str | None
    mistake_tags: list[str] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TradePatch(BaseModel):
    setup_name: str | None = Field(default=None, max_length=128)
    emotion: str | None = Field(default=None, max_length=64)
    mistake_tags: list[str] | None = None
    notes: str | None = None


class StatsOut(BaseModel):
    total_trades: int
    win_rate: float
    profit_factor: float
    average_r: float
    max_drawdown: float
    trades_today: int
    daily_pnl: float
    consecutive_losses: int

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.services.trade_direction import normalize_order_type


def realized_r(order_type: str, entry_price: Decimal | None, sl: Decimal | None, close_price: Decimal | None, profit: Decimal) -> Decimal | None:
    if entry_price is None or sl is None or close_price is None:
        return None
    risk = abs(entry_price - sl)
    if not risk:
        return None
    reward = entry_price - close_price if order_type == "SELL" else close_price - entry_price
    if reward == 0 and profit != 0:
        return None
    return reward / risk


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
    before_entry_image_url: str | None = None
    after_exit_image_url: str | None = None
    analysis_image_url: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_side(self) -> "TradeOut":
        self.order_type = normalize_order_type(self.order_type, self.entry_price, self.sl, self.tp)
        if self.status == "closed":
            self.r_multiple = realized_r(self.order_type, self.entry_price, self.sl, self.close_price, self.profit)
        return self

    model_config = {"from_attributes": True}


class TradePatch(BaseModel):
    setup_name: str | None = Field(default=None, max_length=128)
    emotion: str | None = Field(default=None, max_length=64)
    mistake_tags: list[str] | None = None
    notes: str | None = None
    before_entry_image_url: str | None = Field(default=None, max_length=1024)
    after_exit_image_url: str | None = Field(default=None, max_length=1024)
    analysis_image_url: str | None = Field(default=None, max_length=1024)


class StatsOut(BaseModel):
    total_trades: int
    win_rate: float
    profit_factor: float
    average_r: float
    max_drawdown: float
    trades_today: int
    daily_pnl: float
    consecutive_losses: int

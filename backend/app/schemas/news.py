from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


NewsEnforcementMode = Literal["warn_only", "block_actions", "disabled"]
NewsAccountType = Literal["standard_funded", "swing", "evaluation"]
NewsTradeAction = Literal["new_order", "manual_close", "modify_sl_tp", "pending_order"]


class EconomicEventOut(BaseModel):
    id: int
    source: str
    title: str
    normalized_title: str
    currency: str
    country: str | None = None
    scheduled_at: datetime
    impact: str | None = None
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    is_restricted: bool
    restriction_reason: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None

    model_config = {"from_attributes": True}


class NewsRestrictionSettingsIn(BaseModel):
    account_type: NewsAccountType | None = None
    enforcement_mode: NewsEnforcementMode | None = None
    minutes_before: int | None = Field(default=None, ge=0, le=120)
    minutes_after: int | None = Field(default=None, ge=0, le=120)
    apply_usd_only: bool | None = None
    blocked_actions: list[NewsTradeAction] | None = None


class NewsRestrictionSettingsOut(BaseModel):
    id: int
    account_type: NewsAccountType
    enforcement_mode: NewsEnforcementMode
    minutes_before: int
    minutes_after: int
    apply_usd_only: bool
    blocked_actions: list[NewsTradeAction]
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class NewsRestrictionStatusOut(BaseModel):
    symbol: str
    action: NewsTradeAction
    usd_sensitive: bool
    is_restricted_now: bool
    enforcement_mode: NewsEnforcementMode
    effective_mode: NewsEnforcementMode
    account_type: NewsAccountType
    should_block: bool
    should_warn: bool
    blocked_actions: list[NewsTradeAction]
    current_event: EconomicEventOut | None = None
    upcoming_event: EconomicEventOut | None = None
    seconds_until_event: int | None = None
    seconds_until_restriction_end: int | None = None
    restricted_until: datetime | None = None
    checked_at: datetime


class TradeRestrictionEventOut(BaseModel):
    id: int
    account_id: int | None = None
    account_number: str | None = None
    symbol: str
    action: str
    mode: str
    blocked: bool
    news_event_id: int | None = None
    event_title: str | None = None
    restricted_until: datetime | None = None
    context: dict[str, object]
    created_at: datetime

    model_config = {"from_attributes": True}

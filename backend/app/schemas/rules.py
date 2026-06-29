from decimal import Decimal

from pydantic import BaseModel, Field


class RiskRuleIn(BaseModel):
    max_trades_per_day: int = Field(ge=1, le=100)
    max_daily_loss_percent: Decimal = Field(ge=0, le=100)
    max_total_loss_percent: Decimal = Field(ge=0, le=100)
    max_consecutive_losses: int = Field(ge=1, le=100)
    cooldown_minutes_after_loss: int = Field(ge=0, le=1440)
    max_lot: Decimal = Field(ge=0)
    allow_trading: bool = True


class RiskRuleOut(RiskRuleIn):
    id: int
    account_id: int

    model_config = {"from_attributes": True}


class RuleEvaluationOut(BaseModel):
    account_id: int
    allow_trading: bool
    status: str
    alerts_created: list[str]
    cooldown_until: str | None = None

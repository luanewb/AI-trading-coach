from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, Field


class RiskRuleIn(BaseModel):
    max_trades_per_day: int = Field(ge=1, le=100)
    max_daily_loss_percent: Decimal = Field(ge=0, le=100)
    max_total_loss_percent: Decimal = Field(ge=0, le=100)
    max_consecutive_losses: int = Field(ge=1, le=100)
    cooldown_minutes_after_loss: int = Field(ge=0, le=1440)
    max_lot: Decimal = Field(ge=0)
    max_risk_per_trade_percent: Decimal = Field(default=Decimal("1"), ge=0, le=100)
    allow_trading: bool = True


class RiskRuleOut(RiskRuleIn):
    id: int
    account_id: int

    model_config = {"from_attributes": True}


class RuleCatalogOut(BaseModel):
    id: int
    name: str
    code: str
    description: str
    enabled: bool
    severity: str
    action: str
    category: str
    config: dict[str, object]
    message: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleCatalogCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64, pattern="^[A-Z0-9_]+$")
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    action: str = Field(default="warn", pattern="^(allow|warn|block|lock)$")
    category: str = Field(default="risk", pattern="^(risk|behavior|ftmo|execution|psychology)$")
    config: dict[str, object] = Field(default_factory=dict)
    message: str = Field(min_length=1, max_length=2000)


class RuleCatalogUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    severity: str | None = Field(default=None, pattern="^(info|warning|critical)$")
    action: str | None = Field(default=None, pattern="^(allow|warn|block|lock)$")
    category: str | None = Field(default=None, pattern="^(risk|behavior|ftmo|execution|psychology)$")
    config: dict[str, object] | None = None
    message: str | None = None


class RuleViolationOut(BaseModel):
    rule_code: str
    severity: str
    action: str
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class RuleEvaluationOut(BaseModel):
    account_id: int
    allow_trading: bool
    allowed: bool = True
    blocked: bool = False
    status: str
    decision: str = "ALLOW"
    reason: str = "Allowed"
    message: str = "Allowed"
    warnings: list[RuleViolationOut] = Field(default_factory=list)
    violations: list[RuleViolationOut] = Field(default_factory=list)
    alerts_created: list[str]
    metadata: dict[str, object] = Field(default_factory=dict)
    checked_at: datetime | None = None
    cooldown_until: str | None = None

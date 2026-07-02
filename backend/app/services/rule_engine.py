import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account, Alert, PreTradeCheck, RiskRule, Rule, RuleEvaluation, RuleViolation, Trade
from app.schemas.pre_trade import PreCloseCheckIn, PreTradeCheckIn
from app.services.news_restrictions import log_restriction_event, news_finding_payload, restriction_status
from app.services.stats import calculate_stats, latest_closed_trade
from app.services.telegram import send_telegram_alert
from app.services.timezone import now_utc, trading_day_bounds

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleDefinition:
    name: str
    code: str
    description: str
    severity: str
    action: str
    category: str
    message: str
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleFinding:
    rule_code: str
    message: str
    severity: str
    action: str
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)
    rule_id: int | None = None

    @property
    def blocks(self) -> bool:
        return self.action in {"block", "lock"}

    @property
    def is_warning(self) -> bool:
        return self.action == "warn"


@dataclass(frozen=True)
class EvaluationResult:
    account_id: int
    allowed: bool
    blocked: bool
    status: str
    decision: str
    reason: str
    message: str
    warnings: list[RuleFinding]
    violations: list[RuleFinding]
    metadata: dict[str, Any]
    checked_at: datetime
    evaluation_id: int | None = None


DEFAULT_RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        name="Platform trading allowed",
        code="PLATFORM_TRADING_ALLOWED",
        description="Blocks all new trades when platform-level trading is disabled.",
        severity="critical",
        action="block",
        category="execution",
        message="Trading is disabled by risk rule configuration.",
    ),
    RuleDefinition(
        name="No stop loss",
        code="NO_STOP_LOSS",
        description="Blocks planned or open trades that do not have a stop loss.",
        severity="critical",
        action="block",
        category="risk",
        message="Trade blocked because stop loss is missing.",
    ),
    RuleDefinition(
        name="Max trades per day",
        code="MAX_TRADES_PER_DAY",
        description="Warns or blocks when trades opened today reach the configured limit.",
        severity="warning",
        action="block",
        category="behavior",
        message="Trade blocked because the max trades per day limit was reached.",
    ),
    RuleDefinition(
        name="Max daily loss",
        code="MAX_DAILY_LOSS",
        description="Blocks or locks trading when daily closed loss reaches the configured percentage.",
        severity="critical",
        action="lock",
        category="ftmo",
        message="Trading locked because the daily loss limit was reached.",
    ),
    RuleDefinition(
        name="Max total loss",
        code="MAX_TOTAL_LOSS",
        description="Blocks or locks trading when account loss versus balance reaches the configured percentage.",
        severity="critical",
        action="lock",
        category="ftmo",
        message="Trading locked because the total account loss limit was reached.",
    ),
    RuleDefinition(
        name="Max drawdown",
        code="MAX_DRAWDOWN_LIMIT",
        description="Blocks or locks trading when realized drawdown reaches the configured maximum loss percentage.",
        severity="critical",
        action="lock",
        category="risk",
        message="Trading locked because realized drawdown reached the maximum loss limit.",
    ),
    RuleDefinition(
        name="Max consecutive losses",
        code="MAX_CONSECUTIVE_LOSSES",
        description="Warns or blocks after the configured number of consecutive losing trades.",
        severity="warning",
        action="block",
        category="psychology",
        message="Trade blocked because the consecutive loss limit was reached.",
    ),
    RuleDefinition(
        name="Cooldown after loss",
        code="COOLDOWN_AFTER_LOSS",
        description="Blocks new trades for the configured minutes after a losing trade.",
        severity="warning",
        action="block",
        category="psychology",
        message="Trade blocked because post-loss cooldown is active.",
    ),
    RuleDefinition(
        name="Max lot size",
        code="MAX_LOT_SIZE",
        description="Blocks planned trades with lot size above the configured limit.",
        severity="warning",
        action="block",
        category="execution",
        message="Trade blocked because lot size exceeds the configured maximum.",
    ),
    RuleDefinition(
        name="Risk per trade",
        code="RISK_PER_TRADE",
        description="Warns or blocks when planned risk exceeds the configured percentage of equity.",
        severity="critical",
        action="block",
        category="risk",
        message="Trade blocked because planned risk per trade is too high.",
    ),
    RuleDefinition(
        name="Revenge trading",
        code="REVENGE_TRADING",
        description="Detects same-symbol or larger-lot trades shortly after a loss.",
        severity="critical",
        action="block",
        category="psychology",
        message="Trade blocked because it looks like revenge trading after a recent loss.",
    ),
    RuleDefinition(
        name="FTMO restricted news window",
        code="NEWS_RESTRICTED_WINDOW",
        description="Warns or blocks USD-sensitive trading actions during configured FTMO restricted news windows.",
        severity="critical",
        action="block",
        category="ftmo",
        message="Trade blocked because an FTMO restricted news window is active.",
    ),
)

DEFAULT_RULES_BY_CODE = {rule.code: rule for rule in DEFAULT_RULES}


def get_or_create_rule(db: Session, account: Account) -> RiskRule:
    rule = db.scalar(select(RiskRule).where(RiskRule.account_id == account.id))
    if rule:
        return rule

    rule = RiskRule(account_id=account.id)
    db.add(rule)
    db.flush()
    return rule


def create_alert(db: Session, account_id: int, severity: str, alert_type: str, message: str) -> Alert:
    alert = Alert(account_id=account_id, severity=severity, type=alert_type, message=message)
    db.add(alert)
    db.flush()
    send_telegram_alert(alert)
    return alert


def ensure_rule_catalog(db: Session) -> list[Rule]:
    rules: list[Rule] = []
    for definition in DEFAULT_RULES:
        rule = db.scalar(select(Rule).where(Rule.code == definition.code))
        if not rule:
            rule = Rule(
                name=definition.name,
                code=definition.code,
                description=definition.description,
                enabled=True,
                severity=definition.severity,
                action=definition.action,
                category=definition.category,
                config=definition.config,
                message=definition.message,
            )
            db.add(rule)
            db.flush()
        rules.append(rule)
    all_rules = list(db.scalars(select(Rule).order_by(Rule.code)))
    return all_rules or rules


def update_catalog_rule(db: Session, code: str, values: dict[str, object]) -> Rule | None:
    ensure_rule_catalog(db)
    rule = db.scalar(select(Rule).where(Rule.code == code))
    if not rule:
        return None
    for field_name, value in values.items():
        if value is not None:
            setattr(rule, field_name, value)
    db.flush()
    return rule


def delete_catalog_rule(db: Session, code: str) -> bool | None:
    rule = db.scalar(select(Rule).where(Rule.code == code))
    if not rule:
        return None
    if code in DEFAULT_RULES_BY_CODE:
        return False
    db.delete(rule)
    db.flush()
    return True


def create_catalog_rule(db: Session, values: dict[str, object]) -> Rule:
    ensure_rule_catalog(db)
    rule = Rule(**values)
    db.add(rule)
    db.flush()
    return rule


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _rule_catalog(db: Session) -> dict[str, Rule]:
    rules = list(db.scalars(select(Rule))) if hasattr(db, "scalars") else []
    if not rules:
        return {}
    return {rule.code: rule for rule in rules}


def _rule_enabled(catalog: dict[str, Rule], code: str) -> bool:
    rule = catalog.get(code)
    return bool(rule.enabled) if rule else True


def _rule_action(catalog: dict[str, Rule], code: str) -> str:
    rule = catalog.get(code)
    return str(rule.action) if rule else DEFAULT_RULES_BY_CODE[code].action


def _rule_severity(catalog: dict[str, Rule], code: str) -> str:
    rule = catalog.get(code)
    return str(rule.severity) if rule else DEFAULT_RULES_BY_CODE[code].severity


def _rule_category(catalog: dict[str, Rule], code: str) -> str:
    rule = catalog.get(code)
    return str(rule.category) if rule else DEFAULT_RULES_BY_CODE[code].category


def _rule_message(catalog: dict[str, Rule], code: str, fallback: str | None = None) -> str:
    rule = catalog.get(code)
    if rule and rule.message:
        return str(rule.message)
    return fallback or DEFAULT_RULES_BY_CODE[code].message


def _finding(catalog: dict[str, Rule], code: str, message: str | None = None, metadata: dict[str, Any] | None = None) -> RuleFinding | None:
    if not _rule_enabled(catalog, code):
        return None
    rule = catalog.get(code)
    return RuleFinding(
        rule_code=code,
        message=_rule_message(catalog, code, message),
        severity=_rule_severity(catalog, code),
        action=_rule_action(catalog, code),
        category=_rule_category(catalog, code),
        metadata=metadata or {},
        rule_id=rule.id if rule else None,
    )


def _add_finding(findings: list[RuleFinding], finding: RuleFinding | None) -> None:
    if finding:
        findings.append(finding)


def _news_restriction_finding(catalog: dict[str, Rule], status: dict[str, object]) -> RuleFinding | None:
    code = "NEWS_RESTRICTED_WINDOW"
    payload = news_finding_payload(status)
    if not payload or not _rule_enabled(catalog, code):
        return None
    rule_code, action, message, metadata = payload
    rule = catalog.get(code)
    return RuleFinding(
        rule_code=rule_code,
        message=_rule_message(catalog, code, message),
        severity=_rule_severity(catalog, code),
        action=action,
        category=_rule_category(catalog, code),
        metadata=metadata,
        rule_id=rule.id if rule else None,
    )


def _compare_values(left: object, operator: str, right: object) -> bool:
    if operator == "exists":
        return left is not None
    if operator == "missing":
        return left is None
    if operator in {"in", "not_in"}:
        values = right if isinstance(right, list) else [right]
        matched = left in values
        return matched if operator == "in" else not matched

    if operator in {"gt", "gte", "lt", "lte"}:
        left_decimal = _decimal(left)
        right_decimal = _decimal(right)
        if operator == "gt":
            return left_decimal > right_decimal
        if operator == "gte":
            return left_decimal >= right_decimal
        if operator == "lt":
            return left_decimal < right_decimal
        return left_decimal <= right_decimal

    if operator == "ne":
        return left != right
    return left == right


def _condition_matches(values: dict[str, object], condition: dict[str, object]) -> bool:
    field_name = str(condition.get("field", ""))
    if not field_name:
        return False
    operator = str(condition.get("operator", "eq"))
    right = values.get(str(condition["value_from"])) if "value_from" in condition else condition.get("value")
    return _compare_values(values.get(field_name), operator, right)


def _custom_scope_findings(catalog: dict[str, Rule], values: dict[str, object], scope_name: str) -> list[RuleFinding]:
    findings: list[RuleFinding] = []

    for code, rule in catalog.items():
        if code in DEFAULT_RULES_BY_CODE or not rule.enabled:
            continue
        config = rule.config or {}
        scope = str(config.get("scope", "pre_trade"))
        if scope not in {scope_name, "all"}:
            continue
        raw_conditions = config.get("conditions")
        conditions = raw_conditions if isinstance(raw_conditions, list) else [config]
        matches = [_condition_matches(values, condition) for condition in conditions if isinstance(condition, dict)]
        logic = str(config.get("logic", "all"))
        rule_matches = any(matches) if logic == "any" else bool(matches) and all(matches)
        if rule_matches:
            _add_finding(
                findings,
                _finding(
                    catalog,
                    code,
                    message=rule.message,
                    metadata={
                        "conditions": config.get("conditions", [{"field": config.get("field"), "operator": config.get("operator", "eq"), "value": config.get("value"), "value_from": config.get("value_from")}]),
                        "scope": scope,
                        "values": values,
                    },
                ),
            )

    return findings


def _custom_pre_trade_findings(catalog: dict[str, Rule], payload: PreTradeCheckIn) -> list[RuleFinding]:
    return _custom_scope_findings(
        catalog,
        {
            "symbol": payload.symbol,
            "order_type": payload.order_type,
            "lot": payload.lot,
            "entry_price": payload.entry_price,
            "sl": payload.sl,
            "tp": payload.tp,
            "risk_percent": payload.risk_percent,
            "risk_amount": payload.risk_amount,
            "ema34": payload.ema34,
            "ema89": payload.ema89,
        },
        "pre_trade",
    )


def _custom_pre_close_findings(catalog: dict[str, Rule], payload: PreCloseCheckIn) -> list[RuleFinding]:
    return _custom_scope_findings(
        catalog,
        {
            "ticket": payload.ticket,
            "symbol": payload.symbol,
            "position_type": payload.position_type,
            "lot": payload.lot,
            "entry_price": payload.entry_price,
            "current_price": payload.current_price,
            "profit": payload.profit,
            "sl": payload.sl,
            "tp": payload.tp,
            "candle_close": payload.candle_close,
            "ema34": payload.ema34,
            "ema89": payload.ema89,
            "close_reason": payload.close_reason,
        },
        "pre_close",
    )


def _daily_loss_percent(account: Account, daily_pnl: Decimal) -> Decimal:
    base_equity = _decimal(account.equity or account.balance) - daily_pnl
    if base_equity <= 0 or daily_pnl >= 0:
        return Decimal("0")
    return abs(daily_pnl) / base_equity * Decimal("100")


def _total_loss_percent(account: Account) -> Decimal:
    balance = _decimal(account.balance)
    equity = _decimal(account.equity)
    if balance <= 0 or equity >= balance:
        return Decimal("0")
    return (balance - equity) / balance * Decimal("100")


def _max_drawdown_percent(account: Account, stats: dict[str, float | int]) -> Decimal:
    balance = _decimal(account.balance or account.equity)
    drawdown = _decimal(stats.get("max_drawdown", 0))
    if balance <= 0 or drawdown <= 0:
        return Decimal("0")
    return drawdown / balance * Decimal("100")


def _latest_loss(db: Session, account_id: int) -> Trade | None:
    last_trade = latest_closed_trade(db, account_id)
    if last_trade and _decimal(last_trade.profit) < 0 and last_trade.close_time:
        return last_trade
    return None


def _cooldown_until(last_loss: Trade | None, minutes: int) -> datetime | None:
    if not last_loss or not last_loss.close_time:
        return None

    close_time = last_loss.close_time
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=now_utc().tzinfo)

    cooldown_end = close_time + timedelta(minutes=minutes)
    return cooldown_end if cooldown_end > now_utc() else None


def _risk_percent_from_order(
    account: Account,
    lot: Decimal,
    entry_price: Decimal | None,
    sl: Decimal | None,
    risk_percent: Decimal | None = None,
    risk_amount: Decimal | None = None,
) -> tuple[Decimal | None, dict[str, object]]:
    equity = _decimal(account.equity or account.balance)
    metadata: dict[str, object] = {"equity": equity}

    if risk_percent is not None:
        metadata["source"] = "payload.risk_percent"
        metadata["risk_percent"] = risk_percent
        if risk_amount is not None:
            metadata["risk_amount"] = risk_amount
        return risk_percent, metadata

    if risk_amount is not None:
        metadata["source"] = "payload.risk_amount"
        metadata["risk_amount"] = risk_amount
        if equity <= 0:
            return None, metadata
        return risk_amount / equity * Decimal("100"), metadata

    if entry_price is None or sl is None or equity <= 0:
        metadata["source"] = "unavailable"
        return None, metadata

    estimated_amount = abs(entry_price - sl) * lot
    metadata.update(
        {
            "source": "entry_sl_lot_estimate",
            "risk_amount": estimated_amount,
            "entry_price": entry_price,
            "sl": sl,
            "lot": lot,
        }
    )
    return estimated_amount / equity * Decimal("100"), metadata


def _core_findings(
    db: Session,
    account: Account,
    rule: RiskRule,
    stats: dict[str, float | int],
    catalog: dict[str, Rule],
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    day_start, day_end = trading_day_bounds()

    if not rule.allow_trading:
        _add_finding(findings, _finding(catalog, "PLATFORM_TRADING_ALLOWED", metadata={"allow_trading": False}))

    trades_today = int(stats["trades_today"])
    if trades_today >= int(rule.max_trades_per_day):
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_TRADES_PER_DAY",
                message=f"Trades today reached {trades_today} / {rule.max_trades_per_day}.",
                metadata={"trades_today": trades_today, "max_trades_per_day": int(rule.max_trades_per_day)},
            ),
        )

    daily_pnl = _decimal(stats["daily_pnl"])
    daily_loss_percent = _daily_loss_percent(account, daily_pnl)
    max_daily_loss_percent = _decimal(rule.max_daily_loss_percent)
    if max_daily_loss_percent > 0 and daily_loss_percent >= max_daily_loss_percent:
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_DAILY_LOSS",
                message=f"Daily equity loss is {daily_loss_percent:.2f}% and reached max {max_daily_loss_percent:.2f}%.",
                metadata={
                    "daily_pnl": daily_pnl,
                    "daily_loss_percent": daily_loss_percent,
                    "max_daily_loss_percent": max_daily_loss_percent,
                    "day_start": day_start,
                    "day_end": day_end,
                },
            ),
        )

    total_loss_percent = _total_loss_percent(account)
    max_total_loss_percent = _decimal(rule.max_total_loss_percent)
    if max_total_loss_percent > 0 and total_loss_percent >= max_total_loss_percent:
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_TOTAL_LOSS",
                message=f"Total equity loss is {total_loss_percent:.2f}% versus current balance.",
                metadata={
                    "balance": _decimal(account.balance),
                    "equity": _decimal(account.equity),
                    "total_loss_percent": total_loss_percent,
                    "max_total_loss_percent": max_total_loss_percent,
                },
            ),
        )

    max_drawdown_percent = _max_drawdown_percent(account, stats)
    if max_total_loss_percent > 0 and max_drawdown_percent >= max_total_loss_percent:
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_DRAWDOWN_LIMIT",
                message=f"Realized max drawdown is {max_drawdown_percent:.2f}% versus the configured {max_total_loss_percent:.2f}% limit.",
                metadata={
                    "max_drawdown": _decimal(stats.get("max_drawdown", 0)),
                    "max_drawdown_percent": max_drawdown_percent,
                    "max_total_loss_percent": max_total_loss_percent,
                },
            ),
        )

    consecutive_losses = int(stats["consecutive_losses"])
    if consecutive_losses >= int(rule.max_consecutive_losses):
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_CONSECUTIVE_LOSSES",
                message=f"Consecutive losses reached {consecutive_losses} / {rule.max_consecutive_losses}.",
                metadata={"consecutive_losses": consecutive_losses, "max_consecutive_losses": int(rule.max_consecutive_losses)},
            ),
        )

    last_loss = _latest_loss(db, account.id)
    cooldown_end = _cooldown_until(last_loss, int(rule.cooldown_minutes_after_loss))
    if cooldown_end:
        _add_finding(
            findings,
            _finding(
                catalog,
                "COOLDOWN_AFTER_LOSS",
                message=f"Post-loss cooldown is active until {cooldown_end.isoformat()}.",
                metadata={
                    "cooldown_until": cooldown_end,
                    "cooldown_minutes_after_loss": int(rule.cooldown_minutes_after_loss),
                    "last_loss_ticket": last_loss.ticket if last_loss else None,
                },
            ),
        )

    return findings


def _trade_findings(account: Account, rule: RiskRule, trade: Trade, catalog: dict[str, Rule]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []

    if _decimal(trade.lot) > _decimal(rule.max_lot):
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_LOT_SIZE",
                message=f"Trade {trade.ticket} lot size {trade.lot} exceeds max lot {rule.max_lot}.",
                metadata={"lot": _decimal(trade.lot), "max_lot": _decimal(rule.max_lot), "ticket": trade.ticket},
            ),
        )

    if trade.status == "open" and (trade.sl is None or _decimal(trade.sl) <= 0):
        _add_finding(
            findings,
            _finding(
                catalog,
                "NO_STOP_LOSS",
                message=f"Trade {trade.ticket} opened without stop loss.",
                metadata={"ticket": trade.ticket, "sl": trade.sl},
            ),
        )

    risk_percent, metadata = _risk_percent_from_order(
        account=account,
        lot=_decimal(trade.lot),
        entry_price=_decimal(trade.entry_price) if trade.entry_price is not None else None,
        sl=_decimal(trade.sl) if trade.sl is not None else None,
    )
    max_risk = _decimal(rule.max_risk_per_trade_percent)
    if risk_percent is not None and max_risk > 0 and risk_percent > max_risk:
        _add_finding(
            findings,
            _finding(
                catalog,
                "RISK_PER_TRADE",
                message=f"Trade {trade.ticket} risk is {risk_percent:.2f}% and exceeds max {max_risk:.2f}%.",
                metadata={**metadata, "max_risk_per_trade_percent": max_risk, "ticket": trade.ticket},
            ),
        )

    return findings


def _pre_trade_findings(db: Session, account: Account, payload: PreTradeCheckIn, catalog: dict[str, Rule]) -> list[RuleFinding]:
    rule = get_or_create_rule(db, account)
    stats = calculate_stats(db, account.id)
    findings = _core_findings(db, account, rule, stats, catalog)
    findings.extend(_custom_pre_trade_findings(catalog, payload))

    if payload.sl is None or _decimal(payload.sl) <= 0:
        _add_finding(findings, _finding(catalog, "NO_STOP_LOSS", metadata={"sl": payload.sl}))

    if _decimal(payload.lot) > _decimal(rule.max_lot):
        _add_finding(
            findings,
            _finding(
                catalog,
                "MAX_LOT_SIZE",
                message=f"Lot {payload.lot} exceeds max lot {rule.max_lot}.",
                metadata={"lot": payload.lot, "max_lot": rule.max_lot},
            ),
        )

    risk_percent, risk_metadata = _risk_percent_from_order(
        account=account,
        lot=_decimal(payload.lot),
        entry_price=_decimal(payload.entry_price),
        sl=_decimal(payload.sl) if payload.sl is not None else None,
        risk_percent=_decimal(payload.risk_percent) if payload.risk_percent is not None else None,
        risk_amount=_decimal(payload.risk_amount) if payload.risk_amount is not None else None,
    )
    max_risk = _decimal(rule.max_risk_per_trade_percent)
    if risk_percent is not None and max_risk > 0 and risk_percent > max_risk:
        _add_finding(
            findings,
            _finding(
                catalog,
                "RISK_PER_TRADE",
                message=f"Planned trade risk is {risk_percent:.2f}% and exceeds max {max_risk:.2f}%.",
                metadata={**risk_metadata, "max_risk_per_trade_percent": max_risk},
            ),
        )

    last_loss = _latest_loss(db, account.id)
    cooldown_end = _cooldown_until(last_loss, int(rule.cooldown_minutes_after_loss))
    if last_loss and cooldown_end:
        same_symbol = last_loss.symbol == payload.symbol
        larger_lot = _decimal(payload.lot) > _decimal(last_loss.lot)
        if same_symbol or larger_lot:
            _add_finding(
                findings,
                _finding(
                    catalog,
                    "REVENGE_TRADING",
                    message="Planned trade matches revenge trading pattern after a recent loss.",
                    metadata={
                        "cooldown_until": cooldown_end,
                        "last_loss_ticket": last_loss.ticket,
                        "last_loss_symbol": last_loss.symbol,
                        "planned_symbol": payload.symbol,
                        "last_loss_lot": _decimal(last_loss.lot),
                        "planned_lot": payload.lot,
                        "same_symbol": same_symbol,
                        "larger_lot": larger_lot,
                    },
                ),
            )

    daily_pnl = _decimal(stats["daily_pnl"])
    daily_loss_percent = _daily_loss_percent(account, daily_pnl)
    max_daily_loss_percent = _decimal(rule.max_daily_loss_percent)
    warning_threshold = max_daily_loss_percent * Decimal("0.80")
    if (
        max_daily_loss_percent > 0
        and daily_loss_percent >= warning_threshold
        and not any(finding.rule_code == "MAX_DAILY_LOSS" for finding in findings)
    ):
        findings.append(
            RuleFinding(
                rule_code="MAX_DAILY_LOSS_WARNING",
                message=f"Daily equity loss {daily_loss_percent:.2f}% is close to max {max_daily_loss_percent:.2f}%.",
                severity="warning",
                action="warn",
                category="ftmo",
                metadata={
                    "daily_pnl": daily_pnl,
                    "daily_loss_percent": daily_loss_percent,
                    "max_daily_loss_percent": max_daily_loss_percent,
                    "warning_threshold_percent": warning_threshold,
                },
            )
        )

    return findings


def _finding_out(finding: RuleFinding) -> dict[str, object]:
    return {
        "rule_code": finding.rule_code,
        "severity": finding.severity,
        "action": finding.action,
        "message": finding.message,
        "metadata": _jsonable(finding.metadata),
    }


def _build_result(account_id: int, findings: list[RuleFinding], metadata: dict[str, Any] | None = None) -> EvaluationResult:
    warnings = [finding for finding in findings if finding.is_warning and not finding.blocks]
    violations = [finding for finding in findings if finding.blocks]
    blocked = bool(violations)
    lock = any(finding.action == "lock" for finding in violations)
    decision = "LOCK" if lock else ("BLOCK" if blocked else ("WARN" if warnings else "ALLOW"))
    status = "locked" if lock else ("blocked" if blocked else ("warning" if warnings else "allowed"))
    primary = violations[0] if violations else (warnings[0] if warnings else None)
    reason = primary.rule_code if primary else "Allowed"
    message = primary.message if primary else "Allowed"
    return EvaluationResult(
        account_id=account_id,
        allowed=not blocked,
        blocked=blocked,
        status=status,
        decision=decision,
        reason=reason,
        message=message,
        warnings=warnings,
        violations=violations,
        metadata=metadata or {},
        checked_at=now_utc(),
    )


def _persist_result(db: Session, result: EvaluationResult, context: str) -> EvaluationResult:
    evaluation = RuleEvaluation(
        account_id=result.account_id,
        context=context,
        allowed=result.allowed,
        blocked=result.blocked,
        status=result.status,
        decision=result.decision,
        reason=result.reason,
        message=result.message,
        evaluation_metadata=_jsonable(result.metadata),
        checked_at=result.checked_at,
    )
    db.add(evaluation)
    db.flush()

    for finding in result.warnings + result.violations:
        db.add(
            RuleViolation(
                evaluation_id=evaluation.id,
                rule_id=finding.rule_id,
                account_id=result.account_id,
                rule_code=finding.rule_code,
                severity=finding.severity,
                action=finding.action,
                message=finding.message,
                violation_metadata=_jsonable(finding.metadata),
            )
        )
    db.flush()

    return EvaluationResult(
        account_id=result.account_id,
        allowed=result.allowed,
        blocked=result.blocked,
        status=result.status,
        decision=result.decision,
        reason=result.reason,
        message=result.message,
        warnings=result.warnings,
        violations=result.violations,
        metadata=result.metadata,
        checked_at=result.checked_at,
        evaluation_id=evaluation.id,
    )


def _result_payload(result: EvaluationResult, alerts_created: list[str] | None = None) -> dict[str, object]:
    cooldown_until = None
    for finding in result.violations + result.warnings:
        if "cooldown_until" in finding.metadata:
            cooldown_until = str(_jsonable(finding.metadata["cooldown_until"]))
            break

    return {
        "account_id": result.account_id,
        "allow_trading": result.allowed,
        "allowed": result.allowed,
        "blocked": result.blocked,
        "status": result.status,
        "decision": result.decision,
        "reason": result.reason,
        "message": result.message,
        "warnings": [_finding_out(finding) for finding in result.warnings],
        "violations": [_finding_out(finding) for finding in result.violations],
        "alerts_created": alerts_created or [],
        "metadata": _jsonable(result.metadata),
        "checked_at": result.checked_at,
        "cooldown_until": cooldown_until,
    }


def _cache_status(account_id: int, status: dict[str, str | bool | list[str] | None]) -> None:
    settings = get_settings()
    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        client.hset(f"risk:{account_id}", mapping={k: str(v) for k, v in status.items()})
        client.expire(f"risk:{account_id}", 3600)
    except Exception:
        logger.warning("Redis risk status cache unavailable", exc_info=True)


def evaluate_rules(db: Session, account: Account, trade: Trade | None = None) -> dict[str, object]:
    rule = get_or_create_rule(db, account)
    catalog = _rule_catalog(db)
    stats = calculate_stats(db, account.id)
    findings = _core_findings(db, account, rule, stats, catalog)
    if trade:
        findings.extend(_trade_findings(account, rule, trade, catalog))

    result = _build_result(account.id, findings, metadata={"stats": stats, "trade_id": trade.id if trade else None})
    result = _persist_result(db, result, context="trade_event" if trade else "manual_evaluate")

    alerts_created: list[str] = []
    for finding in result.violations:
        create_alert(db, account.id, finding.severity, finding.rule_code, finding.message)
        alerts_created.append(finding.rule_code)

    payload = _result_payload(result, alerts_created=alerts_created)
    _cache_status(
        account.id,
        {
            "status": str(payload["status"]),
            "allow_trading": bool(payload["allow_trading"]),
            "alerts_created": alerts_created,
            "cooldown_until": payload["cooldown_until"],
        },
    )
    return payload


def pre_trade_check(db: Session, account: Account, payload: PreTradeCheckIn) -> dict[str, object]:
    catalog = _rule_catalog(db)
    findings = _pre_trade_findings(db, account, payload, catalog)
    news_status = restriction_status(db, symbol=payload.symbol, action="new_order")
    _add_finding(findings, _news_restriction_finding(catalog, news_status))
    log_restriction_event(
        db,
        account_id=account.id,
        account_number=account.account_number,
        symbol=payload.symbol,
        action="new_order",
        status=news_status,
        context={
            "order_type": payload.order_type,
            "lot": payload.lot,
            "entry_price": payload.entry_price,
            "sl": payload.sl,
            "tp": payload.tp,
            "source": "pre_trade_check",
        },
    )
    result = _build_result(
        account.id,
        findings,
        metadata={
            "planned_order": {
                "symbol": payload.symbol,
                "order_type": payload.order_type,
                "lot": payload.lot,
                "entry_price": payload.entry_price,
                "sl": payload.sl,
                "tp": payload.tp,
                "risk_percent": payload.risk_percent,
                "risk_amount": payload.risk_amount,
                "ema34": payload.ema34,
                "ema89": payload.ema89,
            },
            "news_restriction": news_status,
        },
    )
    result = _persist_result(db, result, context="pre_trade")
    rule_codes = [finding.rule_code for finding in result.violations + result.warnings]
    legacy_reason = result.reason if result.blocked else ("Allowed" if not result.warnings else result.message)

    check = PreTradeCheck(
        account_id=account.id,
        symbol=payload.symbol,
        order_type=payload.order_type,
        lot=payload.lot,
        entry_price=payload.entry_price,
        sl=payload.sl,
        tp=payload.tp,
        allowed=result.allowed,
        reason=legacy_reason,
        rule_codes=rule_codes,
        details=_jsonable(
            {
                "status": result.status,
                "decision": result.decision,
                "message": result.message,
                "warnings": [_finding_out(finding) for finding in result.warnings],
                "violations": [_finding_out(finding) for finding in result.violations],
                "metadata": result.metadata,
            }
        ),
        rule_evaluation_id=result.evaluation_id,
    )
    db.add(check)
    db.flush()

    response = _result_payload(result)
    response.update(
        {
            "reason": legacy_reason,
            "alerts": rule_codes,
            "rule_evaluation_id": result.evaluation_id,
        }
    )
    return response


def pre_close_check(db: Session, account: Account, payload: PreCloseCheckIn) -> dict[str, object]:
    catalog = _rule_catalog(db)
    findings = _custom_pre_close_findings(catalog, payload)
    news_status = restriction_status(db, symbol=payload.symbol, action="manual_close")
    _add_finding(findings, _news_restriction_finding(catalog, news_status))
    log_restriction_event(
        db,
        account_id=account.id,
        account_number=account.account_number,
        symbol=payload.symbol,
        action="manual_close",
        status=news_status,
        context={
            "ticket": payload.ticket,
            "position_type": payload.position_type,
            "lot": payload.lot,
            "entry_price": payload.entry_price,
            "current_price": payload.current_price,
            "profit": payload.profit,
            "close_reason": payload.close_reason,
            "source": "pre_close_check",
        },
    )
    result = _build_result(
        account.id,
        findings,
        metadata={
            "close_request": {
                "ticket": payload.ticket,
                "symbol": payload.symbol,
                "position_type": payload.position_type,
                "lot": payload.lot,
                "entry_price": payload.entry_price,
                "current_price": payload.current_price,
                "profit": payload.profit,
                "sl": payload.sl,
                "tp": payload.tp,
                "candle_close": payload.candle_close,
                "ema34": payload.ema34,
                "ema89": payload.ema89,
                "close_reason": payload.close_reason,
            },
            "news_restriction": news_status,
        },
    )
    result = _persist_result(db, result, context="pre_close")
    rule_codes = [finding.rule_code for finding in result.violations + result.warnings]
    legacy_reason = result.reason if result.blocked else ("Allowed" if not result.warnings else result.message)
    response = _result_payload(result)
    response.update(
        {
            "reason": legacy_reason,
            "alerts": rule_codes,
            "rule_evaluation_id": result.evaluation_id,
        }
    )
    return response

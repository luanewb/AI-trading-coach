from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404
from app.db.session import get_db
from app.models import AccountSnapshot, PreTradeCheck, RiskRule, Rule, RuleEvaluation, RuleViolation
from app.schemas.dashboard import (
    AccountSnapshotPointOut,
    ActivityFilter,
    CountBudgetOut,
    CooldownStatusOut,
    MaxLotStatusOut,
    PreTradeHistoryItemOut,
    RiskActivityItemOut,
    RiskBudgetOut,
    RiskSummaryOut,
    RuleIndicatorOut,
    SnapshotRange,
)
from app.services.stats import calculate_stats, latest_closed_trade
from app.services.timezone import now_utc, trading_day_bounds

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _selected_account(db: Session, account_id: int | None):
    if account_id is None:
        return current_account_or_404(db)
    return current_account_or_404(db, account_id)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _percent(used: Decimal, limit: Decimal) -> float:
    if limit <= 0:
        return 0.0
    return float(min(Decimal("100"), max(Decimal("0"), used / limit * Decimal("100"))))


def _risk_budget(current: Decimal, used: Decimal, limit: Decimal) -> RiskBudgetOut:
    used = max(Decimal("0"), used)
    limit = max(Decimal("0"), limit)
    remaining = max(Decimal("0"), limit - used)
    percent_used = _percent(used, limit)
    return RiskBudgetOut(
        current=_money(current),
        used=_money(used),
        limit=_money(limit),
        remaining=_money(remaining),
        percent_used=percent_used,
        percent_remaining=max(0.0, 100.0 - percent_used),
    )


def _count_budget(current: int, limit: int) -> CountBudgetOut:
    limit = max(0, int(limit))
    current = max(0, int(current))
    remaining = max(0, limit - current)
    percent_used = float(min(100, max(0, (current / limit * 100) if limit else 0)))
    return CountBudgetOut(
        current=current,
        limit=limit,
        remaining=remaining,
        percent_used=percent_used,
        percent_remaining=max(0.0, 100.0 - percent_used),
    )


def _risk_rule_or_default(db: Session, account_id: int) -> RiskRule:
    rule = db.scalar(select(RiskRule).where(RiskRule.account_id == account_id))
    if rule:
        return rule
    return RiskRule(
        account_id=account_id,
        max_trades_per_day=5,
        max_daily_loss_percent=Decimal("5"),
        max_total_loss_percent=Decimal("10"),
        max_consecutive_losses=3,
        cooldown_minutes_after_loss=30,
        max_lot=Decimal("1"),
        max_risk_per_trade_percent=Decimal("1"),
        allow_trading=True,
    )


def _downsample_snapshots(snapshots: list[AccountSnapshot], limit: int) -> list[AccountSnapshot]:
    if len(snapshots) <= limit:
        return snapshots
    if limit <= 1:
        return snapshots[-1:]
    last_index = len(snapshots) - 1
    indexes = {round(index * last_index / (limit - 1)) for index in range(limit)}
    indexes.add(last_index)
    return [snapshots[index] for index in sorted(indexes)]


def _cooldown_until(db: Session, account_id: int, minutes: int):
    if minutes <= 0:
        return None
    last_trade = latest_closed_trade(db, account_id)
    if not last_trade or _decimal(last_trade.profit) >= 0 or not last_trade.close_time:
        return None
    close_time = last_trade.close_time
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=now_utc().tzinfo)
    cooldown_end = close_time + timedelta(minutes=minutes)
    return cooldown_end if cooldown_end > now_utc() else None


def _metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _pre_trade_counts(details: dict[str, object]) -> tuple[int, int]:
    warnings = details.get("warnings")
    violations = details.get("violations")
    return (
        len(warnings) if isinstance(warnings, list) else 0,
        len(violations) if isinstance(violations, list) else 0,
    )


def _pre_trade_decision(check: PreTradeCheck) -> str:
    details = check.details or {}
    decision = details.get("decision")
    if decision:
        return str(decision)
    return "ALLOW" if check.allowed else "BLOCK"


def _pre_trade_primary_action(check: PreTradeCheck) -> str:
    details = check.details or {}
    for key in ("violations", "warnings"):
        findings = details.get(key)
        if isinstance(findings, list) and findings:
            first = findings[0]
            if isinstance(first, dict) and first.get("action"):
                return str(first["action"])
    return "allow" if check.allowed else "block"


def _matches_filter(item: RiskActivityItemOut, activity_filter: ActivityFilter) -> bool:
    if activity_filter == "all":
        return True
    if activity_filter == "resolved":
        return item.status == "resolved"
    if activity_filter == "warning":
        return item.action == "warn" or item.severity == "warning"
    if activity_filter == "blocked":
        return item.action == "block" or item.decision == "BLOCK"
    if activity_filter == "locked":
        return item.action == "lock" or item.decision == "LOCK"
    return True


@router.get("/risk-summary", response_model=RiskSummaryOut)
def risk_summary(db: Session = Depends(get_db), account_id: int | None = None) -> RiskSummaryOut:
    account = _selected_account(db, account_id)
    rule = _risk_rule_or_default(db, account.id)
    stats = calculate_stats(db, account.id)
    now = now_utc()

    balance = _decimal(account.balance)
    equity = _decimal(account.equity)
    daily_pnl = _decimal(stats["daily_pnl"])
    daily_loss_used = abs(min(daily_pnl, Decimal("0")))
    daily_loss_limit = balance * _decimal(rule.max_daily_loss_percent) / Decimal("100")
    realized_drawdown = _decimal(stats.get("max_drawdown", 0))
    current_drawdown = max(Decimal("0"), balance - equity)
    total_drawdown_used = max(realized_drawdown, current_drawdown)
    total_drawdown_limit = balance * _decimal(rule.max_total_loss_percent) / Decimal("100")
    daily_loss = _risk_budget(daily_pnl, daily_loss_used, daily_loss_limit)
    total_drawdown = _risk_budget(current_drawdown, total_drawdown_used, total_drawdown_limit)
    trades_today = _count_budget(int(stats["trades_today"]), int(rule.max_trades_per_day))
    consecutive_losses = _count_budget(int(stats["consecutive_losses"]), int(rule.max_consecutive_losses))

    cooldown_end = _cooldown_until(db, account.id, int(rule.cooldown_minutes_after_loss))
    cooldown_remaining = int(max(0, (cooldown_end - now).total_seconds())) if cooldown_end else 0
    cooldown = CooldownStatusOut(active=bool(cooldown_end), cooldown_until=cooldown_end, remaining_seconds=cooldown_remaining)

    latest_check = db.scalar(
        select(PreTradeCheck)
        .where(PreTradeCheck.account_id == account.id)
        .order_by(PreTradeCheck.created_at.desc(), PreTradeCheck.id.desc())
        .limit(1)
    )
    active_violations = list(
        db.scalars(
            select(RuleViolation)
            .where(RuleViolation.account_id == account.id, RuleViolation.is_resolved.is_(False))
            .order_by(RuleViolation.created_at.desc(), RuleViolation.id.desc())
            .limit(10)
        )
    )

    lock_active = any(item.action == "lock" for item in active_violations) or total_drawdown.percent_used >= 100
    block_active = (
        not rule.allow_trading
        or daily_loss.percent_used >= 100
        or trades_today.percent_used >= 100
        or consecutive_losses.percent_used >= 100
        or cooldown.active
        or any(item.action == "block" for item in active_violations)
    )
    warning_active = (
        daily_loss.percent_used >= 80
        or total_drawdown.percent_used >= 80
        or trades_today.percent_used >= 80
        or consecutive_losses.percent_used >= 80
        or any(item.action == "warn" or item.severity == "warning" for item in active_violations)
    )

    if lock_active:
        trading_status = "locked"
        status_reason = "A lock-level restriction is active."
    elif block_active:
        trading_status = "blocked"
        status_reason = "At least one blocking restriction is active."
    elif warning_active:
        trading_status = "warning"
        status_reason = "Risk is near a configured limit or a warning is active."
    else:
        trading_status = "allowed"
        status_reason = "Trading is inside configured risk limits."

    return RiskSummaryOut(
        account_id=account.id,
        account_number=account.account_number,
        trading_status=trading_status,
        status_label=trading_status.title(),
        status_reason=status_reason,
        current_daily_pnl=_money(daily_pnl),
        daily_loss=daily_loss,
        total_drawdown=total_drawdown,
        trades_today=trades_today,
        consecutive_losses=consecutive_losses,
        cooldown=cooldown,
        max_lot=MaxLotStatusOut(
            planned_lot=_decimal(latest_check.lot) if latest_check else None,
            configured_max_lot=_decimal(rule.max_lot),
        ),
        active_restrictions=[
            {
                "rule_code": item.rule_code,
                "severity": item.severity,
                "action": item.action,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in active_violations
        ],
        checked_at=now,
    )


@router.get("/risk-activity", response_model=list[RiskActivityItemOut])
def risk_activity(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    filter: ActivityFilter = "all",
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RiskActivityItemOut]:
    account = _selected_account(db, account_id)
    violation_rows = db.execute(
        select(RuleViolation, RuleEvaluation)
        .join(RuleEvaluation, RuleEvaluation.id == RuleViolation.evaluation_id)
        .where(RuleViolation.account_id == account.id)
        .order_by(RuleViolation.created_at.desc(), RuleViolation.id.desc())
        .limit(limit)
    ).all()
    checks = list(
        db.scalars(
            select(PreTradeCheck)
            .where(PreTradeCheck.account_id == account.id)
            .order_by(PreTradeCheck.created_at.desc(), PreTradeCheck.id.desc())
            .limit(limit)
        )
    )

    items: list[RiskActivityItemOut] = []
    for violation, evaluation in violation_rows:
        metadata = violation.violation_metadata or {}
        items.append(
            RiskActivityItemOut(
                id=f"violation-{violation.id}",
                timestamp=violation.created_at,
                rule_code=violation.rule_code,
                severity=violation.severity,
                action=violation.action,
                message=violation.message,
                source="rule_violation",
                decision=evaluation.decision if evaluation else None,
                symbol=_metadata_value(metadata, "symbol") or _metadata_value(metadata, "planned_symbol"),
                ticket=_metadata_value(metadata, "ticket") or _metadata_value(metadata, "last_loss_ticket"),
                status="resolved" if violation.is_resolved else "active",
            )
        )

    for check in checks:
        details = check.details or {}
        decision = _pre_trade_decision(check)
        action = _pre_trade_primary_action(check)
        if check.allowed and action == "allow":
            continue
        severity = "warning" if action == "warn" else "critical"
        items.append(
            RiskActivityItemOut(
                id=f"pre-trade-{check.id}",
                timestamp=check.created_at,
                rule_code=check.rule_codes[0] if check.rule_codes else check.reason,
                severity=str(details.get("severity") or severity),
                action=action,
                message=str(details.get("message") or check.reason),
                source="pre_trade_check",
                decision=decision,
                symbol=check.symbol,
                ticket=None,
                status="active",
            )
        )

    filtered = [item for item in items if _matches_filter(item, filter)]
    return sorted(filtered, key=lambda item: item.timestamp, reverse=True)[:limit]


@router.get("/account-snapshots", response_model=list[AccountSnapshotPointOut])
def account_snapshots(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    range: SnapshotRange = "7d",
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[AccountSnapshotPointOut]:
    account = _selected_account(db, account_id)
    hours = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}[range]
    since = now_utc() - timedelta(hours=hours)
    snapshots = list(
        db.scalars(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account.id, AccountSnapshot.timestamp >= since)
            .order_by(AccountSnapshot.timestamp.asc(), AccountSnapshot.id.asc())
        )
    )
    snapshots = _downsample_snapshots(snapshots, limit)

    peak = Decimal("0")
    points: list[AccountSnapshotPointOut] = []
    for snapshot in snapshots:
        equity = _decimal(snapshot.equity)
        peak = max(peak, equity)
        drawdown = max(Decimal("0"), peak - equity)
        drawdown_percent = float(drawdown / peak * Decimal("100")) if peak > 0 else 0.0
        points.append(
            AccountSnapshotPointOut(
                id=snapshot.id,
                timestamp=snapshot.timestamp,
                balance=_decimal(snapshot.balance),
                equity=equity,
                drawdown=drawdown,
                drawdown_percent=drawdown_percent,
            )
        )
    return points


@router.get("/pre-trade-history", response_model=list[PreTradeHistoryItemOut])
def pre_trade_history(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PreTradeHistoryItemOut]:
    account = _selected_account(db, account_id)
    checks = list(
        db.scalars(
            select(PreTradeCheck)
            .where(PreTradeCheck.account_id == account.id)
            .order_by(PreTradeCheck.created_at.desc(), PreTradeCheck.id.desc())
            .limit(limit)
        )
    )
    items: list[PreTradeHistoryItemOut] = []
    for check in checks:
        warning_count, violation_count = _pre_trade_counts(check.details or {})
        items.append(
            PreTradeHistoryItemOut(
                id=check.id,
                timestamp=check.created_at,
                symbol=check.symbol,
                side=check.order_type,
                lot=_decimal(check.lot),
                entry_price=_decimal(check.entry_price) if check.entry_price is not None else None,
                sl=_decimal(check.sl) if check.sl is not None else None,
                tp=_decimal(check.tp) if check.tp is not None else None,
                decision=_pre_trade_decision(check),
                allowed=check.allowed,
                reason=check.reason,
                warning_count=warning_count,
                violation_count=violation_count,
                rule_codes=check.rule_codes,
                details=check.details or {},
            )
        )
    return items


@router.get("/rule-indicators", response_model=list[RuleIndicatorOut])
def rule_indicators(db: Session = Depends(get_db), account_id: int | None = None) -> list[RuleIndicatorOut]:
    account = _selected_account(db, account_id)
    catalog = list(db.scalars(select(Rule).order_by(Rule.code)))
    day_start, day_end = trading_day_bounds()
    today_counts = {
        code: count
        for code, count in db.execute(
            select(RuleViolation.rule_code, func.count(RuleViolation.id))
            .where(
                RuleViolation.account_id == account.id,
                RuleViolation.created_at >= day_start,
                RuleViolation.created_at <= day_end,
            )
            .group_by(RuleViolation.rule_code)
        ).all()
    }
    recent_violations = list(
        db.scalars(
            select(RuleViolation)
            .where(RuleViolation.account_id == account.id)
            .order_by(RuleViolation.created_at.desc(), RuleViolation.id.desc())
            .limit(1000)
        )
    )

    latest_by_code: dict[str, RuleViolation] = {}
    active_by_code: dict[str, RuleViolation] = {}
    for violation in recent_violations:
        latest_by_code.setdefault(violation.rule_code, violation)
        if not violation.is_resolved:
            active_by_code.setdefault(violation.rule_code, violation)

    return [
        RuleIndicatorOut(
            rule_code=rule.code,
            enabled=rule.enabled,
            latest_trigger_time=latest_by_code[rule.code].created_at if rule.code in latest_by_code else None,
            trigger_count_today=int(today_counts.get(rule.code, 0)),
            latest_action_taken=latest_by_code[rule.code].action if rule.code in latest_by_code else None,
            current_active_state=active_by_code[rule.code].action if rule.code in active_by_code else "inactive",
        )
        for rule in catalog
    ]

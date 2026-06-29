import logging
from datetime import timedelta
from decimal import Decimal

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account, Alert, PreTradeCheck, RiskRule, Trade
from app.schemas.pre_trade import PreTradeCheckIn
from app.services.stats import calculate_stats, latest_closed_trade
from app.services.telegram import send_telegram_alert
from app.services.timezone import now_utc, trading_day_bounds

logger = logging.getLogger(__name__)


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


def _daily_loss_percent(account: Account, daily_pnl: Decimal) -> Decimal:
    base_equity = Decimal(account.equity or account.balance or 0) - daily_pnl
    if base_equity <= 0 or daily_pnl >= 0:
        return Decimal("0")
    return abs(daily_pnl) / base_equity * Decimal("100")


def _total_loss_percent(account: Account) -> Decimal:
    balance = Decimal(account.balance or 0)
    equity = Decimal(account.equity or 0)
    if balance <= 0 or equity >= balance:
        return Decimal("0")
    return (balance - equity) / balance * Decimal("100")


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
    stats = calculate_stats(db, account.id)
    alerts_created: list[str] = []
    allow_trading = bool(rule.allow_trading)
    cooldown_until: str | None = None

    day_start, day_end = trading_day_bounds()
    daily_pnl = Decimal(str(stats["daily_pnl"]))
    daily_loss_percent = _daily_loss_percent(account, daily_pnl)
    total_loss_percent = _total_loss_percent(account)

    checks: list[tuple[bool, str, str, str, bool]] = [
        (
            int(stats["trades_today"]) >= rule.max_trades_per_day,
            "warning",
            "OVERTRADE",
            f"Trades today reached {stats['trades_today']} / {rule.max_trades_per_day}.",
            True,
        ),
        (
            daily_loss_percent >= Decimal(rule.max_daily_loss_percent),
            "critical",
            "DAILY_LOSS_LIMIT",
            f"Daily equity loss is {daily_loss_percent:.2f}% from the {day_start.isoformat()} to {day_end.isoformat()} FTMO day window.",
            True,
        ),
        (
            total_loss_percent >= Decimal(rule.max_total_loss_percent),
            "critical",
            "TOTAL_LOSS_LIMIT",
            f"Total equity loss is {total_loss_percent:.2f}% versus current balance.",
            True,
        ),
        (
            int(stats["consecutive_losses"]) >= rule.max_consecutive_losses,
            "warning",
            "CONSECUTIVE_LOSSES",
            f"Consecutive losses reached {stats['consecutive_losses']} / {rule.max_consecutive_losses}.",
            True,
        ),
    ]

    for condition, severity, alert_type, message, should_block in checks:
        if condition:
            create_alert(db, account.id, severity, alert_type, message)
            alerts_created.append(alert_type)
            if should_block:
                allow_trading = False

    last_loss = latest_closed_trade(db, account.id)
    if last_loss and Decimal(last_loss.profit or 0) < 0 and last_loss.close_time:
        close_time = last_loss.close_time
        if close_time.tzinfo is None:
            close_time = close_time.replace(tzinfo=now_utc().tzinfo)
        cooldown_end = close_time + timedelta(minutes=rule.cooldown_minutes_after_loss)
        if cooldown_end > now_utc():
            cooldown_until = cooldown_end.isoformat()
            if trade and trade.status == "open":
                create_alert(db, account.id, "warning", "REVENGE_TRADE", "A new trade was opened during the post-loss cooldown window.")
                alerts_created.append("REVENGE_TRADE")

    if trade:
        if Decimal(trade.lot or 0) > Decimal(rule.max_lot):
            create_alert(db, account.id, "warning", "LOT_TOO_HIGH", f"Trade {trade.ticket} lot size {trade.lot} exceeds max lot {rule.max_lot}.")
            alerts_created.append("LOT_TOO_HIGH")
        if trade.status == "open" and trade.sl is None:
            create_alert(db, account.id, "critical", "NO_STOP_LOSS", f"Trade {trade.ticket} opened without stop loss.")
            alerts_created.append("NO_STOP_LOSS")

    status = "blocked" if not allow_trading else ("cooldown" if cooldown_until else "ok")
    result: dict[str, object] = {
        "account_id": account.id,
        "allow_trading": allow_trading,
        "status": status,
        "alerts_created": alerts_created,
        "cooldown_until": cooldown_until,
    }
    _cache_status(account.id, result)
    return result


def pre_trade_check(db: Session, account: Account, payload: PreTradeCheckIn) -> dict[str, object]:
    rule = get_or_create_rule(db, account)
    stats = calculate_stats(db, account.id)
    alerts: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if not rule.allow_trading:
        blockers.append("Trading is disabled by risk rule configuration.")
        alerts.append("TRADING_DISABLED")

    if payload.sl is None or Decimal(payload.sl) <= 0:
        blockers.append("Stop loss is required before sending an order.")
        alerts.append("NO_STOP_LOSS")

    if Decimal(payload.lot) > Decimal(rule.max_lot):
        blockers.append(f"Lot {payload.lot} exceeds max lot {rule.max_lot}.")
        alerts.append("LOT_TOO_HIGH")

    if int(stats["trades_today"]) >= int(rule.max_trades_per_day):
        blockers.append(f"Trades today reached {stats['trades_today']} / {rule.max_trades_per_day}.")
        alerts.append("OVERTRADE")

    last_loss = latest_closed_trade(db, account.id)
    if last_loss and Decimal(last_loss.profit or 0) < 0 and last_loss.close_time:
        close_time = last_loss.close_time
        if close_time.tzinfo is None:
            close_time = close_time.replace(tzinfo=now_utc().tzinfo)
        cooldown_end = close_time + timedelta(minutes=rule.cooldown_minutes_after_loss)
        if cooldown_end > now_utc():
            blockers.append(f"Post-loss cooldown is active until {cooldown_end.isoformat()}.")
            alerts.append("COOLDOWN_ACTIVE")

    daily_pnl = Decimal(str(stats["daily_pnl"]))
    daily_loss_percent = _daily_loss_percent(account, daily_pnl)
    max_daily_loss_percent = Decimal(rule.max_daily_loss_percent)
    warning_threshold = max_daily_loss_percent * Decimal("0.80")
    if daily_loss_percent >= max_daily_loss_percent:
        blockers.append(f"Daily equity loss {daily_loss_percent:.2f}% reached max {max_daily_loss_percent:.2f}%.")
        alerts.append("DAILY_LOSS_LIMIT")
    elif max_daily_loss_percent > 0 and daily_loss_percent >= warning_threshold:
        warnings.append(f"Daily equity loss {daily_loss_percent:.2f}% is close to max {max_daily_loss_percent:.2f}%.")
        alerts.append("DAILY_LOSS_WARNING")

    critical_alert = db.scalar(
        select(Alert)
        .where(Alert.account_id == account.id, Alert.severity == "critical", Alert.is_resolved.is_(False))
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    if critical_alert:
        blockers.append(f"Active critical alert: {critical_alert.type}.")
        alerts.append("ACTIVE_CRITICAL_ALERT")

    allowed = not blockers
    reason = "Allowed"
    if blockers:
        reason = " ".join(blockers)
    elif warnings:
        reason = "Allowed with warning: " + " ".join(warnings)

    check = PreTradeCheck(
        account_id=account.id,
        symbol=payload.symbol,
        order_type=payload.order_type,
        lot=payload.lot,
        entry_price=payload.entry_price,
        sl=payload.sl,
        tp=payload.tp,
        allowed=allowed,
        reason=reason,
    )
    db.add(check)
    db.flush()
    return {"allowed": allowed, "reason": reason, "alerts": alerts}

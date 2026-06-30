from decimal import Decimal

from sqlalchemy import Select, and_, asc, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models import Account, Trade
from app.services.timezone import trading_day_bounds

SEED_DEMO_ACCOUNT_NUMBERS = {"100001"}


def _closed_trade_query(account_id: int | None = None) -> Select[tuple[Trade]]:
    stmt = select(Trade).where(Trade.status == "closed")
    if account_id:
        stmt = stmt.where(Trade.account_id == account_id)
    return stmt


def executed_trade_filter():
    return or_(Trade.status == "closed", Trade.deal_id.is_not(None), Trade.position_id.is_not(None))


def is_seed_demo_account(account: Account | None) -> bool:
    if not account:
        return False
    return str(account.account_number) in SEED_DEMO_ACCOUNT_NUMBERS


def real_account_filter():
    return not_(Account.account_number.in_(SEED_DEMO_ACCOUNT_NUMBERS))


def get_current_account(db: Session) -> Account | None:
    return db.scalar(
        select(Account)
        .where(real_account_filter())
        .order_by(Account.updated_at.desc(), Account.id.desc())
        .limit(1)
    )


def count_consecutive_losses(trades: list[Trade]) -> int:
    losses = 0
    for trade in reversed(trades):
        if Decimal(trade.profit or 0) < 0:
            losses += 1
        else:
            break
    return losses


def calculate_stats(db: Session, account_id: int | None = None) -> dict[str, float | int]:
    trades = list(db.scalars(_closed_trade_query(account_id).order_by(asc(Trade.close_time), asc(Trade.id))))
    total_trades = len(trades)
    wins = [trade for trade in trades if Decimal(trade.profit or 0) > 0]
    losses = [trade for trade in trades if Decimal(trade.profit or 0) < 0]
    gross_profit = sum((Decimal(trade.profit or 0) for trade in wins), Decimal("0"))
    gross_loss = abs(sum((Decimal(trade.profit or 0) for trade in losses), Decimal("0")))
    r_values = [Decimal(trade.r_multiple) for trade in trades if trade.r_multiple is not None]

    equity_curve = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for trade in trades:
        equity_curve += Decimal(trade.profit or 0)
        peak = max(peak, equity_curve)
        max_drawdown = min(max_drawdown, equity_curve - peak)

    day_start, day_end = trading_day_bounds()
    opened_today = or_(
        and_(Trade.open_time.is_not(None), Trade.open_time >= day_start, Trade.open_time <= day_end),
        and_(Trade.open_time.is_(None), Trade.created_at >= day_start, Trade.created_at <= day_end),
    )
    closed_today = and_(Trade.close_time >= day_start, Trade.close_time <= day_end, Trade.status == "closed")
    open_execution_today = and_(Trade.status != "closed", opened_today, executed_trade_filter())
    trades_today_stmt = select(func.count(Trade.id)).where(or_(closed_today, open_execution_today))
    today_pnl_stmt = select(func.coalesce(func.sum(Trade.profit), 0)).where(
        Trade.close_time >= day_start,
        Trade.close_time <= day_end,
        Trade.status == "closed",
    )
    if account_id:
        trades_today_stmt = trades_today_stmt.where(Trade.account_id == account_id)
        today_pnl_stmt = today_pnl_stmt.where(Trade.account_id == account_id)
    trades_today = db.scalar(trades_today_stmt)
    daily_pnl = db.scalar(today_pnl_stmt)

    return {
        "total_trades": total_trades,
        "win_rate": float((len(wins) / total_trades) * 100) if total_trades else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else float(gross_profit > 0),
        "average_r": float(sum(r_values, Decimal("0")) / len(r_values)) if r_values else 0.0,
        "max_drawdown": float(abs(max_drawdown)),
        "trades_today": int(trades_today or 0),
        "daily_pnl": float(daily_pnl or 0),
        "consecutive_losses": count_consecutive_losses(trades),
    }


def latest_closed_trade(db: Session, account_id: int) -> Trade | None:
    return db.scalar(
        select(Trade)
        .where(Trade.account_id == account_id, Trade.status == "closed")
        .order_by(Trade.close_time.desc().nullslast(), Trade.id.desc())
        .limit(1)
    )

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Trade
from app.services.stats import count_consecutive_losses


def trade(ticket: str, net_profit: str, close_time: datetime) -> Trade:
    return Trade(
        account_id=1,
        ticket=ticket,
        symbol="XAUUSD",
        order_type="SELL",
        lot=Decimal("0.10"),
        profit=Decimal(net_profit),
        commission=Decimal("0"),
        swap=Decimal("0"),
        status="closed",
        close_time=close_time,
    )


def test_consecutive_losses_reset_at_start_of_trading_day() -> None:
    day_start = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 7, 15, 23, 59, 59, tzinfo=timezone.utc)
    trades = [
        trade("YESTERDAY-LOSS", "-100", day_start - timedelta(minutes=1)),
        trade("TODAY-LOSS", "-100", day_start + timedelta(hours=1)),
    ]

    losses = count_consecutive_losses(trades, day_start=day_start, day_end=day_end)

    assert losses == 1


def test_two_consecutive_losses_in_same_trading_day_are_counted() -> None:
    day_start = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 7, 15, 23, 59, 59, tzinfo=timezone.utc)
    trades = [
        trade("LOSS-1", "-100", day_start + timedelta(hours=1)),
        trade("LOSS-2", "-100", day_start + timedelta(hours=2)),
    ]

    losses = count_consecutive_losses(trades, day_start=day_start, day_end=day_end)

    assert losses == 2


def test_non_losing_trade_resets_same_day_loss_streak() -> None:
    day_start = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 7, 15, 23, 59, 59, tzinfo=timezone.utc)
    trades = [
        trade("LOSS-1", "-100", day_start + timedelta(hours=1)),
        trade("BREAKEVEN", "0", day_start + timedelta(hours=2)),
    ]

    losses = count_consecutive_losses(trades, day_start=day_start, day_end=day_end)

    assert losses == 0

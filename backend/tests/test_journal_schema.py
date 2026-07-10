from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.journal import TradeOut


def trade_payload(**overrides):
    values = {
        "id": 1,
        "account_id": 2,
        "ticket": "163027493",
        "deal_id": None,
        "position_id": None,
        "symbol": "XAUUSD",
        "order_type": "ORDER_TYPE_BUY",
        "lot": Decimal("0.98"),
        "entry_price": Decimal("4027.56"),
        "sl": Decimal("4049.00"),
        "tp": Decimal("3951.70"),
        "close_price": Decimal("4027.56"),
        "profit": Decimal("2232.44"),
        "commission": Decimal("-2.76"),
        "swap": Decimal("0"),
        "r_multiple": Decimal("0"),
        "status": "closed",
        "open_time": datetime(2026, 6, 29, 18, 19, 1, tzinfo=timezone.utc),
        "close_time": datetime(2026, 6, 29, 18, 19, 1, tzinfo=timezone.utc),
        "source": "mt5",
        "strategy": None,
        "setup_name": None,
        "emotion": None,
        "mistake_tags": [],
        "notes": None,
        "journal_link": None,
        "journal_entry_mode": "notion",
        "created_at": datetime(2026, 6, 29, 15, 19, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 30, 11, 0, 34, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return values


def test_trade_out_infers_sell_when_sl_above_entry_and_tp_below_entry():
    trade = TradeOut.model_validate(trade_payload(r_multiple=None))

    assert trade.order_type == "SELL"
    assert trade.r_multiple is None


def test_trade_out_infers_buy_when_sl_below_entry_and_tp_above_entry():
    trade = TradeOut.model_validate(
        trade_payload(
            order_type="ORDER_TYPE_SELL",
            entry_price=Decimal("3997.95"),
            sl=Decimal("3973.38"),
            tp=Decimal("4120.80"),
        )
    )

    assert trade.order_type == "BUY"


def test_trade_out_infers_sell_from_tp_when_stop_has_trailed_below_entry():
    trade = TradeOut.model_validate(
        trade_payload(
            order_type="ORDER_TYPE_BUY",
            entry_price=Decimal("4122.81"),
            sl=Decimal("4122.04"),
            tp=Decimal("4046.48"),
            close_price=Decimal("4046.46"),
            profit=Decimal("5649.90"),
            r_multiple=None,
        )
    )

    assert trade.order_type == "SELL"
    assert trade.r_multiple is not None
    assert trade.r_multiple.quantize(Decimal("0.01")) == Decimal("99.16")


def test_trade_out_recalculates_realized_r_from_close_price():
    trade = TradeOut.model_validate(trade_payload(close_price=Decimal("4006.12"), profit=Decimal("2101.12"), r_multiple=None))

    assert trade.order_type == "SELL"
    assert trade.r_multiple == Decimal("1")


def test_trade_out_preserves_stored_r_multiple_override():
    trade = TradeOut.model_validate(
        trade_payload(close_price=Decimal("4117.95"), profit=Decimal("72.60"), r_multiple=Decimal("0"))
    )

    assert trade.r_multiple == Decimal("0")


def test_trade_out_includes_screenshot_links():
    trade = TradeOut.model_validate(
        trade_payload(
            before_entry_image_url="https://www.tradingview.com/x/3pqxSTjB/",
            after_exit_image_url="https://www.tradingview.com/x/afterExit/",
            analysis_image_url="https://www.tradingview.com/x/analysis/",
        )
    )

    assert trade.before_entry_image_url == "https://www.tradingview.com/x/3pqxSTjB/"
    assert trade.after_exit_image_url == "https://www.tradingview.com/x/afterExit/"
    assert trade.analysis_image_url == "https://www.tradingview.com/x/analysis/"


def test_trade_out_includes_notion_journal_link_and_mode():
    trade = TradeOut.model_validate(
        trade_payload(
            journal_link="https://www.notion.so/trade-journal-entry",
            journal_entry_mode="notion",
        )
    )

    assert trade.journal_link == "https://www.notion.so/trade-journal-entry"
    assert trade.journal_entry_mode == "notion"


def test_trade_out_exposes_net_profit_after_costs():
    trade = TradeOut.model_validate(
        trade_payload(
            profit=Decimal("72.60"),
            commission=Decimal("-3.80"),
            swap=Decimal("0"),
        )
    )

    assert trade.net_profit == Decimal("68.80")

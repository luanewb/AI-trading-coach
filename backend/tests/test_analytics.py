from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import analytics as analytics_api
from app.db.session import get_db
from app.main import app
from app.models import Account, Trade
from app.services.analytics import AnalyticsDataset, build_breakdown, build_insights, build_overview, calculate_metrics


class FakeSession:
    def __init__(self, account=None):
        self.account = account

    def scalar(self, _stmt):
        return self.account


def _account(account_id: int = 1) -> Account:
    return Account(
        id=account_id,
        account_number=str(200000 + account_id),
        broker="Demo",
        server="Demo",
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        margin=Decimal("0"),
        free_margin=Decimal("10000"),
    )


def _trade(ticket: str, profit: str, **overrides) -> Trade:
    opened_at = overrides.pop("open_time", datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc))
    values = {
        "id": int(ticket),
        "account_id": 1,
        "ticket": ticket,
        "symbol": "XAUUSD",
        "order_type": "BUY",
        "lot": Decimal("0.10"),
        "entry_price": Decimal("2300"),
        "sl": Decimal("2290"),
        "tp": Decimal("2330"),
        "close_price": Decimal("2310") if Decimal(profit) >= 0 else Decimal("2290"),
        "profit": Decimal(profit),
        "commission": Decimal("0"),
        "swap": Decimal("0"),
        "r_multiple": Decimal("1.0") if Decimal(profit) > 0 else Decimal("-1.0"),
        "status": "closed",
        "open_time": opened_at,
        "close_time": opened_at + timedelta(hours=1),
        "source": "mt5",
        "setup_name": "Breakout",
        "emotion": "Calm",
        "mistake_tags": [],
        "notes": "Followed plan",
    }
    values.update(overrides)
    return Trade(**values)


def _dataset(trades: list[Trade]) -> AnalyticsDataset:
    return AnalyticsDataset(account_id=1, start_date=None, end_date=None, trades=trades, checks=[], violations=[])


def test_overview_handles_no_trades() -> None:
    overview = build_overview(_dataset([]))

    assert overview.no_data is True
    assert overview.metrics.total_closed_trades == 0
    assert overview.metrics.win_rate == 0.0
    assert overview.metrics.profit_factor is None
    assert overview.metrics.confidence.code == "insufficient_sample"
    assert overview.equity_curve == []


def test_wins_losses_metric_calculation() -> None:
    metrics = calculate_metrics([_trade("1", "100"), _trade("2", "-50")])

    assert metrics.total_closed_trades == 2
    assert metrics.wins == 1
    assert metrics.losses == 1
    assert metrics.win_rate == 50.0
    assert metrics.total_realized_pnl == 50.0
    assert metrics.gross_profit == 100.0
    assert metrics.gross_loss == 50.0
    assert metrics.average_winner == 100.0
    assert metrics.average_loser == -50.0
    assert metrics.max_consecutive_wins == 1
    assert metrics.max_consecutive_losses == 1


def test_expectancy_profit_factor_and_average_r() -> None:
    metrics = calculate_metrics([_trade("1", "200"), _trade("2", "100"), _trade("3", "-100")])

    assert metrics.profit_factor == 3.0
    assert metrics.expectancy == 66.67
    assert metrics.average_r_multiple == 0.3333
    assert metrics.best_r_multiple == 1.0
    assert metrics.worst_r_multiple == -1.0
    assert metrics.r_multiple_count == 3


def test_grouping_by_setup_and_symbol() -> None:
    trades = [
        _trade("1", "80", setup_name="Breakout", symbol="XAUUSD"),
        _trade("2", "-20", setup_name="Breakout", symbol="XAUUSD"),
        _trade("3", "40", setup_name="Pullback", symbol="EURUSD"),
    ]

    setup_rows = {row.key: row for row in build_breakdown(_dataset(trades), "setup").rows}
    symbol_rows = {row.key: row for row in build_breakdown(_dataset(trades), "symbol").rows}

    assert setup_rows["Breakout"].metrics.total_closed_trades == 2
    assert setup_rows["Breakout"].metrics.expectancy == 30.0
    assert setup_rows["Pullback"].metrics.win_rate == 100.0
    assert symbol_rows["XAUUSD"].metrics.total_realized_pnl == 60.0
    assert symbol_rows["EURUSD"].metrics.total_closed_trades == 1


def test_confidence_labels() -> None:
    assert calculate_metrics([_trade(str(i), "10") for i in range(1, 10)]).confidence.code == "insufficient_sample"
    assert calculate_metrics([_trade(str(i), "10") for i in range(1, 11)]).confidence.code == "early_signal"
    assert calculate_metrics([_trade(str(i), "10") for i in range(1, 31)]).confidence.code == "meaningful_sample"


def test_endpoint_scopes_account_and_date_filters(monkeypatch) -> None:
    captured = {}

    def override_db():
        yield FakeSession(_account(42))

    def fake_load_dataset(_db, account_id, start_date, end_date):
        captured["account_id"] = account_id
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return AnalyticsDataset(account_id=account_id, start_date=start_date, end_date=end_date, trades=[], checks=[], violations=[])

    monkeypatch.setattr(analytics_api, "load_dataset", fake_load_dataset)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        response = client.get("/api/analytics/overview?account_id=42&start_date=2026-06-01&end_date=2026-07-01")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured == {"account_id": 42, "start_date": date(2026, 6, 1), "end_date": date(2026, 7, 1)}
    assert response.json()["account_id"] == 42


def test_no_fabricated_insight_when_sample_is_insufficient() -> None:
    trades = [_trade(str(i), "100", setup_name="Breakout") for i in range(1, 10)]

    insights = build_insights(_dataset(trades)).insights

    assert len(insights) == 1
    assert insights[0].supported is False
    assert insights[0].confidence.code == "insufficient_sample"
    assert "More closed trades needed" == insights[0].title

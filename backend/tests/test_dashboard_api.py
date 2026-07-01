from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import dashboard as dashboard_api
from app.db.session import get_db
from app.main import app
from app.models import Account, AccountSnapshot, PreTradeCheck, RiskRule, Rule, RuleEvaluation, RuleViolation


class ExecuteResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, scalar_results=None, scalars_results=None, execute_results=None):
        self.scalar_results = list(scalar_results or [])
        self.scalars_results = list(scalars_results or [])
        self.execute_results = list(execute_results or [])

    def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def scalars(self, _stmt):
        if self.scalars_results:
            return self.scalars_results.pop(0)
        return []

    def execute(self, _stmt):
        if self.execute_results:
            return ExecuteResult(self.execute_results.pop(0))
        return ExecuteResult([])


def account() -> Account:
    return Account(
        id=1,
        account_number="100001",
        broker="Demo",
        server="Demo",
        balance=Decimal("10000"),
        equity=Decimal("9600"),
        margin=Decimal("100"),
        free_margin=Decimal("9500"),
    )


def rule(**overrides) -> RiskRule:
    values = {
        "id": 1,
        "account_id": 1,
        "max_trades_per_day": 5,
        "max_daily_loss_percent": Decimal("5"),
        "max_total_loss_percent": Decimal("10"),
        "max_consecutive_losses": 3,
        "cooldown_minutes_after_loss": 30,
        "max_lot": Decimal("1"),
        "max_risk_per_trade_percent": Decimal("1"),
        "allow_trading": True,
    }
    values.update(overrides)
    return RiskRule(**values)


def test_downsample_snapshots_keeps_latest_point():
    base_time = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    snapshots = [
        AccountSnapshot(id=index + 1, account_id=1, balance=Decimal("100000") + index, equity=Decimal("100000") + index, timestamp=base_time + timedelta(minutes=index))
        for index in range(100)
    ]

    sampled = dashboard_api._downsample_snapshots(snapshots, 10)

    assert len(sampled) == 10
    assert sampled[0].id == 1
    assert sampled[-1].id == 100


def client_with_db(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_risk_summary_returns_budget_visibility(monkeypatch):
    current_time = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard_api, "current_account_or_404", lambda _db: account())
    monkeypatch.setattr(dashboard_api, "now_utc", lambda: current_time)
    monkeypatch.setattr(
        dashboard_api,
        "calculate_stats",
        lambda _db, _account_id: {
            "total_trades": 8,
            "win_rate": 50.0,
            "profit_factor": 1.2,
            "average_r": 0.4,
            "max_drawdown": 400.0,
            "trades_today": 4,
            "daily_pnl": -400.0,
            "consecutive_losses": 2,
        },
    )
    monkeypatch.setattr(dashboard_api, "latest_closed_trade", lambda _db, _account_id: None)
    check = PreTradeCheck(id=7, account_id=1, symbol="XAUUSD", order_type="BUY", lot=Decimal("0.75"), allowed=True, reason="Allowed", rule_codes=[], details={}, created_at=current_time)
    db = FakeSession(scalar_results=[rule(), check], scalars_results=[[]])
    client = client_with_db(db)
    try:
        response = client.get("/api/dashboard/risk-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trading_status"] == "warning"
    assert body["daily_loss"]["used"] == "400.00"
    assert body["daily_loss"]["limit"] == "500.00"
    assert body["daily_loss"]["percent_used"] == 80.0
    assert body["trades_today"]["remaining"] == 1
    assert body["max_lot"]["planned_lot"] == "0.75"


def test_risk_activity_filters_resolved_and_warning_items(monkeypatch):
    current_time = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard_api, "current_account_or_404", lambda _db: account())
    evaluation = RuleEvaluation(id=10, account_id=1, context="pre_trade", allowed=True, blocked=False, status="warning", decision="WARN", reason="RISK_PER_TRADE", message="Warn", checked_at=current_time)
    violation = RuleViolation(
        id=11,
        evaluation_id=10,
        rule_id=None,
        account_id=1,
        rule_code="RISK_PER_TRADE",
        severity="warning",
        action="warn",
        message="Planned risk is high.",
        violation_metadata={"symbol": "EURUSD"},
        is_resolved=True,
        created_at=current_time,
    )
    db = FakeSession(execute_results=[[(violation, evaluation)]], scalars_results=[[]])
    client = client_with_db(db)
    try:
        response = client.get("/api/dashboard/risk-activity?filter=resolved")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["rule_code"] == "RISK_PER_TRADE"
    assert body[0]["status"] == "resolved"
    assert body[0]["symbol"] == "EURUSD"


def test_snapshot_and_pre_trade_history_empty_states(monkeypatch):
    monkeypatch.setattr(dashboard_api, "current_account_or_404", lambda _db: account())
    db = FakeSession(scalars_results=[[], []])
    client = client_with_db(db)
    try:
        snapshots = client.get("/api/dashboard/account-snapshots")
        history = client.get("/api/dashboard/pre-trade-history")
    finally:
        app.dependency_overrides.clear()

    assert snapshots.status_code == 200
    assert snapshots.json() == []
    assert history.status_code == 200
    assert history.json() == []


def test_rule_indicators_include_latest_trigger(monkeypatch):
    current_time = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard_api, "current_account_or_404", lambda _db: account())
    catalog_rule = Rule(
        id=1,
        name="Max daily loss",
        code="MAX_DAILY_LOSS",
        description="",
        enabled=True,
        severity="critical",
        action="block",
        category="risk",
        config={},
        message="Daily loss reached.",
    )
    violation = RuleViolation(
        id=2,
        evaluation_id=1,
        rule_id=1,
        account_id=1,
        rule_code="MAX_DAILY_LOSS",
        severity="critical",
        action="block",
        message="Daily loss reached.",
        violation_metadata={},
        is_resolved=False,
        created_at=current_time,
    )
    db = FakeSession(scalars_results=[[catalog_rule], [violation]], execute_results=[[("MAX_DAILY_LOSS", 2)]])
    client = client_with_db(db)
    try:
        response = client.get("/api/dashboard/rule-indicators")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body[0]["rule_code"] == "MAX_DAILY_LOSS"
    assert body[0]["trigger_count_today"] == 2
    assert body[0]["current_active_state"] == "block"

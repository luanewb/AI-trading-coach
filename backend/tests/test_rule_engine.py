from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app
from app.models import Account, Alert, PreTradeCheck, RiskRule, Rule, RuleEvaluation, RuleViolation, Trade
from app.schemas.pre_trade import PreCloseCheckIn, PreTradeCheckIn
from app.api import rules as rules_api
from app.services import rule_engine


class FakeSession:
    def __init__(self, *scalar_results):
        self.scalar_results = list(scalar_results)
        self.added = []
        self.deleted = []

    def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def scalars(self, _stmt):
        return []

    def flush(self):
        for index, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = index
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(timezone.utc)

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, _obj):
        pass


def account(balance="10000", equity="10000"):
    return Account(id=1, account_number="100001", broker="Demo", server="Demo", balance=Decimal(balance), equity=Decimal(equity))


def rule(**overrides):
    values = {
        "id": 1,
        "account_id": 1,
        "max_trades_per_day": 5,
        "max_daily_loss_percent": Decimal("5"),
        "max_total_loss_percent": Decimal("10"),
        "max_consecutive_losses": 3,
        "cooldown_minutes_after_loss": 30,
        "max_lot": Decimal("2"),
        "max_risk_per_trade_percent": Decimal("1"),
        "allow_trading": True,
    }
    values.update(overrides)
    return RiskRule(**values)


def stats(**overrides):
    values = {
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "average_r": 0.0,
        "max_drawdown": 0.0,
        "trades_today": 0,
        "daily_pnl": 0.0,
        "consecutive_losses": 0,
    }
    values.update(overrides)
    return values


def payload(**overrides):
    values = {
        "account_number": "100001",
        "symbol": "XAUUSD",
        "order_type": "BUY",
        "lot": Decimal("0.5"),
        "entry_price": Decimal("2000"),
        "sl": Decimal("1990"),
        "tp": Decimal("2030"),
    }
    values.update(overrides)
    return PreTradeCheckIn(**values)


def patch_stats(monkeypatch, values):
    monkeypatch.setattr(rule_engine, "calculate_stats", lambda _db, _account_id: values)


def assert_mt5_contract(body):
    for field in ("allowed", "status", "decision", "reason", "message", "violations", "warnings"):
        assert field in body
    assert isinstance(body["allowed"], bool)
    assert isinstance(body["status"], str)
    assert isinstance(body["decision"], str)
    assert isinstance(body["reason"], str)
    assert isinstance(body["message"], str)
    assert isinstance(body["violations"], list)
    assert isinstance(body["warnings"], list)


def test_pre_trade_blocks_missing_stop_loss_and_stores_structured_reason(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(rule())

    result = rule_engine.pre_trade_check(db, account(), payload(sl=None))

    check = next(obj for obj in db.added if isinstance(obj, PreTradeCheck))
    assert result["allowed"] is False
    assert "NO_STOP_LOSS" in result["alerts"]
    assert result["status"] == "blocked"
    assert result["decision"] == "BLOCK"
    assert check.allowed is False
    assert check.rule_codes == ["NO_STOP_LOSS"]
    assert check.details["violations"][0]["rule_code"] == "NO_STOP_LOSS"
    assert check.reason == "NO_STOP_LOSS"
    assert any(isinstance(obj, RuleEvaluation) for obj in db.added)
    assert any(isinstance(obj, RuleViolation) and obj.rule_code == "NO_STOP_LOSS" for obj in db.added)
    assert_mt5_contract(result)


def test_pre_trade_blocks_when_platform_trading_is_disabled(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(rule(allow_trading=False))

    result = rule_engine.pre_trade_check(db, account(), payload())

    assert result["allowed"] is False
    assert result["reason"] == "PLATFORM_TRADING_ALLOWED"
    assert "PLATFORM_TRADING_ALLOWED" in result["alerts"]


def test_pre_trade_blocks_when_lot_exceeds_configured_max(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(rule(max_lot=Decimal("0.25")))

    result = rule_engine.pre_trade_check(db, account(), payload(lot=Decimal("0.50")))

    assert result["allowed"] is False
    assert result["reason"] == "MAX_LOT_SIZE"
    assert "MAX_LOT_SIZE" in result["alerts"]


def test_pre_trade_blocks_daily_loss_drawdown_trade_count_and_consecutive_losses(monkeypatch):
    patch_stats(
        monkeypatch,
        stats(trades_today=3, daily_pnl=-500.0, max_drawdown=1200.0, consecutive_losses=2),
    )
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(
        rule(
            max_trades_per_day=3,
            max_daily_loss_percent=Decimal("5"),
            max_total_loss_percent=Decimal("10"),
            max_consecutive_losses=2,
        )
    )

    result = rule_engine.pre_trade_check(db, account(balance="10000", equity="9500"), payload())

    assert result["allowed"] is False
    assert {"MAX_TRADES_PER_DAY", "MAX_DAILY_LOSS", "MAX_DRAWDOWN_LIMIT", "MAX_CONSECUTIVE_LOSSES"}.issubset(set(result["alerts"]))


def test_pre_trade_locks_when_total_loss_limit_is_reached(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(rule(max_total_loss_percent=Decimal("10")))

    result = rule_engine.pre_trade_check(db, account(balance="10000", equity="8900"), payload())

    assert result["allowed"] is False
    assert result["status"] == "locked"
    assert result["decision"] == "LOCK"
    assert result["reason"] == "MAX_TOTAL_LOSS"
    assert "MAX_TOTAL_LOSS" in result["alerts"]


def test_pre_trade_blocks_when_payload_risk_percent_exceeds_limit(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(rule(max_risk_per_trade_percent=Decimal("1")))

    result = rule_engine.pre_trade_check(db, account(), payload(risk_percent=Decimal("2.5")))

    assert result["allowed"] is False
    assert "RISK_PER_TRADE" in result["alerts"]
    assert result["reason"] == "RISK_PER_TRADE"


def test_pre_trade_warns_for_risk_per_trade_when_catalog_action_is_warn(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    risk_rule = Rule(
        id=88,
        name="Risk per trade",
        code="RISK_PER_TRADE",
        description="Warn when planned risk is high.",
        enabled=True,
        severity="warning",
        action="warn",
        category="risk",
        config={},
        message="Planned risk is above the configured maximum.",
    )
    monkeypatch.setattr(rule_engine, "_rule_catalog", lambda _db: {"RISK_PER_TRADE": risk_rule})
    db = FakeSession(rule(max_risk_per_trade_percent=Decimal("1")))

    result = rule_engine.pre_trade_check(db, account(), payload(risk_percent=Decimal("2.5")))

    assert result["allowed"] is True
    assert result["status"] == "warning"
    assert result["decision"] == "WARN"
    assert result["violations"] == []
    assert result["warnings"][0]["rule_code"] == "RISK_PER_TRADE"


def test_pre_trade_detects_revenge_trading_during_post_loss_cooldown(monkeypatch):
    current_time = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    last_loss = Trade(id=10, account_id=1, ticket="L1", symbol="EURUSD", order_type="SELL", lot=Decimal("1"), profit=Decimal("-50"), status="closed", close_time=current_time - timedelta(minutes=5))
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "now_utc", lambda: current_time)
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: last_loss)
    db = FakeSession(rule(cooldown_minutes_after_loss=30))

    result = rule_engine.pre_trade_check(db, account(), payload(symbol="EURUSD", lot=Decimal("1.5")))

    assert result["allowed"] is False
    assert "COOLDOWN_AFTER_LOSS" in result["alerts"]
    assert "REVENGE_TRADING" in result["alerts"]


def test_pre_trade_blocks_during_post_loss_cooldown_without_revenge_pattern(monkeypatch):
    current_time = datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)
    last_loss = Trade(id=11, account_id=1, ticket="L2", symbol="EURUSD", order_type="SELL", lot=Decimal("1"), profit=Decimal("-50"), status="closed", close_time=current_time - timedelta(minutes=5))
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "now_utc", lambda: current_time)
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: last_loss)
    db = FakeSession(rule(cooldown_minutes_after_loss=30))

    result = rule_engine.pre_trade_check(db, account(), payload(symbol="XAUUSD", lot=Decimal("0.5")))

    assert result["allowed"] is False
    assert result["reason"] == "COOLDOWN_AFTER_LOSS"
    assert "COOLDOWN_AFTER_LOSS" in result["alerts"]
    assert "REVENGE_TRADING" not in result["alerts"]


def test_pre_trade_evaluates_custom_catalog_rule(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    custom_rule = Rule(
        id=99,
        name="Block XAUUSD",
        code="BLOCK_XAUUSD",
        description="Custom symbol block.",
        enabled=True,
        severity="critical",
        action="block",
        category="behavior",
        config={"scope": "pre_trade", "field": "symbol", "operator": "eq", "value": "XAUUSD"},
        message="XAUUSD is blocked by custom rule.",
    )
    monkeypatch.setattr(rule_engine, "_rule_catalog", lambda _db: {"BLOCK_XAUUSD": custom_rule})
    db = FakeSession(rule())

    result = rule_engine.pre_trade_check(db, account(), payload())

    assert result["allowed"] is False
    assert result["reason"] == "BLOCK_XAUUSD"
    assert result["violations"][0]["rule_code"] == "BLOCK_XAUUSD"


def test_evaluate_rules_creates_alert_for_open_trade_without_stop_loss(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    monkeypatch.setattr(rule_engine, "send_telegram_alert", lambda _alert: None)
    trade = Trade(id=20, account_id=1, ticket="T1", symbol="XAUUSD", order_type="BUY", lot=Decimal("0.5"), entry_price=Decimal("2000"), sl=None, status="open")
    db = FakeSession(rule())

    result = rule_engine.evaluate_rules(db, account(), trade)

    alert = next(obj for obj in db.added if isinstance(obj, Alert))
    assert result["allow_trading"] is False
    assert result["alerts_created"] == ["NO_STOP_LOSS"]
    assert alert.type == "NO_STOP_LOSS"


def test_pre_trade_endpoint_returns_json_block_response(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(account(), rule())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rules/pre-trade-check",
            headers={"x-api-key": "change-me"},
            json={
                "account_number": "100001",
                "symbol": "XAUUSD",
                "order_type": "BUY",
                "lot": "0.5",
                "entry_price": "2000",
                "tp": "2030",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert_mt5_contract(body)
    assert body["allowed"] is False
    assert body["status"] == "blocked"
    assert body["decision"] == "BLOCK"
    assert body["reason"] == "NO_STOP_LOSS"
    assert body["violations"][0]["rule_code"] == "NO_STOP_LOSS"
    assert body["warnings"] == []


def test_pre_trade_endpoint_returns_json_allowed_contract(monkeypatch):
    patch_stats(monkeypatch, stats())
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    db = FakeSession(account(), rule())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rules/pre-trade-check",
            headers={"x-api-key": "change-me"},
            json={
                "account_number": "100001",
                "symbol": "XAUUSD",
                "order_type": "BUY",
                "lot": "0.5",
                "entry_price": "2000",
                "sl": "1990",
                "tp": "2030",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert_mt5_contract(body)
    assert body["allowed"] is True
    assert body["status"] == "allowed"
    assert body["decision"] == "ALLOW"
    assert body["reason"] == "Allowed"
    assert body["violations"] == []
    assert body["warnings"] == []


def test_pre_trade_endpoint_invalid_payload_returns_validation_errors():
    client = TestClient(app)

    response = client.post(
        "/api/rules/pre-trade-check",
        headers={"x-api-key": "change-me"},
        json={
            "account_number": "100001",
            "symbol": "XAUUSD",
            "order_type": "HOLD",
            "lot": "-1",
            "entry_price": "0",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)
    assert {tuple(error["loc"]) for error in body["detail"]} >= {
        ("body", "order_type"),
        ("body", "lot"),
        ("body", "entry_price"),
    }


def test_pre_trade_endpoint_fails_closed_when_rule_engine_raises(monkeypatch, caplog):
    db = FakeSession(account())

    def override_db():
        yield db

    def explode(_db, _account, _payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(rules_api, "pre_trade_check", explode)
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        with caplog.at_level("ERROR", logger="app.api.rules"):
            response = client.post(
                "/api/rules/pre-trade-check",
                headers={"x-api-key": "change-me"},
                json={
                    "account_number": "100001",
                    "symbol": "XAUUSD",
                    "order_type": "BUY",
                    "lot": "0.5",
                    "entry_price": "2000",
                    "sl": "1990",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert_mt5_contract(body)
    assert body["allowed"] is False
    assert body["reason"] == "RULE_ENGINE_ERROR"
    assert body["violations"][0]["metadata"]["error_type"] == "RuntimeError"
    assert "Pre-trade rule evaluation failed; returning safe block response" in caplog.text


def test_pre_trade_endpoint_fails_closed_and_logs_database_errors(caplog):
    class BrokenSession:
        def scalar(self, _stmt):
            raise SQLAlchemyError("database offline")

        def rollback(self):
            self.rolled_back = True

    db = BrokenSession()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        with caplog.at_level("ERROR", logger="app.api.rules"):
            response = client.post(
                "/api/rules/pre-trade-check",
                headers={"x-api-key": "change-me"},
                json={
                    "account_number": "100001",
                    "symbol": "XAUUSD",
                    "order_type": "BUY",
                    "lot": "0.5",
                    "entry_price": "2000",
                    "sl": "1990",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert_mt5_contract(body)
    assert body["allowed"] is False
    assert body["reason"] == "RULE_ENGINE_ERROR"
    assert body["violations"][0]["metadata"]["error_type"] == "SQLAlchemyError"
    assert db.rolled_back is True
    assert "Pre-trade rule evaluation failed; returning safe block response" in caplog.text


def test_rule_configuration_persists_through_save_and_reload(monkeypatch):
    saved_rule = rule()

    class StatefulRuleSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.commit_count = 0

        def scalar(self, _stmt):
            return saved_rule

        def commit(self):
            self.commit_count += 1

    db = StatefulRuleSession()

    def override_db():
        yield db

    monkeypatch.setattr(rules_api, "current_account_or_404", lambda _db: account())
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        update_response = client.put(
            "/api/rules",
            json={
                "max_trades_per_day": 7,
                "max_daily_loss_percent": "3.5",
                "max_total_loss_percent": "8.5",
                "max_consecutive_losses": 4,
                "cooldown_minutes_after_loss": 45,
                "max_lot": "0.75",
                "max_risk_per_trade_percent": "0.8",
                "allow_trading": False,
            },
        )
        reload_response = client.get("/api/rules")
    finally:
        app.dependency_overrides.clear()

    assert update_response.status_code == 200
    assert reload_response.status_code == 200
    body = reload_response.json()
    assert body["max_trades_per_day"] == 7
    assert body["max_daily_loss_percent"] == "3.5"
    assert body["max_total_loss_percent"] == "8.5"
    assert body["max_consecutive_losses"] == 4
    assert body["cooldown_minutes_after_loss"] == 45
    assert body["max_lot"] == "0.75"
    assert body["max_risk_per_trade_percent"] == "0.8"
    assert body["allow_trading"] is False
    assert db.commit_count == 2


def test_create_rule_catalog_endpoint_returns_created_rule():
    db = FakeSession(None)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rules/catalog",
            json={
                "name": "News lockout",
                "code": "NEWS_LOCKOUT",
                "description": "Avoid trades during high impact news.",
                "enabled": True,
                "severity": "warning",
                "action": "warn",
                "category": "behavior",
                "config": {"minutes_before": 15},
                "message": "High impact news window is active.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "NEWS_LOCKOUT"
    assert body["action"] == "warn"
    assert body["config"] == {"minutes_before": 15}


def test_delete_custom_rule_catalog_endpoint_returns_no_content():
    custom_rule = Rule(
        id=200,
        name="Old close warning",
        code="EARLY_TP_BUY_EMA89",
        description="Old custom rule.",
        enabled=True,
        severity="warning",
        action="warn",
        category="psychology",
        config={},
        message="Old rule.",
    )
    db = FakeSession(custom_rule)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.delete("/api/rules/catalog/EARLY_TP_BUY_EMA89")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert db.deleted == [custom_rule]


def test_delete_builtin_rule_catalog_endpoint_is_blocked():
    builtin_rule = Rule(
        id=201,
        name="No stop loss",
        code="NO_STOP_LOSS",
        description="Built-in rule.",
        enabled=True,
        severity="critical",
        action="block",
        category="risk",
        config={},
        message="Stop loss is required.",
    )
    db = FakeSession(builtin_rule)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.delete("/api/rules/catalog/NO_STOP_LOSS")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert db.deleted == []


def close_payload(**overrides):
    values = {
        "account_number": "100001",
        "ticket": "T1",
        "symbol": "XAUUSD",
        "position_type": "BUY",
        "lot": Decimal("0.5"),
        "entry_price": Decimal("2000"),
        "current_price": Decimal("2020"),
        "profit": Decimal("100"),
        "candle_close": Decimal("1992"),
        "ema34": Decimal("1995"),
        "ema89": Decimal("1990"),
        "close_reason": "close_all",
    }
    values.update(overrides)
    return PreCloseCheckIn(**values)


def test_pre_close_evaluates_custom_indicator_rule(monkeypatch):
    custom_rule = Rule(
        id=100,
        name="Early TP EMA89 check",
        code="EARLY_TP_EMA89_CHECK",
        description="Warn when closing a buy before candle closes below EMA89.",
        enabled=True,
        severity="warning",
        action="warn",
        category="psychology",
        config={
            "scope": "pre_close",
            "logic": "all",
            "conditions": [
                {"field": "position_type", "operator": "eq", "value": "BUY"},
                {"field": "candle_close", "operator": "gte", "value_from": "ema89"},
            ],
        },
        message="No bearish EMA89 close yet. Confirm before taking profit early.",
    )
    monkeypatch.setattr(rule_engine, "_rule_catalog", lambda _db: {"EARLY_TP_EMA89_CHECK": custom_rule})
    db = FakeSession()

    result = rule_engine.pre_close_check(db, account(), close_payload())

    assert result["allowed"] is True
    assert result["decision"] == "WARN"
    assert result["reason"] == "No bearish EMA89 close yet. Confirm before taking profit early."
    assert result["warnings"][0]["rule_code"] == "EARLY_TP_EMA89_CHECK"


def test_pre_close_endpoint_returns_json_warning(monkeypatch):
    custom_rule = Rule(
        id=101,
        name="Early TP EMA89 check",
        code="EARLY_TP_EMA89_CHECK",
        description="Warn when closing a buy before candle closes below EMA89.",
        enabled=True,
        severity="warning",
        action="warn",
        category="psychology",
        config={
            "scope": "pre_close",
            "conditions": [
                {"field": "position_type", "operator": "eq", "value": "BUY"},
                {"field": "candle_close", "operator": "gte", "value_from": "ema89"},
            ],
        },
        message="No bearish EMA89 close yet. Confirm before taking profit early.",
    )
    monkeypatch.setattr(rule_engine, "_rule_catalog", lambda _db: {"EARLY_TP_EMA89_CHECK": custom_rule})
    db = FakeSession(account())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/rules/pre-close-check",
            headers={"x-api-key": "change-me"},
            json={
                "account_number": "100001",
                "ticket": "T1",
                "symbol": "XAUUSD",
                "position_type": "BUY",
                "lot": "0.5",
                "entry_price": "2000",
                "current_price": "2020",
                "profit": "100",
                "candle_close": "1992",
                "ema34": "1995",
                "ema89": "1990",
                "close_reason": "close_all",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["decision"] == "WARN"
    assert body["warnings"][0]["rule_code"] == "EARLY_TP_EMA89_CHECK"

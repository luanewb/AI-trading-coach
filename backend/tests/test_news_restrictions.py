from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models import Account, NewsRestrictedEvent, NewsRestrictionSettings, PreTradeCheck, RiskRule, TradeRestrictionEvent
from app.schemas.pre_trade import PreTradeCheckIn
from app.services import news_restrictions as news_service
from app.services import rule_engine
from app.services.news_restrictions import (
    EconomicEvent,
    is_restricted_usd_event,
    is_usd_sensitive_symbol,
    normalize_event_title,
    restriction_status,
    sync_restricted_events,
    upsert_economic_events,
)


class FakeNewsSession:
    def __init__(self, settings=None, events=None, scalar_results=None):
        self.settings = settings
        self.events = list(events or [])
        self.scalar_results = list(scalar_results or [])
        self.added = []

    def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return self.settings

    def scalars(self, _stmt):
        return list(self.events)

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, NewsRestrictedEvent):
            self.events.append(obj)
        if isinstance(obj, NewsRestrictionSettings):
            self.settings = obj

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


def settings(**overrides):
    values = {
        "id": 1,
        "account_type": "standard_funded",
        "enforcement_mode": "block_actions",
        "minutes_before": 2,
        "minutes_after": 2,
        "apply_usd_only": True,
        "blocked_actions": ["new_order", "manual_close", "modify_sl_tp", "pending_order"],
    }
    values.update(overrides)
    return NewsRestrictionSettings(**values)


def restricted_event(scheduled_at):
    return NewsRestrictedEvent(
        id=10,
        source="mock",
        source_event_id="nfp-1",
        title="Non-Farm Payrolls",
        normalized_title="non_farm_payrolls",
        currency="USD",
        country="US",
        scheduled_at=scheduled_at,
        impact="high",
        is_restricted=True,
        restriction_reason="FTMO restricted USD news event",
        raw_payload={},
    )


def account():
    return Account(id=1, account_number="100001", broker="Demo", server="Demo", balance=Decimal("10000"), equity=Decimal("10000"))


def risk_rule():
    return RiskRule(
        id=1,
        account_id=1,
        max_trades_per_day=5,
        max_daily_loss_percent=Decimal("5"),
        max_total_loss_percent=Decimal("10"),
        max_consecutive_losses=3,
        cooldown_minutes_after_loss=30,
        max_lot=Decimal("2"),
        max_risk_per_trade_percent=Decimal("1"),
        allow_trading=True,
    )


def payload():
    return PreTradeCheckIn(
        account_number="100001",
        symbol="XAUUSD.pro",
        order_type="BUY",
        lot=Decimal("0.5"),
        entry_price=Decimal("2000"),
        sl=Decimal("1990"),
        tp=Decimal("2030"),
    )


def test_normalizes_restricted_event_name_variants():
    assert normalize_event_title("Non-Farm Payrolls") == "non_farm_payrolls"
    assert normalize_event_title("US NFP Employment Change") == "non_farm_payrolls"
    assert normalize_event_title("FOMC Press Conference") == "fomc_press_conference"
    assert is_restricted_usd_event("Core CPI m/m", "USD")[0] is True
    assert is_restricted_usd_event("Core CPI m/m", "EUR")[0] is False


def test_usd_sensitive_symbol_mapping_handles_suffixes():
    assert is_usd_sensitive_symbol("XAUUSD.pro") is True
    assert is_usd_sensitive_symbol("EURUSDm") is True
    assert is_usd_sensitive_symbol("USDJPY.r") is True
    assert is_usd_sensitive_symbol("NAS100.cash") is True
    assert is_usd_sensitive_symbol("DE40") is False


def test_restricted_window_boundaries_are_inclusive():
    scheduled = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db = FakeNewsSession(settings=settings(), events=[restricted_event(scheduled)])

    before = restriction_status(db, symbol="XAUUSD", at_time=scheduled - timedelta(minutes=2, seconds=1))
    start = restriction_status(db, symbol="XAUUSD", at_time=scheduled - timedelta(minutes=2))
    end = restriction_status(db, symbol="XAUUSD", at_time=scheduled + timedelta(minutes=2))
    after = restriction_status(db, symbol="XAUUSD", at_time=scheduled + timedelta(minutes=2, seconds=1))

    assert before["is_restricted_now"] is False
    assert start["is_restricted_now"] is True
    assert end["is_restricted_now"] is True
    assert after["is_restricted_now"] is False


def test_modes_and_account_types_control_blocking():
    scheduled = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    event = restricted_event(scheduled)

    block = restriction_status(FakeNewsSession(settings=settings(enforcement_mode="block_actions"), events=[event]), symbol="XAUUSD", action="new_order", at_time=scheduled)
    warn = restriction_status(FakeNewsSession(settings=settings(enforcement_mode="warn_only"), events=[event]), symbol="XAUUSD", action="new_order", at_time=scheduled)
    disabled = restriction_status(FakeNewsSession(settings=settings(enforcement_mode="disabled"), events=[event]), symbol="XAUUSD", action="new_order", at_time=scheduled)
    swing = restriction_status(FakeNewsSession(settings=settings(account_type="swing"), events=[event]), symbol="XAUUSD", action="new_order", at_time=scheduled)

    assert block["should_block"] is True
    assert warn["should_block"] is False
    assert warn["should_warn"] is True
    assert disabled["should_warn"] is False
    assert swing["effective_mode"] == "warn_only"
    assert swing["should_block"] is False


def test_upsert_economic_event_updates_without_duplicate():
    scheduled = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    event = EconomicEvent(
        id="ftmo-1",
        source="ftmo",
        title="CPI",
        normalized_title="cpi",
        currency="USD",
        scheduled_at=scheduled,
        impact="high",
    )
    db = FakeNewsSession(scalar_results=[None])

    assert upsert_economic_events(db, [event]) == 1
    created = db.events[0]
    db.scalar_results = [created]
    updated_event = EconomicEvent(
        id="ftmo-1",
        source="ftmo",
        title="Core CPI",
        normalized_title="cpi",
        currency="USD",
        scheduled_at=scheduled,
        impact="high",
        forecast="0.2%",
    )
    assert upsert_economic_events(db, [updated_event]) == 1

    assert len(db.events) == 1
    assert created.title == "Core CPI"
    assert created.forecast == "0.2%"


def test_mock_provider_seeds_today_ftmo_nfp_event():
    db = FakeNewsSession()
    count = sync_restricted_events(db, base_time=datetime(2026, 7, 2, 5, 0, tzinfo=timezone.utc))

    assert count == 1
    assert db.events[0].title == "Non-Farm Employment Change"
    assert db.events[0].scheduled_at == datetime(2026, 7, 2, 12, 30, tzinfo=timezone.utc)
    assert db.events[0].forecast == "114 K"
    assert db.events[0].previous == "172 K"


def test_restriction_status_api_contract():
    scheduled = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db = FakeNewsSession(settings=settings(), events=[restricted_event(scheduled)])

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get(
            "/api/news/restriction-status",
            params={"symbol": "XAUUSD", "action": "new_order", "at": scheduled.isoformat()},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["is_restricted_now"] is True
    assert body["should_block"] is True
    assert body["current_event"]["normalized_title"] == "non_farm_payrolls"
    assert body["seconds_until_restriction_end"] == 120


def test_pre_trade_check_blocks_and_logs_restricted_news(monkeypatch):
    scheduled = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(rule_engine, "calculate_stats", lambda _db, _account_id: {
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "average_r": 0.0,
        "max_drawdown": 0.0,
        "trades_today": 0,
        "daily_pnl": 0.0,
        "consecutive_losses": 0,
    })
    monkeypatch.setattr(rule_engine, "latest_closed_trade", lambda _db, _account_id: None)
    monkeypatch.setattr(rule_engine, "now_utc", lambda: scheduled)
    monkeypatch.setattr(news_service, "now_utc", lambda: scheduled)
    monkeypatch.setattr(rule_engine, "_rule_catalog", lambda _db: {})
    db = FakeNewsSession(settings=settings(), events=[restricted_event(scheduled)], scalar_results=[risk_rule()])

    result = rule_engine.pre_trade_check(db, account(), payload())

    assert result["allowed"] is False
    assert result["reason"] == "NEWS_RESTRICTED_WINDOW"
    assert "NEWS_RESTRICTED_WINDOW" in result["alerts"]
    assert any(isinstance(obj, TradeRestrictionEvent) and obj.blocked for obj in db.added)
    assert any(isinstance(obj, PreTradeCheck) and obj.reason == "NEWS_RESTRICTED_WINDOW" for obj in db.added)

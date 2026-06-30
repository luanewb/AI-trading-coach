import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

alembic = pytest.importorskip("alembic")
from alembic import command
from alembic.config import Config

from app.api.mt5 import receive_heartbeat, receive_trade_event
from app.core.config import get_settings
from app.models import Account, AccountSnapshot, PreTradeCheck, RuleEvaluation, RuleViolation, Trade, TradeEvent
from app.schemas.mt5 import HeartbeatIn, TradeEventIn
from app.schemas.pre_trade import PreTradeCheckIn
from app.services import stats as stats_service
from app.services.rule_engine import get_or_create_rule, pre_trade_check


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="set TEST_DATABASE_URL to run PostgreSQL data-foundation tests",
)


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    return config


@pytest.fixture()
def db_session() -> Session:
    database_url = os.environ["TEST_DATABASE_URL"]
    url = make_url(database_url)
    assert url.database and url.database.endswith("_test"), "TEST_DATABASE_URL database name must end with _test"

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    command.upgrade(_alembic_config(database_url), "head")

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _account(db: Session) -> Account:
    account = Account(
        account_number="100001",
        broker="Demo",
        server="Demo",
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        margin=Decimal("0"),
        free_margin=Decimal("10000"),
    )
    db.add(account)
    db.flush()
    get_or_create_rule(db, account)
    db.commit()
    return account


def test_migration_upgrade_creates_foundation_tables(db_session: Session) -> None:
    inspector = inspect(db_session.bind)

    assert {"account_snapshots", "trade_events", "daily_summaries"}.issubset(set(inspector.get_table_names()))
    trade_columns = {column["name"] for column in inspector.get_columns("trades")}
    assert {"deal_id", "position_id", "source", "strategy"}.issubset(trade_columns)
    violation_columns = {column["name"] for column in inspector.get_columns("rule_violations")}
    assert {"is_resolved", "resolved_at", "resolution_note"}.issubset(violation_columns)


def test_duplicate_trade_event_does_not_create_duplicate_trade(db_session: Session) -> None:
    _account(db_session)
    payload = TradeEventIn(
        account_number="100001",
        event_type="order_opened",
        symbol="XAUUSD",
        ticket="900001",
        deal_id="700001",
        position_id="800001",
        order_type="BUY",
        lot=Decimal("0.50"),
        entry_price=Decimal("2320.50"),
        sl=Decimal("2312.50"),
        tp=Decimal("2338.50"),
        open_time=datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc),
        timestamp=datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc),
    )

    first = receive_trade_event(payload, db_session)
    second = receive_trade_event(payload, db_session)

    assert first["trade_id"] == second["trade_id"]
    assert db_session.scalar(select(func.count(Trade.id)).where(Trade.ticket == "900001")) == 1
    assert db_session.scalar(select(func.count(TradeEvent.id)).where(TradeEvent.ticket == "900001")) == 1


def test_pending_order_event_does_not_create_trade(db_session: Session) -> None:
    account = _account(db_session)
    payload = TradeEventIn(
        account_number=account.account_number,
        event_type="order_pending",
        symbol="XAUUSD",
        ticket="910001",
        order_type="BUY",
        lot=Decimal("0.50"),
        entry_price=Decimal("2320.50"),
        sl=Decimal("2312.50"),
        tp=Decimal("2338.50"),
        open_time=datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc),
        timestamp=datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc),
    )

    response = receive_trade_event(payload, db_session)

    assert response["ignored"] is True
    assert db_session.scalar(select(func.count(Trade.id)).where(Trade.ticket == "910001")) == 0
    assert db_session.scalar(select(func.count(TradeEvent.id)).where(TradeEvent.ticket == "910001")) == 1


def test_trades_today_ignores_unexecuted_open_orders(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account(db_session)
    day_start = datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(stats_service, "trading_day_bounds", lambda: (day_start, day_end))
    db_session.add(
        Trade(
            account_id=account.id,
            ticket="910002",
            symbol="XAUUSD",
            order_type="BUY",
            lot=Decimal("0.50"),
            profit=Decimal("0"),
            commission=Decimal("0"),
            swap=Decimal("0"),
            status="open",
            open_time=datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc),
            source="mt5",
        )
    )
    db_session.commit()

    stats = stats_service.calculate_stats(db_session, account.id)

    assert stats["trades_today"] == 0


def test_pre_trade_check_and_rule_violations_persist(db_session: Session) -> None:
    account = _account(db_session)

    result = pre_trade_check(
        db_session,
        account,
        PreTradeCheckIn(
            account_number="100001",
            symbol="XAUUSD",
            order_type="BUY",
            lot=Decimal("0.50"),
            entry_price=Decimal("2320.50"),
            sl=None,
            tp=Decimal("2338.50"),
        ),
    )
    db_session.commit()

    check = db_session.scalar(select(PreTradeCheck).where(PreTradeCheck.account_id == account.id))
    violation = db_session.scalar(select(RuleViolation).where(RuleViolation.account_id == account.id))
    evaluation = db_session.get(RuleEvaluation, result["rule_evaluation_id"])

    assert check is not None
    assert check.allowed is False
    assert check.reason == "NO_STOP_LOSS"
    assert check.rule_evaluation_id == result["rule_evaluation_id"]
    assert evaluation is not None
    assert violation is not None
    assert violation.rule_code == "NO_STOP_LOSS"
    assert violation.is_resolved is False


def test_account_snapshot_persists_on_heartbeat(db_session: Session) -> None:
    response = receive_heartbeat(
        HeartbeatIn(
            account_number="100002",
            broker="Demo",
            server="Demo-FTMO",
            balance=Decimal("10000"),
            equity=Decimal("9975.25"),
            margin=Decimal("125.00"),
            free_margin=Decimal("9850.25"),
            timestamp=datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc),
        ),
        db_session,
    )

    snapshot = db_session.scalar(select(AccountSnapshot).where(AccountSnapshot.account_id == response["account_id"]))
    assert snapshot is not None
    assert snapshot.equity == Decimal("9975.25")
    assert snapshot.free_margin == Decimal("9850.25")
    assert snapshot.timestamp == datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc)

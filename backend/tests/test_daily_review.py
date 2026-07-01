import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

alembic = pytest.importorskip("alembic")
from alembic import command
from alembic.config import Config

from app.api.ai import _generate_review
from app.core.config import get_settings
from app.models import Account, DailyReview, PreTradeCheck, RiskRule, RuleEvaluation, RuleViolation, Trade
from app.services.ai_review import build_daily_metrics, build_daily_review_payload, build_discipline_score


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="set TEST_DATABASE_URL to run PostgreSQL daily-review tests",
)


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    return config


@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setenv("ENABLE_AI", "false")
    monkeypatch.setenv("FTMO_TIMEZONE", "UTC")
    get_settings.cache_clear()
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
        get_settings.cache_clear()


def _account(db: Session, number: str = "200001") -> Account:
    account = Account(
        account_number=number,
        broker="Demo",
        server="Demo",
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        margin=Decimal("0"),
        free_margin=Decimal("10000"),
    )
    db.add(account)
    db.flush()
    db.add(
        RiskRule(
            account_id=account.id,
            max_trades_per_day=2,
            max_daily_loss_percent=Decimal("5"),
            max_total_loss_percent=Decimal("10"),
            max_consecutive_losses=3,
            cooldown_minutes_after_loss=30,
            max_lot=Decimal("1"),
            max_risk_per_trade_percent=Decimal("1"),
            allow_trading=True,
        )
    )
    db.commit()
    return account


def _trade(db: Session, account: Account, ticket: str, profit: str, **overrides) -> Trade:
    values = {
        "account_id": account.id,
        "ticket": ticket,
        "symbol": "XAUUSD",
        "order_type": "BUY",
        "lot": Decimal("0.50"),
        "entry_price": Decimal("2300"),
        "sl": Decimal("2290"),
        "tp": Decimal("2330"),
        "close_price": Decimal("2310"),
        "profit": Decimal(profit),
        "commission": Decimal("0"),
        "swap": Decimal("0"),
        "r_multiple": Decimal("1.5") if Decimal(profit) > 0 else Decimal("-1.0"),
        "status": "closed",
        "open_time": datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
        "close_time": datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        "source": "mt5",
        "setup_name": "Breakout",
        "emotion": "Calm",
        "mistake_tags": [],
        "notes": "Followed plan",
    }
    values.update(overrides)
    trade = Trade(**values)
    db.add(trade)
    db.commit()
    return trade


def _violation(db: Session, account: Account, code: str, action: str = "block") -> RuleViolation:
    evaluation = RuleEvaluation(
        account_id=account.id,
        context="pre_trade",
        allowed=False,
        blocked=True,
        status="blocked",
        decision="BLOCK",
        reason=code,
        message=code,
        checked_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
    )
    db.add(evaluation)
    db.flush()
    violation = RuleViolation(
        evaluation_id=evaluation.id,
        rule_id=None,
        account_id=account.id,
        rule_code=code,
        severity="critical",
        action=action,
        message=f"{code} triggered.",
        violation_metadata={},
        is_resolved=False,
        created_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
    )
    db.add(violation)
    db.commit()
    return violation


def _blocked_check(db: Session, account: Account, code: str = "NO_STOP_LOSS") -> PreTradeCheck:
    check = PreTradeCheck(
        account_id=account.id,
        symbol="XAUUSD",
        order_type="BUY",
        lot=Decimal("1.50"),
        entry_price=Decimal("2300"),
        sl=None,
        tp=Decimal("2330"),
        allowed=False,
        reason=code,
        rule_codes=[code],
        details={},
        created_at=datetime(2026, 7, 1, 10, 5, tzinfo=timezone.utc),
    )
    db.add(check)
    db.commit()
    return check


def test_deterministic_review_with_no_trades(db_session: Session) -> None:
    account = _account(db_session)

    payload = build_daily_review_payload(db_session, account, date(2026, 7, 1))

    assert payload["metrics_snapshot"]["total_trades"] == 0
    assert payload["metrics_snapshot"]["realized_pnl"] == "0.00"
    assert payload["discipline_score"] == 100
    assert "Không tìm thấy lệnh đã đóng" in payload["deterministic_findings"]["risk_patterns"][0]
    assert payload["model_metadata"]["fallback_reason"] == "ENABLE_AI=false"


def test_review_with_wins_and_losses(db_session: Session) -> None:
    account = _account(db_session)
    _trade(db_session, account, "9001", "150")
    _trade(db_session, account, "9002", "-50", mistake_tags=["late_entry"], notes="Chased entry")

    metrics = build_daily_metrics(db_session, account, date(2026, 7, 1))

    assert metrics["total_trades"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["win_rate"] == 50.0
    assert metrics["realized_pnl"] == "100.00"
    assert metrics["average_winner"] == "150.00"
    assert metrics["average_loser"] == "-50.00"
    assert metrics["profit_factor"] == 3.0
    assert metrics["average_r_multiple"] == 0.25
    assert metrics["max_consecutive_losses"] == 1


def test_discipline_score_penalties(db_session: Session) -> None:
    account = _account(db_session)
    _trade(db_session, account, "9001", "-40", setup_name=None, emotion=None, notes=None, mistake_tags=[])
    _trade(db_session, account, "9002", "-30", setup_name=None, emotion=None, notes=None, mistake_tags=["revenge"])
    _trade(db_session, account, "9003", "-20")
    _blocked_check(db_session, account, "NO_STOP_LOSS")
    _violation(db_session, account, "MAX_LOT_SIZE")
    _violation(db_session, account, "COOLDOWN_AFTER_LOSS")
    _violation(db_session, account, "RISK_PER_TRADE")

    metrics = build_daily_metrics(db_session, account, date(2026, 7, 1))
    score, breakdown = build_discipline_score(db_session, account, metrics, date(2026, 7, 1))

    assert score < 60
    penalties = {item["code"]: item["penalty"] for item in breakdown}
    assert penalties["no_stop_loss"] > 0
    assert penalties["max_lot"] > 0
    assert penalties["revenge_trading"] > 0
    assert penalties["cooldown"] > 0
    assert penalties["blocked_orders"] > 0
    assert penalties["journal_completeness"] > 0
    assert penalties["max_trades_per_day"] > 0
    assert penalties["risk_per_trade"] > 0


def test_rule_violation_inclusion(db_session: Session) -> None:
    account = _account(db_session)
    _violation(db_session, account, "RISK_PER_TRADE", action="warn")

    metrics = build_daily_metrics(db_session, account, date(2026, 7, 1))

    assert metrics["rule_violations"]["total"] == 1
    assert metrics["rule_violations"]["by_code"] == [{"name": "RISK_PER_TRADE", "count": 1}]
    assert metrics["rule_violations"]["items"][0]["action"] == "warn"


def test_ai_disabled_fallback(db_session: Session) -> None:
    account = _account(db_session)
    _trade(db_session, account, "9001", "25")

    review = _generate_review(db_session, account.id, date(2026, 7, 1))

    assert review.model_metadata["ai_enabled"] is False
    assert "huấn luyện hành vi giao dịch" in review.ai_narrative
    assert review.ai_summary == review.ai_narrative


def test_duplicate_review_prevention(db_session: Session) -> None:
    account = _account(db_session)

    first = _generate_review(db_session, account.id, date(2026, 7, 1))
    second = _generate_review(db_session, account.id, date(2026, 7, 1))

    assert first.id == second.id
    assert db_session.scalar(select(func.count(DailyReview.id))) == 1


def test_account_scoping(db_session: Session) -> None:
    first_account = _account(db_session, "200001")
    second_account = _account(db_session, "200002")
    _trade(db_session, first_account, "9001", "75", symbol="XAUUSD")
    _trade(db_session, second_account, "9002", "-25", symbol="EURUSD")

    first_review = _generate_review(db_session, first_account.id, date(2026, 7, 1))
    second_review = _generate_review(db_session, second_account.id, date(2026, 7, 1))

    assert first_review.account_id != second_review.account_id
    assert first_review.metrics_snapshot["realized_pnl"] == "75.00"
    assert second_review.metrics_snapshot["realized_pnl"] == "-25.00"
    assert first_review.metrics_snapshot["most_traded_symbols"][0]["name"] == "XAUUSD"
    assert second_review.metrics_snapshot["most_traded_symbols"][0]["name"] == "EURUSD"

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    broker: Mapped[str] = mapped_column(String(128))
    server: Mapped[str] = mapped_column(String(128))
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    free_margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    trades: Mapped[list["Trade"]] = relationship(back_populates="account")
    risk_rule: Mapped["RiskRule"] = relationship(back_populates="account", uselist=False)
    snapshots: Mapped[list["AccountSnapshot"]] = relationship(back_populates="account")


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (
        Index("idx_account_snapshots_account_timestamp", "account_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    free_margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(32), default="mt5")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="snapshots")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("account_id", "ticket", name="uq_trades_account_ticket"),
        Index("idx_trades_account_open_time", "account_id", "open_time"),
        Index("idx_trades_account_close_time", "account_id", "close_time"),
        Index("idx_trades_ticket", "ticket"),
        Index("idx_trades_deal_id", "deal_id"),
        Index("idx_trades_position_id", "position_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    ticket: Mapped[str] = mapped_column(String(64), index=True)
    deal_id: Mapped[str | None] = mapped_column(String(64))
    position_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    order_type: Mapped[str] = mapped_column(String(32))
    lot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    sl: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    tp: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    swap: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(24), default="open")
    open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default="mt5")
    strategy: Mapped[str | None] = mapped_column(String(128))
    setup_name: Mapped[str | None] = mapped_column(String(128))
    emotion: Mapped[str | None] = mapped_column(String(64))
    mistake_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped[Account] = relationship(back_populates="trades")


class TradeEvent(Base):
    __tablename__ = "trade_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_trade_events_event_key"),
        Index("idx_trade_events_account_event_time", "account_id", "event_time"),
        Index("idx_trade_events_ticket", "ticket"),
        Index("idx_trade_events_deal_id", "deal_id"),
        Index("idx_trade_events_position_id", "position_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"), index=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    ticket: Mapped[str] = mapped_column(String(64), index=True)
    deal_id: Mapped[str | None] = mapped_column(String(64))
    position_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    order_type: Mapped[str] = mapped_column(String(32))
    lot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    sl: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    tp: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    swap: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskRule(Base):
    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, default=5)
    max_daily_loss_percent: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=5)
    max_total_loss_percent: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=10)
    max_consecutive_losses: Mapped[int] = mapped_column(Integer, default=3)
    cooldown_minutes_after_loss: Mapped[int] = mapped_column(Integer, default=30)
    max_lot: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1)
    max_risk_per_trade_percent: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=1)
    allow_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped[Account] = relationship(back_populates="risk_rule")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    action: Mapped[str] = mapped_column(String(16), default="block")
    category: Mapped[str] = mapped_column(String(32), default="risk")
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"
    __table_args__ = (
        Index("idx_rule_evaluations_checked_at", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    context: Mapped[str] = mapped_column(String(32), index=True)
    allowed: Mapped[bool] = mapped_column(Boolean)
    blocked: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    evaluation_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleViolation(Base):
    __tablename__ = "rule_violations"
    __table_args__ = (
        Index("idx_rule_violations_account_created_at", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("rule_evaluations.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id", ondelete="SET NULL"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    violation_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreTradeCheck(Base):
    __tablename__ = "pre_trade_checks"
    __table_args__ = (
        Index("idx_pre_trade_checks_account_created_at", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    order_type: Mapped[str] = mapped_column(String(8))
    lot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    sl: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    tp: Mapped[Decimal | None] = mapped_column(Numeric(18, 5))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    rule_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    rule_evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("rule_evaluations.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyReview(Base):
    __tablename__ = "daily_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    review_date: Mapped[date] = mapped_column(Date, index=True)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    mistakes: Mapped[str | None] = mapped_column(Text)
    best_trade: Mapped[str | None] = mapped_column(Text)
    worst_trade: Mapped[str | None] = mapped_column(Text)
    action_plan: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("account_id", "summary_date", name="uq_daily_summaries_account_date"),
        Index("idx_daily_summaries_account_date", "account_id", "summary_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    summary_date: Mapped[date] = mapped_column(Date, index=True)
    start_of_day_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    start_of_day_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    end_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    end_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    max_daily_loss_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    max_daily_loss_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
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


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    ticket: Mapped[str] = mapped_column(String(64), index=True)
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
    setup_name: Mapped[str | None] = mapped_column(String(128))
    emotion: Mapped[str | None] = mapped_column(String(64))
    mistake_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped[Account] = relationship(back_populates="trades")


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
    allow_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped[Account] = relationship(back_populates="risk_rule")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreTradeCheck(Base):
    __tablename__ = "pre_trade_checks"

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

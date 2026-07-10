import logging
from decimal import Decimal
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_mt5_api_key
from app.db.session import get_db
from app.models import Account, AccountSnapshot, Trade, TradeEvent
from app.schemas.mt5 import HeartbeatIn, TradeEventIn
from app.services.rule_engine import evaluate_rules, get_or_create_rule
from app.services.stats import real_account_filter
from app.services.trade_direction import is_sell_order, normalize_order_type

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mt5", tags=["mt5"])
TRACKED_TRADE_EVENT_TYPES = {"order_opened", "order_closed"}
MANAGEMENT_EVENT_TYPES = {"order_modified", "position_updated"}
MANAGEMENT_NOTE_PREFIX = "Bot: Trade management changes:"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _event_key(account_id: int, payload: TradeEventIn) -> str:
    parts = [
        str(account_id),
        payload.event_type,
        payload.ticket,
        payload.deal_id or "",
        payload.position_id or "",
        payload.symbol,
        payload.order_type,
        str(payload.lot),
        str(payload.sl or ""),
        str(payload.tp or ""),
        str(payload.close_price or ""),
        payload.open_time.isoformat() if payload.open_time else "",
        payload.close_time.isoformat() if payload.close_time else "",
    ]
    return "|".join(parts)


def _upsert_trade_event(db: Session, account_id: int, payload: TradeEventIn, trade_id: int | None = None) -> tuple[TradeEvent, bool]:
    event_key = _event_key(account_id, payload)
    event = db.scalar(select(TradeEvent).where(TradeEvent.event_key == event_key))
    if not event:
        event = TradeEvent(
            account_id=account_id,
            trade_id=trade_id,
            event_key=event_key,
            event_type=payload.event_type,
            ticket=payload.ticket,
            deal_id=payload.deal_id,
            position_id=payload.position_id,
            symbol=payload.symbol,
            order_type=payload.order_type,
            lot=payload.lot,
            entry_price=payload.entry_price,
            sl=payload.sl,
            tp=payload.tp,
            close_price=payload.close_price,
            profit=payload.profit,
            commission=payload.commission,
            swap=payload.swap,
            open_time=payload.open_time,
            close_time=_event_close_time(payload),
            event_time=payload.timestamp,
            payload=_jsonable(payload.model_dump()),
        )
        db.add(event)
        return event, True
    elif trade_id:
        event.trade_id = trade_id
    return event, False


def _find_trade_event(db: Session, account_id: int, payload: TradeEventIn) -> TradeEvent | None:
    return db.scalar(select(TradeEvent).where(TradeEvent.event_key == _event_key(account_id, payload)))


def _calculate_r_multiple(trade: Trade) -> Decimal | None:
    if not trade.entry_price or not trade.sl or not trade.close_price:
        return None
    risk = abs(Decimal(trade.entry_price) - Decimal(trade.sl))
    if not risk:
        return None
    if is_sell_order(trade.order_type, trade.entry_price, trade.sl, trade.tp):
        reward = Decimal(trade.entry_price) - Decimal(trade.close_price)
    else:
        reward = Decimal(trade.close_price) - Decimal(trade.entry_price)
    return reward / risk


def _same_decimal(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None or right is None:
        return left is right
    return Decimal(left) == Decimal(right)


def _is_repeated_close_event(trade: Trade, payload: TradeEventIn) -> bool:
    return (
        payload.event_type == "order_closed"
        and trade.status == "closed"
        and trade.close_time == payload.close_time
        and _same_decimal(trade.close_price, payload.close_price)
        and _same_decimal(trade.profit, payload.profit)
    )


def _has_recorded_close_event(db: Session, trade: Trade) -> bool:
    if not trade.id:
        return False
    return (
        db.scalar(
            select(TradeEvent.id)
            .where(TradeEvent.trade_id == trade.id, TradeEvent.event_type == "order_closed")
            .limit(1)
        )
        is not None
    )


def _is_duplicate_close_event(db: Session, trade: Trade, payload: TradeEventIn) -> bool:
    return (
        payload.event_type == "order_closed"
        and trade.status == "closed"
        and (_is_repeated_close_event(trade, payload) or _has_recorded_close_event(db, trade))
    )


def _event_close_time(payload: TradeEventIn) -> datetime | None:
    if payload.event_type != "order_closed" or not payload.close_time:
        return None
    if payload.close_time > payload.timestamp + datetime.resolution:
        return payload.timestamp
    return payload.close_time


def _decimal_text(value: Decimal) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _management_events_stmt(trade: Trade, close_time: datetime | None):
    stmt = select(TradeEvent).where(
        TradeEvent.account_id == trade.account_id,
        TradeEvent.event_type.in_(MANAGEMENT_EVENT_TYPES),
    )
    if trade.position_id:
        stmt = stmt.where(TradeEvent.position_id == trade.position_id)
    else:
        stmt = stmt.where(TradeEvent.ticket == trade.ticket)
    if trade.open_time:
        stmt = stmt.where(TradeEvent.event_time >= trade.open_time)
    if close_time:
        stmt = stmt.where(TradeEvent.event_time <= close_time)
    return stmt.order_by(TradeEvent.event_time.asc(), TradeEvent.id.asc())


def _changed_price_path(db: Session, trade: Trade, field_name: str, close_time: datetime | None) -> list[Decimal]:
    initial = getattr(trade, field_name)
    if initial is None:
        return []
    values = [Decimal(initial)]
    for event in db.scalars(_management_events_stmt(trade, close_time)):
        value = getattr(event, field_name)
        if value is None:
            continue
        price = Decimal(value)
        if price > 0 and price != values[-1]:
            values.append(price)
    return values if len(values) > 1 else []


def _management_note(db: Session, trade: Trade, close_time: datetime | None) -> str | None:
    parts: list[str] = []
    for field_name in ("sl", "tp"):
        values = _changed_price_path(db, trade, field_name, close_time)
        if values:
            path = " -> ".join(_decimal_text(value) for value in values)
            parts.append(f"{field_name.upper()} {path}")
    if not parts:
        return None
    return f"{MANAGEMENT_NOTE_PREFIX} {'; '.join(parts)}."


def _append_management_note(db: Session, trade: Trade, close_time: datetime | None) -> None:
    note = _management_note(db, trade, close_time)
    if not note or note in (trade.notes or ""):
        return
    trade.notes = f"{trade.notes.rstrip()}\n{note}" if trade.notes else note


def _find_trade_for_event(db: Session, account_id: int, payload: TradeEventIn) -> Trade | None:
    if payload.position_id:
        trade = db.scalar(
            select(Trade)
            .where(Trade.account_id == account_id, Trade.position_id == payload.position_id)
            .order_by(Trade.id.asc())
            .limit(1)
        )
        if trade:
            return trade
    return db.scalar(select(Trade).where(Trade.account_id == account_id, Trade.ticket == payload.ticket))


@router.post("/heartbeat", dependencies=[Depends(require_mt5_api_key)])
def receive_heartbeat(payload: HeartbeatIn, db: Session = Depends(get_db)) -> dict[str, object]:
    account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
    if not account:
        account = Account(
            account_number=payload.account_number,
            broker=payload.broker,
            server=payload.server,
            balance=payload.balance,
            equity=payload.equity,
            margin=payload.margin,
            free_margin=payload.free_margin,
        )
        db.add(account)
        db.flush()
        get_or_create_rule(db, account)
    else:
        account.broker = payload.broker
        account.server = payload.server
        account.balance = payload.balance
        account.equity = payload.equity
        account.margin = payload.margin
        account.free_margin = payload.free_margin

    db.add(
        AccountSnapshot(
            account_id=account.id,
            balance=payload.balance,
            equity=payload.equity,
            margin=payload.margin,
            free_margin=payload.free_margin,
            timestamp=payload.timestamp,
            source="mt5",
        )
    )
    result = evaluate_rules(db, account, persist=False)
    db.commit()
    logger.info("Heartbeat stored for account %s", payload.account_number)
    return {"ok": True, "account_id": account.id, "risk": result}


@router.post("/trade-event", dependencies=[Depends(require_mt5_api_key)])
def receive_trade_event(payload: TradeEventIn, db: Session = Depends(get_db)) -> dict[str, object]:
    account: Account | None = None
    if payload.account_number:
        account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
    if not account:
        account = db.scalar(
            select(Account)
            .where(real_account_filter())
            .order_by(Account.updated_at.desc(), Account.id.desc())
            .limit(1)
        )
    if not account:
        raise HTTPException(status_code=400, detail="Send heartbeat before trade events")

    is_close_event = payload.event_type == "order_closed"
    is_tracked_trade_event = payload.event_type in TRACKED_TRADE_EVENT_TYPES
    has_execution_identity = bool(payload.deal_id or payload.position_id)
    trade = _find_trade_for_event(db, account.id, payload)
    existing_event = _find_trade_event(db, account.id, payload)
    if existing_event:
        if trade and existing_event.trade_id is None:
            existing_event.trade_id = trade.id
            db.commit()
        logger.info("Duplicate trade event %s ignored for ticket %s", payload.event_type, payload.ticket)
        return {"ok": True, "duplicate": True, "trade_id": existing_event.trade_id}
    if trade and _is_duplicate_close_event(db, trade, payload):
        trade.order_type = normalize_order_type(trade.order_type, trade.entry_price, trade.sl, trade.tp)
        _append_management_note(db, trade, trade.close_time)
        trade.r_multiple = _calculate_r_multiple(trade)
        _upsert_trade_event(db, account.id, payload, trade.id)
        db.commit()
        logger.info("Repeated close event %s linked without changing trade %s", payload.deal_id, trade.ticket)
        return {"ok": True, "duplicate": True, "trade_id": trade.id}
    if trade and trade.status == "closed" and not is_close_event:
        _upsert_trade_event(db, account.id, payload, trade.id)
        db.commit()
        logger.info("Ignored non-close event %s for already closed trade %s", payload.event_type, trade.ticket)
        return {"ok": True, "ignored": True, "trade_id": trade.id}

    if not trade and (not is_tracked_trade_event or (payload.event_type == "order_opened" and not has_execution_identity)):
        _upsert_trade_event(db, account.id, payload)
        db.commit()
        logger.info("Ignored non-executed trade event %s for ticket %s", payload.event_type, payload.ticket)
        return {"ok": True, "ignored": True}
    if trade and trade.ticket != payload.ticket and not is_close_event:
        _upsert_trade_event(db, account.id, payload, trade.id)
        db.commit()
        logger.info("Linked non-close event %s for ticket %s to position trade %s", payload.event_type, payload.ticket, trade.ticket)
        return {"ok": True, "ignored": True, "trade_id": trade.id}
    if trade and not is_close_event and payload.event_type != "order_opened":
        _upsert_trade_event(db, account.id, payload, trade.id)
        db.commit()
        logger.info("Recorded management event %s for trade %s without changing initial SL/TP", payload.event_type, trade.ticket)
        return {"ok": True, "ignored": True, "trade_id": trade.id}

    status = "closed" if is_close_event else "open"
    order_type = normalize_order_type(payload.order_type, payload.entry_price, payload.sl, payload.tp)
    if not trade:
        close_time = _event_close_time(payload)
        trade = Trade(
            account_id=account.id,
            ticket=payload.ticket,
            deal_id=payload.deal_id,
            position_id=payload.position_id,
            symbol=payload.symbol,
            order_type=order_type,
            lot=payload.lot,
            entry_price=payload.entry_price,
            sl=payload.sl,
            tp=payload.tp,
            close_price=payload.close_price if is_close_event else None,
            profit=payload.profit if is_close_event else Decimal("0"),
            commission=payload.commission,
            swap=payload.swap,
            status=status,
            open_time=payload.open_time,
            close_time=close_time,
            source=payload.source,
            strategy=payload.strategy,
        )
        db.add(trade)
    else:
        trade.deal_id = payload.deal_id or trade.deal_id
        trade.position_id = payload.position_id or trade.position_id
        trade.symbol = payload.symbol
        if not is_close_event:
            trade.order_type = normalize_order_type(
                order_type or trade.order_type,
                payload.entry_price or trade.entry_price,
                payload.sl if payload.sl is not None else trade.sl,
                payload.tp if payload.tp is not None else trade.tp,
            )
            trade.lot = payload.lot
            trade.entry_price = payload.entry_price
            trade.sl = payload.sl
            trade.tp = payload.tp
            if trade.status != "closed":
                trade.status = "open"
        else:
            trade.order_type = normalize_order_type(trade.order_type, trade.entry_price, trade.sl, trade.tp)
            trade.lot = trade.lot or payload.lot
            trade.entry_price = trade.entry_price or payload.entry_price
            trade.sl = trade.sl if trade.sl is not None else payload.sl
            trade.tp = trade.tp if trade.tp is not None else payload.tp
            trade.close_price = payload.close_price
            close_time = _event_close_time(payload) or trade.close_time
            _append_management_note(db, trade, close_time)
            if trade.status == "closed":
                trade.profit = Decimal(trade.profit or 0) + Decimal(payload.profit or 0)
                trade.commission = Decimal(trade.commission or 0) + Decimal(payload.commission or 0)
                trade.swap = Decimal(trade.swap or 0) + Decimal(payload.swap or 0)
            else:
                trade.profit = payload.profit
                trade.commission = Decimal(trade.commission or 0) + Decimal(payload.commission or 0)
                trade.swap = Decimal(trade.swap or 0) + Decimal(payload.swap or 0)
            trade.status = status
        trade.open_time = trade.open_time or payload.open_time
        if is_close_event:
            trade.close_time = _event_close_time(payload) or trade.close_time
        trade.source = payload.source or trade.source
        trade.strategy = payload.strategy or trade.strategy

    db.flush()
    trade.r_multiple = _calculate_r_multiple(trade)

    _upsert_trade_event(db, account.id, payload, trade.id)

    result = evaluate_rules(db, account, trade)
    db.commit()
    logger.info("Trade event %s stored for ticket %s", payload.event_type, payload.ticket)
    return {"ok": True, "trade_id": trade.id, "risk": result}

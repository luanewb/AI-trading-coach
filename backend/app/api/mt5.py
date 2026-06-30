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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mt5", tags=["mt5"])


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


def _calculate_r_multiple(trade: Trade) -> Decimal | None:
    if not trade.entry_price or not trade.sl or not trade.close_price:
        return None
    risk = abs(Decimal(trade.entry_price) - Decimal(trade.sl))
    if not risk:
        return None
    if str(trade.order_type).lower() in {"sell", "short"}:
        reward = Decimal(trade.entry_price) - Decimal(trade.close_price)
    else:
        reward = Decimal(trade.close_price) - Decimal(trade.entry_price)
    return reward / risk


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
    result = evaluate_rules(db, account)
    db.commit()
    logger.info("Heartbeat stored for account %s", payload.account_number)
    return {"ok": True, "account_id": account.id, "risk": result}


@router.post("/trade-event", dependencies=[Depends(require_mt5_api_key)])
def receive_trade_event(payload: TradeEventIn, db: Session = Depends(get_db)) -> dict[str, object]:
    account: Account | None = None
    if payload.account_number:
        account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
    if not account:
        account = db.scalar(select(Account).order_by(Account.updated_at.desc(), Account.id.desc()).limit(1))
    if not account:
        raise HTTPException(status_code=400, detail="Send heartbeat before trade events")

    trade = db.scalar(select(Trade).where(Trade.account_id == account.id, Trade.ticket == payload.ticket))
    status = "closed" if payload.event_type == "order_closed" else "open"
    if not trade:
        trade = Trade(
            account_id=account.id,
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
            status=status,
            open_time=payload.open_time,
            close_time=payload.close_time,
            source=payload.source,
            strategy=payload.strategy,
        )
        db.add(trade)
    else:
        trade.deal_id = payload.deal_id or trade.deal_id
        trade.position_id = payload.position_id or trade.position_id
        trade.symbol = payload.symbol
        trade.order_type = payload.order_type
        trade.lot = payload.lot
        trade.entry_price = payload.entry_price
        trade.sl = payload.sl
        trade.tp = payload.tp
        trade.close_price = payload.close_price
        trade.profit = payload.profit
        trade.commission = payload.commission
        trade.swap = payload.swap
        trade.status = status
        trade.open_time = payload.open_time or trade.open_time
        trade.close_time = payload.close_time or trade.close_time
        trade.source = payload.source or trade.source
        trade.strategy = payload.strategy or trade.strategy

    db.flush()
    trade.r_multiple = _calculate_r_multiple(trade)

    event_key = _event_key(account.id, payload)
    event = db.scalar(select(TradeEvent).where(TradeEvent.event_key == event_key))
    if not event:
        event = TradeEvent(
            account_id=account.id,
            trade_id=trade.id,
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
            close_time=payload.close_time,
            event_time=payload.timestamp,
            payload=_jsonable(payload.model_dump()),
        )
        db.add(event)
    else:
        event.trade_id = trade.id

    result = evaluate_rules(db, account, trade)
    db.commit()
    logger.info("Trade event %s stored for ticket %s", payload.event_type, payload.ticket)
    return {"ok": True, "trade_id": trade.id, "risk": result}

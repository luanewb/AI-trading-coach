import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_mt5_api_key
from app.db.session import get_db
from app.models import Account, Trade
from app.schemas.mt5 import HeartbeatIn, TradeEventIn
from app.services.rule_engine import evaluate_rules, get_or_create_rule

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mt5", tags=["mt5"])


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
        )
        db.add(trade)
    else:
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

    if trade.status == "closed" and trade.entry_price and trade.sl:
        risk = abs(Decimal(trade.entry_price) - Decimal(trade.sl))
        reward = abs((Decimal(trade.close_price or trade.entry_price)) - Decimal(trade.entry_price))
        trade.r_multiple = reward / risk if risk else None

    db.flush()
    result = evaluate_rules(db, account, trade)
    db.commit()
    logger.info("Trade event %s stored for ticket %s", payload.event_type, payload.ticket)
    return {"ok": True, "trade_id": trade.id, "risk": result}

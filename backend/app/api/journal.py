from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Trade
from app.schemas.journal import StatsOut, TradeOut, TradePatch
from app.services.stats import calculate_stats

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    db: Session = Depends(get_db),
    symbol: str | None = None,
    setup: str | None = None,
    result: str | None = Query(default=None, pattern="^(win|loss)$"),
    trade_date: date | None = None,
) -> list[Trade]:
    stmt = select(Trade).order_by(Trade.open_time.desc().nullslast(), Trade.id.desc())
    if symbol:
        stmt = stmt.where(Trade.symbol.ilike(f"%{symbol}%"))
    if setup:
        stmt = stmt.where(Trade.setup_name.ilike(f"%{setup}%"))
    if result == "win":
        stmt = stmt.where(Trade.profit > 0)
    if result == "loss":
        stmt = stmt.where(Trade.profit < 0)
    if trade_date:
        start = datetime.combine(trade_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(trade_date, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(Trade.open_time >= start, Trade.open_time <= end)
    return list(db.scalars(stmt))


@router.patch("/trades/{trade_id}", response_model=TradeOut)
def update_trade(trade_id: int, payload: TradePatch, db: Session = Depends(get_db)) -> Trade:
    trade = db.get(Trade, trade_id)
    if not trade:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Trade not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trade, field, value)
    db.commit()
    db.refresh(trade)
    return trade


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> dict[str, float | int]:
    return calculate_stats(db)

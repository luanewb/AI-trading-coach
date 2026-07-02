from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.news import (
    EconomicEventOut,
    NewsRestrictionSettingsIn,
    NewsRestrictionSettingsOut,
    NewsRestrictionStatusOut,
    TradeRestrictionEventOut,
)
from app.services.news_restrictions import (
    event_to_dict,
    get_or_create_settings,
    list_restricted_events,
    list_restriction_logs,
    restriction_status,
    update_settings,
)
from app.services.timezone import now_utc

router = APIRouter(tags=["news-restrictions"])


@router.get("/api/news/restricted-events", response_model=list[EconomicEventOut])
def restricted_events(currency: str = "USD", db: Session = Depends(get_db)) -> list[dict[str, object]]:
    settings = get_or_create_settings(db)
    events = list_restricted_events(db, currency=currency)
    return [payload for event in events if (payload := event_to_dict(event, settings))]


@router.get("/api/news/restricted-events/upcoming", response_model=list[EconomicEventOut])
def upcoming_restricted_events(currency: str = "USD", db: Session = Depends(get_db)) -> list[dict[str, object]]:
    settings = get_or_create_settings(db)
    events = list_restricted_events(db, currency=currency, from_time=now_utc(), to_time=now_utc() + timedelta(days=14), limit=100)
    return [payload for event in events if (payload := event_to_dict(event, settings))]


@router.get("/api/news/restriction-status", response_model=NewsRestrictionStatusOut)
def get_restriction_status(
    symbol: str,
    action: str = "new_order",
    at: datetime | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return restriction_status(db, symbol=symbol, action=action, at_time=at)


@router.get("/api/news/restriction-logs", response_model=list[TradeRestrictionEventOut])
def restriction_logs(db: Session = Depends(get_db)) -> list[object]:
    return list_restriction_logs(db)


@router.get("/api/settings/news-restrictions", response_model=NewsRestrictionSettingsOut)
def get_news_restriction_settings(db: Session = Depends(get_db)) -> object:
    settings = get_or_create_settings(db)
    db.commit()
    return settings


@router.patch("/api/settings/news-restrictions", response_model=NewsRestrictionSettingsOut)
def patch_news_restriction_settings(payload: NewsRestrictionSettingsIn, db: Session = Depends(get_db)) -> object:
    settings = update_settings(db, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(settings)
    return settings

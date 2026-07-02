import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import NewsRestrictedEvent, NewsRestrictionSettings, TradeRestrictionEvent
from app.services.timezone import now_utc

logger = logging.getLogger(__name__)

RESTRICTED_EVENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("non_farm_payrolls", ("non farm payroll", "nonfarm payroll", "nfp", "non-farm employment change")),
    ("us_unemployment_rate", ("unemployment rate", "jobless rate")),
    ("average_hourly_earnings", ("average hourly earnings", "wage", "wages", "earnings m/m")),
    ("cpi", ("consumer price index", "cpi", "core cpi", "inflation rate")),
    ("advance_gdp", ("advance gdp", "gross domestic product advance", "gdp advance", "advance gross domestic product")),
    ("fomc_rate_decision", ("fomc rate decision", "federal funds rate", "interest rate decision", "fed interest rate")),
    ("fomc_statement", ("fomc statement", "fed monetary policy statement")),
    ("fomc_press_conference", ("fomc press conference", "fed press conference", "fomc presser")),
    ("fomc_minutes", ("fomc minutes", "fed minutes")),
)

DEFAULT_BLOCKED_ACTIONS = ["new_order", "manual_close", "modify_sl_tp", "pending_order"]
VALID_ACTIONS = set(DEFAULT_BLOCKED_ACTIONS)
VALID_MODES = {"warn_only", "block_actions", "disabled"}
VALID_ACCOUNT_TYPES = {"standard_funded", "swing", "evaluation"}


@dataclass(frozen=True)
class EconomicEvent:
    id: str
    source: str
    title: str
    normalized_title: str
    currency: str
    scheduled_at: datetime
    country: str | None = None
    impact: str | None = None
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    is_restricted: bool = False
    restriction_reason: str | None = None
    raw_payload: dict[str, object] | None = None


class EconomicCalendarProvider(Protocol):
    def get_events(self, *, from_time: datetime, to_time: datetime, currencies: list[str] | None = None) -> list[EconomicEvent]:
        ...


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _ensure_utc(value).isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def normalize_event_title(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    text = re.sub(r"\s+", " ", text)
    for canonical, aliases in RESTRICTED_EVENT_PATTERNS:
        if any(alias in text for alias in aliases):
            return canonical
    return text.replace(" ", "_")


def is_restricted_usd_event(title: str, currency: str | None) -> tuple[bool, str | None, str]:
    normalized = normalize_event_title(title)
    if (currency or "").upper() != "USD":
        return False, None, normalized
    restricted = any(normalized == canonical for canonical, _aliases in RESTRICTED_EVENT_PATTERNS)
    reason = "FTMO restricted USD news event" if restricted else None
    return restricted, reason, normalized


def is_usd_sensitive_symbol(symbol: str) -> bool:
    clean = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    if not clean:
        return False
    usd_pairs = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD", "XAUUSD", "XAGUSD")
    usd_indices = ("US30", "DJ30", "DJI", "NAS100", "US100", "USTEC", "SPX500", "US500", "USOIL", "WTI")
    if any(clean.startswith(item) for item in usd_pairs + usd_indices):
        return True
    return "USD" in clean[:8]


def _stable_event_id(source: str, title: str, currency: str, scheduled_at: datetime) -> str:
    raw = f"{source}|{title}|{currency}|{_ensure_utc(scheduled_at).isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


class MockCalendarProvider:
    def get_events(self, *, from_time: datetime, to_time: datetime, currencies: list[str] | None = None) -> list[EconomicEvent]:
        scheduled_at = datetime(2026, 7, 2, 12, 30, tzinfo=timezone.utc)
        if _ensure_utc(from_time) > scheduled_at or _ensure_utc(to_time) < scheduled_at:
            return []
        if currencies and "USD" not in {currency.upper() for currency in currencies}:
            return []
        return [
            EconomicEvent(
                id="ftmo-2026-07-02-us-nfp",
                source="mock",
                title="Non-Farm Employment Change",
                normalized_title="non_farm_payrolls",
                currency="USD",
                country="US",
                scheduled_at=scheduled_at,
                impact="high",
                forecast="114 K",
                previous="172 K",
                is_restricted=True,
                restriction_reason="FTMO restricted USD news event",
                raw_payload={
                    "instrument": "USD + US Indices + XAUUSD + DXY",
                    "source_note": "Development seed matching the FTMO restricted calendar screenshot for 2026-07-02.",
                },
            )
        ]


class _HttpCalendarProvider:
    source = "http"

    def __init__(self, url: str, api_key: str | None = None, api_key_header: str = "Authorization") -> None:
        self.url = url
        self.api_key = api_key
        self.api_key_header = api_key_header

    def get_events(self, *, from_time: datetime, to_time: datetime, currencies: list[str] | None = None) -> list[EconomicEvent]:
        headers: dict[str, str] = {}
        if self.api_key:
            value = self.api_key if self.api_key.lower().startswith("bearer ") else f"Bearer {self.api_key}"
            headers[self.api_key_header] = value
        params = {
            "from": _ensure_utc(from_time).isoformat(),
            "to": _ensure_utc(to_time).isoformat(),
        }
        if currencies:
            params["currencies"] = ",".join(currencies)
        with httpx.Client(timeout=20) as client:
            response = client.get(self.url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        items = payload.get("events", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return []
        return [event for item in items if isinstance(item, dict) and (event := self._parse_item(item))]

    def _parse_item(self, item: dict[str, Any]) -> EconomicEvent | None:
        title = str(item.get("title") or item.get("event") or item.get("name") or "").strip()
        currency = str(item.get("currency") or item.get("ccy") or "").upper()
        scheduled_at = _parse_datetime(item.get("scheduledAt") or item.get("scheduled_at") or item.get("date") or item.get("time"))
        if not title or not currency or not scheduled_at:
            return None
        restricted, reason, normalized = is_restricted_usd_event(title, currency)
        source_id = str(item.get("id") or item.get("event_id") or _stable_event_id(self.source, title, currency, scheduled_at))
        return EconomicEvent(
            id=source_id,
            source=self.source,
            title=title,
            normalized_title=normalized,
            currency=currency,
            country=item.get("country"),
            scheduled_at=scheduled_at,
            impact=item.get("impact"),
            actual=item.get("actual"),
            forecast=item.get("forecast"),
            previous=item.get("previous"),
            is_restricted=restricted,
            restriction_reason=reason,
            raw_payload=item,
        )


class FTMOCalendarProvider(_HttpCalendarProvider):
    source = "ftmo"


class FallbackEconomicCalendarProvider(_HttpCalendarProvider):
    source = "fallback"


def build_calendar_provider() -> EconomicCalendarProvider:
    settings = get_settings()
    provider = settings.news_restrictions_provider.lower().strip()
    if provider == "ftmo" and settings.news_restrictions_ftmo_calendar_url:
        return FTMOCalendarProvider(
            settings.news_restrictions_ftmo_calendar_url,
            settings.news_restrictions_api_key,
            settings.news_restrictions_api_key_header,
        )
    if provider == "fallback" and settings.news_restrictions_fallback_url:
        return FallbackEconomicCalendarProvider(
            settings.news_restrictions_fallback_url,
            settings.news_restrictions_api_key,
            settings.news_restrictions_api_key_header,
        )
    return MockCalendarProvider()


def get_or_create_settings(db: Session) -> NewsRestrictionSettings:
    settings = db.scalar(select(NewsRestrictionSettings).order_by(NewsRestrictionSettings.id).limit(1))
    if isinstance(settings, NewsRestrictionSettings):
        if not settings.blocked_actions:
            settings.blocked_actions = list(DEFAULT_BLOCKED_ACTIONS)
        return settings
    settings = NewsRestrictionSettings(
        account_type="standard_funded",
        enforcement_mode="block_actions",
        minutes_before=2,
        minutes_after=2,
        apply_usd_only=True,
        blocked_actions=list(DEFAULT_BLOCKED_ACTIONS),
    )
    db.add(settings)
    db.flush()
    return settings


def update_settings(db: Session, values: dict[str, object]) -> NewsRestrictionSettings:
    settings = get_or_create_settings(db)
    for key, value in values.items():
        if value is None:
            continue
        if key == "blocked_actions":
            actions = [str(action) for action in value if str(action) in VALID_ACTIONS] if isinstance(value, list) else []
            setattr(settings, key, actions or list(DEFAULT_BLOCKED_ACTIONS))
        elif key == "enforcement_mode" and str(value) in VALID_MODES:
            setattr(settings, key, str(value))
        elif key == "account_type" and str(value) in VALID_ACCOUNT_TYPES:
            setattr(settings, key, str(value))
        else:
            setattr(settings, key, value)
    db.flush()
    return settings


def event_window(event: NewsRestrictedEvent, settings: NewsRestrictionSettings) -> tuple[datetime, datetime]:
    scheduled_at = _ensure_utc(event.scheduled_at)
    return scheduled_at - timedelta(minutes=settings.minutes_before), scheduled_at + timedelta(minutes=settings.minutes_after)


def event_to_dict(event: NewsRestrictedEvent | None, settings: NewsRestrictionSettings | None = None) -> dict[str, object] | None:
    if not event:
        return None
    payload: dict[str, object] = {
        "id": event.id,
        "source": event.source,
        "title": event.title,
        "normalized_title": event.normalized_title,
        "currency": event.currency,
        "country": event.country,
        "scheduled_at": _ensure_utc(event.scheduled_at),
        "impact": event.impact,
        "actual": event.actual,
        "forecast": event.forecast,
        "previous": event.previous,
        "is_restricted": event.is_restricted,
        "restriction_reason": event.restriction_reason,
    }
    if settings:
        start, end = event_window(event, settings)
        payload["window_start"] = start
        payload["window_end"] = end
    return payload


def upsert_economic_events(db: Session, events: list[EconomicEvent]) -> int:
    count = 0
    for event in events:
        restricted, reason, normalized = is_restricted_usd_event(event.title, event.currency)
        existing = db.scalar(
            select(NewsRestrictedEvent).where(
                NewsRestrictedEvent.source == event.source,
                NewsRestrictedEvent.source_event_id == event.id,
            )
        )
        values = {
            "title": event.title,
            "normalized_title": event.normalized_title or normalized,
            "currency": event.currency.upper(),
            "country": event.country,
            "scheduled_at": _ensure_utc(event.scheduled_at),
            "impact": event.impact,
            "actual": event.actual,
            "forecast": event.forecast,
            "previous": event.previous,
            "is_restricted": event.is_restricted or restricted,
            "restriction_reason": event.restriction_reason or reason,
            "raw_payload": event.raw_payload or {},
        }
        if isinstance(existing, NewsRestrictedEvent):
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(NewsRestrictedEvent(source=event.source, source_event_id=event.id, **values))
        count += 1
    db.flush()
    return count


def sync_restricted_events(db: Session, provider: EconomicCalendarProvider | None = None, *, base_time: datetime | None = None) -> int:
    provider = provider or build_calendar_provider()
    anchor = _ensure_utc(base_time or now_utc())
    events = provider.get_events(
        from_time=anchor - timedelta(hours=24),
        to_time=anchor + timedelta(days=14),
        currencies=["USD"],
    )
    return upsert_economic_events(db, events)


def list_restricted_events(db: Session, *, currency: str = "USD", from_time: datetime | None = None, to_time: datetime | None = None, limit: int = 200) -> list[NewsRestrictedEvent]:
    stmt = (
        select(NewsRestrictedEvent)
        .where(NewsRestrictedEvent.currency == currency.upper(), NewsRestrictedEvent.is_restricted.is_(True))
        .order_by(NewsRestrictedEvent.scheduled_at.asc())
        .limit(limit)
    )
    if from_time:
        stmt = stmt.where(NewsRestrictedEvent.scheduled_at >= _ensure_utc(from_time))
    if to_time:
        stmt = stmt.where(NewsRestrictedEvent.scheduled_at <= _ensure_utc(to_time))
    return list(db.scalars(stmt))


def restriction_status(db: Session, *, symbol: str, action: str = "new_order", at_time: datetime | None = None) -> dict[str, object]:
    checked_at = _ensure_utc(at_time or now_utc())
    settings = get_or_create_settings(db)
    action = action if action in VALID_ACTIONS else "new_order"
    usd_sensitive = is_usd_sensitive_symbol(symbol)
    effective_mode = settings.enforcement_mode
    if settings.account_type != "standard_funded" and settings.enforcement_mode == "block_actions":
        effective_mode = "warn_only"
    if settings.apply_usd_only and not usd_sensitive:
        effective_mode = "disabled"

    lookback = checked_at - timedelta(minutes=max(settings.minutes_after, 1))
    lookahead = checked_at + timedelta(days=14)
    candidates = list_restricted_events(db, currency="USD", from_time=lookback, to_time=lookahead)
    current_event = None
    upcoming_event = None
    seconds_until_event = None
    seconds_until_end = None
    restricted_until = None
    for event in candidates:
        start, end = event_window(event, settings)
        if start <= checked_at <= end:
            current_event = event
            restricted_until = end
            seconds_until_end = max(0, int((end - checked_at).total_seconds()))
            break
        if event.scheduled_at > checked_at and upcoming_event is None:
            upcoming_event = event
            seconds_until_event = max(0, int((_ensure_utc(event.scheduled_at) - checked_at).total_seconds()))

    is_restricted_now = current_event is not None and effective_mode != "disabled"
    should_block = is_restricted_now and effective_mode == "block_actions" and action in (settings.blocked_actions or DEFAULT_BLOCKED_ACTIONS)
    should_warn = is_restricted_now and (should_block or effective_mode == "warn_only")

    return {
        "symbol": symbol,
        "action": action,
        "usd_sensitive": usd_sensitive,
        "is_restricted_now": is_restricted_now,
        "enforcement_mode": settings.enforcement_mode,
        "effective_mode": effective_mode,
        "account_type": settings.account_type,
        "should_block": should_block,
        "should_warn": should_warn,
        "blocked_actions": settings.blocked_actions or list(DEFAULT_BLOCKED_ACTIONS),
        "current_event": event_to_dict(current_event, settings),
        "upcoming_event": event_to_dict(upcoming_event, settings),
        "seconds_until_event": seconds_until_event,
        "seconds_until_restriction_end": seconds_until_end,
        "restricted_until": restricted_until,
        "checked_at": checked_at,
    }


def log_restriction_event(
    db: Session,
    *,
    account_id: int | None,
    account_number: str | None,
    symbol: str,
    action: str,
    status: dict[str, object],
    context: dict[str, object] | None = None,
) -> TradeRestrictionEvent | None:
    event = status.get("current_event")
    if not event or not status.get("should_warn"):
        return None
    log = TradeRestrictionEvent(
        account_id=account_id,
        account_number=account_number,
        symbol=symbol,
        action=action,
        mode=str(status.get("effective_mode") or status.get("enforcement_mode")),
        blocked=bool(status.get("should_block")),
        news_event_id=event.get("id") if isinstance(event, dict) else None,
        event_title=event.get("title") if isinstance(event, dict) else None,
        restricted_until=status.get("restricted_until"),
        context=_jsonable(context or {}),
    )
    db.add(log)
    db.flush()
    return log


def news_finding_payload(status: dict[str, object]) -> tuple[str, str, str, dict[str, object]] | None:
    event = status.get("current_event")
    if not isinstance(event, dict) or not status.get("should_warn"):
        return None
    action = "block" if status.get("should_block") else "warn"
    event_title = str(event.get("title") or "restricted news")
    until = status.get("restricted_until")
    message = f"FTMO restricted news window is active for {event_title}."
    if until:
        message = f"{message} Restriction ends at {until}."
    metadata = {
        "news_event": event,
        "effective_mode": status.get("effective_mode"),
        "blocked_actions": status.get("blocked_actions"),
        "seconds_until_restriction_end": status.get("seconds_until_restriction_end"),
    }
    return "NEWS_RESTRICTED_WINDOW", action, message, metadata


def list_restriction_logs(db: Session, *, limit: int = 200) -> list[TradeRestrictionEvent]:
    stmt = select(TradeRestrictionEvent).order_by(TradeRestrictionEvent.created_at.desc(), TradeRestrictionEvent.id.desc()).limit(limit)
    return list(db.scalars(stmt))

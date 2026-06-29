from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def trading_day_bounds(target: datetime | None = None) -> tuple[datetime, datetime]:
    settings = get_settings()
    local_tz = ZoneInfo(settings.ftmo_timezone)
    local_now = (target or now_utc()).astimezone(local_tz)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=local_tz)
    end_local = datetime.combine(local_now.date(), time.max, tzinfo=local_tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

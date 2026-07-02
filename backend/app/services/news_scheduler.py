import asyncio
import logging
from contextlib import suppress

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.news_restrictions import sync_restricted_events

logger = logging.getLogger(__name__)
_task: asyncio.Task[None] | None = None


async def _sync_loop() -> None:
    settings = get_settings()
    interval = max(60, settings.news_restrictions_sync_interval_seconds)
    while True:
        try:
            with SessionLocal() as db:
                count = sync_restricted_events(db)
                db.commit()
                logger.info("Synced restricted news events", extra={"event_count": count})
        except Exception:
            logger.warning("Restricted news sync failed", exc_info=True)
        await asyncio.sleep(interval)


def start_news_sync_scheduler() -> None:
    global _task
    settings = get_settings()
    if not settings.news_restrictions_sync_enabled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _task is None or _task.done():
        _task = loop.create_task(_sync_loop())


async def stop_news_sync_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
    _task = None

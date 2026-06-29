import logging

import httpx

from app.core.config import get_settings
from app.models import Alert

logger = logging.getLogger(__name__)


def send_telegram_alert(alert: Alert) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return

    message = f"[{alert.severity.upper()}] {alert.type}\n{alert.message}"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(url, json={"chat_id": settings.telegram_chat_id, "text": message}, timeout=8)
        response.raise_for_status()
    except Exception:
        logger.exception("Failed to send Telegram alert")

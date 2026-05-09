"""Отправка уведомления о лиде в Telegram."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def send_lead_message(text: str) -> tuple[bool, str | None, str | None]:
    """
    Возвращает (успех, message_id или None, текст ошибки или None).
    Если токен или chat_id не заданы — считается пропуском (не ошибкой HTTP).
    """
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_lead_chat_id.strip()
    if not token or not chat_id:
        return False, None, "Telegram: TELEGRAM_BOT_TOKEN или TELEGRAM_LEAD_CHAT_ID не заданы"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            err = data.get("description", str(data))
            return False, None, err
        mid = str(data.get("result", {}).get("message_id", ""))
        return True, mid or None, None
    except Exception as e:
        logger.exception("Telegram send failed")
        return False, None, str(e)

"""Проверка отправки сообщения в Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_LEAD_CHAT_ID).

Запуск из корня проекта:
  python scripts/test_telegram.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from load_env import load_env

load_env()

from app.telegram_notify import send_lead_message


def main() -> None:
    text = (
        "Тест ASSISTANT_DM: если вы видите это сообщение, токен и chat_id настроены верно.\n"
        "Дальше проверьте заявку через чат на /ui/ — после submit_lead придёт второе сообщение с данными лида."
    )
    ok, mid, err = send_lead_message(text)
    if ok:
        print("OK, message_id=", mid)
        return
    print("Ошибка:", err or "unknown")
    sys.exit(1)


if __name__ == "__main__":
    main()

"""Создание лида в БД и уведомления Telegram / email."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.email_notify import send_lead_email, utc_now_iso
from app.models import Lead
from app.telegram_notify import send_lead_message

logger = logging.getLogger(__name__)


def normalize_phone_for_storage(phone: str) -> str:
    """
    Убирает пробелы, скобки, дефисы и др.; для типичных РФ-номеров даёт 11 цифр с ведущей 7.
    Примеры: 89766758495, +7 964 ..., 8 (495) 739-00-08 → 79766758495, 79643426354, 74957390008.
    Иностранные номера — как последовательность цифр (от 10 знаков), без принудительной 7.
    """
    d = "".join(c for c in (phone or "").strip() if c.isdigit())
    if not d:
        return ""

    if len(d) == 11 and d[0] == "8":
        d = "7" + d[1:]
    if len(d) == 11 and d[0] == "7":
        return d
    if len(d) == 10 and d[0] == "9":
        return "7" + d
    if len(d) == 10 and (
        d.startswith("495")
        or d.startswith("499")
        or d.startswith("812")
        or d.startswith("383")
        or d.startswith("391")
    ):
        return "7" + d
    if len(d) >= 10:
        return d
    return ""


def phone_for_display(stored_digits: str) -> str:
    """Человекочитаемый вид для Telegram и отображения."""
    if len(stored_digits) == 11 and stored_digits.startswith("7"):
        return (
            "+7 "
            + "("
            + stored_digits[1:4]
            + ") "
            + stored_digits[4:7]
            + "-"
            + stored_digits[7:9]
            + "-"
            + stored_digits[9:11]
        )
    return stored_digits


def format_lead_telegram_text(
    *,
    lead_id: int,
    display_name: str | None,
    phone: str,
    preferred_contact_at: str | None,
    topic: str | None,
    notes: str | None,
) -> str:
    lines = [
        "Новая заявка с сайта (ассистент)",
        f"ID: {lead_id}",
        f"Имя: {display_name or '—'}",
        f"Телефон: {phone_for_display(phone)}",
        f"Удобное время: {preferred_contact_at or '—'}",
        f"Тема: {topic or '—'}",
    ]
    if notes:
        lines.append(f"Комментарий: {notes}")
    return "\n".join(lines)


def submit_lead_from_tool(
    db: Session,
    *,
    session_id: str | None,
    args: dict,
) -> dict:
    """
    Вызывается из обработчика tool_calls submit_lead.
    Возвращает сериализуемый dict для поля content сообщения role=tool.
    """
    display_name = (args.get("display_name") or "").strip() or None
    phone_raw = (args.get("phone") or "").strip()
    preferred_contact_at = (args.get("preferred_contact_at") or "").strip() or None
    topic = (args.get("topic") or "").strip() or None
    notes = (args.get("notes") or "").strip() or None

    if not display_name or len(display_name) < 2:
        return {
            "ok": False,
            "error": "Не передано имя: сначала спросите, как обращаться, и вызовите submit_lead с непустым display_name из ответа клиента.",
        }

    bogus_names = {"—", "-", ".", "клиент", "client", "user", "пользователь", "не указано", "нет", "нет имени"}
    if display_name.lower() in bogus_names:
        return {
            "ok": False,
            "error": "Нужно реальное имя или форма обращения от клиента, не заглушка.",
        }

    phone = normalize_phone_for_storage(phone_raw)
    if len(phone) < 10:
        return {"ok": False, "error": "Укажите корректный номер телефона (минимум 10 цифр после нормализации)."}

    if session_id:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        cutoff_naive = cutoff.replace(tzinfo=None)
        dup = db.scalars(
            select(Lead)
            .where(
                Lead.session_id == session_id,
                Lead.phone == phone,
                Lead.created_at >= cutoff_naive,
            )
            .limit(1)
        ).first()
        if dup is not None:
            # Раньше дубликат не слал Telegram — кажется «заявка принята, а в канале тишина».
            dup_note = (
                "Повторная заявка (тот же номер недавно в этой же сессии)\n"
                f"Лид уже был: #{dup.id}\n"
                f"Имя (новая попытка): {display_name}\n"
                f"Удобное время: {preferred_contact_at or '—'}\n"
                f"Тема: {topic or '—'}"
                + (f"\nКомментарий: {notes}" if notes else "")
            )
            tg_ok, tg_mid, tg_err = send_lead_message(dup_note)
            if not tg_ok and tg_err:
                logger.warning("Duplicate lead telegram: %s", tg_err)
            return {
                "ok": True,
                "duplicate": True,
                "lead_id": dup.id,
                "message": "Заявка с этим номером недавно уже была в этой сессии; данные сохранены. Уведомление отправлено повторно.",
                "telegram_notified": bool(tg_ok),
                "telegram_error": tg_err,
            }

    lead = Lead(
        session_id=session_id,
        display_name=display_name,
        phone=phone,
        preferred_contact_at=preferred_contact_at,
        topic=topic,
        notes=notes,
        status="new",
    )
    db.add(lead)
    db.flush()

    text = format_lead_telegram_text(
        lead_id=lead.id,
        display_name=display_name,
        phone=phone,
        preferred_contact_at=preferred_contact_at,
        topic=topic,
        notes=notes,
    )

    tg_ok, tg_mid, tg_err = send_lead_message(text)
    if tg_ok and tg_mid:
        lead.telegram_message_id = tg_mid
        lead.status = "notified"
        lead.error_detail = None
        logger.info("Lead %s sent to Telegram, message_id=%s", lead.id, tg_mid)
    elif tg_err:
        lead.error_detail = tg_err
        lead.status = "failed" if settings.telegram_bot_token.strip() else "new"
        logger.warning("Lead %s: Telegram не отправлено: %s", lead.id, tg_err)

    if settings.email_leads_enabled:
        subj = f"Заявка #{lead.id} — {display_name or phone}"
        ok_mail, mail_err = send_lead_email(subj, text)
        if ok_mail:
            lead.email_sent_at = utc_now_iso()
            lead.email_error = None
        else:
            lead.email_error = mail_err

    db.commit()

    return {
        "ok": True,
        "lead_id": lead.id,
        "display_name": display_name,
        "preferred_contact_at": preferred_contact_at,
        "topic": topic,
        "telegram_notified": bool(tg_ok),
        "telegram_error": tg_err,
        "message": "Заявка сохранена.",
    }


def parse_tool_arguments(arguments: str) -> dict:
    try:
        data = json.loads(arguments or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("submit_lead: invalid JSON arguments")
        return {}

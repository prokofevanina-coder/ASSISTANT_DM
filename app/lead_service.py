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


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone.strip() if not ch.isspace())


def format_lead_telegram_text(
    *,
    lead_id: int,
    display_name: str | None,
    phone: str,
    preferred_contact_at: str | None,
    topic: str | None,
    notes: str | None,
    session_id: str | None,
) -> str:
    lines = [
        "Новая заявка с сайта (ассистент)",
        f"ID: {lead_id}",
        f"Имя: {display_name or '—'}",
        f"Телефон: {phone}",
        f"Удобное время: {preferred_contact_at or '—'}",
        f"Тема: {topic or '—'}",
    ]
    if notes:
        lines.append(f"Комментарий: {notes}")
    if session_id:
        lines.append(f"session_id: {session_id}")
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

    phone = _normalize_phone(phone_raw)
    if len(phone) < 5:
        return {"ok": False, "error": "Укажите корректный номер телефона"}

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
            return {
                "ok": True,
                "duplicate": True,
                "lead_id": dup.id,
                "message": "Заявка с этим номером недавно уже создана в этой сессии.",
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
        session_id=session_id,
    )

    tg_ok, tg_mid, tg_err = send_lead_message(text)
    if tg_ok and tg_mid:
        lead.telegram_message_id = tg_mid
        lead.status = "notified"
        lead.error_detail = None
    elif tg_err:
        lead.error_detail = tg_err
        lead.status = "failed" if settings.telegram_bot_token.strip() else "new"

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

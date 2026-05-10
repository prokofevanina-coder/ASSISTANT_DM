"""Оркестрация диалога: история, LLM, submit_lead."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.knowledge import build_system_instructions, load_knowledge_bundle
from app.lead_service import (
    normalize_phone_for_storage,
    parse_tool_arguments,
    phone_for_display,
    submit_lead_from_tool,
)
from app.llm import SUBMIT_LEAD_TOOL, chat_completion
from app.models import ChatMessage, ChatSession, Lead

logger = logging.getLogger(__name__)


def _strip_markdown_for_chat(text: str) -> str:
    """
    Убирает типичную разметку Markdown из ответа: # заголовки, **…**, списки (-, *, + в начале строки).
    Чат рендерит plain text — без этой очистки остаются «лишние» символы ** #- -
    """
    if not text:
        return text
    s = text
    s = re.sub(r"(?m)^#{1,6}\s*", "", s)
    for _ in range(8):
        prev = s
        s = re.sub(r"__([^_]+)__", r"\1", s)
        if s == prev:
            break
    s = s.replace("__", "")
    s = s.replace("**", "")
    dash = r"\-\u2010\u2011\u2012\u2013\u2014\u2212"
    bullet = rf"(?:[*+•]|[{dash}])"
    s = re.sub(rf"(?m)^[\s\uFEFF]*{bullet}\s+", "• ", s)
    return s.strip()


_PROMPT_TEXT: str | None = None
_PROMPT_MTIME: float | None = None


def _load_prompt_system_text() -> str:
    """Читает prompt_system.txt; при изменении файла на диске подхватывает новую версию без перезапуска процесса."""
    global _PROMPT_TEXT, _PROMPT_MTIME
    path = Path(__file__).resolve().parent.parent / "prompt_system.txt"
    if not path.is_file():
        return "Ты — вежливый ассистент по корпоративным тренингам."
    mtime = path.stat().st_mtime
    if _PROMPT_TEXT is not None and _PROMPT_MTIME == mtime:
        return _PROMPT_TEXT
    _PROMPT_TEXT = path.read_text(encoding="utf-8")
    _PROMPT_MTIME = mtime
    logger.debug("prompt_system.txt перечитан (mtime=%s)", mtime)
    return _PROMPT_TEXT


def _ensure_session(db: Session, session_id: str | None, user_agent: str | None) -> str:
    sid = session_id or str(uuid4())
    row = db.get(ChatSession, sid)
    if row is None:
        row = ChatSession(id=sid, user_agent=user_agent)
        db.add(row)
        db.commit()
        db.refresh(row)
        return sid
    if user_agent and row.user_agent != user_agent:
        row.user_agent = user_agent
        db.commit()
    return sid


def _merge_session_prefill(
    db: Session,
    sid: str,
    name: str | None,
    phone: str | None,
) -> None:
    if name is None and phone is None:
        return
    row = db.get(ChatSession, sid)
    if row is None:
        return
    meta: dict = {}
    if row.metadata_json:
        try:
            meta = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            meta = {}
    changed = False
    if name is not None and str(name).strip():
        meta["prefill_display_name"] = str(name).strip()[:200]
        changed = True
    if phone is not None and str(phone).strip():
        pn = normalize_phone_for_storage(str(phone).strip())
        if pn:
            meta["prefill_phone"] = pn
            changed = True
    if changed:
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
        db.commit()


def _prefill_system_note(db: Session, sid: str) -> str:
    row = db.get(ChatSession, sid)
    if not row or not row.metadata_json:
        return ""
    try:
        meta = json.loads(row.metadata_json)
    except json.JSONDecodeError:
        return ""
    name = meta.get("prefill_display_name")
    phone = meta.get("prefill_phone")
    if not name and not phone:
        return ""
    parts: list[str] = []
    if name:
        parts.append(f"как обращаться — {name}")
    if phone:
        parts.append(f"телефон — {phone_for_display(phone)}")
    return (
        "\n\n[Данные из формы виджета] Клиент указал: "
        + "; ".join(parts)
        + ". При вызове submit_lead подставь эти значения в display_name и phone, "
        "если в тексте переписки клиент не указал явно другие. Номер в инструмент можно передать как у клиента — "
        "сервер нормализует цифры. Не переспрашивай имя и телефон без необходимости; "
        "уточни тему/тренинг, удобное время связи и явное согласие на передачу контакта специалисту."
    )


def _session_has_lead(db: Session, session_id: str) -> bool:
    cnt = db.scalar(select(func.count()).select_from(Lead).where(Lead.session_id == session_id))
    return bool(cnt and cnt > 0)


_LEAD_ALREADY_SENT_NOTE = (
    "\n\n[Контекст сессии] Заявка с контактами уже была передана специалисту ранее в этом диалоге "
    "(данные есть в истории). Не запрашивай заново имя, телефон и удобное время звонка, "
    "если они уже указаны в переписке — отвечай на новые вопросы по сути. "
    "Кратко можно напомнить, что менеджер свяжется по уже оставленным контактам. "
    "Если клиент сам хочет изменить номер или время — прими правки; при необходимости можно отправить "
    "уточняющую заявку через инструмент submit_lead."
)


def _history_openai_messages(db: Session, session_id: str) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.id.asc())
        .limit(settings.chat_history_limit)
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in rows]


def _append_assistant_for_tools(msg) -> dict:
    payload: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in msg.tool_calls
        ]
    return payload


def run_turn(
    db: Session,
    *,
    session_id: str | None,
    user_text: str,
    user_agent: str | None,
    prefill_display_name: str | None = None,
    prefill_phone: str | None = None,
) -> tuple[str, str, bool]:
    """
    Сохраняет сообщение пользователя, вызывает LLM с возможными tool_calls submit_lead,
    сохраняет ответ ассистента. Возвращает (reply_text, session_id, session_has_lead).
    """
    if not settings.openai_api_key.strip():
        raise RuntimeError("OPENAI_API_KEY не задан")

    sid = _ensure_session(db, session_id, user_agent)
    _merge_session_prefill(db, sid, prefill_display_name, prefill_phone)
    system_full = build_system_instructions(_load_prompt_system_text(), load_knowledge_bundle())
    system_full += _prefill_system_note(db, sid)
    if _session_has_lead(db, sid):
        system_full += _LEAD_ALREADY_SENT_NOTE

    um = ChatMessage(session_id=sid, role="user", content=user_text)
    db.add(um)
    db.commit()

    messages: list[dict] = [{"role": "system", "content": system_full}]
    messages.extend(_history_openai_messages(db, sid))

    tools = [SUBMIT_LEAD_TOOL]
    max_rounds = 6
    final_text = ""

    for _ in range(max_rounds):
        completion = chat_completion(messages, tools=tools)
        msg = completion.choices[0].message

        if msg.tool_calls:
            messages.append(_append_assistant_for_tools(msg))
            for tc in msg.tool_calls:
                if tc.function.name != "submit_lead":
                    tool_body = json.dumps({"ok": False, "error": f"unknown tool {tc.function.name}"})
                else:
                    args = parse_tool_arguments(tc.function.arguments or "{}")
                    tool_body_dict = submit_lead_from_tool(db, session_id=sid, args=args)
                    tool_body = json.dumps(tool_body_dict, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_body,
                    }
                )
            continue

        final_text = (msg.content or "").strip()
        break

    if not final_text:
        final_text = "Извините, не удалось сформулировать ответ. Попробуйте переформулировать вопрос."

    final_text = _strip_markdown_for_chat(final_text)

    am = ChatMessage(session_id=sid, role="assistant", content=final_text)
    db.add(am)
    db.commit()
    has_lead = _session_has_lead(db, sid)
    return final_text, sid, has_lead

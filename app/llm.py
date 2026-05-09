"""Клиент OpenAI-совместимого API (ProxyAPI)."""

import logging
from functools import lru_cache

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


SUBMIT_LEAD_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_lead",
        "description": (
            "Зафиксировать заявку пользователя на звонок специалиста. "
            "Вызывай только когда есть явное согласие передать контакт и собраны обязательные поля."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": "Имя или как обращаться",
                },
                "phone": {
                    "type": "string",
                    "description": "Телефон в любом удобном формате",
                },
                "preferred_contact_at": {
                    "type": "string",
                    "description": "Когда удобно связаться (день, время, диапазон)",
                },
                "topic": {
                    "type": "string",
                    "description": "Интересующий тренинг или тема",
                },
                "notes": {
                    "type": "string",
                    "description": "Дополнительные пожелания",
                },
            },
            "required": ["display_name", "phone", "preferred_contact_at"],
        },
    },
}


@lru_cache
def get_openai_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key or "missing",
        base_url=settings.openai_base_url.rstrip("/"),
    )


def chat_completion(messages: list[dict], *, tools: list[dict] | None = None):
    client = get_openai_client()
    kwargs = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.5,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)

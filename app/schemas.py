"""Pydantic-схемы API."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, description="UUID сессии; если пусто — создаётся новая")
    message: str = Field(..., min_length=1, max_length=12000)
    prefill_display_name: str | None = Field(default=None, max_length=200)
    prefill_phone: str | None = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    session_has_lead: bool = Field(
        default=False,
        description="True, если в этой сессии уже сохранена заявка (лид); клиент может показать баннер «специалисту передано».",
    )

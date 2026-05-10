"""Точка входа FastAPI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from load_env import load_env

load_env()

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.chat import run_turn
from app.config import settings
from app.database import get_db, init_db
from app.logging_setup import configure_logging
from app.schemas import ChatRequest, ChatResponse

configure_logging(_ROOT)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("БД инициализирована")
    yield


app = FastAPI(title="Assistant DM API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
):
    chat_logger = logging.getLogger("assistant.chat")
    preview = settings.chat_log_preview_chars
    user_preview = body.message.strip().replace("\r", " ").replace("\n", " ")
    if len(user_preview) > preview:
        user_preview = user_preview[:preview] + "…"
    try:
        reply, sid, session_has_lead = run_turn(
            db,
            session_id=body.session_id,
            user_text=body.message.strip(),
            user_agent=user_agent,
            prefill_display_name=body.prefill_display_name,
            prefill_phone=body.prefill_phone,
        )
        reply_preview = reply.replace("\r", " ").replace("\n", " ")
        if len(reply_preview) > preview:
            reply_preview = reply_preview[:preview] + "…"
        chat_logger.info(
            "session=%s | user (%d chars): %s | assistant (%d chars): %s",
            sid,
            len(body.message),
            user_preview,
            len(reply),
            reply_preview,
        )
    except RuntimeError as e:
        chat_logger.warning("session=%s | error: %s | user: %s", body.session_id, e, user_preview)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("chat failed")
        chat_logger.warning("session=%s | exception | user: %s", body.session_id, user_preview)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from e
    return ChatResponse(session_id=sid, reply=reply, session_has_lead=session_has_lead)


_static_dir = _ROOT / "static"
_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

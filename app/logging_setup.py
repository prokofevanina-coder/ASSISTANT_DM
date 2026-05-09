"""Файловые логи + консоль."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


def configure_logging(project_root: Path) -> None:
    """Два файла: app.log (всё приложение), chat.log (диалоги для отладки)."""
    log_dir = (project_root / settings.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    max_bytes = max(1, settings.log_file_max_mb) * 1024 * 1024

    app_file = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    app_file.setLevel(level)
    app_file.setFormatter(fmt)

    chat_file = RotatingFileHandler(
        log_dir / "chat.log",
        maxBytes=max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    chat_file.setLevel(level)
    chat_file.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)

    root.addHandler(app_file)
    root.addHandler(console)

    chat_logger = logging.getLogger("assistant.chat")
    chat_logger.handlers.clear()
    chat_logger.setLevel(level)
    chat_logger.propagate = False
    chat_logger.addHandler(chat_file)
    chat_logger.addHandler(console)

    logging.getLogger(__name__).info(
        "Log files: %s/app.log (app), %s/chat.log (chat)",
        log_dir,
        log_dir,
    )

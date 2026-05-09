"""Загрузка переменных окружения из .env в корне проекта."""

from pathlib import Path


def load_env(env_filename: str = ".env") -> None:
    """
    Подключает python-dotenv, если установлен; ищет .env рядом с этим файлом
    (корень проекта ASSISTANT_DM).
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent
    load_dotenv(root / env_filename)

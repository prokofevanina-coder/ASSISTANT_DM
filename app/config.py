"""Настройки из переменных окружения (.env в корне проекта)."""

from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openai_base_url: str = "https://openai.api.proxyapi.ru/v1"
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "PROXY_API_KEY"),
    )
    openai_model: str = "openai/gpt-4o-mini"

    app_env: str = "development"
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file_max_mb: int = 5
    log_backup_count: int = 5
    chat_log_preview_chars: int = 400

    database_url: str = "sqlite:///./assistant_dm.db"

    telegram_bot_token: str = ""
    telegram_lead_chat_id: str = ""

    email_leads_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    email_to: str = ""

    chat_history_limit: int = 40


settings = Settings()

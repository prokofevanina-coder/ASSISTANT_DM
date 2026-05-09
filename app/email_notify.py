"""Опциональная отправка копии лида на email (SMTP)."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)


def send_lead_email(subject: str, body: str) -> tuple[bool, str | None]:
    """Возвращает (успех, текст ошибки или None)."""
    if not settings.email_leads_enabled:
        return True, None
    if not settings.smtp_host or not settings.email_from or not settings.email_to:
        return False, "SMTP: не заданы SMTP_HOST, EMAIL_FROM или EMAIL_TO"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = settings.email_to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.email_from, [settings.email_to], msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        logger.exception("SMTP send failed")
        return False, str(e)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

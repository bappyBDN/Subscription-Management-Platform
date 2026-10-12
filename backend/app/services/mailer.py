"""Email sender. With no SMTP_HOST configured, emails are logged (and kept in OUTBOX for tests)."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("smp.mail")
OUTBOX: list[dict] = []


def send_email(to: str | None, subject: str, body: str) -> None:
    if not to:
        return
    settings = get_settings()
    OUTBOX.append({"to": to, "subject": subject, "body": body})
    del OUTBOX[:-200]
    if not settings.smtp_host:
        logger.info("EMAIL to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception:  # noqa: BLE001 — never fail a business action because mail is down
        logger.exception("Failed to send email to %s", to)

"""Email sender. With no mail server configured (or MAIL_ENABLED=false), emails are logged (and kept in OUTBOX
for tests)."""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.core.config import get_settings

logger = logging.getLogger("smp.mail")
OUTBOX: list[dict] = []


class MailError(Exception):
    pass


def _deliver(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    name, addr = parseaddr(settings.smtp_from)
    msg["From"] = formataddr((name or "SMP", addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if settings.smtp_port == 465:
        smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with smtp:
        if settings.smtp_port != 465 and settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def explain(exc: Exception) -> str:
    """A message an admin can act on."""
    settings = get_settings()
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        hint = (" For Gmail use a 16-letter app password (myaccount.google.com/apppasswords), not the normal"
                " password." if "gmail" in settings.smtp_host else "")
        return f"The mail server rejected the user name or password.{hint}"
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)) and not isinstance(exc, smtplib.SMTPException):
        return (f"Could not reach {settings.smtp_host}:{settings.smtp_port} ({exc}). The server's hosting provider"
                " may block outgoing mail ports (e.g. DigitalOcean blocks 25, 465 and 587 until asked).")
    return f"{type(exc).__name__}: {exc}"


def send_email(to: str | None, subject: str, body: str, raise_errors: bool = False) -> None:
    if not to:
        return
    settings = get_settings()
    OUTBOX.append({"to": to, "subject": subject, "body": body})
    del OUTBOX[:-200]
    if not settings.mail_on:
        logger.info("EMAIL to=%s subject=%s\n%s", to, subject, body)
        return
    try:
        _deliver(to, subject, body)
        logger.info("EMAIL sent to=%s subject=%s", to, subject)
    except Exception as exc:  # noqa: BLE001 — never fail a business action because mail is down
        logger.error("Failed to send email to %s: %s", to, explain(exc))
        if raise_errors:
            raise MailError(explain(exc)) from exc

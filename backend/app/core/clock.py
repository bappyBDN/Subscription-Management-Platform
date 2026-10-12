"""Time helpers. Timestamps are stored as naive UTC; business dates use the app timezone."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def to_naive_utc(value: datetime) -> datetime:
    """Accept an aware datetime (any zone) or a naive one meant as app-local time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(get_settings().app_timezone))
    return value.astimezone(timezone.utc).replace(tzinfo=None)

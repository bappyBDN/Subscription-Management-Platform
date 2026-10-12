from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User

# Never written to the audit log
_SECRET_FIELDS = {"password", "password_hash", "secret", "secret_ciphertext", "secret_nonce", "code", "code_hash"}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if k not in _SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return None
    return value


def snapshot(obj: Any, fields: list[str]) -> dict:
    return _clean({f: getattr(obj, f, None) for f in fields})


def log(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before_json=_clean(before) if before else None,
            after_json=_clean(after) if after else None,
            ip=ip,
        )
    )

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.text_rules import contains_card_number  # noqa: F401  (re-export)

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(subject: str | int, secret: str, minutes: int, kind: str = "access", extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "kind": kind, "iat": now, "exp": now + timedelta(minutes=minutes)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str, kind: str = "access") -> dict:
    """Raise jwt.PyJWTError when the token is invalid, expired or of the wrong kind."""
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    if payload.get("kind") != kind:
        raise jwt.InvalidTokenError("wrong token kind")
    return payload


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str, secret: str) -> str:
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def otp_matches(code: str, code_hash: str, secret: str) -> bool:
    return hmac.compare_digest(hash_otp(code, secret), code_hash)

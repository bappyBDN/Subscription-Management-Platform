from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.security import generate_otp, hash_otp, otp_matches
from app.models import OtpCode, User
from app.services.mailer import send_email


class OtpError(Exception):
    pass


def issue(db: Session, user: User, purpose: str, ref_id: int | None = None) -> None:
    settings = get_settings()
    # invalidate earlier unused codes for the same purpose
    for old in db.query(OtpCode).filter_by(user_id=user.id, purpose=purpose, ref_id=ref_id, used_at=None):
        old.used_at = utcnow()
    code = generate_otp()
    db.add(
        OtpCode(
            user_id=user.id,
            purpose=purpose,
            ref_id=ref_id,
            code_hash=hash_otp(code, settings.jwt_secret),
            expires_at=utcnow() + timedelta(minutes=settings.otp_expire_minutes),
        )
    )
    db.flush()
    send_email(
        user.employee.email,
        "Your SMP verification code",
        f"Your verification code is {code}. It expires in {settings.otp_expire_minutes} minutes.",
    )


def verify(db: Session, user: User, purpose: str, code: str, ref_id: int | None = None) -> None:
    settings = get_settings()
    row = (
        db.query(OtpCode)
        .filter_by(user_id=user.id, purpose=purpose, ref_id=ref_id, used_at=None)
        .order_by(OtpCode.id.desc())
        .first()
    )
    if row is None or row.expires_at < utcnow():
        raise OtpError("Code expired or not requested — request a new one")
    if row.attempts >= settings.otp_max_attempts:
        raise OtpError("Too many attempts — request a new code")
    if not otp_matches(code.strip(), row.code_hash, settings.jwt_secret):
        row.attempts += 1
        db.flush()
        raise OtpError("Incorrect code")
    row.used_at = utcnow()
    db.flush()

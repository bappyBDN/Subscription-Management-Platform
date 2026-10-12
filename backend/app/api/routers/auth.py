from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.deps import client_ip, get_current_user, is_manager
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.enums import EmployeeStatus, OtpPurpose
from app.models import Employee, User
from app.schemas.auth import ChangePasswordIn, LoginIn, LoginOut, ManagerBrief, MeOut, VerifyOtpIn
from app.services import audit, otp

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong employee code / email or password")


def _find_user(db: Session, username: str) -> User | None:
    name = username.strip().lower()
    emp = (
        db.query(Employee)
        .filter((func.lower(Employee.emp_code) == name) | (func.lower(Employee.email) == name))
        .first()
    )
    return emp.user if emp else None


def _access_token(db: Session, user: User) -> str:
    settings = get_settings()
    user.last_login_at = utcnow()
    db.commit()
    return create_token(user.id, settings.jwt_secret, settings.jwt_expire_minutes)


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    user = _find_user(db, data.username)
    if user is None or not user.is_active or user.employee.status != EmployeeStatus.ACTIVE:
        raise INVALID
    if user.locked_until and user.locked_until > utcnow():
        raise HTTPException(status.HTTP_423_LOCKED, "Too many failed attempts — try again later")
    if not verify_password(data.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        audit.log(db, user, "auth.failed_login", "user", user.id, ip=client_ip(request))
        db.commit()
        raise INVALID
    user.failed_logins = 0
    user.locked_until = None

    if user.needs_2fa:
        otp.issue(db, user, OtpPurpose.LOGIN)
        db.commit()
        token = create_token(user.id, settings.jwt_secret, settings.otp_token_expire_minutes, kind="otp")
        return LoginOut(otp_required=True, otp_token=token)

    audit.log(db, user, "auth.login", "user", user.id, ip=client_ip(request))
    return LoginOut(access_token=_access_token(db, user))


@router.post("/verify-otp", response_model=LoginOut)
def verify_otp(data: VerifyOtpIn, request: Request, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.otp_token, get_settings().jwt_secret, kind="otp")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login session expired — sign in again") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise INVALID
    try:
        otp.verify(db, user, OtpPurpose.LOGIN, data.code)
    except otp.OtpError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    audit.log(db, user, "auth.login", "user", user.id, ip=client_ip(request))
    return LoginOut(access_token=_access_token(db, user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = user.employee
    return MeOut(
        user_id=user.id,
        employee_id=e.id,
        emp_code=e.emp_code,
        name=e.name,
        designation=e.designation,
        department=e.department,
        team=e.team,
        unit=e.unit,
        email=e.email,
        phone=e.phone,
        roles=user.role_list,
        is_manager=is_manager(db, user),
        can_reveal_vault=user.is_dmd or user.can_reveal_vault,
        manager=ManagerBrief.model_validate(e.manager) if e.manager else None,
        last_login_at=user.last_login_at,
    )


@router.post("/change-password", status_code=204)
def change_password(data: ChangePasswordIn, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    user.password_hash = hash_password(data.new_password)
    audit.log(db, user, "auth.change_password", "user", user.id, ip=client_ip(request))
    db.commit()

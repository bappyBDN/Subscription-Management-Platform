import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.enums import EmployeeStatus
from app.models import Employee, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(creds.credentials, get_settings().jwt_secret, kind="access")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.employee.status != EmployeeStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """DMD Sir or a delegate admin."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def require_dmd(user: User = Depends(get_current_user)) -> User:
    if not user.is_dmd:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only DMD Sir can do this")
    return user


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ---- scoping helpers -------------------------------------------------------

def direct_report_ids(db: Session, user: User) -> list[int]:
    return [eid for (eid,) in db.query(Employee.id).filter(Employee.manager_id == user.employee_id).all()]


def is_manager(db: Session, user: User) -> bool:
    return db.query(Employee.id).filter(Employee.manager_id == user.employee_id).first() is not None


def visible_employee_ids(db: Session, user: User) -> list[int] | None:
    """None = everyone (admin). Otherwise self + direct reports."""
    if user.is_admin:
        return None
    return [user.employee_id, *direct_report_ids(db, user)]


def not_found(what: str = "Not found") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, what)


def forbidden(what: str = "You do not have access to this") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, what)


def bad_request(what: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, what)


def no_null(changes: dict, required: set[str]) -> dict:
    """PATCH bodies may clear optional fields with null, but not required ones."""
    bad = sorted(k for k, v in changes.items() if v is None and k in required)
    if bad:
        raise bad_request(f"These fields cannot be empty: {', '.join(bad)}")
    return changes


def get_or_404(db: Session, model, obj_id: int, what: str = "Not found"):
    obj = db.get(model, obj_id)
    if obj is None:
        raise not_found(what)
    return obj

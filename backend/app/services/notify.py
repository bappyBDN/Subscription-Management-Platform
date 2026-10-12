from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.enums import Role
from app.models import Notification, User
from app.services.mailer import send_email


def notify(
    db: Session,
    users: Iterable[User | None],
    type_: str,
    title: str,
    body: str = "",
    link: str | None = None,
    email: bool = True,
) -> None:
    seen: set[int] = set()
    for user in users:
        if user is None or user.id in seen or not user.is_active:
            continue
        seen.add(user.id)
        db.add(Notification(user_id=user.id, type=type_, title=title, body=body, link=link))
        if email:
            send_email(user.employee.email if user.employee else None, f"[SMP] {title}", body)


def admins(db: Session, include_delegates: bool = True) -> list[User]:
    users = db.query(User).filter(User.is_active.is_(True)).all()
    wanted = (Role.DMD, Role.DELEGATE) if include_delegates else (Role.DMD,)
    return [u for u in users if u.has_role(*wanted)]


def dmd_users(db: Session) -> list[User]:
    return admins(db, include_delegates=False)

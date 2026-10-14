from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.deps import bad_request, get_current_user, get_or_404, not_found, require_admin
from app.db.session import get_db
from app.models import AuditLog, Notification, User
from app.services import mailer

router = APIRouter(tags=["system"])


@router.get("/mail/status")
def mail_status(user: User = Depends(require_admin)):
    """How email is set up (no secrets)."""
    s = get_settings()
    return {"enabled": s.mail_on, "host": s.smtp_host or None, "port": s.smtp_port, "user": s.smtp_user or None,
            "sender": s.smtp_from, "password_set": bool(s.smtp_password),
            "password_length": len(s.smtp_password)}


@router.post("/mail/test")
def mail_test(user: User = Depends(require_admin)):
    """Send a test email to the signed-in admin and report the real error if it fails."""
    to = user.employee.email
    if not to:
        raise bad_request("Your employee record has no email address")
    if not get_settings().mail_on:
        raise bad_request("Email is off: set SMTP_HOST (or GMAIL_USER + GMAIL_APP_PASSWORD) and restart the backend")
    try:
        mailer.send_email(to, "SMP test email", "Email from SMP works.", raise_errors=True)
    except mailer.MailError as exc:
        raise bad_request(f"Sending to {to} failed: {exc}") from None
    return {"sent_to": to}


@router.get("/notifications")
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    unread = q.filter(Notification.read_at.is_(None)).count()
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    items = q.order_by(Notification.id.desc()).limit(limit).all()
    return {
        "unread": unread,
        "items": [{"id": n.id, "type": n.type, "title": n.title, "body": n.body, "link": n.link,
                   "read_at": n.read_at, "created_at": n.created_at} for n in items],
    }


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = get_or_404(db, Notification, notification_id, "Notification not found")
    if n.user_id != user.id:
        raise not_found("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).update(
        {Notification.read_at: utcnow()})
    db.commit()


@router.get("/audit-logs")
def audit_logs(user_id: int | None = None, action: str | None = None, entity: str | None = None,
               entity_id: int | None = None, from_: date | None = Query(None, alias="from"),
               to: date | None = None, limit: int = Query(200, ge=1, le=1000),
               user: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    if entity:
        q = q.filter(AuditLog.entity == entity)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if from_:
        q = q.filter(AuditLog.created_at >= from_)
    if to:
        q = q.filter(AuditLog.created_at < to + timedelta(days=1))
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"id": r.id, "user_id": r.user_id, "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
             "before": r.before_json, "after": r.after_json, "ip": r.ip, "created_at": r.created_at} for r in rows]

"""Unit and department budgets: month-to-date spend vs monthly budget, alerts at 80% / 100%."""

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import to_naive_utc, today
from app.models import CardCharge, Department, Notification, OrgUnit, User
from app.services.notify import admins, notify


def paid_month_to_date(db: Session, unit_id: int | None = None, department_id: int | None = None) -> Decimal:
    q = db.query(func.coalesce(func.sum(CardCharge.amount_bdt), 0)).filter(
        CardCharge.charge_date >= today().replace(day=1), CardCharge.is_expected.is_(False))
    if unit_id is not None:
        q = q.filter(CardCharge.unit_id == unit_id)
    if department_id is not None:
        q = q.filter(CardCharge.department_id == department_id)
    return Decimal(q.scalar() or 0)


def _already_sent(db: Session, type_: str, link: str) -> bool:
    # created_at is stored in UTC; the month starts at local (Asia/Dhaka) midnight
    start = to_naive_utc(datetime.combine(today().replace(day=1), time.min))
    return db.query(Notification.id).filter(Notification.type == type_, Notification.link == link,
                                            Notification.created_at >= start).first() is not None


def _alert(db: Session, name: str, spent: Decimal, budget: Decimal, link: str, head_id: int | None) -> None:
    if not budget or budget <= 0:
        return
    pct = spent / budget * 100
    level = "budget.over" if pct >= 100 else "budget.warning" if pct >= 80 else None
    if level is None or _already_sent(db, level, link):
        return
    recipients = admins(db)
    if head_id:
        head = db.query(User).filter(User.employee_id == head_id).first()
        recipients.append(head)
    word = "exceeded" if level == "budget.over" else "at"
    notify(db, recipients, level, f"{name} subscription budget {word} {pct:.0f}% this month",
           f"Paid this month: BDT {spent:,.2f} of BDT {budget:,.2f}.", link)


def check_owner_budgets(db: Session, unit_id: int | None, department_id: int | None) -> None:
    """Called after a charge is recorded: alert once per month per threshold."""
    if unit_id:
        unit = db.get(OrgUnit, unit_id)
        if unit:
            _alert(db, unit.code, paid_month_to_date(db, unit_id=unit.id), Decimal(unit.monthly_budget_bdt or 0),
                   f"/costs/units/{unit.id}", unit.head_employee_id)
    if department_id:
        dept = db.get(Department, department_id)
        if dept:
            _alert(db, dept.label, paid_month_to_date(db, department_id=dept.id),
                   Decimal(dept.monthly_budget_bdt or 0), f"/costs/departments/{dept.id}", dept.head_employee_id)

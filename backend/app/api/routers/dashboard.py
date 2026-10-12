from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.deps import direct_report_ids, forbidden, get_current_user, require_admin
from app.db.session import get_db
from app.enums import AssignmentStatus, RequestStatus, SubscriptionStatus
from app.models import Employee, Subscription, SubscriptionRequest, User
from app.services import cost
from app.services.costs_db import Context

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
View = Literal["accrued", "paid"]
Currency = Literal["BDT", "USD"]


def _convert(ctx: Context, data, currency: str):
    """Convert every Decimal amount in a nested structure from BDT to USD when asked."""
    if currency == "BDT":
        return data
    if isinstance(data, dict):
        return {k: (_convert(ctx, v, currency) if k not in ("budget_used_pct",) else v) for k, v in data.items()}
    if isinstance(data, list):
        return [_convert(ctx, v, currency) for v in data]
    if isinstance(data, Decimal):
        return ctx.to_usd(data)
    return data


@router.get("/summary")
def summary(view: View = "accrued", currency: Currency = "BDT", user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    ctx = Context(db, user)
    day = today()
    data = ctx.summary(day, view)
    data["currency"] = currency

    if ctx.is_admin:
        subs = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE).all()
        pending_q = db.query(SubscriptionRequest).filter(
            SubscriptionRequest.status.in_([RequestStatus.PENDING_DMD, RequestStatus.ON_HOLD, RequestStatus.PENDING_MANAGER])
        )
        renewals = [s for s in subs if s.next_renewal_date and day <= s.next_renewal_date <= day + timedelta(days=7)]
        handovers = db.query(SubscriptionRequest).filter(
            SubscriptionRequest.status.in_([RequestStatus.APPROVED, RequestStatus.HANDOVER_PENDING])).count()
        data["counts"] = {
            "active_subscriptions": len(subs),
            "seats_total": sum(s.seats_total for s in subs),
            "seats_used": sum(s.seats_used for s in subs),
            "revoke_pending": sum(1 for s in subs for a in s.assignments if a.status == AssignmentStatus.REVOKE_PENDING),
            "pending_approvals": pending_q.count(),
            "oldest_pending_days": max(((day - r.status_changed_at.date()).days for r in pending_q.all()), default=0),
            "renewals_7_days": len(renewals),
            "renewals_7_days_amount": sum((Decimal(s.cost_per_cycle) for s in renewals), Decimal("0")),
            "pending_handovers": handovers,
        }
    else:
        reports = direct_report_ids(db, user)
        data["counts"] = {
            "team_size": len(reports),
            "pending_my_approval": db.query(SubscriptionRequest).filter(
                SubscriptionRequest.employee_id.in_(reports or [-1]),
                SubscriptionRequest.status == RequestStatus.PENDING_MANAGER).count(),
            "my_open_requests": db.query(SubscriptionRequest).filter(
                SubscriptionRequest.employee_id == user.employee_id,
                SubscriptionRequest.status.in_([RequestStatus.PENDING_MANAGER, RequestStatus.PENDING_DMD,
                                                RequestStatus.ON_HOLD, RequestStatus.INFO_NEEDED,
                                                RequestStatus.APPROVED, RequestStatus.HANDOVER_PENDING])).count(),
        }
    out = _convert(ctx, {k: v for k, v in data.items() if k != "counts"}, currency)
    out["counts"] = data["counts"]
    return out


@router.get("/series")
def series(days: int = Query(30, ge=1, le=366), view: View = "accrued", currency: Currency = "BDT",
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = Context(db, user)
    end = today()
    return _convert(ctx, ctx.daily_series(end - timedelta(days=days - 1), end, view), currency)


@router.get("/monthly")
def monthly(months: int = Query(12, ge=1, le=36), view: View = "accrued", currency: Currency = "BDT",
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = Context(db, user)
    return _convert(ctx, ctx.monthly_series(today(), months, view), currency)


def _range(period: str) -> tuple[date, date]:
    end = today()
    if period == "month":
        return end.replace(day=1), end
    if period == "year":
        return date(end.year, 1, 1), end
    return end - timedelta(days=29), end  # last 30 days


@router.get("/by-tool")
def by_tool(period: Literal["30d", "month", "year"] = "month", view: View = "accrued", currency: Currency = "BDT",
            user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Context(db, user)
    start, end = _range(period)
    return _convert(ctx, ctx.grouped("tool", start, end, view), currency)


@router.get("/by-department")
def by_department(period: Literal["30d", "month", "year"] = "month", group: Literal["department", "unit"] = "department",
                  view: View = "accrued", currency: Currency = "BDT",
                  user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Context(db, user)
    start, end = _range(period)
    return _convert(ctx, ctx.grouped(group, start, end, view), currency)


@router.get("/top-employees")
def top_employees(period: Literal["30d", "month", "year"] = "month", limit: int = Query(10, ge=1, le=100),
                  currency: Currency = "BDT", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = Context(db, user)
    if not ctx.is_admin and not direct_report_ids(db, user):
        raise forbidden()
    start, end = _range(period)
    shares = cost.per_employee(ctx.subs, start, end, ctx.fx)
    rows = []
    for emp_id, amount in shares.items():
        if emp_id is None or (ctx.ids is not None and emp_id not in ctx.ids):
            continue
        emp = db.get(Employee, emp_id)
        rows.append({"employee_id": emp_id, "name": emp.name, "emp_code": emp.emp_code,
                     "department": emp.department, "amount": amount})
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return _convert(ctx, rows[:limit], currency)


@router.get("/renewals")
def renewals(days: int = Query(30, ge=1, le=366), user: User = Depends(require_admin), db: Session = Depends(get_db)):
    day = today()
    subs = (
        db.query(Subscription)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.next_renewal_date.is_not(None),
                Subscription.next_renewal_date <= day + timedelta(days=days))
        .order_by(Subscription.next_renewal_date)
        .all()
    )
    return [
        {
            "subscription_id": s.id,
            "vendor_name": s.vendor.name,
            "plan_name": s.plan_name,
            "next_renewal_date": s.next_renewal_date,
            "overdue": s.next_renewal_date < day,
            "amount": s.cost_per_cycle,
            "currency": s.currency,
            "holders": [a.employee.name for a in s.assignments if a.status != AssignmentStatus.REVOKED],
        }
        for s in subs
    ]

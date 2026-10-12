"""Reports, as JSON or Excel (format=xlsx)."""

import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.deps import bad_request, direct_report_ids, forbidden, get_current_user
from app.db.session import get_db
from app.enums import AssignmentStatus
from app.models import Assignment, CardCharge, Employee, Handover, OrgUnit, Subscription, SubscriptionRequest, User
from app.services import cost
from app.services.costs_db import Context, org_maps

router = APIRouter(prefix="/reports", tags=["reports"])

ReportType = Literal["register", "cost-summary", "cost-by-tool", "cost-by-unit", "cost-by-department",
                     "cost-by-employee", "requests", "credential-holders", "renewals"]
ADMIN_ONLY = {"register", "cost-by-tool", "cost-by-unit", "cost-by-department", "credential-holders", "renewals"}


def _months(start: date, end: date):
    cur = start.replace(day=1)
    while cur <= end:
        nxt = cost.add_months(cur, 1)
        yield cur, min(nxt - timedelta(days=1), end), max(cur, start)
        cur = nxt


def _paid_by(db: Session, column, start: date, end: date) -> dict:
    rows = (db.query(column, func.coalesce(func.sum(CardCharge.amount_bdt), 0))
            .filter(CardCharge.charge_date >= start, CardCharge.charge_date <= end, CardCharge.is_expected.is_(False))
            .group_by(column).all())
    return {k: Decimal(v) for k, v in rows}


def build(db: Session, user: User, kind: str, start: date, end: date) -> list[dict]:
    ctx = Context(db, user)
    if kind == "register":
        return [
            {"id": s.id, "tool": s.vendor.name, "plan": s.plan_name, "type": s.type, "seats_used": s.seats_used,
             "seats_total": s.seats_total, "cost_per_cycle": s.cost_per_cycle, "currency": s.currency,
             "billing_cycle": s.billing_cycle, "start_date": s.start_date, "next_renewal_date": s.next_renewal_date,
             "card": f"•••• {s.card.last4}" if s.card else "", "owner": s.owner_label, "unit": s.unit_code, "department": s.department_name or "",
             "status": s.status,
             "holders": ", ".join(a.employee.name for a in s.assignments if a.status != AssignmentStatus.REVOKED)}
            for s in db.query(Subscription).order_by(Subscription.id).all()
        ]
    if kind == "cost-summary":
        rows = []
        for m_start, m_end, from_day in _months(start, end):
            accrued = ctx.total("accrued", from_day, m_end).amount
            paid = ctx.total("paid", from_day, m_end).amount if ctx.is_admin else None
            rows.append({"month": m_start.strftime("%Y-%m"), "accrued_bdt": cost.q(accrued),
                         "accrued_usd": ctx.to_usd(accrued),
                         "paid_bdt": cost.q(paid) if paid is not None else None})
        return rows
    if kind == "cost-by-tool":
        return ctx.grouped("tool", start, end, "accrued")
    if kind in ("cost-by-unit", "cost-by-department"):
        emp_dept, dept_unit = org_maps(db)
        alloc = cost.allocate(ctx.subs, start, end, ctx.fx, emp_dept, dept_unit)
        paid_unit = _paid_by(db, CardCharge.unit_id, start, end)
        rows = []
        for unit in db.query(OrgUnit).order_by(OrgUnit.code).all():
            a = alloc.get(unit.id, cost.Allocation())
            if kind == "cost-by-unit":
                rows.append({"unit": unit.code, "name": unit.name, "accrued_bdt": cost.q(a.total),
                             "accrued_usd": ctx.to_usd(a.total), "paid_bdt": cost.q(paid_unit.get(unit.id, Decimal("0"))),
                             "shared_pool_bdt": cost.q(a.pool),
                             "monthly_budget_bdt": cost.q(Decimal(unit.monthly_budget_bdt or 0))})
                continue
            paid_dept = _paid_by(db, CardCharge.department_id, start, end)
            for dept in unit.departments:
                rows.append({"unit": unit.code, "department": dept.name, "cost_center": dept.cost_center or "",
                             "direct_bdt": cost.q(a.direct.get(dept.id, Decimal("0"))),
                             "allocated_bdt": cost.q(a.allocated.get(dept.id, Decimal("0"))),
                             "total_bdt": cost.q(a.department_total(dept.id)),
                             "paid_bdt": cost.q(paid_dept.get(dept.id, Decimal("0"))),
                             "monthly_budget_bdt": cost.q(Decimal(dept.monthly_budget_bdt or 0))})
            rows.append({"unit": unit.code, "department": "Shared pool (empty seats)", "cost_center": "",
                         "direct_bdt": Decimal("0.00"), "allocated_bdt": Decimal("0.00"), "total_bdt": cost.q(a.pool),
                         "paid_bdt": Decimal("0.00"), "monthly_budget_bdt": Decimal("0.00")})
        return rows
    if kind == "cost-by-employee":
        shares = cost.per_employee(ctx.subs, start, end, ctx.fx)
        rows = []
        for emp_id, amount in shares.items():
            if ctx.ids is not None and emp_id not in ctx.ids:
                continue
            emp = db.get(Employee, emp_id) if emp_id else None
            rows.append({"emp_code": emp.emp_code if emp else "", "name": emp.name if emp else "Unassigned seats",
                         "unit": emp.unit_code if emp else "", "department": (emp.department_name or "") if emp else "",
                         "team": emp.team if emp else "",
                         "amount_bdt": amount})
        return sorted(rows, key=lambda r: r["amount_bdt"], reverse=True)
    if kind == "requests":
        q = db.query(SubscriptionRequest).filter(SubscriptionRequest.submitted_at >= start,
                                                 SubscriptionRequest.submitted_at < end + timedelta(days=1))
        if ctx.ids is not None:
            q = q.filter(SubscriptionRequest.employee_id.in_(ctx.ids))
        rows = []
        for r in q.order_by(SubscriptionRequest.id).all():
            decided = next((a.created_at for a in reversed(r.approvals) if a.step == "dmd"), None)
            rows.append({"req_no": r.req_no, "employee": r.snapshot.get("name"), "emp_code": r.snapshot.get("emp_code"),
                         "team": r.snapshot.get("team"), "tool": r.tool_name, "plan": r.plan_name, "type": r.type,
                         "status": r.status, "est_monthly_bdt": r.est_cost_bdt, "submitted_at": r.submitted_at,
                         "dmd_decided_at": decided,
                         "turnaround_days": (decided - r.submitted_at).days if decided else None})
        return rows
    if kind == "credential-holders":
        rows = []
        q = db.query(Assignment).filter(Assignment.status != AssignmentStatus.REVOKED).order_by(Assignment.subscription_id)
        for a in q.all():
            h = db.query(Handover).filter(Handover.request_id == a.request_id).first() if a.request_id else None
            rows.append({"tool": a.subscription.vendor.name, "plan": a.subscription.plan_name,
                         "account_email": a.subscription.account_email, "employee": a.employee.name,
                         "emp_code": a.employee.emp_code, "since": a.start_date, "until": a.end_date,
                         "status": a.status, "delivered_by": h.method if h else "manual"})
        return rows
    if kind == "renewals":
        subs = (db.query(Subscription).filter(Subscription.next_renewal_date.is_not(None),
                                              Subscription.next_renewal_date >= start,
                                              Subscription.next_renewal_date <= end)
                .order_by(Subscription.next_renewal_date).all())
        return [{"date": s.next_renewal_date, "tool": s.vendor.name, "plan": s.plan_name,
                 "amount": s.cost_per_cycle, "currency": s.currency, "card": s.card.last4 if s.card else ""}
                for s in subs]
    raise bad_request("Unknown report")


def to_xlsx(rows: list[dict], title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    if rows:
        headers = list(rows[0].keys())
        ws.append([h.replace("_", " ").title() for h in headers])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in (row.get(h) for h in headers)])
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 50)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/{kind}")
def report(kind: ReportType, from_: date | None = Query(None, alias="from"), to: date | None = None,
           format: Literal["json", "xlsx"] = "json", user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    if not user.is_admin:
        if kind in ADMIN_ONLY or not direct_report_ids(db, user):
            raise forbidden("This report is for DMD Sir, delegates and managers (team only)")
    end = to or today()
    start = from_ or end.replace(day=1)
    if start > end:
        raise bad_request("'from' must be before 'to'")
    if (end - start).days > 731:
        raise bad_request("Choose a range of two years or less")
    rows = build(db, user, kind, start, end)
    if format == "xlsx":
        filename = f"smp-{kind}-{start}-{end}.xlsx"
        return StreamingResponse(
            io.BytesIO(to_xlsx(rows, kind)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return {"report": kind, "from": start, "to": end, "rows": rows}

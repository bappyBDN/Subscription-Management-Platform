"""v2 cost & payment tracking by unit and department.

Accrued cost comes from the allocation engine (department direct + share of unit-wide seats + shared pool).
Paid figures come from card charges, using the owner snapshot stored on each charge.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.deps import bad_request, forbidden, get_current_user, get_or_404
from app.db.session import get_db
from app.enums import AssignmentStatus, SubscriptionStatus
from app.models import CardCharge, Department, Employee, OrgUnit, Subscription, User
from app.services import cost, settings_store
from app.services.costs_db import load_subinfos, org_maps
from app.services.org import cost_scope

router = APIRouter(prefix="/costs", tags=["costs"])


class CostData:
    """Everything one cost request needs, loaded once."""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.settings = settings_store.get_all(db)
        self.fx = settings_store.fx_rates(self.settings)
        self.subs = load_subinfos(db)
        self.emp_dept, self.dept_unit = org_maps(db)
        self.unit_scope, self.dept_scope = cost_scope(db, user)
        self.is_admin = self.unit_scope is None

    # ---- access
    def can_see_unit(self, unit_id: int) -> bool:
        return self.is_admin or unit_id in self.unit_scope

    def can_see_department(self, dept_id: int) -> bool:
        return self.is_admin or dept_id in self.dept_scope

    # ---- maths
    def allocate(self, start: date, end: date) -> dict[int, cost.Allocation]:
        return cost.allocate(self.subs, start, end, self.fx, self.emp_dept, self.dept_unit)

    def usd(self, amount: Decimal) -> Decimal:
        return cost.q(Decimal(amount) / (self.fx.get("USD") or Decimal("1")))

    def paid(self, start: date, end: date, column) -> dict[int | None, Decimal]:
        rows = (
            self.db.query(column, func.coalesce(func.sum(CardCharge.amount_bdt), 0))
            .filter(CardCharge.charge_date >= start, CardCharge.charge_date <= end, CardCharge.is_expected.is_(False))
            .group_by(column)
            .all()
        )
        return {key: Decimal(total) for key, total in rows}


def _range(from_: date | None, to: date | None) -> tuple[date, date]:
    end = to or today()
    start = from_ or end.replace(day=1)
    if start > end:
        raise bad_request("'from' must be before 'to'")
    if (end - start).days > 731:
        raise bad_request("Choose a range of two years or less")
    return start, end


def _empty() -> cost.Allocation:
    return cost.Allocation()


@router.get("/units")
def unit_costs(from_: date | None = Query(None, alias="from"), to: date | None = None,
               view: Literal["accrued", "paid"] = "accrued",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Total cost per unit + seats + budget status (current month)."""
    data = CostData(db, user)
    if not data.is_admin and not data.unit_scope:
        raise forbidden("Unit cost is for DMD Sir, delegates and unit heads — department heads use /costs/departments")
    start, end = _range(from_, to)
    alloc = data.allocate(start, end)
    paid = data.paid(start, end, CardCharge.unit_id)
    day = today()
    mtd = data.allocate(day.replace(day=1), day)

    rows = []
    for unit in db.query(OrgUnit).filter(OrgUnit.active.is_(True)).order_by(OrgUnit.code).all():
        if not data.can_see_unit(unit.id):
            continue
        a = alloc.get(unit.id, _empty())
        amount = a.total if view == "accrued" else paid.get(unit.id, Decimal("0"))
        subs = db.query(Subscription).filter(Subscription.unit_id == unit.id,
                                             Subscription.status == SubscriptionStatus.ACTIVE).all()
        rows.append({
            "unit_id": unit.id, "code": unit.code, "name": unit.name,
            "amount_bdt": cost.q(amount), "amount_usd": data.usd(amount), "estimated": a.estimated,
            "accrued_bdt": cost.q(a.total), "paid_bdt": cost.q(paid.get(unit.id, Decimal("0"))),
            "shared_pool_bdt": cost.q(a.pool),
            "subscriptions": len(subs),
            "seats_used": sum(s.seats_used for s in subs), "seats_total": sum(s.seats_total for s in subs),
            "month_to_date_bdt": cost.q(mtd.get(unit.id, _empty()).total),
            **cost.budget_status(mtd.get(unit.id, _empty()).total, day, Decimal(unit.monthly_budget_bdt or 0)),
        })
    return {"from": start, "to": end, "view": view, "rows": rows,
            "total_bdt": cost.q(sum((r["amount_bdt"] for r in rows), Decimal("0")))}


@router.get("/units/{unit_id}/departments")
def department_costs(unit_id: int, from_: date | None = Query(None, alias="from"), to: date | None = None,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Departments of one unit: direct + allocated share of unit-wide seats, plus the unit's shared pool."""
    unit = get_or_404(db, OrgUnit, unit_id, "Unit not found")
    data = CostData(db, user)
    unit_visible = data.can_see_unit(unit.id)
    if not unit_visible and not any(data.dept_unit.get(d) == unit.id for d in (data.dept_scope or ())):
        raise forbidden()
    start, end = _range(from_, to)
    a = data.allocate(start, end).get(unit.id, _empty())
    paid = data.paid(start, end, CardCharge.department_id)
    day = today()
    mtd = data.allocate(day.replace(day=1), day).get(unit.id, _empty())

    rows = []
    for dept in unit.departments:
        if not dept.active or not (unit_visible or data.can_see_department(dept.id)):
            continue
        total = a.department_total(dept.id)
        rows.append({
            "department_id": dept.id, "name": dept.name, "code": dept.code, "cost_center": dept.cost_center,
            "direct_bdt": cost.q(a.direct.get(dept.id, Decimal("0"))),
            "allocated_bdt": cost.q(a.allocated.get(dept.id, Decimal("0"))),
            "total_bdt": cost.q(total), "total_usd": data.usd(total),
            "paid_bdt": cost.q(paid.get(dept.id, Decimal("0"))),
            "month_to_date_bdt": cost.q(mtd.department_total(dept.id)),
            **cost.budget_status(mtd.department_total(dept.id), day, Decimal(dept.monthly_budget_bdt or 0)),
        })
    rows.sort(key=lambda r: r["total_bdt"], reverse=True)
    out = {"unit": {"id": unit.id, "code": unit.code, "name": unit.name}, "from": start, "to": end, "rows": rows}
    if unit_visible:  # pool and unit total only for people who may see the whole unit
        out["shared_pool_bdt"] = cost.q(a.pool)
        out["unit_total_bdt"] = cost.q(a.total)
    return out


@router.get("/departments/{department_id}")
def department_detail(department_id: int, from_: date | None = Query(None, alias="from"), to: date | None = None,
                      months: int = Query(12, ge=1, le=36),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dept = get_or_404(db, Department, department_id, "Department not found")
    data = CostData(db, user)
    if not data.can_see_department(dept.id):
        raise forbidden()
    start, end = _range(from_, to)
    a = data.allocate(start, end).get(dept.unit_id, _empty())
    paid = data.paid(start, end, CardCharge.department_id).get(dept.id, Decimal("0"))
    day = today()
    mtd = data.allocate(day.replace(day=1), day).get(dept.unit_id, _empty()).department_total(dept.id)

    # subscriptions: owned by the department, or unit-wide ones its people hold seats on
    members = {e for e, d in data.emp_dept.items() if d == dept.id}
    sub_rows = []
    for s in data.subs:
        if s.unit_id != dept.unit_id:
            continue
        owned = s.owner_scope == "department" and s.department_id == dept.id
        used = s.owner_scope == "unit" and members & set(s.assignee_days)
        if not (owned or used):
            continue
        share = cost.allocate([s], start, end, data.fx, data.emp_dept, data.dept_unit).get(s.unit_id, _empty())
        sub_rows.append({"subscription_id": s.id, "name": s.label, "owner_scope": s.owner_scope,
                         "cost_to_department_bdt": cost.q(share.department_total(dept.id))})
    sub_rows.sort(key=lambda r: r["cost_to_department_bdt"], reverse=True)

    per_person = cost.per_employee_by_seat([s for s in data.subs if s.unit_id == dept.unit_id], start, end, data.fx)
    employees = []
    for emp in db.query(Employee).filter(Employee.department_id == dept.id).order_by(Employee.name).all():
        employees.append({"employee_id": emp.id, "emp_code": emp.emp_code, "name": emp.name, "team": emp.team,
                          "status": emp.status, "cost_bdt": per_person.get(emp.id, Decimal("0.00"))})
    employees.sort(key=lambda r: r["cost_bdt"], reverse=True)

    trend = []
    for m_start, m_end in _months_back(day, months):
        trend.append({"month": m_start.strftime("%Y-%m"),
                      "amount_bdt": cost.q(data.allocate(m_start, m_end).get(dept.unit_id, _empty())
                                           .department_total(dept.id))})
    return {
        "department": {"id": dept.id, "name": dept.name, "unit_id": dept.unit_id, "unit_code": dept.unit.code,
                       "head_employee_id": dept.head_employee_id, "cost_center": dept.cost_center},
        "from": start, "to": end,
        "direct_bdt": cost.q(a.direct.get(dept.id, Decimal("0"))),
        "allocated_bdt": cost.q(a.allocated.get(dept.id, Decimal("0"))),
        "total_bdt": cost.q(a.department_total(dept.id)),
        "paid_bdt": cost.q(paid),
        "month_to_date_bdt": cost.q(mtd),
        **cost.budget_status(mtd, day, Decimal(dept.monthly_budget_bdt or 0)),
        "subscriptions": sub_rows,
        "employees": employees,
        "trend": trend,
    }


def _months_back(day: date, months: int) -> list[tuple[date, date]]:
    out = []
    first = day.replace(day=1)
    for i in range(months - 1, -1, -1):
        m_start = cost.add_months(first, -i)
        m_end = min(cost.add_months(m_start, 1) - timedelta(days=1), day)
        out.append((m_start, m_end))
    return out


@router.get("/trend")
def trend(group: Literal["unit", "department"] = "unit", unit_id: int | None = None,
          months: int = Query(12, ge=1, le=36), user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Monthly accrued cost per unit, or per department (optionally of one unit), for charts."""
    data = CostData(db, user)
    if not data.is_admin and not data.unit_scope and not data.dept_scope:
        raise forbidden()
    periods = _months_back(today(), months)
    allocs = [data.allocate(s, e) for s, e in periods]
    series = []
    if group == "unit":
        for unit in db.query(OrgUnit).filter(OrgUnit.active.is_(True)).order_by(OrgUnit.code).all():
            if data.can_see_unit(unit.id) and (unit_id is None or unit.id == unit_id):
                series.append({"id": unit.id, "name": unit.code,
                               "values": [cost.q(a.get(unit.id, _empty()).total) for a in allocs]})
    else:
        q = db.query(Department).filter(Department.active.is_(True))
        if unit_id is not None:
            q = q.filter(Department.unit_id == unit_id)
        for dept in q.order_by(Department.unit_id, Department.name).all():
            if data.can_see_department(dept.id):
                series.append({"id": dept.id, "name": dept.label,
                               "values": [cost.q(a.get(dept.unit_id, _empty()).department_total(dept.id))
                                          for a in allocs]})
    return {"months": [s.strftime("%Y-%m") for s, _ in periods], "series": series}


@router.get("/payments")
def payments(group: Literal["unit", "department"] = "unit", from_: date | None = Query(None, alias="from"),
             to: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actual card payments by the unit/department that owned the subscription when it was paid."""
    data = CostData(db, user)
    if not data.is_admin and not data.unit_scope and not data.dept_scope:
        raise forbidden()
    start, end = _range(from_, to)
    column = CardCharge.unit_id if group == "unit" else CardCharge.department_id
    rows_q = (
        db.query(column, func.count(CardCharge.id), func.coalesce(func.sum(CardCharge.amount_bdt), 0),
                 func.coalesce(func.sum(CardCharge.bank_fee_bdt), 0))
        .filter(CardCharge.charge_date >= start, CardCharge.charge_date <= end, CardCharge.is_expected.is_(False))
        .group_by(column)
        .all()
    )
    rows = []
    for key, count, total, fees in rows_q:
        if group == "unit":
            if key is None or not data.can_see_unit(key):
                continue
            name = db.get(OrgUnit, key).code
        else:
            if key is None:  # unit-wide subscriptions: paid by the unit, not one department
                if not data.is_admin and not data.unit_scope:
                    continue
                name = "Unit-wide (shared)"
            elif not data.can_see_department(key):
                continue
            else:
                name = db.get(Department, key).label
        rows.append({"id": key, "name": name, "charges": count, "paid_bdt": cost.q(Decimal(total)),
                     "bank_fees_bdt": cost.q(Decimal(fees))})
    rows.sort(key=lambda r: r["paid_bdt"], reverse=True)
    return {"group": group, "from": start, "to": end, "rows": rows,
            "total_bdt": cost.q(sum((r["paid_bdt"] for r in rows), Decimal("0")))}


@router.get("/budgets")
def budgets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """This month's budget position for every unit and department the user may see."""
    data = CostData(db, user)
    if not data.is_admin and not data.unit_scope and not data.dept_scope:
        raise forbidden()
    day = today()
    mtd = data.allocate(day.replace(day=1), day)
    units, depts = [], []
    for unit in db.query(OrgUnit).filter(OrgUnit.active.is_(True)).order_by(OrgUnit.code).all():
        a = mtd.get(unit.id, _empty())
        if data.can_see_unit(unit.id):
            units.append({"unit_id": unit.id, "code": unit.code, "month_to_date_bdt": cost.q(a.total),
                          **cost.budget_status(a.total, day, Decimal(unit.monthly_budget_bdt or 0))})
        for dept in unit.departments:
            if dept.active and data.can_see_department(dept.id):
                spent = a.department_total(dept.id)
                depts.append({"department_id": dept.id, "name": dept.label, "month_to_date_bdt": cost.q(spent),
                              **cost.budget_status(spent, day, Decimal(dept.monthly_budget_bdt or 0))})
    return {"as_of": day, "units": units, "departments": depts}


@router.get("/seats")
def seat_usage(unit_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Seat usage per subscription for the units the user may see (who holds what)."""
    data = CostData(db, user)
    if not data.is_admin and not data.unit_scope:
        raise forbidden()
    q = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE)
    if unit_id is not None:
        q = q.filter(Subscription.unit_id == unit_id)
    rows = []
    for s in q.order_by(Subscription.unit_id, Subscription.id).all():
        if not data.can_see_unit(s.unit_id):
            continue
        holders = [a for a in s.assignments if a.status != AssignmentStatus.REVOKED]
        rows.append({"subscription_id": s.id, "name": f"{s.vendor.name} {s.plan_name}", "owner": s.owner_label,
                     "seats_total": s.seats_total, "seats_used": len(holders),
                     "holders": [{"employee_id": a.employee_id, "name": a.employee.name,
                                  "department": a.employee.department_name, "status": a.status} for a in holders]})
    return rows

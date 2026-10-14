"""Load subscriptions from the database into the pure cost engine and apply role scoping."""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.enums import AssignmentStatus
from app.models import Assignment, Department, Employee, OrgFunction, Subscription, User
from app.services import cost, settings_store
from app.services.cost import ChargeInfo, SubInfo
from app.services.org import headed_departments, headed_functions, headed_units, led_teams


def load_subinfos(db: Session, employee_ids: list[int] | None = None, unit_id: int | None = None) -> list[SubInfo]:
    """employee_ids=None -> every subscription. Otherwise only those any of the employees hold.
    unit_id limits to subscriptions owned by that unit."""
    query = db.query(Subscription).options(
        selectinload(Subscription.charges),
        selectinload(Subscription.assignments).selectinload(Assignment.employee),
        selectinload(Subscription.vendor),
        selectinload(Subscription.org_unit),
        selectinload(Subscription.org_department),
        selectinload(Subscription.usage_days),
        selectinload(Subscription.shares),
    )
    if unit_id is not None:
        query = query.filter(Subscription.unit_id == unit_id)
    if employee_ids is not None:
        query = query.join(Assignment).filter(Assignment.employee_id.in_(employee_ids or [-1])).distinct()
    out = []
    for sub in query.all():
        holders = {}
        for a in sub.assignments:
            # a seat counts from start_date until end_date (exclusive); revoke_pending still costs
            end = a.end_date
            if a.status == AssignmentStatus.REVOKED and end is None:
                end = a.start_date
            holders.setdefault(a.employee_id, []).append((a.start_date, end))
        dept_label = (sub.department_name if sub.owner_scope in ("department", "function") and sub.department_name
                      else "Shared" if sub.owner_scope == "shared" else f"{sub.unit_code} SBU-wide")
        out.append(
            SubInfo(
                id=sub.id,
                billing_cycle=sub.billing_cycle,
                start_date=sub.start_date,
                end_date=sub.cancelled_on,
                cost_per_cycle=Decimal(sub.cost_per_cycle),
                currency=sub.currency,
                charges=[ChargeInfo(c.charge_date, Decimal(c.amount_bdt)) for c in sub.charges if not c.is_expected],
                assignee_days=holders,
                label=f"{sub.vendor.name} {sub.plan_name}",
                group={"tool": sub.vendor.name, "department": dept_label, "unit": sub.unit_code or "Unassigned"},
                unit_id=sub.unit_id,
                department_id=sub.department_id,
                owner_scope=sub.owner_scope,
                function_id=sub.function_id,
                shares=[(s.department_id, s.function_id) for s in sub.shares],
                seats_total=sub.seats_total,
                team_id=sub.team_id,
                usage=([ChargeInfo(u.usage_date, Decimal(u.amount_bdt)) for u in sub.usage_days]
                       if sub.usage_provider else None),
            )
        )
    return out


def scope_ids(db: Session, user: User) -> list[int] | None:
    from app.core.deps import visible_employee_ids

    return visible_employee_ids(db, user)


def _owns(sub: SubInfo, units: set[int], depts: set[int], fns: set[int], teams: set[int]) -> bool:
    """Whole subscriptions a head carries (shared ones are split, see Context._shared_part)."""
    if sub.team_id in teams:
        return True
    if sub.owner_scope == "shared":
        return False
    return (sub.unit_id in units
            or (sub.owner_scope in ("department", "function") and sub.department_id in depts)
            or (sub.owner_scope == "function" and sub.function_id in fns))


class Context:
    """Settings + FX + subscriptions for one request."""

    def __init__(self, db: Session, user: User):
        self.settings = settings_store.get_all(db)
        self.fx = settings_store.fx_rates(self.settings)
        self.ids = scope_ids(db, user)
        self.is_admin = self.ids is None
        self.subs = load_subinfos(db, self.ids)
        # SBU, department and function heads and team leaders carry the whole cost of what they own (team-owned
        # subscriptions are never split across people, so shares alone would miss them), plus their part of
        # shared subscriptions
        self.owned: list[SubInfo] = []
        self.shared: list[SubInfo] = []
        if not self.is_admin:
            units, depts = set(headed_units(db, user)), set(headed_departments(db, user))
            fns, teams = set(headed_functions(db, user)), set(led_teams(db, user))
            if units or depts or fns or teams:
                emp_dept, self._dept_unit = org_maps(db)
                self._maps = (emp_dept, self._dept_unit, function_map(db))
                # every department of a headed SBU counts as headed; a function inside a headed department too
                self._depts = depts | {d for d, u in self._dept_unit.items() if u in units}
                fn_dept = dict(db.query(OrgFunction.id, OrgFunction.department_id).all())
                self._fns = {f for f in fns if fn_dept.get(f) not in self._depts}
                everything = load_subinfos(db)
                self.owned = [s for s in everything if _owns(s, units, self._depts, fns, teams)]
                self.shared = [s for s in everything if s.owner_scope == "shared" and s.id not in
                               {o.id for o in self.owned} and any(d in self._depts or f in self._fns
                                                                   for d, f in s.shares)]
        self._owned_ids = {s.id for s in self.owned} | {s.id for s in self.shared}

    def _shared_part(self, start: date, end: date, subs: list[SubInfo] | None = None) -> Decimal:
        """The headed departments' / functions' part of shared subscriptions."""
        subs = self.shared if subs is None else subs
        if not subs:
            return Decimal("0")
        total = Decimal("0")
        for alloc in cost.allocate(subs, start, end, self.fx, *self._maps).values():
            total += sum((v for d, v in alloc.direct.items() if d in self._depts), Decimal("0"))
            total += sum((v for f, v in alloc.functions.items() if f in self._fns), Decimal("0"))
        return total

    def total(self, view: str, start: date, end: date) -> cost.Total:
        if self.is_admin:
            return cost.period_total(view, self.subs, start, end, self.fx)
        # managers / employees: the full cost of what they own, plus their people's share of other subscriptions
        owned = cost.accrued_total(self.owned, start, end, self.fx)
        others = [s for s in self.subs if s.id not in self._owned_ids]
        shares = cost.per_employee(others, start, end, self.fx)
        mine = sum((v for k, v in shares.items() if k in self.ids), Decimal("0"))
        return cost.Total(owned.amount + self._shared_part(start, end) + mine, owned.estimated)

    def summary(self, today: date, view: str) -> dict:
        if self.is_admin:
            return cost.summary(
                self.subs, today, self.fx, view,
                self.settings["week_start"], int(self.settings["year_start_month"]),
                Decimal(self.settings["monthly_budget_bdt"]),
            )
        month_start = today.replace(day=1)
        t_today = self.total("accrued", today, today)
        t_week = self.total("accrued", cost.week_start(today, self.settings["week_start"]), today)
        t_month = self.total("accrued", month_start, today)
        t_year = self.total("accrued", cost.year_start(today, int(self.settings["year_start_month"])), today)
        days = (today - month_start).days + 1
        dim = calendar.monthrange(today.year, today.month)[1]
        return {
            "view": "accrued",
            "today": t_today.as_dict(),
            "week": t_week.as_dict(),
            "month": t_month.as_dict(),
            "year": t_year.as_dict(),
            "projected_month": cost.q(t_month.amount / days * dim),
            "run_rate_year": cost.q(t_today.amount * 365),
            "monthly_budget": None,
            "budget_used_pct": None,
        }

    def daily_series(self, start: date, end: date, view: str) -> list[dict]:
        if self.is_admin:
            return cost.daily_series(self.subs, start, end, self.fx, view)
        return [{"date": d.isoformat(), "amount": cost.q(self.total("accrued", d, d).amount)}
                for d in cost.daterange(start, end)]

    def monthly_series(self, today: date, months: int, view: str) -> list[dict]:
        if self.is_admin:
            return cost.monthly_series(self.subs, today, months, self.fx, view)
        rows = []
        for row in cost.monthly_series(self.subs, today, months, self.fx, view):
            y, m = map(int, row["month"].split("-"))
            start = date(y, m, 1)
            end = min(date(y, m, calendar.monthrange(y, m)[1]), today)
            rows.append({"month": row["month"], "amount": cost.q(self.total("accrued", start, end).amount)})
        return rows

    def _mine_per_sub(self, start: date, end: date) -> list[tuple[SubInfo, Decimal]]:
        """Each subscription with the part of its cost that is this (non-admin) user's — the same parts
        `total` adds up."""
        rows = [(s, cost.accrued_total([s], start, end, self.fx).amount) for s in self.owned]
        rows += [(s, self._shared_part(start, end, [s])) for s in self.shared]
        for s in self.subs:
            if s.id not in self._owned_ids:
                shares = cost.per_employee([s], start, end, self.fx)
                rows.append((s, sum((v for k, v in shares.items() if k in self.ids), Decimal("0"))))
        return rows

    def grouped(self, key: str, start: date, end: date, view: str) -> list[dict]:
        if self.is_admin:
            return cost.grouped_total(self.subs, key, start, end, self.fx, view)
        groups: dict[str, Decimal] = defaultdict(Decimal)
        for sub, amount in self._mine_per_sub(start, end):
            if amount:
                groups[sub.group.get(key) or "Unassigned"] += amount
        rows = [{"name": name, "amount": cost.q(amount)} for name, amount in groups.items()]
        return sorted(rows, key=lambda r: r["amount"], reverse=True)

    def to_usd(self, amount: Decimal) -> Decimal:
        rate = self.fx.get("USD") or Decimal("1")
        return cost.q(Decimal(amount) / rate)


def org_maps(db: Session) -> tuple[dict[int, int | None], dict[int, int]]:
    """(employee_id -> department_id, department_id -> unit_id) for cost allocation."""
    emp_dept = {eid: did for eid, did in db.query(Employee.id, Employee.department_id).all()}
    dept_unit = {did: uid for did, uid in db.query(Department.id, Department.unit_id).all()}
    return emp_dept, dept_unit


def function_map(db: Session) -> dict[int, int | None]:
    """employee_id -> function_id."""
    return {eid: fid for eid, fid in db.query(Employee.id, Employee.function_id).all()}

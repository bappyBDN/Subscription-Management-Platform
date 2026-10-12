"""Load subscriptions from the database into the pure cost engine and apply role scoping."""

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.enums import AssignmentStatus
from app.models import Assignment, Subscription, User
from app.services import cost, settings_store
from app.services.cost import ChargeInfo, SubInfo


def load_subinfos(db: Session, employee_ids: list[int] | None = None) -> list[SubInfo]:
    """employee_ids=None -> every subscription. Otherwise only those any of the employees hold."""
    query = db.query(Subscription).options(
        selectinload(Subscription.charges),
        selectinload(Subscription.assignments).selectinload(Assignment.employee),
        selectinload(Subscription.vendor),
    )
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
        dept = sub.department or next((a.employee.department for a in sub.assignments if a.employee), None)
        unit = sub.unit or next((a.employee.unit for a in sub.assignments if a.employee), None)
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
                group={"tool": sub.vendor.name, "department": dept or "Unassigned", "unit": unit or "Unassigned"},
            )
        )
    return out


def scope_ids(db: Session, user: User) -> list[int] | None:
    from app.core.deps import visible_employee_ids

    return visible_employee_ids(db, user)


class Context:
    """Settings + FX + subscriptions for one request."""

    def __init__(self, db: Session, user: User):
        self.settings = settings_store.get_all(db)
        self.fx = settings_store.fx_rates(self.settings)
        self.ids = scope_ids(db, user)
        self.subs = load_subinfos(db, self.ids)
        self.is_admin = self.ids is None

    def total(self, view: str, start: date, end: date) -> cost.Total:
        if self.is_admin:
            return cost.period_total(view, self.subs, start, end, self.fx)
        # managers / employees: only the share of cost that belongs to their people (accrued)
        shares = cost.per_employee(self.subs, start, end, self.fx)
        return cost.Total(sum((v for k, v in shares.items() if k in self.ids), Decimal("0")), False)

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

    def grouped(self, key: str, start: date, end: date, view: str) -> list[dict]:
        return cost.grouped_total(self.subs, key, start, end, self.fx, view)

    def to_usd(self, amount: Decimal) -> Decimal:
        rate = self.fx.get("USD") or Decimal("1")
        return cost.q(Decimal(amount) / rate)

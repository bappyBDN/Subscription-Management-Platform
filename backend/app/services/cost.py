"""Cost engine (pure — no database access).

Two views:
  accrued – each subscription's cost spread evenly over the days it is active
  paid    – actual card charges on their charge date

Inputs are plain dataclasses so the maths is unit-tested without a database.
"""

import calendar
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def q(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def charge_bdt(amount_original: Decimal, fx_rate: Decimal, bank_fee_bdt: Decimal = Decimal("0")) -> Decimal:
    return q(Decimal(amount_original) * Decimal(fx_rate) + Decimal(bank_fee_bdt))


@dataclass(frozen=True)
class ChargeInfo:
    charge_date: date
    amount_bdt: Decimal


@dataclass
class SubInfo:
    id: int
    billing_cycle: str  # monthly | yearly | usage | one_time
    start_date: date
    end_date: date | None  # first day it is NOT active (cancelled_on), or None
    cost_per_cycle: Decimal
    currency: str
    charges: list[ChargeInfo] = field(default_factory=list)  # actual charges only
    # employee_id -> list of (start, end-exclusive or None) seat periods
    assignee_days: dict[int, list[tuple[date, date | None]]] = field(default_factory=dict)
    label: str = ""
    group: dict[str, str] = field(default_factory=dict)  # e.g. {"tool": "Claude", "department": "IT", "unit": "BMD"}

    def is_active_on(self, day: date) -> bool:
        if day < self.start_date:
            return False
        return self.end_date is None or day < self.end_date


@dataclass(frozen=True)
class DayCost:
    amount: Decimal
    estimated: bool


def _days_in_month(day: date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


def _days_in_year(day: date) -> int:
    return 366 if calendar.isleap(day.year) else 365


def estimate_cycle_bdt(sub: SubInfo, fx_rates: dict[str, Decimal]) -> Decimal:
    if sub.currency == "BDT":
        return Decimal(sub.cost_per_cycle)
    rate = fx_rates.get(sub.currency, Decimal("0"))
    return Decimal(sub.cost_per_cycle) * rate


def daily_cost(sub: SubInfo, day: date, fx_rates: dict[str, Decimal]) -> DayCost:
    """Accrued BDT cost of one subscription on one day (not rounded)."""
    if sub.billing_cycle in ("usage", "one_time"):
        total = sum((c.amount_bdt for c in sub.charges if c.charge_date == day), Decimal("0"))
        return DayCost(total, False)

    if not sub.is_active_on(day):
        return DayCost(Decimal("0"), False)

    previous = [c for c in sub.charges if c.charge_date <= day]
    if previous:
        cycle_amount = max(previous, key=lambda c: c.charge_date).amount_bdt
        estimated = False
    else:
        cycle_amount = estimate_cycle_bdt(sub, fx_rates)
        estimated = True

    divisor = _days_in_year(day) if sub.billing_cycle == "yearly" else _days_in_month(day)
    return DayCost(Decimal(cycle_amount) / divisor, estimated)


def daterange(start: date, end: date) -> Iterable[date]:
    """Inclusive range."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


@dataclass
class Total:
    amount: Decimal = Decimal("0")
    estimated: bool = False

    def add(self, dc: DayCost) -> None:
        self.amount += dc.amount
        self.estimated = self.estimated or (dc.estimated and dc.amount > 0)

    def as_dict(self) -> dict:
        return {"amount": q(self.amount), "estimated": self.estimated}


def accrued_total(subs: Iterable[SubInfo], start: date, end: date, fx_rates: dict[str, Decimal]) -> Total:
    total = Total()
    for sub in subs:
        for day in daterange(start, end):
            total.add(daily_cost(sub, day, fx_rates))
    return total


def paid_total(subs: Iterable[SubInfo], start: date, end: date) -> Total:
    total = Total()
    for sub in subs:
        for c in sub.charges:
            if start <= c.charge_date <= end:
                total.amount += c.amount_bdt
    return total


def period_total(view: str, subs: list[SubInfo], start: date, end: date, fx_rates: dict[str, Decimal]) -> Total:
    if view == "paid":
        return paid_total(subs, start, end)
    return accrued_total(subs, start, end, fx_rates)


def week_start(day: date, start_weekday: str = "sat") -> date:
    target = WEEKDAYS[start_weekday]
    return day - timedelta(days=(day.weekday() - target) % 7)


def year_start(day: date, start_month: int = 1) -> date:
    year = day.year if day.month >= start_month else day.year - 1
    return date(year, start_month, 1)


def summary(
    subs: list[SubInfo],
    today: date,
    fx_rates: dict[str, Decimal],
    view: str = "accrued",
    week_start_day: str = "sat",
    year_start_month: int = 1,
    monthly_budget_bdt: Decimal = Decimal("0"),
) -> dict:
    month_start = today.replace(day=1)
    t_today = period_total(view, subs, today, today, fx_rates)
    t_week = period_total(view, subs, week_start(today, week_start_day), today, fx_rates)
    t_month = period_total(view, subs, month_start, today, fx_rates)
    t_year = period_total(view, subs, year_start(today, year_start_month), today, fx_rates)

    days_elapsed = (today - month_start).days + 1
    projected_month = t_month.amount / days_elapsed * _days_in_month(today)
    today_accrued = accrued_total(subs, today, today, fx_rates).amount
    budget = Decimal(monthly_budget_bdt or 0)

    return {
        "view": view,
        "today": t_today.as_dict(),
        "week": t_week.as_dict(),
        "month": t_month.as_dict(),
        "year": t_year.as_dict(),
        "projected_month": q(projected_month),
        "run_rate_year": q(today_accrued * 365),
        "monthly_budget": q(budget) if budget else None,
        "budget_used_pct": float(q(t_month.amount / budget * 100)) if budget else None,
    }


def daily_series(subs: list[SubInfo], start: date, end: date, fx_rates: dict[str, Decimal], view: str = "accrued") -> list[dict]:
    out = []
    for day in daterange(start, end):
        out.append({"date": day.isoformat(), "amount": q(period_total(view, subs, day, day, fx_rates).amount)})
    return out


def monthly_series(subs: list[SubInfo], today: date, months: int, fx_rates: dict[str, Decimal], view: str = "accrued") -> list[dict]:
    out = []
    year, month = today.year, today.month
    starts = []
    for _ in range(months):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    for start in reversed(starts):
        last = date(start.year, start.month, _days_in_month(start))
        end = min(last, today)
        out.append({"month": start.strftime("%Y-%m"), "amount": q(period_total(view, subs, start, end, fx_rates).amount)})
    return out


def grouped_total(subs: list[SubInfo], key: str, start: date, end: date, fx_rates: dict[str, Decimal], view: str = "accrued") -> list[dict]:
    groups: dict[str, Decimal] = defaultdict(Decimal)
    for sub in subs:
        groups[sub.group.get(key) or "Unassigned"] += period_total(view, [sub], start, end, fx_rates).amount
    rows = [{"name": name, "amount": q(amount)} for name, amount in groups.items()]
    return sorted(rows, key=lambda r: r["amount"], reverse=True)


def per_employee(subs: list[SubInfo], start: date, end: date, fx_rates: dict[str, Decimal]) -> dict[int | None, Decimal]:
    """Accrued cost per employee; a subscription's daily cost is split across that day's holders.

    Key None = unassigned seats.
    """
    result: dict[int | None, Decimal] = defaultdict(Decimal)
    for sub in subs:
        for day in daterange(start, end):
            dc = daily_cost(sub, day, fx_rates).amount
            if not dc:
                continue
            holders = [
                emp for emp, periods in sub.assignee_days.items()
                if any(a_start <= day and (a_end is None or day < a_end) for a_start, a_end in periods)
            ]
            if not holders:
                result[None] += dc
                continue
            share = dc / len(holders)
            for emp in holders:
                result[emp] += share
    return {k: q(v) for k, v in result.items()}


def estimate_request_cost(cost_per_cycle: Decimal, currency: str, billing_cycle: str, seats: int, fx_rates: dict[str, Decimal]) -> dict:
    rate = Decimal("1") if currency == "BDT" else fx_rates.get(currency, Decimal("0"))
    per_cycle = Decimal(cost_per_cycle) * seats
    if billing_cycle == "yearly":
        monthly, yearly = per_cycle / 12, per_cycle
    elif billing_cycle == "monthly":
        monthly, yearly = per_cycle, per_cycle * 12
    else:  # usage / one-time: show the single amount
        monthly, yearly = per_cycle, per_cycle
    return {
        "currency": currency,
        "monthly_original": q(monthly),
        "yearly_original": q(yearly),
        "monthly_bdt": q(monthly * rate),
        "yearly_bdt": q(yearly * rate),
        "fx_rate": rate,
    }


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))

from datetime import date
from decimal import Decimal

from app.services import cost
from app.services.cost import ChargeInfo, SubInfo

FX = {"USD": Decimal("120")}


def monthly_sub(**kw) -> SubInfo:
    data = dict(
        id=1,
        billing_cycle="monthly",
        start_date=date(2026, 1, 1),
        end_date=None,
        cost_per_cycle=Decimal("20"),
        currency="USD",
    )
    data.update(kw)
    return SubInfo(**data)


def test_charge_bdt_includes_fx_and_fee():
    assert cost.charge_bdt(Decimal("20"), Decimal("121.5"), Decimal("45.25")) == Decimal("2475.25")


def test_monthly_daily_cost_uses_last_actual_charge():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 9, 5), Decimal("3000")), ChargeInfo(date(2026, 10, 5), Decimal("3100"))])
    # October has 31 days; the last charge on/before Oct 10 is 3100
    dc = cost.daily_cost(sub, date(2026, 10, 10), FX)
    assert not dc.estimated
    assert cost.q(dc.amount) == Decimal("100.00")
    # Before the October charge the September charge applies (30-day month -> /30 is Sept, but day is Oct 1 -> /31)
    dc = cost.daily_cost(sub, date(2026, 9, 10), FX)
    assert cost.q(dc.amount) == Decimal("100.00")


def test_monthly_without_charge_is_estimated_from_fx():
    sub = monthly_sub()
    dc = cost.daily_cost(sub, date(2026, 4, 1), FX)  # 20 * 120 / 30
    assert dc.estimated
    assert cost.q(dc.amount) == Decimal("80.00")


def test_yearly_spread_over_days_in_year():
    sub = monthly_sub(billing_cycle="yearly", charges=[ChargeInfo(date(2026, 1, 1), Decimal("36500"))])
    assert cost.q(cost.daily_cost(sub, date(2026, 6, 1), FX).amount) == Decimal("100.00")


def test_usage_charge_counts_only_on_charge_date():
    sub = monthly_sub(billing_cycle="usage", charges=[ChargeInfo(date(2026, 10, 3), Decimal("1200"))])
    assert cost.daily_cost(sub, date(2026, 10, 3), FX).amount == Decimal("1200")
    assert cost.daily_cost(sub, date(2026, 10, 4), FX).amount == Decimal("0")


def test_inactive_before_start_and_after_cancel():
    sub = monthly_sub(start_date=date(2026, 10, 5), end_date=date(2026, 10, 20))
    assert cost.daily_cost(sub, date(2026, 10, 4), FX).amount == 0
    assert cost.daily_cost(sub, date(2026, 10, 5), FX).amount > 0
    assert cost.daily_cost(sub, date(2026, 10, 20), FX).amount == 0


def test_accrued_month_total_equals_charge():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 10, 1), Decimal("3100"))])
    total = cost.accrued_total([sub], date(2026, 10, 1), date(2026, 10, 31), FX)
    assert cost.q(total.amount) == Decimal("3100.00")


def test_paid_view_sums_charges_in_range():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 9, 30), Decimal("10")), ChargeInfo(date(2026, 10, 1), Decimal("3100"))])
    assert cost.paid_total([sub], date(2026, 10, 1), date(2026, 10, 31)).amount == Decimal("3100")


def test_week_start_saturday():
    # 12 Oct 2026 is a Monday -> week started Saturday 10 Oct
    assert cost.week_start(date(2026, 10, 12), "sat") == date(2026, 10, 10)
    assert cost.week_start(date(2026, 10, 10), "sat") == date(2026, 10, 10)
    assert cost.week_start(date(2026, 10, 12), "sun") == date(2026, 10, 11)


def test_year_start_fiscal_july():
    assert cost.year_start(date(2026, 10, 12), 7) == date(2026, 7, 1)
    assert cost.year_start(date(2026, 3, 1), 7) == date(2025, 7, 1)
    assert cost.year_start(date(2026, 3, 1), 1) == date(2026, 1, 1)


def test_summary_shape_and_budget():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 10, 1), Decimal("3100"))])
    s = cost.summary([sub], date(2026, 10, 12), FX, monthly_budget_bdt=Decimal("6200"))
    assert s["today"]["amount"] == Decimal("100.00")
    assert s["month"]["amount"] == Decimal("1200.00")
    assert s["projected_month"] == Decimal("3100.00")
    assert s["budget_used_pct"] == 19.35
    assert s["week"]["amount"] == Decimal("300.00")  # Sat 10, Sun 11, Mon 12


def test_per_employee_splits_shared_seat():
    sub = monthly_sub(
        charges=[ChargeInfo(date(2026, 10, 1), Decimal("3100"))],
        assignee_days={7: [(date(2026, 10, 1), None)], 8: [(date(2026, 10, 1), None)]},
    )
    result = cost.per_employee([sub], date(2026, 10, 1), date(2026, 10, 2), FX)
    assert result[7] == Decimal("100.00")
    assert result[8] == Decimal("100.00")


def test_per_employee_unassigned_bucket():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 10, 1), Decimal("3100"))])
    assert cost.per_employee([sub], date(2026, 10, 1), date(2026, 10, 1), FX)[None] == Decimal("100.00")


def test_estimate_request_cost_monthly_and_yearly():
    est = cost.estimate_request_cost(Decimal("20"), "USD", "monthly", 2, FX)
    assert est["monthly_bdt"] == Decimal("4800.00")
    assert est["yearly_bdt"] == Decimal("57600.00")
    est = cost.estimate_request_cost(Decimal("240"), "USD", "yearly", 1, FX)
    assert est["monthly_original"] == Decimal("20.00")


def test_monthly_series_covers_n_months():
    sub = monthly_sub(charges=[ChargeInfo(date(2026, 1, 1), Decimal("3100"))])
    series = cost.monthly_series([sub], date(2026, 3, 15), 3, FX)
    assert [r["month"] for r in series] == ["2026-01", "2026-02", "2026-03"]
    assert series[0]["amount"] == Decimal("3100.00")


def test_add_months_clamps_day():
    assert cost.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert cost.add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)


def test_per_employee_counts_every_seat_period():
    # held 1-2 Oct, revoked, re-assigned from 5 Oct: days 3-4 are unassigned
    sub = monthly_sub(
        charges=[ChargeInfo(date(2026, 10, 1), Decimal("3100"))],
        assignee_days={7: [(date(2026, 10, 1), date(2026, 10, 3)), (date(2026, 10, 5), None)]},
    )
    result = cost.per_employee([sub], date(2026, 10, 1), date(2026, 10, 6), FX)
    assert result[7] == Decimal("400.00")
    assert result[None] == Decimal("200.00")

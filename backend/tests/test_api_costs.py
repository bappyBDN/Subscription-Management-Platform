"""Card charges, dashboard, reports and jobs."""

from datetime import date, timedelta
from decimal import Decimal

from app.core.clock import today
from app.jobs import tasks
from app.models import CardCharge, DailyCost


def test_charge_bdt_is_computed_and_fx_defaults(client, auth, subscription):
    r = client.post("/api/charges", headers=auth("delegate"), json={
        "subscription_id": subscription.id, "charge_date": today().isoformat(),
        "amount_original": "90", "currency": "USD", "fx_rate": "121.5", "bank_fee_bdt": "40"})
    assert r.status_code == 201
    assert Decimal(r.json()["amount_bdt"]) == Decimal("10975.00")
    assert r.json()["card_id"] == subscription.card_id
    r = client.post("/api/charges", headers=auth("delegate"), json={
        "subscription_id": subscription.id, "charge_date": today().isoformat(), "amount_original": "10"})
    assert Decimal(r.json()["fx_rate"]) == Decimal("122")


def test_card_last4_only(client, auth):
    assert client.post("/api/cards", headers=auth("dmd"), json={
        "label": "x", "holder_name": "DMD Sir", "last4": "4111111111111111"}).status_code == 422


def test_dashboard_summary_admin_vs_employee(client, auth, org, subscription):
    s = client.get("/api/dashboard/summary", headers=auth("dmd")).json()
    assert Decimal(s["today"]["amount"]) > 0
    assert s["counts"]["active_subscriptions"] == 1 and s["counts"]["renewals_7_days"] == 1
    usd = client.get("/api/dashboard/summary?currency=USD", headers=auth("dmd")).json()
    assert Decimal(usd["month"]["amount"]) < Decimal(s["month"]["amount"])
    # employee with no seats sees zero, not the org total
    e = client.get("/api/dashboard/summary", headers=auth("staff")).json()
    assert Decimal(e["month"]["amount"]) == 0
    client.post(f"/api/subscriptions/{subscription.id}/assignments",
                json={"employee_id": org["emps"]["staff"].id, "start_date": today().replace(day=1).isoformat()},
                headers=auth("dmd"))
    e = client.get("/api/dashboard/summary", headers=auth("staff")).json()
    assert Decimal(e["month"]["amount"]) > 0


def test_series_and_groupings(client, auth, subscription):
    assert len(client.get("/api/dashboard/series?days=30", headers=auth("dmd")).json()) == 30
    assert len(client.get("/api/dashboard/monthly?months=12", headers=auth("dmd")).json()) == 12
    tools = client.get("/api/dashboard/by-tool?period=month", headers=auth("dmd")).json()
    assert tools[0]["name"] == "Claude"
    assert client.get("/api/dashboard/renewals", headers=auth("dmd")).json()[0]["subscription_id"] == subscription.id


def test_reports_json_and_xlsx(client, auth, subscription):
    r = client.get("/api/reports/register", headers=auth("delegate")).json()
    assert r["rows"][0]["tool"] == "Claude" and r["rows"][0]["card"] == "•••• 4417"
    r = client.get(f"/api/reports/cost-summary?from={(today() - timedelta(days=60)).isoformat()}",
                   headers=auth("dmd")).json()
    assert len(r["rows"]) >= 2
    x = client.get("/api/reports/register?format=xlsx", headers=auth("dmd"))
    assert x.status_code == 200 and x.content[:2] == b"PK"
    # managers get team reports only
    assert client.get("/api/reports/cost-by-employee", headers=auth("mgr")).status_code == 200
    assert client.get("/api/reports/register", headers=auth("mgr")).status_code == 403


def test_settings_only_dmd_can_change(client, auth):
    assert client.put("/api/settings", json={"week_start": "sun"}, headers=auth("delegate")).status_code == 403
    r = client.put("/api/settings", json={"week_start": "sun", "monthly_budget_bdt": "50000"}, headers=auth("dmd"))
    assert r.json()["week_start"] == "sun" and r.json()["monthly_budget_bdt"] == "50000"


def test_import_subscriptions_csv(client, auth, org):
    csv = ("vendor,plan_name,seats_total,cost_per_cycle,currency,billing_cycle,start_date,next_renewal_date,"
           "card_last4,unit,department,holder_codes\n"
           "ChatGPT,Plus,1,20,USD,monthly,2026-01-05,2026-11-05,4417,AES,IT,E1\n"
           "NewTool,Basic,1,abc,USD,monthly,2026-01-05,,,AES,,\n"
           "Gemini,Advanced,1,20,USD,monthly,2026-01-05,,,XYZ,,\n")
    r = client.post("/api/subscriptions/import", headers=auth("delegate"),
                    files={"file": ("subs.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200
    assert r.json()["created"] == 1 and [e["row"] for e in r.json()["errors"]] == [3, 4]
    subs = client.get("/api/subscriptions", headers=auth("delegate")).json()
    assert subs[0]["owner_scope"] == "department" and subs[0]["owner_label"] == "AES / IT"
    vendors = [v["name"] for v in client.get("/api/vendors", headers=auth("delegate")).json()]
    assert "NewTool" not in vendors and "Gemini" not in vendors  # failed rows leave nothing behind


def test_notifications_flow(client, auth, org, subscription):
    client.post("/api/requests", headers=auth("staff"), json={
        "subscription_id": subscription.id, "needed_from": today().isoformat(),
        "reason": "I review supplier contracts daily and need Claude to summarise them."})
    n = client.get("/api/notifications", headers=auth("mgr")).json()
    assert n["unread"] == 1 and n["items"][0]["link"].startswith("/requests/")
    client.post("/api/notifications/read-all", headers=auth("mgr"))
    assert client.get("/api/notifications", headers=auth("mgr")).json()["unread"] == 0


def test_jobs(db, client, auth, subscription):
    day = today()
    assert tasks.daily_cost(db, day - timedelta(days=1)) == 1
    assert db.query(DailyCost).count() == 1
    assert tasks.renewal_reminders(db, day) == 1  # renews in 7 days
    subscription.next_renewal_date = day
    db.commit()
    assert tasks.expected_charges(db, day) == 1
    assert db.query(CardCharge).filter(CardCharge.is_expected.is_(True)).count() == 1
    assert subscription.next_renewal_date > day
    assert tasks.dmd_digest(db, day) == 1

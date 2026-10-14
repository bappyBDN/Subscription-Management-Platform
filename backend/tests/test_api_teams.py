"""Teams, team-owned subscriptions, team cost and DeepSeek usage metering."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.clock import today
from app.core.config import get_settings
from app.models import Subscription, Team, UsageDay, Vendor
from app.services import usage
from app.services.settings_store import fx_rates, get_all


@pytest.fixture()
def analytics(db, org):
    """AES team "AI Analytics" led by Employee One, with Rahim Vai as the other member, owning a
    DeepSeek API-credit subscription whose cost is metered from the DeepSeek balance."""
    aes = org["units"]["aes"]
    staff, colleague = org["emps"]["staff"], org["emps"]["colleague"]
    staff.team = colleague.team = "AI Analytics"
    team = Team(unit_id=aes.id, name="AI Analytics", lead_employee_id=staff.id)
    vendor = Vendor(name="DeepSeek", category="ai")
    db.add_all([team, vendor])
    db.flush()
    sub = Subscription(vendor_id=vendor.id, plan_name="API credit", type="api_credit", seats_total=5,
                       cost_per_cycle=Decimal("10"), currency="USD", billing_cycle="usage",
                       start_date=today() - timedelta(days=60), owner_scope="unit", unit_id=aes.id,
                       team_id=team.id, usage_provider="deepseek")
    db.add(sub)
    db.commit()
    return {"team": team, "sub": sub}


def _fx(db):
    return fx_rates(get_all(db))


# ------------------------------------------------------------------ teams master

def test_team_crud_and_validation(client, auth, org):
    aes = org["units"]["aes"]
    body = {"unit_id": aes.id, "name": "Software", "lead_employee_id": org["emps"]["mgr"].id}
    assert client.post("/api/teams", json=body, headers=auth("staff")).status_code == 403
    r = client.post("/api/teams", json=body, headers=auth("dmd"))
    assert r.status_code == 201, r.text
    team = r.json()
    assert team["unit_code"] == "AES" and team["lead_name"] == "Manager One"
    r = client.patch(f"/api/teams/{team['id']}", json={"department_id": org["depts"]["marketing"].id},
                     headers=auth("dmd"))
    assert r.status_code == 400 and "another unit" in r.json()["detail"]
    r = client.patch(f"/api/teams/{team['id']}", json={"department_id": org["depts"]["it"].id}, headers=auth("dmd"))
    assert r.json()["department_name"] == "IT"
    assert team["members"] == 3  # everyone in AES whose team field is "Software"
    assert "already has a team" in client.post("/api/teams", json=body, headers=auth("dmd")).json()["detail"]
    r = client.patch(f"/api/teams/{team['id']}", json={"lead_employee_id": org["emps"]["other"].id},
                     headers=auth("dmd"))
    assert r.status_code == 400 and "same unit" in r.json()["detail"]
    r = client.patch(f"/api/teams/{team['id']}", json={"active": False}, headers=auth("dmd"))
    assert r.status_code == 200 and r.json()["active"] is False
    # a unit head whose unit has no active team gets an empty list, not an error
    assert client.get("/api/costs/teams", headers=auth("mgr")).json()["rows"] == []
    client.patch(f"/api/teams/{team['id']}", json={"active": True}, headers=auth("dmd"))
    me = client.get("/api/auth/me", headers=auth("mgr")).json()
    assert me["leads_team_ids"] == [team["id"]]


def test_subscription_team_must_be_in_the_unit(client, auth, org, analytics):
    r = client.post("/api/subscriptions", headers=auth("dmd"), json={
        "vendor_id": org["chatgpt"].id, "plan_name": "Team", "cost_per_cycle": "30",
        "start_date": today().isoformat(), "unit_id": org["units"]["bmd"].id, "team_id": analytics["team"].id})
    assert r.status_code == 400 and "another unit" in r.json()["detail"]
    r = client.get(f"/api/subscriptions/{analytics['sub'].id}", headers=auth("dmd"))
    assert r.json()["team_name"] == "AI Analytics" and r.json()["owner_label"] == "AES / AI Analytics team"


# ------------------------------------------------------------------ access rule

def test_only_team_members_can_request_a_team_subscription(client, auth, org, analytics):
    sub_id = analytics["sub"].id
    mine = client.get("/api/my/available-subscriptions", headers=auth("staff")).json()
    assert [s["subscription_id"] for s in mine] == [sub_id]
    # same unit and department, but in the Software team
    assert client.get("/api/my/available-subscriptions", headers=auth("mgr")).json() == []
    r = client.post(f"/api/subscriptions/{sub_id}/assignments", json={"employee_id": org["emps"]["mgr"].id},
                    headers=auth("dmd"))
    assert r.status_code == 400 and "AI Analytics team" in r.json()["detail"]
    r = client.post(f"/api/subscriptions/{sub_id}/assignments", json={"employee_id": org["emps"]["colleague"].id},
                    headers=auth("dmd"))
    assert r.status_code == 201


# ------------------------------------------------------------------ usage metering

def test_balance_drop_becomes_daily_usage(db, org, analytics):
    sub, day = analytics["sub"], today()
    fx = _fx(db)
    first = usage.record_balance(db, sub, day - timedelta(days=1), Decimal("50"), "USD", fx)
    assert first.amount_original == 0  # baseline only
    usage.record_balance(db, sub, day, Decimal("47.50"), "USD", fx)
    row = usage.record_balance(db, sub, day, Decimal("46"), "USD", fx)  # second sync the same day adds up
    assert row.amount_original == Decimal("4") and row.amount_bdt == Decimal("4") * fx["USD"]
    topped = usage.record_balance(db, sub, day, Decimal("96"), "USD", fx)  # a top-up is not negative spend
    assert topped.amount_original == Decimal("4") and topped.topped_up == Decimal("50")
    assert db.query(UsageDay).count() == 2


def test_sync_reads_deepseek_and_reports_errors(client, auth, db, org, analytics, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    r = client.post("/api/usage/sync", headers=auth("dmd"))
    assert r.status_code == 400 and "DEEPSEEK_API_KEY" in r.json()["detail"]

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    balances = iter([{"USD": Decimal("20")}, {"USD": Decimal("18.25")}])
    monkeypatch.setattr(usage, "fetch_deepseek_balances", lambda key, url: next(balances))
    assert client.post("/api/usage/sync", headers=auth("staff")).status_code == 403
    assert client.post("/api/usage/sync", headers=auth("dmd")).json()["amount_original"] == 0  # baseline
    r = client.post("/api/usage/sync", headers=auth("delegate"))
    assert r.status_code == 200 and Decimal(str(r.json()["amount_original"])) == Decimal("1.75")
    status = client.get("/api/usage/status", headers=auth("dmd")).json()
    assert status["key_configured"] and status["team_name"] == "AI Analytics"
    assert Decimal(str(status["last"]["balance"])) == Decimal("18.25")

    def rejected(key, url):
        raise usage.UsageError("DeepSeek rejected the API key")

    monkeypatch.setattr(usage, "fetch_deepseek_balances", rejected)
    assert "rejected" in client.post("/api/usage/sync", headers=auth("dmd")).json()["detail"]


# ------------------------------------------------------------------ team cost

def test_team_cost_is_the_teams_not_individuals(client, auth, db, org, analytics):
    sub, day = analytics["sub"], today()
    fx = _fx(db)
    usage.record_balance(db, sub, day - timedelta(days=1), Decimal("50"), "USD", fx)
    usage.record_balance(db, sub, day, Decimal("48"), "USD", fx)
    db.commit()
    client.post(f"/api/subscriptions/{sub.id}/assignments", json={"employee_id": org["emps"]["staff"].id},
                headers=auth("dmd"))
    spent = Decimal("2") * fx["USD"]

    r = client.get("/api/costs/teams", headers=auth("dmd"))
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["name"] == "AI Analytics" and row["lead_name"] == "Employee One" and row["members"] == 2
    assert Decimal(row["today_bdt"]) == spent and Decimal(row["month_to_date_bdt"]) == spent
    assert row["subscriptions"][0]["metered"] is True

    # the organisation total includes it, but no individual carries it
    assert Decimal(client.get("/api/dashboard/summary", headers=auth("dmd")).json()["today"]["amount"]) == spent
    top = client.get("/api/dashboard/top-employees", headers=auth("dmd")).json()
    assert all(Decimal(p["amount"]) == 0 for p in top)

    # the team leader and the unit head see it; other employees do not
    assert client.get("/api/costs/teams", headers=auth("staff")).json()["rows"][0]["team_id"] == row["team_id"]
    assert len(client.get("/api/costs/teams", headers=auth("mgr")).json()["rows"]) == 1
    assert client.get("/api/costs/teams", headers=auth("colleague")).status_code == 403
    assert client.get(f"/api/costs/teams/{row['team_id']}", headers=auth("fin")).status_code == 403

    detail = client.get(f"/api/costs/teams/{row['team_id']}?days=7", headers=auth("staff")).json()
    assert len(detail["series"]) == 7 and Decimal(detail["series"][-1]["amount"]) == spent
    assert [m["emp_code"] for m in detail["member_list"]] == ["E1", "C1"]

    # the team leader's and unit head's dashboards carry the team's cost; a plain member's does not
    for key in ("staff", "mgr"):
        s = client.get("/api/dashboard/summary", headers=auth(key)).json()
        assert Decimal(s["today"]["amount"]) == spent and Decimal(s["month"]["amount"]) == spent, key
    assert Decimal(client.get("/api/dashboard/summary", headers=auth("colleague")).json()["month"]["amount"]) == 0


def test_unnamed_seats_count_as_used(client, auth, org, analytics):
    """A team can use seats whose holders are not recorded; they are used seats, not free ones."""
    r = client.post("/api/subscriptions", headers=auth("dmd"), json={
        "vendor_id": org["claude"].id, "plan_name": "Max", "type": "team", "seats_total": 20, "seats_unnamed": 4,
        "cost_per_cycle": "115", "start_date": today().replace(day=1).isoformat(),
        "unit_id": org["units"]["aes"].id, "team_id": analytics["team"].id})
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["seats_used"] == 4 and sub["seats_unnamed"] == 4
    client.post(f"/api/subscriptions/{sub['id']}/assignments", json={"employee_id": org["emps"]["staff"].id},
                headers=auth("dmd"))
    r = client.patch(f"/api/subscriptions/{sub['id']}", json={"seats_total": 4}, headers=auth("dmd"))
    assert r.status_code == 400 and "5 seats are in use" in r.json()["detail"]
    row = client.get("/api/costs/teams", headers=auth("dmd")).json()["rows"][0]
    claude = next(s for s in row["subscriptions"] if s["name"] == "Claude Max")
    assert (claude["seats_used"], claude["seats_free"], claude["seats_total"]) == (5, 15, 20)
    assert row["estimated"] is True and row["month_to_date_bdt"] > 0  # no card charge yet: estimated from the price

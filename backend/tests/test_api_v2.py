"""v2: unit/department ownership, access rule, proposals, cost allocation and payments."""

from datetime import timedelta
from decimal import Decimal

from app.core.clock import today
from app.services.cost import add_months

REASON = "I need this tool every day for reporting and analysis work in my team."


def _prev_month() -> tuple[str, str]:
    first = add_months(today().replace(day=1), -1)
    last = today().replace(day=1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def _assign(client, headers, sub, emp, start):
    r = client.post(f"/api/subscriptions/{sub.id}/assignments",
                    json={"employee_id": emp.id, "start_date": start.isoformat()}, headers=headers)
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ access rule

def test_available_subscriptions_follow_unit_and_department(client, auth, subscription, it_subscription,
                                                            marketing_subscription):
    staff = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth("staff")).json()}
    assert staff == {subscription.id, it_subscription.id}  # AES unit-wide + AES/IT
    fin = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth("fin")).json()}
    assert fin == {subscription.id}  # AES unit-wide only, not IT's Copilot
    other = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth("other")).json()}
    assert other == {marketing_subscription.id}
    row = next(s for s in client.get("/api/my/available-subscriptions", headers=auth("staff")).json()
               if s["subscription_id"] == subscription.id)
    assert row["seats_free"] == 3 and Decimal(row["monthly_bdt_per_seat"]) == Decimal("3660.00")


def test_cannot_request_another_departments_or_units_subscription(client, auth, it_subscription,
                                                                  marketing_subscription):
    body = {"needed_from": today().isoformat(), "reason": REASON}
    r = client.post("/api/requests", json={**body, "subscription_id": it_subscription.id}, headers=auth("fin"))
    assert r.status_code == 403 and "AES / IT" in r.json()["detail"]
    r = client.post("/api/requests", json={**body, "subscription_id": marketing_subscription.id}, headers=auth("staff"))
    assert r.status_code == 403
    r = client.post("/api/requests", json={**body, "subscription_id": it_subscription.id}, headers=auth("staff"))
    assert r.status_code == 201 and r.json()["department_id"] == it_subscription.department_id


def test_seat_request_needs_a_subscription_and_not_a_duplicate(client, auth, org, subscription):
    r = client.post("/api/requests", json={"needed_from": today().isoformat(), "reason": REASON,
                                           "vendor_id": org["claude"].id, "plan_name": "Pro"}, headers=auth("staff"))
    assert r.status_code == 422
    _assign(client, auth("dmd"), subscription, org["emps"]["staff"], today())
    r = client.post("/api/requests", json={"subscription_id": subscription.id, "needed_from": today().isoformat(),
                                           "reason": REASON}, headers=auth("staff"))
    assert r.status_code == 400 and "already" in r.json()["detail"]


def test_admin_cannot_assign_outside_owner(client, auth, org, it_subscription):
    r = client.post(f"/api/subscriptions/{it_subscription.id}/assignments",
                    json={"employee_id": org["emps"]["fin"].id}, headers=auth("dmd"))
    assert r.status_code == 400 and "not in AES / IT" in r.json()["detail"]


def test_subscription_owner_validation(client, auth, org):
    base = {"vendor_id": org["chatgpt"].id, "plan_name": "Team", "cost_per_cycle": "30",
            "start_date": today().isoformat()}
    r = client.post("/api/subscriptions", json={**base, "owner_scope": "department", "unit_id": org["units"]["aes"].id},
                    headers=auth("dmd"))
    assert r.status_code == 422  # department scope without department
    r = client.post("/api/subscriptions", json={**base, "owner_scope": "department", "unit_id": org["units"]["aes"].id,
                                                "department_id": org["depts"]["marketing"].id}, headers=auth("dmd"))
    assert r.status_code == 400 and "another unit" in r.json()["detail"]
    r = client.post("/api/subscriptions", json={**base, "owner_scope": "department", "unit_id": org["units"]["aes"].id,
                                                "department_id": org["depts"]["finance"].id}, headers=auth("dmd"))
    assert r.status_code == 201 and r.json()["owner_label"] == "AES / Finance"


# ------------------------------------------------------------------ proposals

def test_proposal_flow(client, auth, org, subscription):
    body = {"type": "proposal", "vendor_id": org["copilot"].id, "plan_name": "Pro", "seats": 2,
            "needed_from": today().isoformat(), "reason": REASON}
    # an ordinary employee cannot propose
    assert client.post("/api/requests", json=body, headers=auth("staff")).status_code == 403
    # a tool the unit already has -> request a seat instead
    r = client.post("/api/requests", json={**body, "vendor_id": org["claude"].id}, headers=auth("mgr"))
    assert r.status_code == 400 and "request a seat" in r.json()["detail"]
    # department head proposes for IT
    r = client.post("/api/requests", json=body, headers=auth("mgr"))
    assert r.status_code == 201, r.text
    prop = r.json()
    assert prop["type"] == "proposal" and prop["owner_scope"] == "department" and prop["subscription_id"] is None
    rid = prop["id"]
    # DMD Sir is the manager's manager: recommend, then approve
    client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend"}, headers=auth("dmd"))
    assert client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"},
                       headers=auth("dmd")).json()["status"] == "approved"
    assert [p["id"] for p in client.get("/api/requests?scope=proposals", headers=auth("delegate")).json()] == [rid]
    # proposals are not handed over
    r = client.post(f"/api/requests/{rid}/handover", headers=auth("dmd"),
                    json={"method": "vault", "subscription_id": subscription.id, "secret": "x"})
    assert r.status_code == 400
    # fulfilling with a unit-wide subscription is refused; with a new IT-owned one it works
    assert client.post(f"/api/requests/{rid}/fulfil", json={"subscription_id": subscription.id},
                       headers=auth("dmd")).status_code == 400
    new_sub = client.post("/api/subscriptions", headers=auth("delegate"), json={
        "vendor_id": org["copilot"].id, "plan_name": "Pro", "seats_total": 2, "cost_per_cycle": "20",
        "start_date": today().isoformat(), "owner_scope": "department", "unit_id": org["units"]["aes"].id,
        "department_id": org["depts"]["it"].id}).json()
    r = client.post(f"/api/requests/{rid}/fulfil", json={"subscription_id": new_sub["id"]}, headers=auth("delegate"))
    assert r.json()["status"] == "fulfilled" and r.json()["subscription_id"] == new_sub["id"]
    # now IT staff can request a seat on it
    ids = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth("staff")).json()}
    assert new_sub["id"] in ids


def test_unit_wide_proposal_only_for_unit_head(client, auth, org, db):
    org["depts"]["it"].head_employee_id = None
    org["units"]["aes"].head_employee_id = None
    db.commit()
    body = {"type": "proposal", "owner_scope": "unit", "other_tool_name": "Perplexity", "plan_name": "Pro",
            "needed_from": today().isoformat(), "reason": REASON, "est_cost_per_cycle": "20"}
    # still a manager (has reports) -> may propose, but not unit-wide
    assert client.post("/api/requests", json=body, headers=auth("mgr")).status_code == 403
    r = client.post("/api/requests", json={**body, "owner_scope": "department"}, headers=auth("mgr"))
    assert r.status_code == 201 and float(r.json()["est_cost_original"]) == 20.0


def test_me_shows_heads_and_proposal_right(client, auth, org):
    me = client.get("/api/auth/me", headers=auth("mgr")).json()
    assert me["heads_unit_ids"] == [org["units"]["aes"].id]
    assert me["heads_department_ids"] == [org["depts"]["it"].id]
    assert me["can_propose"] and me["unit"] == "AES" and me["department"] == "IT"
    assert not client.get("/api/auth/me", headers=auth("staff")).json()["can_propose"]


# ------------------------------------------------------------------ cost allocation

def _setup_costs(client, auth, org, subscription, it_subscription):
    """Last month: Claude Team (BDT 10,800, 3 seats) held by staff (IT) + fin (Finance), 1 empty seat;
    IT's Copilot (BDT 1,200) held by staff."""
    start = subscription.start_date
    _assign(client, auth("dmd"), subscription, org["emps"]["staff"], start)
    _assign(client, auth("dmd"), subscription, org["emps"]["fin"], start)
    _assign(client, auth("dmd"), it_subscription, org["emps"]["staff"], start)


def test_unit_and_department_costs(client, auth, org, subscription, it_subscription, marketing_subscription):
    _setup_costs(client, auth, org, subscription, it_subscription)
    frm, to = _prev_month()
    units = client.get(f"/api/costs/units?from={frm}&to={to}", headers=auth("dmd")).json()
    aes = next(r for r in units["rows"] if r["code"] == "AES")
    assert Decimal(aes["amount_bdt"]) == Decimal("12000.00")
    assert Decimal(aes["shared_pool_bdt"]) == Decimal("3600.00")
    assert aes["seats_used"] == 3 and aes["seats_total"] == 4

    depts = client.get(f"/api/costs/units/{org['units']['aes'].id}/departments?from={frm}&to={to}",
                       headers=auth("dmd")).json()
    by = {r["name"]: r for r in depts["rows"]}
    assert Decimal(by["IT"]["direct_bdt"]) == Decimal("1200.00")
    assert Decimal(by["IT"]["allocated_bdt"]) == Decimal("3600.00")
    assert Decimal(by["IT"]["total_bdt"]) == Decimal("4800.00")
    assert Decimal(by["Finance"]["total_bdt"]) == Decimal("3600.00")
    assert Decimal(depts["shared_pool_bdt"]) == Decimal("3600.00")
    assert Decimal(depts["unit_total_bdt"]) == Decimal("12000.00")
    assert by["IT"]["budget_bdt"] is not None  # IT has a BDT 12,000 budget

    detail = client.get(f"/api/costs/departments/{org['depts']['it'].id}?from={frm}&to={to}",
                        headers=auth("mgr")).json()
    assert Decimal(detail["total_bdt"]) == Decimal("4800.00")
    staff_row = next(e for e in detail["employees"] if e["emp_code"] == "E1")
    assert Decimal(staff_row["cost_bdt"]) == Decimal("4800.00")
    assert {s["subscription_id"] for s in detail["subscriptions"]} == {subscription.id, it_subscription.id}
    assert len(detail["trend"]) == 12


def test_cost_visibility_by_role(client, auth, org, subscription):
    # unit head sees only his unit
    rows = client.get("/api/costs/units", headers=auth("mgr")).json()["rows"]
    assert [r["code"] for r in rows] == ["AES"]
    # ordinary staff and other-unit staff cannot see unit cost
    assert client.get("/api/costs/units", headers=auth("staff")).status_code == 403
    assert client.get(f"/api/costs/departments/{org['depts']['it'].id}", headers=auth("other")).status_code == 403
    assert client.get(f"/api/costs/units/{org['units']['bmd'].id}/departments",
                      headers=auth("mgr")).status_code == 403


def test_trend_series(client, auth, org, subscription):
    t = client.get("/api/costs/trend?group=unit&months=6", headers=auth("dmd")).json()
    assert len(t["months"]) == 6 and {s["name"] for s in t["series"]} == {"AES", "BMD"}
    t = client.get(f"/api/costs/trend?group=department&unit_id={org['units']['aes'].id}", headers=auth("dmd")).json()
    assert {s["name"] for s in t["series"]} == {"AES / IT", "AES / Finance"}


# ------------------------------------------------------------------ payments, anomaly, budget, savings

def test_charge_snapshot_payments_anomaly_and_budget(client, auth, org, subscription, it_subscription):
    # Copilot expects USD 10; USD 100 is an anomaly and pushes IT (budget 12,000) over budget this month
    r = client.post("/api/charges", headers=auth("delegate"), json={
        "subscription_id": it_subscription.id, "charge_date": today().isoformat(), "amount_original": "100",
        "fx_rate": "122"})
    assert r.status_code == 201
    charge = r.json()
    assert charge["unit_id"] == org["units"]["aes"].id and charge["department_id"] == org["depts"]["it"].id
    assert charge["anomaly"] and "+900%" in charge["anomaly_note"]
    assert [c["id"] for c in client.get("/api/charges?anomaly=true", headers=auth("dmd")).json()] == [charge["id"]]
    assert client.get(f"/api/charges?department_id={org['depts']['it'].id}", headers=auth("dmd")).json()

    # unit-wide subscription charge: unit snapshot only
    r = client.post("/api/charges", headers=auth("delegate"), json={
        "subscription_id": subscription.id, "charge_date": today().isoformat(), "amount_original": "90"})
    assert r.json()["department_id"] is None and not r.json()["anomaly"]

    pay = client.get("/api/costs/payments?group=department", headers=auth("dmd")).json()
    names = {row["name"]: Decimal(row["paid_bdt"]) for row in pay["rows"]}
    assert names["AES / IT"] == Decimal("12200.00") and "Unit-wide (shared)" in names

    # IT head got the IT over-budget alert, once (he also heads AES, whose own budget alert is separate)
    it_link = f"/costs/departments/{org['depts']['it'].id}"
    notes = client.get("/api/notifications", headers=auth("mgr")).json()["items"]
    assert sum(1 for n in notes if n["type"] == "budget.over" and n["link"] == it_link) == 1
    client.post("/api/charges", headers=auth("delegate"), json={
        "subscription_id": it_subscription.id, "charge_date": today().isoformat(), "amount_original": "10"})
    notes = client.get("/api/notifications", headers=auth("mgr")).json()["items"]
    assert sum(1 for n in notes if n["type"] == "budget.over" and n["link"] == it_link) == 1

    budgets = client.get("/api/costs/budgets", headers=auth("dmd")).json()
    assert any(d["name"] == "AES / IT" for d in budgets["departments"])


def test_savings_finder(client, auth, org, subscription):
    _assign(client, auth("dmd"), subscription, org["emps"]["staff"], today())
    s = client.get("/api/insights/savings", headers=auth("dmd")).json()
    empty = next(i for i in s["items"] if i["type"] == "empty_seats")
    assert Decimal(empty["monthly_saving_bdt"]) == Decimal("7320.00")  # 2 empty seats x USD 30 x 122
    assert Decimal(s["total_yearly_saving_bdt"]) == Decimal(s["total_monthly_saving_bdt"]) * 12
    # unit head gets his unit; staff cannot
    assert client.get("/api/insights/savings", headers=auth("mgr")).status_code == 200
    assert client.get("/api/insights/savings", headers=auth("staff")).status_code == 403


def test_reports_by_unit_and_department(client, auth, org, subscription, it_subscription):
    _setup_costs(client, auth, org, subscription, it_subscription)
    frm, to = _prev_month()
    units = client.get(f"/api/reports/cost-by-unit?from={frm}&to={to}", headers=auth("dmd")).json()["rows"]
    assert Decimal(next(r for r in units if r["unit"] == "AES")["accrued_bdt"]) == Decimal("12000.00")
    depts = client.get(f"/api/reports/cost-by-department?from={frm}&to={to}", headers=auth("dmd")).json()["rows"]
    pool = next(r for r in depts if r["unit"] == "AES" and r["department"].startswith("Shared pool"))
    assert Decimal(pool["total_bdt"]) == Decimal("3600.00")
    x = client.get(f"/api/reports/cost-by-department?from={frm}&to={to}&format=xlsx", headers=auth("dmd"))
    assert x.status_code == 200 and x.content[:2] == b"PK"


def test_employee_org_changes(client, auth, org):
    staff = org["emps"]["staff"]
    r = client.patch(f"/api/employees/{staff.id}", json={"department_id": org["depts"]["marketing"].id},
                     headers=auth("dmd"))
    assert r.status_code == 400 and "another unit" in r.json()["detail"]
    r = client.patch(f"/api/employees/{staff.id}", json={"unit_id": org["units"]["bmd"].id}, headers=auth("dmd"))
    assert r.status_code == 200 and r.json()["unit_code"] == "BMD" and r.json()["department_id"] is None


def test_units_and_departments_crud(client, auth, org):
    r = client.post("/api/units", json={"code": "agl", "name": "Anwar Galvanizing"}, headers=auth("dmd"))
    assert r.status_code == 201 and r.json()["code"] == "AGL"
    assert client.post("/api/units", json={"code": "AGL", "name": "dup"}, headers=auth("dmd")).status_code == 400
    uid = r.json()["id"]
    r = client.post("/api/departments", json={"unit_id": uid, "name": "Sales", "monthly_budget_bdt": "5000"},
                    headers=auth("delegate"))
    assert r.status_code == 201
    assert client.post("/api/departments", json={"unit_id": uid, "name": "Sales"},
                       headers=auth("delegate")).status_code == 400
    units = client.get("/api/units", headers=auth("staff")).json()
    assert next(u for u in units if u["code"] == "AGL")["departments"][0]["name"] == "Sales"
    assert client.post("/api/units", json={"code": "X", "name": "x"}, headers=auth("staff")).status_code == 403

"""SBU > department > function, function-owned and shared subscriptions, and how shared cost is split."""

from datetime import date, timedelta
from decimal import Decimal

from app.core.clock import today
from app.models import OrgFunction
from app.services import cost
from app.services.cost import SubInfo


def _function(db, org, dept="it", name="AI Analytics", head=None):
    fn = OrgFunction(department_id=org["depts"][dept].id, name=name, head_employee_id=head.id if head else None)
    db.add(fn)
    db.commit()
    return fn


def _sub_body(org, **owner):
    start = (today().replace(day=1) - timedelta(days=40)).isoformat()
    return {"vendor_id": org["claude"].id, "plan_name": "Team", "type": "team", "seats_total": 4,
            "cost_per_cycle": "40", "currency": "USD", "billing_cycle": "monthly", "start_date": start,
            "unit_id": org["units"]["aes"].id, "account_email": "buyer@gmail.com", **owner}


def test_function_crud_and_nesting(client, auth, db, org):
    headers = auth("dmd")
    r = client.post("/api/functions", headers=headers,
                    json={"department_id": org["depts"]["it"].id, "name": "AI Analytics",
                          "head_employee_id": org["emps"]["mgr"].id})
    assert r.status_code == 201, r.text
    fn = r.json()
    assert fn["unit_code"] == "AES" and fn["department_name"] == "IT" and fn["head_name"] == "Manager One"
    assert client.post("/api/functions", headers=headers,
                       json={"department_id": org["depts"]["it"].id, "name": "AI Analytics"}).status_code == 400

    units = client.get("/api/units", headers=headers).json()
    it = next(d for u in units for d in u["departments"] if d["name"] == "IT")
    assert [f["name"] for f in it["functions"]] == ["AI Analytics"]

    # employees: the function must be in their department
    staff = org["emps"]["staff"]
    assert client.patch(f"/api/employees/{staff.id}", headers=headers,
                        json={"function_id": fn["id"]}).json()["function_name"] == "AI Analytics"
    other = org["emps"]["other"]  # BMD / Marketing
    assert client.patch(f"/api/employees/{other.id}", headers=headers,
                        json={"function_id": fn["id"]}).status_code == 400
    assert client.get(f"/api/functions?department_id={org['depts']['it'].id}",
                      headers=headers).json()[0]["members"] == 1

    # a function with members cannot be deleted
    r = client.delete(f"/api/functions/{fn['id']}", headers=headers)
    assert r.status_code == 409 and "1 employee" in r.json()["detail"]


def test_function_owned_subscription(client, auth, db, org):
    fn = _function(db, org)
    org["emps"]["staff"].function_id = fn.id
    db.commit()
    r = client.post("/api/subscriptions", headers=auth("dmd"), json=_sub_body(org, owner_scope="function",
                                                                               function_id=fn.id))
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["department_id"] == org["depts"]["it"].id and sub["function_name"] == "AI Analytics"
    assert sub["owner_label"] == "AES / IT / AI Analytics" and sub["account_email"] == "buyer@gmail.com"

    mine = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth("staff")).json()}
    theirs = {s["subscription_id"] for s in
              client.get("/api/my/available-subscriptions", headers=auth("colleague")).json()}
    assert sub["id"] in mine and sub["id"] not in theirs  # same department, but not in the function


def test_shared_subscription_validation_and_access(client, auth, db, org):
    headers = auth("dmd")
    it, marketing = org["depts"]["it"].id, org["depts"]["marketing"].id
    one = _sub_body(org, owner_scope="shared", shares=[{"department_id": it}])
    assert client.post("/api/subscriptions", headers=headers, json=one).status_code == 422
    fn = _function(db, org)
    clash = _sub_body(org, owner_scope="shared",
                      shares=[{"department_id": it}, {"department_id": it, "function_id": fn.id}])
    assert client.post("/api/subscriptions", headers=headers, json=clash).status_code == 400

    body = _sub_body(org, owner_scope="shared", shares=[{"department_id": it}, {"department_id": marketing}])
    r = client.post("/api/subscriptions", headers=headers, json=body)
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["owner_label"] == "Shared: AES / IT, BMD / Marketing"
    assert {s["department_name"] for s in sub["shares"]} == {"IT", "Marketing"}

    # people of both sharers (even in another SBU) may request it; Finance may not
    for key, expected in (("staff", True), ("other", True), ("fin", False)):
        ids = {s["subscription_id"] for s in client.get("/api/my/available-subscriptions", headers=auth(key)).json()}
        assert (sub["id"] in ids) is expected, key

    r = client.patch(f"/api/subscriptions/{sub['id']}", headers=headers, json={"owner_scope": "department",
                                                                               "department_id": it})
    assert r.status_code == 200 and r.json()["shares"] == []


def test_shared_split_by_seats_used():
    sub = SubInfo(id=1, billing_cycle="monthly", start_date=date(2026, 1, 1), end_date=None,
                  cost_per_cycle=Decimal("40"), currency="BDT", seats_total=4, owner_scope="shared",
                  shares=[(10, None), (20, 7)])
    emp_dept = {1: 10, 2: 10, 3: 20, 4: 30}
    emp_func = {3: 7}
    # 4 seats at 10/day each: dept 10 holds two, function 7 one, employee 4 belongs to neither sharer
    parts = cost.shared_split(sub, Decimal("40"), [1, 2, 3, 4], emp_dept, emp_func)
    assert parts[(10, None)] == Decimal("25") and parts[(20, 7)] == Decimal("15")
    # nobody holds a seat: equal split
    parts = cost.shared_split(sub, Decimal("40"), [], emp_dept, emp_func)
    assert parts[(10, None)] == parts[(20, 7)] == Decimal("20")


def test_shared_cost_lands_in_each_sharers_sbu(client, auth, db, org):
    headers = auth("dmd")
    it, marketing = org["depts"]["it"].id, org["depts"]["marketing"].id
    sub = client.post("/api/subscriptions", headers=headers, json=_sub_body(
        org, owner_scope="shared", shares=[{"department_id": it}, {"department_id": marketing}])).json()
    client.post(f"/api/subscriptions/{sub['id']}/assignments", headers=headers,
                json={"employee_id": org["emps"]["staff"].id, "start_date": today().replace(day=1).isoformat()})

    units = {r["code"]: Decimal(r["amount_bdt"]) for r in client.get("/api/costs/units", headers=headers).json()["rows"]}
    assert units["AES"] > units["BMD"] > 0  # IT also pays the seat its member holds

    # the IT head (Manager One heads AES and IT) sees IT's part on the dashboard, not the whole subscription
    month = Decimal(client.get("/api/dashboard/summary", headers=auth("mgr")).json()["month"]["amount"])
    assert month == units["AES"]

    # the head's "spend by tool" bars add up to the same figure; a plain employee sees only their own seat
    tools = client.get("/api/dashboard/by-tool?period=month", headers=auth("mgr")).json()
    assert [t["name"] for t in tools] == ["Claude"]
    assert abs(sum(Decimal(t["amount"]) for t in tools) - month) <= Decimal("0.05")
    assert client.get("/api/dashboard/by-tool", headers=auth("colleague")).json() == []


def test_function_head_dashboard(client, auth, db, org):
    fn = _function(db, org, dept="finance", name="Payables", head=org["emps"]["fin"])
    r = client.post("/api/subscriptions", headers=auth("dmd"), json=_sub_body(org, owner_scope="function",
                                                                               function_id=fn.id))
    assert r.status_code == 201, r.text
    s = client.get("/api/dashboard/summary", headers=auth("fin")).json()
    assert Decimal(s["month"]["amount"]) > 0
    me = client.get("/api/auth/me", headers=auth("fin")).json()
    assert me["heads_function_ids"] == [fn.id] and me["can_propose"] is True

"""Safe delete: records without history are removed, anything with history is refused with a reason."""

from app.models import AuditLog, Department, Employee, OrgUnit, Subscription, Team, User, Vendor, VendorPlan


def _employee(db, org, code, manager=None, dept="it"):
    e = Employee(emp_code=code, name=f"Person {code}", designation="Staff", unit_id=org["units"]["aes"].id,
                 department_id=org["depts"][dept].id, manager_id=manager.id if manager else None,
                 email=f"{code.lower()}@test.local")
    db.add(e)
    db.commit()
    return e


def test_only_admins_can_delete(client, auth, db, org):
    emp = _employee(db, org, "N1")
    assert client.delete(f"/api/employees/{emp.id}", headers=auth("mgr")).status_code == 403


def test_employee_without_history_is_deleted_and_links_cleared(client, auth, db, org):
    boss = _employee(db, org, "N1")
    report = _employee(db, org, "N2", manager=boss)
    org["depts"]["finance"].head_employee_id = boss.id
    team = Team(unit_id=org["units"]["aes"].id, name="New team", lead_employee_id=boss.id)
    db.add_all([team, User(employee_id=boss.id, password_hash="x", roles="employee")])
    db.commit()
    boss_id = boss.id

    r = client.delete(f"/api/employees/{boss_id}", headers=auth("dmd"))
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(Employee, boss_id) is None
    assert db.query(User).filter_by(employee_id=boss_id).first() is None  # unused account went too
    assert db.get(Employee, report.id).manager_id is None
    assert db.get(Department, org["depts"]["finance"].id).head_employee_id is None
    assert db.get(Team, team.id).lead_employee_id is None
    assert db.query(AuditLog).filter_by(action="employee.delete", entity_id=boss_id).count() == 1


def test_employee_with_history_is_refused(client, auth, db, org, subscription):
    headers = auth("dmd")
    staff = org["emps"]["staff"]
    client.post(f"/api/subscriptions/{subscription.id}/assignments", json={"employee_id": staff.id}, headers=headers)
    r = client.delete(f"/api/employees/{staff.id}", headers=headers)
    assert r.status_code == 409
    assert "1 seat (current or past)" in r.json()["detail"] and "inactive" in r.json()["detail"]
    assert db.get(Employee, staff.id) is not None

    # an account that has signed in has audit history
    auth("other")
    r = client.delete(f"/api/employees/{org['emps']['other'].id}", headers=headers)
    assert r.status_code == 409 and "audit log record" in r.json()["detail"]


def test_account_guards(client, auth, org):
    assert client.delete(f"/api/users/{org['users']['dmd'].id}", headers=auth("dmd")).status_code == 400
    assert client.delete(f"/api/employees/{org['emps']['dmd'].id}", headers=auth("delegate")).status_code == 403


def test_unused_login_account_is_deleted_employee_stays(client, auth, db, org):
    emp = _employee(db, org, "N1")
    r = client.post("/api/users", headers=auth("dmd"), json={"employee_id": emp.id, "password": "Welcome#123"})
    uid = r.json()["id"]
    assert client.delete(f"/api/users/{uid}", headers=auth("dmd")).status_code == 204
    db.expire_all()
    assert db.get(User, uid) is None and db.get(Employee, emp.id) is not None


def test_departments_units_and_teams(client, auth, db, org):
    headers = auth("dmd")
    assert client.delete(f"/api/departments/{org['depts']['it'].id}", headers=headers).status_code == 409

    unit = OrgUnit(code="NEW", name="New unit")
    db.add(unit)
    db.flush()
    dept = Department(unit_id=unit.id, name="Empty")
    db.add(dept)
    db.flush()
    team = Team(unit_id=unit.id, name="T", department_id=dept.id)
    db.add(team)
    db.commit()
    ids = unit.id, dept.id, team.id

    assert client.delete(f"/api/units/{org['units']['aes'].id}", headers=headers).status_code == 409
    assert client.delete(f"/api/units/{ids[0]}", headers=headers).status_code == 204
    db.expire_all()
    assert db.get(OrgUnit, ids[0]) is None and db.get(Department, ids[1]) is None and db.get(Team, ids[2]) is None


def test_team_with_subscriptions_is_refused(client, auth, db, org, subscription):
    team = Team(unit_id=org["units"]["aes"].id, name="Owners")
    db.add(team)
    db.flush()
    subscription.team_id = team.id
    db.commit()
    r = client.delete(f"/api/teams/{team.id}", headers=auth("dmd"))
    assert r.status_code == 409 and "1 subscription" in r.json()["detail"]


def test_vendors_cards_subscriptions(client, auth, db, org, subscription):
    headers = auth("dmd")
    # Claude has a subscription; Copilot is unused
    assert client.delete(f"/api/vendors/{org['claude'].id}", headers=headers).status_code == 409
    copilot = org["copilot"].id
    assert client.delete(f"/api/vendors/{copilot}", headers=headers).status_code == 204
    db.expire_all()
    assert db.get(Vendor, copilot) is None

    # the card pays a subscription
    assert client.delete(f"/api/cards/{org['card'].id}", headers=headers).status_code == 409
    r = client.post("/api/cards", headers=headers, json={"label": "Spare", "holder_name": "DMD Sir", "last4": "0001"})
    assert client.delete(f"/api/cards/{r.json()['id']}", headers=headers).status_code == 204

    # the fixture subscription has a card charge; a fresh one is deleted
    r = client.delete(f"/api/subscriptions/{subscription.id}", headers=headers)
    assert r.status_code == 409 and "Cancel it instead" in r.json()["detail"]
    fresh = Subscription(vendor_id=org["chatgpt"].id, plan_name="Plus", type="individual", seats_total=1,
                         cost_per_cycle=20, currency="USD", billing_cycle="monthly", start_date=subscription.start_date,
                         owner_scope="unit", unit_id=org["units"]["bmd"].id)
    db.add(fresh)
    db.commit()
    assert client.delete(f"/api/subscriptions/{fresh.id}", headers=headers).status_code == 204
    assert db.query(VendorPlan).filter_by(vendor_id=copilot).count() == 0

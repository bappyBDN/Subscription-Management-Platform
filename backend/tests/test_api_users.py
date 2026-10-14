"""Creating accounts and resetting passwords, with the sign-in details emailed to the employee."""

from app.models import Employee
from app.services import mailer


def _new_employee(db, org, email="new1@test.local"):
    e = Employee(emp_code="N1", name="New Joiner", designation="Staff", unit_id=org["units"]["aes"].id,
                 department_id=org["depts"]["it"].id, email=email)
    db.add(e)
    db.commit()
    return e


def test_create_account_emails_password_and_user_can_sign_in_and_change_it(client, db, org, auth):
    emp = _new_employee(db, org)
    r = client.post("/api/users", headers=auth("dmd"), json={"employee_id": emp.id, "password": "Welcome#123"})
    assert r.status_code == 201, r.text

    mail = mailer.OUTBOX[-1]
    assert mail["to"] == "new1@test.local"
    assert "Password: Welcome#123" in mail["body"] and "Username: N1" in mail["body"]

    r = client.post("/api/auth/login", json={"username": "N1", "password": "Welcome#123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/auth/change-password", headers=headers,
                    json={"current_password": "Welcome#123", "new_password": "MyOwn#4567"})
    assert r.status_code == 204, r.text
    assert client.post("/api/auth/login", json={"username": "N1", "password": "MyOwn#4567"}).status_code == 200


def test_create_account_without_email(client, db, org, auth):
    emp = _new_employee(db, org, email=None)
    body, headers = {"employee_id": emp.id, "password": "Welcome#123"}, auth("dmd")
    assert client.post("/api/users", headers=headers, json=body).status_code == 400
    sent = len(mailer.OUTBOX)
    r = client.post("/api/users", headers=headers, json={**body, "send_email": False})
    assert r.status_code == 201, r.text
    assert len(mailer.OUTBOX) == sent


def test_password_reset_emails_only_when_asked(client, org, auth):
    uid, headers = org["users"]["staff"].id, auth("dmd")
    sent = len(mailer.OUTBOX)
    r = client.patch(f"/api/users/{uid}", headers=headers, json={"password": "Reset#0001"})
    assert r.status_code == 200, r.text
    assert len(mailer.OUTBOX) == sent

    r = client.patch(f"/api/users/{uid}", headers=headers, json={"password": "Reset#0002", "send_email": True})
    assert r.status_code == 200, r.text
    mail = mailer.OUTBOX[-1]
    assert mail["to"] == "e1@test.local" and "Password: Reset#0002" in mail["body"]
    assert client.post("/api/auth/login", json={"username": "E1", "password": "Reset#0002"}).status_code == 200

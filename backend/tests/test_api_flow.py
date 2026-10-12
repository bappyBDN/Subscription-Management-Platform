"""End-to-end API tests: request -> manager -> DMD Sir -> handover (3 methods) -> receipt."""

from datetime import date, datetime, timedelta

from app.core.clock import today
from tests.conftest import last_otp

REASON = "I review supplier contracts daily and need Claude to summarise them."


def new_request(client, headers, sub, **extra):
    """v2: a seat request always names a subscription the requester's unit/department owns."""
    body = {"subscription_id": sub.id, "needed_from": today().isoformat(), "reason": REASON, "duration_months": 6}
    body.update(extra)
    r = client.post("/api/requests", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_login_requires_otp_for_dmd_but_not_staff(client, org):
    r = client.post("/api/auth/login", json={"username": "E1", "password": "Secret#2026"})
    assert r.json()["access_token"] and not r.json()["otp_required"]
    r = client.post("/api/auth/login", json={"username": "dmd1@test.local", "password": "Secret#2026"})
    assert r.json()["otp_required"] and r.json()["access_token"] is None
    bad = client.post("/api/auth/verify-otp", json={"otp_token": r.json()["otp_token"], "code": "000000"})
    assert bad.status_code == 401


def test_lockout_after_five_failures(client, org):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "E1", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "E1", "password": "Secret#2026"}).status_code == 423


def test_me_shows_manager_and_roles(client, auth):
    me = client.get("/api/auth/me", headers=auth("staff")).json()
    assert me["manager"]["name"] == "Manager One"
    assert me["roles"] == ["employee"] and not me["is_manager"]
    assert client.get("/api/auth/me", headers=auth("mgr")).json()["is_manager"]


def test_request_snapshot_number_and_estimate(client, auth, org, subscription):
    req = new_request(client, auth("staff"), subscription)
    assert req["req_no"].startswith(f"SMP-{today().year}-")
    assert req["status"] == "pending_manager"
    assert req["snapshot"]["emp_code"] == "E1" and req["snapshot"]["manager_name"] == "Manager One"
    assert req["snapshot"]["unit"] == "AES" and req["snapshot"]["department"] == "IT"
    assert req["plan_name"] == "Team" and req["tool_name"] == "Claude"
    assert req["unit_id"] == org["units"]["aes"].id and req["owner_scope"] == "unit"
    # one seat of a 3-seat USD 90 subscription, at the default FX setting of 122
    assert float(req["est_cost_original"]) == 30.0
    assert float(req["est_cost_bdt"]) == 30 * 122.0


def test_reason_too_short_and_card_number_rejected(client, auth, org, subscription):
    r = client.post("/api/requests", headers=auth("staff"), json={
        "subscription_id": subscription.id, "needed_from": today().isoformat(), "reason": "need it"})
    assert r.status_code == 422
    r = client.post("/api/requests", headers=auth("staff"), json={
        "subscription_id": subscription.id, "needed_from": today().isoformat(),
        "reason": REASON + " pay with 4111 1111 1111 1111"})
    assert r.status_code == 422


def test_employee_without_manager_goes_straight_to_dmd(client, auth, org, db, marketing_subscription):
    org["emps"]["other"].manager_id = None
    db.commit()
    assert new_request(client, auth("other"), marketing_subscription)["status"] == "pending_dmd"


def test_full_flow_vault_handover(client, auth, org, subscription):
    req = new_request(client, auth("staff"), subscription)
    rid = req["id"]

    # other people cannot see it; manager can
    assert client.get(f"/api/requests/{rid}", headers=auth("other")).status_code == 403
    pending = client.get("/api/requests?scope=pending", headers=auth("mgr")).json()
    assert [p["id"] for p in pending] == [rid]

    # manager cannot approve, only recommend
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"}, headers=auth("mgr"))
    assert r.status_code == 400
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend", "comment": "ok"}, headers=auth("mgr"))
    assert r.json()["status"] == "pending_dmd"

    # delegate cannot approve
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"}, headers=auth("delegate"))
    assert r.status_code == 403

    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"}, headers=auth("dmd"))
    assert r.json()["status"] == "approved"
    assert [a["step"] for a in r.json()["approvals"]] == ["manager", "dmd"]

    # handover via vault on the existing team subscription
    r = client.post(f"/api/requests/{rid}/handover", headers=auth("delegate"), json={
        "method": "vault", "subscription_id": subscription.id, "secret": "S3cret!pw",
        "login_email": "ai-team@test.local", "login_url": "https://claude.ai"})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "handover_pending"
    hid = detail["handover"]["id"]
    assert detail["handover"]["has_secret"] and "secret" not in detail["handover"]

    # reveal needs an OTP; other employees cannot reveal
    assert client.post(f"/api/handovers/{hid}/reveal-otp", headers=auth("other")).status_code == 403
    assert client.post(f"/api/handovers/{hid}/reveal-otp", headers=auth("staff")).status_code == 204
    r = client.post(f"/api/handovers/{hid}/reveal", json={"code": "123456"}, headers=auth("staff"))
    if r.status_code != 401:  # the random code could coincide; then just continue
        assert r.status_code == 200
    client.post(f"/api/handovers/{hid}/reveal-otp", headers=auth("staff"))
    r = client.post(f"/api/handovers/{hid}/reveal", json={"code": last_otp("e1@test.local")}, headers=auth("staff"))
    assert r.status_code == 200 and r.json()["secret"] == "S3cret!pw"
    assert r.headers["cache-control"] == "no-store"

    # delegate without permission cannot reveal
    assert client.post(f"/api/handovers/{hid}/reveal-otp", headers=auth("delegate")).status_code == 403

    r = client.post(f"/api/handovers/{hid}/received", headers=auth("staff"))
    assert r.json()["status"] == "active"
    mine = client.get("/api/my/subscriptions", headers=auth("staff")).json()
    assert mine["active"][0]["subscription_id"] == subscription.id
    assert mine["active"][0]["end_date"]  # 6-month duration

    logs = client.get("/api/audit-logs?action=vault.reveal", headers=auth("dmd")).json()
    assert len(logs) == 1 and logs[0]["entity_id"] == hid


def test_appointment_handover(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription)["id"]
    client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend"}, headers=auth("mgr"))
    client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"}, headers=auth("dmd"))
    r = client.post(f"/api/requests/{rid}/handover", headers=auth("dmd"),
                    json={"method": "appointment", "subscription_id": subscription.id, "location": "DMD office"})
    hid = r.json()["handover"]["id"]
    slot = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    r = client.post(f"/api/handovers/{hid}/propose-slot", json={"at": slot}, headers=auth("staff"))
    assert r.status_code == 200 and r.json()["proposed_at"]
    assert client.post(f"/api/handovers/{hid}/confirm-slot", json={"at": slot}, headers=auth("staff")).status_code == 403
    r = client.post(f"/api/handovers/{hid}/confirm-slot", json={"at": slot, "location": "Level 5"}, headers=auth("dmd"))
    assert r.json()["confirmed_at"] and r.json()["location"] == "Level 5"
    assert client.post(f"/api/handovers/{hid}/received", headers=auth("staff")).json()["status"] == "active"


def test_colleague_handover(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription)["id"]
    client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend"}, headers=auth("mgr"))
    client.post(f"/api/requests/{rid}/decision", json={"decision": "approve"}, headers=auth("dmd"))
    r = client.post(f"/api/requests/{rid}/handover", headers=auth("dmd"), json={
        "method": "colleague", "subscription_id": subscription.id, "collector_id": org["emps"]["colleague"].id,
        "collector_note": "Collect from Rahim vai after lunch"})
    assert r.json()["handover"]["collector_name"] == "Rahim Vai"
    hid = r.json()["handover"]["id"]
    tasks = client.get("/api/my/handover-tasks", headers=auth("colleague")).json()
    assert tasks[0]["handover_id"] == hid
    # the collector can see the request but cannot reveal anything
    assert client.get(f"/api/requests/{rid}", headers=auth("colleague")).status_code == 200
    assert client.post(f"/api/handovers/{hid}/handed-over", headers=auth("other")).status_code == 403
    assert client.post(f"/api/handovers/{hid}/handed-over", headers=auth("colleague")).json()["handed_over_at"]
    assert client.post(f"/api/handovers/{hid}/received", headers=auth("colleague")).status_code == 403
    assert client.post(f"/api/handovers/{hid}/received", headers=auth("staff")).json()["status"] == "active"


def test_info_needed_edit_and_resubmit(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription)["id"]
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "info"}, headers=auth("mgr"))
    assert r.status_code == 400  # comment required
    client.post(f"/api/requests/{rid}/decision", json={"decision": "info", "comment": "Which project?"}, headers=auth("mgr"))
    r = client.patch(f"/api/requests/{rid}", json={"expected_use": "Project Alpha contracts"}, headers=auth("staff"))
    assert r.status_code == 200
    r = client.post(f"/api/requests/{rid}/resubmit", headers=auth("staff"))
    assert r.json()["status"] == "pending_manager"


def test_hold_resume_reject_and_withdraw(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription)["id"]
    client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend"}, headers=auth("mgr"))
    assert client.post(f"/api/requests/{rid}/decision", json={"decision": "hold"}, headers=auth("dmd")).json()["status"] == "on_hold"
    assert client.post(f"/api/requests/{rid}/decision", json={"decision": "resume"}, headers=auth("dmd")).json()["status"] == "pending_dmd"
    assert client.post(f"/api/requests/{rid}/decision", json={"decision": "reject", "comment": "Use the team seat"},
                       headers=auth("dmd")).json()["status"] == "rejected"
    rid2 = new_request(client, auth("staff"), subscription)["id"]
    assert client.post(f"/api/requests/{rid2}/withdraw", headers=auth("mgr")).status_code == 403
    assert client.post(f"/api/requests/{rid2}/withdraw", headers=auth("staff")).json()["status"] == "withdrawn"


def test_urgent_override_and_bulk_approve(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription)["id"]
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "override", "comment": "client demo today"},
                    headers=auth("dmd"))
    assert r.json()["status"] == "approved"
    ids = [new_request(client, auth("staff"), subscription)["id"] for _ in range(2)]
    client.post(f"/api/requests/{ids[0]}/decision", json={"decision": "recommend"}, headers=auth("mgr"))
    result = client.post("/api/requests/bulk-approve", json={"request_ids": ids}, headers=auth("dmd")).json()
    assert result["approved"] == [ids[0]] and result["failed"][0]["id"] == ids[1]


def test_dmd_can_adjust_plan_before_approving(client, auth, org, subscription):
    rid = new_request(client, auth("staff"), subscription, seats=2)["id"]
    client.post(f"/api/requests/{rid}/decision", json={"decision": "recommend"}, headers=auth("mgr"))
    r = client.post(f"/api/requests/{rid}/decision", json={"decision": "approve", "seats": 1, "duration_months": 3},
                    headers=auth("dmd"))
    assert r.json()["seats"] == 1 and r.json()["duration_months"] == 3


def test_no_free_seat_blocks_handover(client, auth, org, db, subscription):
    subscription.seats_total = 1
    db.commit()
    client.post(f"/api/subscriptions/{subscription.id}/assignments", json={"employee_id": org["emps"]["mgr"].id},
                headers=auth("dmd"))
    rid = new_request(client, auth("staff"), subscription)["id"]
    client.post(f"/api/requests/{rid}/decision", json={"decision": "override", "comment": "urgent"}, headers=auth("dmd"))
    r = client.post(f"/api/requests/{rid}/handover", headers=auth("dmd"),
                    json={"method": "vault", "subscription_id": subscription.id, "secret": "x"})
    assert r.status_code == 400 and "seat" in r.json()["detail"]


def test_inactive_employee_marks_seats_for_review(client, auth, org, subscription):
    client.post(f"/api/subscriptions/{subscription.id}/assignments", json={"employee_id": org["emps"]["staff"].id},
                headers=auth("dmd"))
    r = client.patch(f"/api/employees/{org['emps']['staff'].id}", json={"status": "inactive"}, headers=auth("delegate"))
    assert r.status_code == 200
    detail = client.get(f"/api/subscriptions/{subscription.id}", headers=auth("dmd")).json()
    assert detail["assignments"][0]["status"] == "revoke_pending"
    # the inactive employee can no longer use the API
    assert client.post("/api/auth/login", json={"username": "E1", "password": "Secret#2026"}).status_code == 401


def test_employee_cannot_touch_admin_endpoints(client, auth):
    for path in ("/api/subscriptions", "/api/charges", "/api/cards", "/api/audit-logs", "/api/reports/register"):
        assert client.get(path, headers=auth("staff")).status_code == 403, path

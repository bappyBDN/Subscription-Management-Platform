from app.models import Assignment, Handover, Subscription, SubscriptionRequest, User
from app.services.requests_service import allowed_actions, waiting_days


def subscription_out(sub: Subscription) -> dict:
    return {
        "id": sub.id,
        "vendor_id": sub.vendor_id,
        "vendor_name": sub.vendor.name,
        "plan_name": sub.plan_name,
        "type": sub.type,
        "seats_total": sub.seats_total,
        "seats_used": sub.seats_used,
        "cost_per_cycle": sub.cost_per_cycle,
        "currency": sub.currency,
        "billing_cycle": sub.billing_cycle,
        "start_date": sub.start_date,
        "next_renewal_date": sub.next_renewal_date,
        "card_id": sub.card_id,
        "card_last4": sub.card.last4 if sub.card else None,
        "account_email": sub.account_email,
        "owner_scope": sub.owner_scope,
        "unit_id": sub.unit_id,
        "unit_code": sub.unit_code,
        "department_id": sub.department_id,
        "department_name": sub.department_name,
        "owner_label": sub.owner_label,
        "status": sub.status,
        "cancelled_on": sub.cancelled_on,
        "notes": sub.notes,
    }


def assignment_out(a: Assignment) -> dict:
    return {
        "id": a.id,
        "subscription_id": a.subscription_id,
        "employee_id": a.employee_id,
        "employee_name": a.employee.name if a.employee else None,
        "emp_code": a.employee.emp_code if a.employee else None,
        "request_id": a.request_id,
        "start_date": a.start_date,
        "end_date": a.end_date,
        "status": a.status,
    }


def subscription_detail(sub: Subscription) -> dict:
    data = subscription_out(sub)
    data["assignments"] = [assignment_out(a) for a in sub.assignments]
    return data


def handover_out(h: Handover | None) -> dict | None:
    if h is None:
        return None
    return {
        "id": h.id,
        "method": h.method,
        "has_secret": h.has_secret,
        "login_email": h.login_email,
        "login_url": h.login_url,
        "notes": h.notes,
        "proposed_at": h.proposed_at,
        "confirmed_at": h.confirmed_at,
        "location": h.location,
        "collector_id": h.collector_id,
        "collector_name": h.collector.name if h.collector else None,
        "collector_note": h.collector_note,
        "due_date": h.due_date,
        "handed_over_at": h.handed_over_at,
        "received_at": h.received_at,
    }


def request_out(req: SubscriptionRequest) -> dict:
    return {
        "id": req.id,
        "req_no": req.req_no,
        "employee_id": req.employee_id,
        "snapshot": req.snapshot,
        "type": req.type,
        "vendor_id": req.vendor_id,
        "tool_name": req.tool_name,
        "other_tool_url": req.other_tool_url,
        "plan_name": req.plan_name,
        "seats": req.seats,
        "duration_months": req.duration_months,
        "needed_from": req.needed_from,
        "reason": req.reason,
        "expected_use": req.expected_use,
        "est_cost_bdt": req.est_cost_bdt,
        "est_cost_original": req.est_cost_original,
        "est_currency": req.est_currency,
        "est_billing_cycle": req.est_billing_cycle,
        "owner_scope": req.owner_scope,
        "unit_id": req.unit_id,
        "department_id": req.department_id,
        "status": req.status,
        "subscription_id": req.subscription_id,
        "submitted_at": req.submitted_at,
        "status_changed_at": req.status_changed_at,
        "waiting_days": waiting_days(req),
    }


def request_detail(req: SubscriptionRequest, user: User) -> dict:
    data = request_out(req)
    data["approvals"] = [
        {
            "id": a.id,
            "step": a.step,
            "approver_id": a.approver_id,
            "approver_name": a.approver.employee.name if a.approver else None,
            "decision": a.decision,
            "comment": a.comment,
            "from_status": a.from_status,
            "to_status": a.to_status,
            "created_at": a.created_at,
        }
        for a in req.approvals
    ]
    data["handover"] = handover_out(req.handover)
    data["allowed_actions"] = allowed_actions(user, req)
    return data

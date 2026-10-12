"""Business logic for requests, approvals and handovers."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.clock import to_naive_utc, today, utcnow
from app.core.config import get_settings
from app.enums import AssignmentStatus, HandoverMethod, OwnerScope, RequestStatus, RequestType, SubscriptionStatus
from app.models import (
    Approval,
    Assignment,
    Department,
    Employee,
    Handover,
    OrgUnit,
    Subscription,
    SubscriptionRequest,
    User,
    Vendor,
    VendorPlan,
)
from app.schemas.requests import DecisionIn, HandoverIn, RequestIn, RequestUpdate
from app.services import audit, settings_store, workflow
from app.services.cost import add_months, estimate_request_cost
from app.services.notify import admins, dmd_users, notify
from app.services.workflow import WorkflowError

S = RequestStatus


class ServiceError(Exception):
    """Business rule violation -> HTTP 400."""


class AccessError(Exception):
    """Not allowed -> HTTP 403."""


# ---------------------------------------------------------------- helpers

def _user_of(db: Session, employee_id: int | None) -> User | None:
    if employee_id is None:
        return None
    return db.query(User).filter(User.employee_id == employee_id).first()


def actors_for(user: User, req: SubscriptionRequest) -> set[str]:
    actors: set[str] = set()
    if req.employee_id == user.employee_id:
        actors.add("requester")
    if req.employee.manager_id == user.employee_id:
        actors.add("manager")
    if user.is_dmd:
        actors.add("dmd")
    if user.is_admin:
        actors.add("admin")
    return actors


def can_view(user: User, req: SubscriptionRequest) -> bool:
    if actors_for(user, req):
        return True
    h = req.handover
    return bool(h and h.collector_id == user.employee_id)


def allowed_actions(user: User, req: SubscriptionRequest) -> list[str]:
    actors = actors_for(user, req)
    actions = []
    is_proposal = req.type == RequestType.PROPOSAL
    for action, t in workflow.TRANSITIONS.get(S(req.status), {}).items():
        if action in ("auto_activate", "auto_end"):
            continue
        if (action == "fulfil") != is_proposal and action in ("fulfil", "set_handover"):
            continue
        if t.actors & actors:
            actions.append(action)
    return actions


def snapshot_of(employee: Employee) -> dict:
    mgr = employee.manager
    return {
        "name": employee.name,
        "emp_code": employee.emp_code,
        "designation": employee.designation,
        "unit_id": employee.unit_id,
        "unit": employee.unit_code,
        "department_id": employee.department_id,
        "department": employee.department_name,
        "team": employee.team,
        "email": employee.email,
        "phone": employee.phone,
        "manager_id": mgr.id if mgr else None,
        "manager_name": mgr.name if mgr else None,
        "manager_code": mgr.emp_code if mgr else None,
    }


def next_req_no(db: Session) -> str:
    year = today().year
    prefix = f"SMP-{year}-"
    last = (
        db.query(func.max(SubscriptionRequest.req_no))
        .filter(SubscriptionRequest.req_no.like(f"{prefix}%"))
        .scalar()
    )
    n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{n:04d}"


def _link(req: SubscriptionRequest) -> str:
    return f"/requests/{req.id}"


def _tool(db: Session, req: SubscriptionRequest) -> str:
    return f"{req.tool_name} {req.plan_name}".strip()


# ---------------------------------------------------------------- estimate

def estimate(
    db: Session,
    vendor_id: int | None,
    plan_name: str | None,
    seats: int,
    est_cost_per_cycle: Decimal | None = None,
    est_currency: str | None = None,
    est_billing_cycle: str | None = None,
    subscription_id: int | None = None,
) -> dict:
    fx = settings_store.fx_rates(settings_store.get_all(db))
    source = "unknown"
    cost = currency = cycle = None
    if est_cost_per_cycle is not None:
        cost, currency, cycle, source = est_cost_per_cycle, est_currency or "USD", est_billing_cycle or "monthly", "provided"
    elif subscription_id and (sub := db.get(Subscription, subscription_id)):
        per_seat = Decimal(sub.cost_per_cycle) / max(sub.seats_total, 1)
        cost, currency, cycle, source = per_seat, sub.currency, sub.billing_cycle, "subscription"
    elif vendor_id and plan_name:
        plan = (
            db.query(VendorPlan)
            .filter(VendorPlan.vendor_id == vendor_id, func.lower(VendorPlan.plan_name) == plan_name.lower())
            .first()
        )
        if plan:
            cost, currency, cycle, source = plan.default_cost, plan.currency, plan.billing_cycle, "catalogue"
    if cost is None:
        return {
            "currency": "USD", "monthly_original": Decimal("0"), "yearly_original": Decimal("0"),
            "monthly_bdt": Decimal("0"), "yearly_bdt": Decimal("0"), "fx_rate": fx["USD"],
            "billing_cycle": None, "source": "unknown",
        }
    result = estimate_request_cost(Decimal(cost), currency, cycle, seats, fx)
    result.update(billing_cycle=cycle, source=source)
    return result


def _apply_estimate(db: Session, req: SubscriptionRequest, data: RequestIn | RequestUpdate | None = None) -> None:
    """Store the monthly cost estimate on the request (BDT + original currency).

    Priority: cost typed by the requester > existing subscription > catalogue plan > earlier typed cost.
    The per-seat unit cost is kept so a later change of seats or plan re-prices correctly.
    """
    typed = getattr(data, "est_cost_per_cycle", None) if data is not None else None
    use_sub = req.subscription_id if req.type != RequestType.PROPOSAL else None
    if typed is not None:
        unit = typed
        currency = getattr(data, "est_currency", None) or req.est_currency or "USD"
        cycle = getattr(data, "est_billing_cycle", None) or req.est_billing_cycle or "monthly"
        est = estimate(db, None, None, req.seats, unit, currency, cycle)
    else:
        est = estimate(db, req.vendor_id, req.plan_name, req.seats, subscription_id=use_sub)
        if est["source"] == "unknown" and req.est_unit_cost is not None:
            est = estimate(db, None, None, req.seats, req.est_unit_cost, req.est_currency, req.est_billing_cycle)
            est["source"] = "provided"
        unit = None
    if est["source"] == "unknown":
        req.est_unit_cost = req.est_cost_bdt = req.est_cost_original = req.est_currency = req.est_billing_cycle = None
        return
    if unit is None:  # derive the per-seat cycle cost back from the monthly figure
        per_month = Decimal(est["monthly_original"]) / max(req.seats, 1)
        unit = per_month * 12 if est["billing_cycle"] == "yearly" else per_month
    req.est_unit_cost = unit
    req.est_cost_bdt = est["monthly_bdt"]
    req.est_cost_original = est["monthly_original"]
    req.est_currency = est["currency"]
    req.est_billing_cycle = est["billing_cycle"]


# ---------------------------------------------------------------- create / edit

def can_propose(db: Session, user: User) -> bool:
    """Department heads, unit heads, reporting managers (and admins) may propose a new tool."""
    emp = user.employee
    if user.is_admin:
        return True
    if db.query(Employee.id).filter(Employee.manager_id == emp.id).first():
        return True
    if db.query(Department.id).filter(Department.head_employee_id == emp.id).first():
        return True
    return db.query(OrgUnit.id).filter(OrgUnit.head_employee_id == emp.id).first() is not None


def is_unit_head(db: Session, user: User, unit_id: int) -> bool:
    unit = db.get(OrgUnit, unit_id)
    return bool(unit and unit.head_employee_id == user.employee_id)


def available_subscriptions(db: Session, employee: Employee) -> list[Subscription]:
    """v2 access rule: active unit-wide subscriptions of the employee's unit + those of their own department."""
    query = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE,
                                          Subscription.unit_id == employee.unit_id)
    return [s for s in query.order_by(Subscription.id).all() if s.available_to(employee)]


def create_request(db: Session, user: User, data: RequestIn, ip: str | None) -> SubscriptionRequest:
    employee = user.employee
    sub = None
    if data.type == RequestType.PROPOSAL:
        if not can_propose(db, user):
            raise AccessError("Only a department head, unit head or reporting manager can propose a new tool")
        if data.vendor_id and not db.get(Vendor, data.vendor_id):
            raise ServiceError("Unknown tool")
        if data.owner_scope == OwnerScope.DEPARTMENT and not employee.department_id:
            raise ServiceError("You are not linked to a department — propose it for the unit or ask admin to set your department")
        if data.owner_scope == OwnerScope.UNIT and not (user.is_admin or is_unit_head(db, user, employee.unit_id)):
            raise AccessError("Only the unit head can propose a unit-wide tool; propose it for your department instead")
        if data.vendor_id:
            existing = [s for s in available_subscriptions(db, employee) if s.vendor_id == data.vendor_id]
            if existing:
                raise ServiceError(
                    f"Your unit/department already has {existing[0].vendor.name} {existing[0].plan_name} "
                    f"(subscription #{existing[0].id}) — request a seat on it instead")
        plan_name, vendor_id, owner_scope = data.plan_name, data.vendor_id, data.owner_scope
    else:
        sub = db.get(Subscription, data.subscription_id)
        if not sub or sub.status != SubscriptionStatus.ACTIVE:
            raise ServiceError("That subscription is not active")
        if not sub.available_to(employee):
            raise AccessError(
                f"{sub.vendor.name} {sub.plan_name} belongs to {sub.owner_label}. You can only request "
                "subscriptions of your own unit or department — ask your head to raise a proposal")
        holds = any(a.employee_id == employee.id and a.status != AssignmentStatus.REVOKED for a in sub.assignments)
        if data.type == RequestType.NEW and holds:
            raise ServiceError("You already have a seat on this subscription")
        if data.type in (RequestType.RENEWAL, RequestType.CANCEL, RequestType.UPGRADE) and not holds:
            raise ServiceError(f"You can only {data.type} a subscription you currently hold")
        plan_name, vendor_id, owner_scope = data.plan_name or sub.plan_name, sub.vendor_id, sub.owner_scope

    now = utcnow()
    status = workflow.initial_status(employee.manager_id is not None)
    req = SubscriptionRequest(
        req_no=next_req_no(db),
        employee_id=employee.id,
        snapshot=snapshot_of(employee),
        type=data.type,
        vendor_id=vendor_id,
        other_tool_name=None if vendor_id else data.other_tool_name,
        other_tool_url=data.other_tool_url,
        plan_name=plan_name,
        seats=data.seats,
        duration_months=data.duration_months,
        needed_from=data.needed_from,
        reason=data.reason,
        expected_use=data.expected_use,
        subscription_id=sub.id if sub else None,
        unit_id=employee.unit_id,
        department_id=employee.department_id,
        owner_scope=owner_scope,
        status=status,
        submitted_at=now,
        status_changed_at=now,
    )
    db.add(req)
    db.flush()
    db.refresh(req)
    _apply_estimate(db, req, data)
    audit.log(db, user, "request.create", "request", req.id,
              after={"req_no": req.req_no, "status": status, "type": req.type, "subscription_id": req.subscription_id},
              ip=ip)

    what = f"proposes a new tool: {_tool(db, req)}" if req.type == RequestType.PROPOSAL else f"requests {_tool(db, req)}"
    note = "" if sub is None or sub.seats_free > 0 else " (no free seat — a seat must be added)"
    target = [_user_of(db, employee.manager_id)] if status == S.PENDING_MANAGER else dmd_users(db)
    notify(db, target, "request.submitted", f"{req.req_no}: {employee.name} {what}{note}", req.reason, _link(req))
    db.flush()
    return req


def update_request(db: Session, user: User, req: SubscriptionRequest, data: RequestUpdate, ip: str | None) -> SubscriptionRequest:
    if req.employee_id != user.employee_id:
        raise AccessError("Only the requester can edit this request")
    if req.status != S.INFO_NEEDED:
        raise ServiceError("A request can only be edited while more information is needed")
    changes = data.model_dump(exclude_unset=True, exclude={"est_cost_per_cycle", "est_currency", "est_billing_cycle"})
    required = {"plan_name", "seats", "needed_from", "reason"}
    if any(changes.get(k, "") is None for k in required):
        raise ServiceError("Plan, seats, needed-from date and reason cannot be empty")
    if req.type != RequestType.PROPOSAL and {"vendor_id", "other_tool_name", "other_tool_url"} & set(changes):
        raise ServiceError("The tool of a seat request cannot be changed — withdraw it and request another subscription")
    if changes.get("vendor_id") and not db.get(Vendor, changes["vendor_id"]):
        raise ServiceError("Unknown tool")
    if changes.get("duration_months") not in (None, 1, 3, 6, 12):
        raise ServiceError("duration_months must be 1, 3, 6, 12 or empty")
    before = audit.snapshot(req, list(changes))
    for key, value in changes.items():
        setattr(req, key, value)
    _apply_estimate(db, req, data)
    audit.log(db, user, "request.update", "request", req.id, before=before, after=changes, ip=ip)
    db.flush()
    return req


# ---------------------------------------------------------------- transitions

def _move(db: Session, user: User, req: SubscriptionRequest, action: str, comment: str | None,
          ip: str | None, record_step: str | None = None, force_to: str | None = None) -> str:
    actors = actors_for(user, req)
    if action in ("auto_activate", "auto_end"):
        actors = actors | {"system"}
    try:
        new_status = workflow.transition(req.status, action, actors, comment)
    except WorkflowError as exc:
        raise ServiceError(str(exc)) from exc
    new_status = force_to or new_status
    old = req.status
    req.status = new_status
    req.status_changed_at = utcnow()
    if record_step:
        req.approvals.append(Approval(step=record_step, approver_id=user.id, decision=action,
                                      comment=comment, from_status=old, to_status=new_status))
    audit.log(db, user, f"request.{action}", "request", req.id,
              before={"status": old}, after={"status": new_status, "comment": comment}, ip=ip)
    db.flush()
    return new_status


def withdraw(db: Session, user: User, req: SubscriptionRequest, ip: str | None) -> None:
    if req.employee_id != user.employee_id:
        raise AccessError("Only the requester can withdraw this request")
    _move(db, user, req, "withdraw", None, ip)


def resubmit(db: Session, user: User, req: SubscriptionRequest, ip: str | None) -> None:
    if req.employee_id != user.employee_id:
        raise AccessError("Only the requester can resubmit this request")
    has_manager = req.employee.manager_id is not None
    # no manager -> straight back to DMD Sir
    _move(db, user, req, "resubmit", None, ip, force_to=None if has_manager else S.PENDING_DMD)
    target = [_user_of(db, req.employee.manager_id)] if has_manager else dmd_users(db)
    notify(db, target, "request.resubmitted", f"{req.req_no} resubmitted by {req.employee.name}", "", _link(req))
    db.flush()


def decide(db: Session, user: User, req: SubscriptionRequest, data: DecisionIn, ip: str | None) -> SubscriptionRequest:
    actors = actors_for(user, req)
    if not actors & {"manager", "dmd"}:
        raise AccessError("You cannot decide on this request")
    if data.decision == "override":
        if not settings_store.as_bool(settings_store.get_all(db)["allow_urgent_override"]):
            raise ServiceError("Urgent override is turned off in settings")

    # DMD Sir may adjust the request before approving
    if data.decision in ("approve", "override") and "dmd" in actors:
        adjustments = {k: v for k, v in {"plan_name": data.plan_name, "seats": data.seats,
                                          "duration_months": data.duration_months}.items() if v is not None}
        if adjustments.get("duration_months") not in (None, 1, 3, 6, 12):
            raise ServiceError("duration_months must be 1, 3, 6, 12")
        if adjustments:
            before = audit.snapshot(req, list(adjustments))
            for k, v in adjustments.items():
                setattr(req, k, v)
            _apply_estimate(db, req)
            audit.log(db, user, "request.adjust", "request", req.id, before=before, after=adjustments, ip=ip)

    if data.decision == "override" or "manager" not in actors:
        step = "dmd"
    else:
        step = workflow.step_for(req.status)
    new_status = _move(db, user, req, data.decision, data.comment, ip, record_step=step)
    requester = _user_of(db, req.employee_id)
    title_tool = _tool(db, req)

    if new_status == S.PENDING_DMD:
        notify(db, dmd_users(db), "request.recommended",
               f"{req.req_no}: {req.employee.name} — {title_tool} recommended by manager",
               data.comment or "", f"/approvals/{req.id}")
    elif new_status == S.REJECTED:
        notify(db, [requester], "request.rejected", f"{req.req_no} was rejected", data.comment or "", _link(req))
    elif new_status == S.INFO_NEEDED:
        notify(db, [requester], "request.info_needed", f"{req.req_no}: more information needed",
               data.comment or "", _link(req))
    elif new_status == S.ON_HOLD:
        notify(db, [requester], "request.on_hold", f"{req.req_no} is on hold", data.comment or "", _link(req), email=False)
    elif new_status == S.APPROVED:
        notify(db, [requester], "request.approved", f"{req.req_no} approved — {title_tool}",
               "DMD Sir approved your request. You will be told how to collect access.", _link(req))
        if req.type == RequestType.PROPOSAL:
            notify(db, [u for u in admins(db) if u.id != user.id], "proposal.approved",
                   f"{req.req_no} approved — add the subscription for {req.snapshot.get('unit')} and fulfil it",
                   "", f"/requests/{req.id}", email=False)
        else:
            notify(db, [u for u in admins(db) if u.id != user.id], "handover.needed",
                   f"{req.req_no} approved — prepare handover", "", f"/requests/{req.id}/handover", email=False)
        _after_approval(db, user, req, ip)
    db.flush()
    return req


def _after_approval(db: Session, user: User, req: SubscriptionRequest, ip: str | None) -> None:
    action = workflow.after_approval_action(req.type)
    if action is None:
        return
    assignment = (
        db.query(Assignment)
        .filter(Assignment.subscription_id == req.subscription_id, Assignment.employee_id == req.employee_id,
                Assignment.status != AssignmentStatus.REVOKED)
        .first()
    )
    if action == "auto_activate" and assignment:
        base = max(assignment.end_date or today(), today())
        assignment.end_date = add_months(base, req.duration_months) if req.duration_months else None
        assignment.status = AssignmentStatus.ACTIVE
    if action == "auto_end" and assignment:
        assignment.status = AssignmentStatus.REVOKED
        assignment.end_date = today()
        notify(db, admins(db), "assignment.revoke",
               f"{req.employee.name} gave up {req.tool_name} — remove access / change password", "",
               f"/subscriptions/{req.subscription_id}", email=False)
    _move(db, user, req, action, None, ip)


def bulk_approve(db: Session, user: User, ids: list[int], comment: str | None, ip: str | None) -> dict:
    done, failed = [], []
    for rid in ids:
        req = db.get(SubscriptionRequest, rid)
        if not req:
            failed.append({"id": rid, "error": "not found"})
            continue
        try:
            # decide() validates before it changes anything, so a failure leaves the request untouched
            decide(db, user, req, DecisionIn(decision="approve", comment=comment), ip)
            done.append(rid)
        except (ServiceError, AccessError) as exc:
            failed.append({"id": rid, "error": str(exc)})
    return {"approved": done, "failed": failed}


# ---------------------------------------------------------------- handover

def set_handover(db: Session, user: User, req: SubscriptionRequest, data: HandoverIn, ip: str | None) -> Handover:
    if not user.is_admin:
        raise AccessError("Only DMD Sir or a delegate can set up the handover")
    if req.status not in (S.APPROVED, S.HANDOVER_PENDING):
        raise ServiceError("Handover can only be set after approval")
    if req.type == RequestType.PROPOSAL:
        raise ServiceError("A proposal is completed with 'fulfil' after the subscription is added — not by handover")

    sub_id = data.subscription_id or (req.subscription_id if req.type != RequestType.UPGRADE else None)
    sub = db.get(Subscription, sub_id) if sub_id else None
    if not sub:
        raise ServiceError("Choose the subscription (seat) this access belongs to — add it to the register first if it is new")
    if sub.status != SubscriptionStatus.ACTIVE:
        raise ServiceError("That subscription is not active")
    if not sub.available_to(req.employee):
        raise ServiceError(f"That subscription belongs to {sub.owner_label} — not available to "
                           f"{req.employee.name}'s unit/department")
    already_holds = any(a.employee_id == req.employee_id and a.status != AssignmentStatus.REVOKED for a in sub.assignments)
    if not already_holds and sub.seats_free < 1:
        raise ServiceError("No free seat on that subscription — increase seats or choose another")

    collector = None
    if data.method == HandoverMethod.COLLEAGUE:
        collector = db.get(Employee, data.collector_id)
        if not collector or collector.status != "active":
            raise ServiceError("The chosen colleague is not an active employee")

    h = req.handover or Handover(created_by_id=user.id)
    h.subscription = sub
    h.method = data.method
    h.login_email = data.login_email
    h.login_url = data.login_url
    h.notes = data.notes
    if data.method == HandoverMethod.VAULT:
        ct, nonce = crypto.encrypt_secret(data.secret, get_settings().vault_key, _aad(req.id))
        h.secret_ciphertext, h.secret_nonce = ct, nonce
    else:
        h.secret_ciphertext = h.secret_nonce = None
    h.confirmed_at = to_naive_utc(data.confirmed_at) if data.confirmed_at else None
    h.location = data.location
    h.reminder_sent_at = None
    h.collector_id = collector.id if collector else None
    h.collector_note = data.collector_note
    h.due_date = data.due_date
    h.handed_over_at = None
    if req.handover is None:
        req.handover = h
    db.flush()

    if req.status == S.APPROVED:
        _move(db, user, req, "set_handover", None, ip)
    audit.log(db, user, "handover.set", "handover", h.id,
              after={"method": h.method, "subscription_id": sub.id, "collector_id": h.collector_id}, ip=ip)

    requester = _user_of(db, req.employee_id)
    if h.method == HandoverMethod.VAULT:
        notify(db, [requester], "handover.vault", f"{req.req_no}: your access is ready",
               "Open SMP and use 'Reveal credential'. The password is never sent by email.", _link(req))
    elif h.method == HandoverMethod.APPOINTMENT:
        when = f" Confirmed slot: {h.confirmed_at:%d %b %Y %H:%M} UTC." if h.confirmed_at else " Please propose a date and time."
        notify(db, [requester], "handover.appointment", f"{req.req_no}: collect access from DMD Sir",
               (h.notes or "") + when, _link(req))
    else:
        notify(db, [requester], "handover.colleague", f"{req.req_no}: collect access from {collector.name}",
               h.collector_note or "", _link(req))
        notify(db, [_user_of(db, collector.id)], "handover.task",
               f"Hand over {req.tool_name} access to {req.employee.name}", h.collector_note or "", "/my/handover-tasks")
    db.flush()
    return h


def fulfil(db: Session, user: User, req: SubscriptionRequest, subscription_id: int, ip: str | None) -> None:
    """Close an approved proposal by linking the subscription that was added for it."""
    if not user.is_admin:
        raise AccessError("Only DMD Sir or a delegate can fulfil a proposal")
    if req.type != RequestType.PROPOSAL:
        raise ServiceError("Only proposals are fulfilled — seat requests use a handover")
    sub = db.get(Subscription, subscription_id)
    if not sub or sub.status != SubscriptionStatus.ACTIVE:
        raise ServiceError("Subscription not found or not active")
    if sub.unit_id != req.unit_id:
        raise ServiceError("The subscription must belong to the proposer's unit")
    if req.owner_scope == OwnerScope.DEPARTMENT and not (
            sub.owner_scope == OwnerScope.DEPARTMENT and sub.department_id == req.department_id):
        raise ServiceError("The proposal was for the department — the subscription must be owned by that department")
    if req.owner_scope == OwnerScope.UNIT and sub.owner_scope != OwnerScope.UNIT:
        raise ServiceError("The proposal was for the whole unit — the subscription must be unit-wide")
    _move(db, user, req, "fulfil", None, ip)
    req.subscription_id = sub.id
    notify(db, [_user_of(db, req.employee_id)], "proposal.fulfilled",
           f"{req.req_no}: {sub.vendor.name} {sub.plan_name} is now available to {sub.owner_label}",
           "Colleagues can now request a seat on it.", _link(req))
    db.flush()


def _aad(request_id: int) -> bytes:
    return f"handover:{request_id}".encode()


def propose_slot(db: Session, user: User, h: Handover, at, ip: str | None) -> None:
    req = h.request
    if req.employee_id != user.employee_id:
        raise AccessError("Only the requester can propose a slot")
    if h.method != HandoverMethod.APPOINTMENT or req.status != S.HANDOVER_PENDING:
        raise ServiceError("This handover is not an appointment")
    h.proposed_at = to_naive_utc(at)
    h.confirmed_at = None
    audit.log(db, user, "handover.propose_slot", "handover", h.id, after={"proposed_at": h.proposed_at}, ip=ip)
    notify(db, admins(db), "handover.slot_proposed",
           f"{req.req_no}: {req.employee.name} proposes {h.proposed_at:%d %b %Y %H:%M} UTC", "", f"/requests/{req.id}/handover")
    db.flush()


def confirm_slot(db: Session, user: User, h: Handover, at, location: str | None, ip: str | None) -> None:
    if not user.is_admin:
        raise AccessError("Only DMD Sir or a delegate can confirm a slot")
    if h.method != HandoverMethod.APPOINTMENT or h.request.status != S.HANDOVER_PENDING:
        raise ServiceError("This handover is not an open appointment")
    h.confirmed_at = to_naive_utc(at)
    h.reminder_sent_at = None
    if location:
        h.location = location
    audit.log(db, user, "handover.confirm_slot", "handover", h.id, after={"confirmed_at": h.confirmed_at}, ip=ip)
    req = h.request
    notify(db, [_user_of(db, req.employee_id)], "handover.slot_confirmed",
           f"{req.req_no}: come to DMD Sir on {h.confirmed_at:%d %b %Y %H:%M} UTC", h.location or "", _link(req))
    db.flush()


def mark_handed_over(db: Session, user: User, h: Handover, ip: str | None) -> None:
    if not (user.is_admin or h.collector_id == user.employee_id):
        raise AccessError("Only the nominated colleague or an admin can mark this handed over")
    if h.request.status != S.HANDOVER_PENDING:
        raise ServiceError("Handover is not pending")
    h.handed_over_at = utcnow()
    audit.log(db, user, "handover.handed_over", "handover", h.id, ip=ip)
    req = h.request
    notify(db, [_user_of(db, req.employee_id)], "handover.handed_over",
           f"{req.req_no}: please confirm you received access", "", _link(req), email=False)
    db.flush()


def can_reveal(user: User, h: Handover) -> bool:
    if h.request.employee_id == user.employee_id:
        return True
    return user.is_dmd or (user.has_role("delegate") and user.can_reveal_vault)


def reveal(db: Session, user: User, h: Handover, ip: str | None) -> str:
    if not can_reveal(user, h):
        raise AccessError("You are not allowed to view this credential")
    if not h.has_secret:
        raise ServiceError("No credential is stored for this handover")
    if h.request.status not in (S.HANDOVER_PENDING, S.ACTIVE):
        raise ServiceError("This credential is no longer available")
    secret = crypto.decrypt_secret(h.secret_ciphertext, h.secret_nonce, get_settings().vault_key, _aad(h.request_id))
    audit.log(db, user, "vault.reveal", "handover", h.id, ip=ip)
    db.flush()
    return secret


def rotate(db: Session, user: User, h: Handover, secret: str, notes: str | None, ip: str | None) -> None:
    if not user.is_admin:
        raise AccessError("Only DMD Sir or a delegate can change a stored credential")
    ct, nonce = crypto.encrypt_secret(secret, get_settings().vault_key, _aad(h.request_id))
    h.method = HandoverMethod.VAULT
    h.secret_ciphertext, h.secret_nonce = ct, nonce
    if notes is not None:
        h.notes = notes
    audit.log(db, user, "vault.rotate", "handover", h.id, ip=ip)
    db.flush()
    # every holder of a vault credential on the same subscription is told
    holders = (
        db.query(Handover)
        .filter(Handover.subscription_id == h.subscription_id, Handover.secret_ciphertext.is_not(None))
        .all()
    )
    for other in holders:
        if other.id != h.id:
            other.secret_ciphertext, other.secret_nonce = crypto.encrypt_secret(
                secret, get_settings().vault_key, _aad(other.request_id))
    notify(db, [_user_of(db, x.request.employee_id) for x in holders], "vault.rotated",
           "A shared credential was changed", "Reveal it again in SMP to get the new value.", "/my/subscriptions")
    db.flush()


def receive(db: Session, user: User, h: Handover, ip: str | None) -> None:
    req = h.request
    if req.employee_id != user.employee_id:
        raise AccessError("Only the requester can confirm receipt")
    _move(db, user, req, "receive", None, ip)
    h.received_at = utcnow()
    start = max(req.needed_from, today())
    end = add_months(start, req.duration_months) if req.duration_months else None
    existing = (
        db.query(Assignment)
        .filter(Assignment.subscription_id == h.subscription_id, Assignment.employee_id == req.employee_id,
                Assignment.status != AssignmentStatus.REVOKED)
        .first()
    )
    if existing:
        existing.status = AssignmentStatus.ACTIVE
        existing.end_date = end
        existing.request_id = req.id
    else:
        h.subscription.assignments.append(Assignment(employee_id=req.employee_id, request_id=req.id,
                                                     start_date=start, end_date=end, status=AssignmentStatus.ACTIVE))
    if req.type == RequestType.UPGRADE and req.subscription_id and req.subscription_id != h.subscription_id:
        old = (
            db.query(Assignment)
            .filter(Assignment.subscription_id == req.subscription_id, Assignment.employee_id == req.employee_id,
                    Assignment.status == AssignmentStatus.ACTIVE)
            .first()
        )
        if old:
            old.status = AssignmentStatus.REVOKED
            old.end_date = today()
    if req.subscription_id is None:
        req.subscription_id = h.subscription_id
    notify(db, dmd_users(db), "handover.received", f"{req.req_no}: {req.employee.name} confirmed access",
           "", _link(req), email=False)
    db.flush()


def mark_assignments_for_review(db: Session, user: User, employee: Employee, reason: str, ip: str | None) -> int:
    rows = (
        db.query(Assignment)
        .filter(Assignment.employee_id == employee.id, Assignment.status == AssignmentStatus.ACTIVE)
        .all()
    )
    for a in rows:
        a.status = AssignmentStatus.REVOKE_PENDING
    if rows:
        audit.log(db, user, "assignment.revoke_pending", "employee", employee.id, after={"reason": reason, "count": len(rows)}, ip=ip)
        notify(db, admins(db), "assignment.revoke",
               f"{employee.name} ({employee.emp_code}) {reason} — review {len(rows)} subscription(s)",
               "Change shared passwords or remove the seat, then revoke the assignment.", "/subscriptions")
    db.flush()
    return len(rows)


def waiting_days(req: SubscriptionRequest) -> int:
    return max((utcnow() - req.status_changed_at).days, 0)


def sla_breached(req: SubscriptionRequest, sla_days: int) -> bool:
    return req.status in workflow.OPEN_STATUSES and utcnow() - req.status_changed_at > timedelta(days=sla_days)


__all__ = [
    "AccessError", "ServiceError", "actors_for", "allowed_actions", "bulk_approve", "can_view", "confirm_slot",
    "available_subscriptions", "can_propose", "create_request", "decide", "estimate", "fulfil", "mark_assignments_for_review", "mark_handed_over", "propose_slot",
    "receive", "resubmit", "reveal", "rotate", "set_handover", "update_request", "waiting_days", "withdraw",
]

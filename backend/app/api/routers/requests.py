"""Subscription requests, approvals and handover."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.serializers import handover_out, request_detail, request_out
from app.core.crypto import VaultError
from app.core.deps import (
    bad_request,
    client_ip,
    direct_report_ids,
    forbidden,
    get_current_user,
    get_or_404,
    require_admin,
    require_dmd,
)
from app.db.session import get_db
from app.enums import OtpPurpose, RequestStatus
from app.models import Assignment, Handover, SubscriptionRequest, User
from app.schemas.requests import (
    BulkApproveIn,
    DecisionIn,
    EstimateIn,
    EstimateOut,
    HandoverBrief,
    HandoverIn,
    RequestDetail,
    RequestIn,
    RequestOut,
    RequestUpdate,
    RevealIn,
    RevealOut,
    RotateIn,
    SlotIn,
)
from app.services import otp
from app.services import requests_service as svc

router = APIRouter(tags=["requests"])
S = RequestStatus


def _run(db: Session, fn, *args):
    """Run a service call, map business errors to HTTP and commit."""
    try:
        result = fn(*args)
    except svc.ServiceError as exc:
        db.rollback()
        raise bad_request(str(exc)) from None
    except svc.AccessError as exc:
        db.rollback()
        raise forbidden(str(exc)) from None
    except VaultError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Vault error: {exc}") from None
    db.commit()
    return result


def _get_request(db: Session, user: User, request_id: int) -> SubscriptionRequest:
    req = get_or_404(db, SubscriptionRequest, request_id, "Request not found")
    if not svc.can_view(user, req):
        raise forbidden()
    return req


def _get_handover(db: Session, user: User, handover_id: int) -> Handover:
    h = get_or_404(db, Handover, handover_id, "Handover not found")
    if not svc.can_view(user, h.request):
        raise forbidden()
    return h


# ------------------------------------------------------------------ requests

@router.post("/requests/estimate", response_model=EstimateOut)
def estimate(data: EstimateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.estimate(db, data.vendor_id, data.plan_name, data.seats, data.est_cost_per_cycle,
                        data.est_currency, data.est_billing_cycle)


@router.post("/requests", response_model=RequestDetail, status_code=201)
def create_request(data: RequestIn, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    req = _run(db, svc.create_request, db, user, data, client_ip(request))
    return request_detail(req, user)


@router.get("/requests", response_model=list[RequestOut])
def list_requests(scope: str = "mine", status_: str | None = Query(default=None, alias="status"), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """scope: mine | team | pending (waiting for my action) | handover (approved, needs handover) | all"""
    query = db.query(SubscriptionRequest)
    if scope == "mine":
        query = query.filter(SubscriptionRequest.employee_id == user.employee_id)
    elif scope == "team":
        if not user.is_admin:
            query = query.filter(SubscriptionRequest.employee_id.in_(direct_report_ids(db, user) or [-1]))
    elif scope == "pending":
        reports = direct_report_ids(db, user)
        conditions = []
        if reports:
            conditions.append((SubscriptionRequest.status == S.PENDING_MANAGER)
                              & SubscriptionRequest.employee_id.in_(reports))
        if user.is_dmd:
            conditions.append(SubscriptionRequest.status.in_([S.PENDING_DMD, S.ON_HOLD]))
        if not conditions:
            return []
        expr = conditions[0]
        for c in conditions[1:]:
            expr = expr | c
        query = query.filter(expr)
    elif scope == "handover":
        if not user.is_admin:
            raise forbidden()
        query = query.filter(SubscriptionRequest.status.in_([S.APPROVED, S.HANDOVER_PENDING]))
    elif scope == "all":
        if not user.is_admin:
            raise forbidden()
    else:
        raise bad_request("scope must be mine, team, pending, handover or all")
    if status_:
        query = query.filter(SubscriptionRequest.status == status_)
    order = SubscriptionRequest.status_changed_at.asc() if scope == "pending" else SubscriptionRequest.id.desc()
    return [request_out(r) for r in query.order_by(order).limit(500).all()]


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return request_detail(_get_request(db, user, request_id), user)


@router.get("/requests/{request_id}/requester-tools")
def requester_tools(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The requester's current tools — shown to approvers next to the request."""
    req = _get_request(db, user, request_id)
    if not ({"manager", "dmd", "admin"} & svc.actors_for(user, req)):
        raise forbidden()
    rows = db.query(Assignment).filter(Assignment.employee_id == req.employee_id,
                                       Assignment.status != "revoked").all()
    return [{"subscription_id": a.subscription_id, "vendor_name": a.subscription.vendor.name,
             "plan_name": a.subscription.plan_name, "status": a.status, "end_date": a.end_date} for a in rows]


@router.patch("/requests/{request_id}", response_model=RequestDetail)
def update_request(request_id: int, data: RequestUpdate, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    req = _get_request(db, user, request_id)
    _run(db, svc.update_request, db, user, req, data, client_ip(request))
    return request_detail(req, user)


@router.post("/requests/{request_id}/resubmit", response_model=RequestDetail)
def resubmit(request_id: int, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    req = _get_request(db, user, request_id)
    _run(db, svc.resubmit, db, user, req, client_ip(request))
    return request_detail(req, user)


@router.post("/requests/{request_id}/withdraw", response_model=RequestDetail)
def withdraw(request_id: int, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    req = _get_request(db, user, request_id)
    _run(db, svc.withdraw, db, user, req, client_ip(request))
    return request_detail(req, user)


@router.post("/requests/{request_id}/decision", response_model=RequestDetail)
def decide(request_id: int, data: DecisionIn, request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    req = _get_request(db, user, request_id)
    _run(db, svc.decide, db, user, req, data, client_ip(request))
    return request_detail(req, user)


@router.post("/requests/bulk-approve")
def bulk_approve(data: BulkApproveIn, request: Request, user: User = Depends(require_dmd),
                 db: Session = Depends(get_db)):
    return _run(db, svc.bulk_approve, db, user, data.request_ids, data.comment, client_ip(request))


# ------------------------------------------------------------------ handover

@router.post("/requests/{request_id}/handover", response_model=RequestDetail)
def set_handover(request_id: int, data: HandoverIn, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    req = _get_request(db, user, request_id)
    _run(db, svc.set_handover, db, user, req, data, client_ip(request))
    db.refresh(req)
    return request_detail(req, user)


@router.get("/handovers/{handover_id}", response_model=HandoverBrief)
def get_handover(handover_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return handover_out(_get_handover(db, user, handover_id))


@router.get("/my/handover-tasks")
def my_handover_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Handover)
        .join(SubscriptionRequest)
        .filter(Handover.collector_id == user.employee_id, SubscriptionRequest.status == S.HANDOVER_PENDING)
        .all()
    )
    return [
        {
            "handover_id": h.id,
            "request_id": h.request_id,
            "req_no": h.request.req_no,
            "requester_name": h.request.employee.name,
            "requester_code": h.request.employee.emp_code,
            "tool_name": h.request.tool_name,
            "plan_name": h.request.plan_name,
            "note": h.collector_note,
            "due_date": h.due_date,
            "handed_over_at": h.handed_over_at,
        }
        for h in rows
    ]


@router.post("/handovers/{handover_id}/propose-slot", response_model=HandoverBrief)
def propose_slot(handover_id: int, data: SlotIn, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    _run(db, svc.propose_slot, db, user, h, data.at, client_ip(request))
    return handover_out(h)


@router.post("/handovers/{handover_id}/confirm-slot", response_model=HandoverBrief)
def confirm_slot(handover_id: int, data: SlotIn, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    _run(db, svc.confirm_slot, db, user, h, data.at, data.location, client_ip(request))
    return handover_out(h)


@router.post("/handovers/{handover_id}/handed-over", response_model=HandoverBrief)
def handed_over(handover_id: int, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    _run(db, svc.mark_handed_over, db, user, h, client_ip(request))
    return handover_out(h)


@router.post("/handovers/{handover_id}/reveal-otp", status_code=204)
def reveal_otp(handover_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    if not svc.can_reveal(user, h) or not h.has_secret:
        raise forbidden("No credential available for you here")
    otp.issue(db, user, OtpPurpose.REVEAL, ref_id=h.id)
    db.commit()


@router.post("/handovers/{handover_id}/reveal", response_model=RevealOut)
def reveal(handover_id: int, data: RevealIn, request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    if not svc.can_reveal(user, h):
        raise forbidden("You are not allowed to view this credential")
    try:
        otp.verify(db, user, OtpPurpose.REVEAL, data.code, ref_id=h.id)
    except otp.OtpError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    secret = _run(db, svc.reveal, db, user, h, client_ip(request))
    return RevealOut(secret=secret, login_email=h.login_email, login_url=h.login_url, notes=h.notes)


@router.post("/handovers/{handover_id}/rotate", response_model=HandoverBrief)
def rotate(handover_id: int, data: RotateIn, request: Request, user: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    _run(db, svc.rotate, db, user, h, data.secret, data.notes, client_ip(request))
    return handover_out(h)


@router.post("/handovers/{handover_id}/received", response_model=RequestDetail)
def received(handover_id: int, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    h = _get_handover(db, user, handover_id)
    _run(db, svc.receive, db, user, h, client_ip(request))
    return request_detail(h.request, user)


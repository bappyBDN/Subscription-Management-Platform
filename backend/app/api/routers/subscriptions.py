"""Subscription register, seat assignments and card charges."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.serializers import assignment_out, subscription_detail, subscription_out
from app.core.clock import today
from app.core.deps import bad_request, client_ip, get_current_user, get_or_404, no_null, not_found, require_admin
from app.db.session import get_db
from app.enums import AssignmentStatus, OwnerScope, SubscriptionStatus
from app.models import Assignment, Card, CardCharge, Employee, Subscription, User, Vendor
from app.schemas.subscriptions import (
    AssignIn,
    AssignmentOut,
    AvailableSubscriptionOut,
    CancelIn,
    ChargeIn,
    ChargeOut,
    ChargeUpdate,
    ImportResult,
    SubscriptionDetail,
    SubscriptionIn,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services import audit, budget, insights, settings_store
from app.services import requests_service as svc
from app.services.cost import charge_bdt, estimate_request_cost, q
from app.services.importer import read_rows
from app.services.notify import admins, dmd_users, notify
from app.services.org import OrgError, check_unit_department, department_by_name, unit_by_code

router = APIRouter(tags=["subscriptions"])

SUB_FIELDS = ["plan_name", "type", "seats_total", "cost_per_cycle", "currency", "billing_cycle", "start_date",
              "next_renewal_date", "card_id", "account_email", "owner_scope", "unit_id", "department_id", "status", "notes"]


def _check_owner(db: Session, owner_scope: str, unit_id: int, department_id: int | None) -> None:
    if owner_scope == OwnerScope.DEPARTMENT and not department_id:
        raise bad_request("A department-owned subscription needs a department")
    try:
        check_unit_department(db, unit_id, department_id if owner_scope == OwnerScope.DEPARTMENT else None)
    except OrgError as exc:
        raise bad_request(str(exc)) from None


def _check_refs(db: Session, vendor_id: int | None = None, card_id: int | None = None) -> None:
    if vendor_id is not None and not db.get(Vendor, vendor_id):
        raise bad_request("Unknown tool")
    if card_id is not None and not db.get(Card, card_id):
        raise bad_request("Unknown card")


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(status: str | None = None, vendor_id: int | None = None, unit_id: int | None = None,
                       department_id: int | None = None, owner_scope: str | None = None,
                       renewal_within_days: int | None = None,
                       user: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(Subscription)
    if status:
        query = query.filter(Subscription.status == status)
    if vendor_id:
        query = query.filter(Subscription.vendor_id == vendor_id)
    if unit_id:
        query = query.filter(Subscription.unit_id == unit_id)
    if department_id:
        query = query.filter(Subscription.department_id == department_id)
    if owner_scope:
        query = query.filter(Subscription.owner_scope == owner_scope)
    if renewal_within_days is not None:
        query = query.filter(Subscription.next_renewal_date.is_not(None),
                             Subscription.next_renewal_date <= today() + timedelta(days=renewal_within_days))
    return [subscription_out(s) for s in query.order_by(Subscription.next_renewal_date).all()]


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
def create_subscription(data: SubscriptionIn, request: Request, user: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    _check_refs(db, data.vendor_id, data.card_id)
    _check_owner(db, data.owner_scope, data.unit_id, data.department_id)
    sub = Subscription(**data.model_dump())
    db.add(sub)
    db.flush()
    db.refresh(sub)
    audit.log(db, user, "subscription.create", "subscription", sub.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return subscription_out(sub)


@router.get("/my/available-subscriptions", response_model=list[AvailableSubscriptionOut])
def available_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Subscriptions this employee may request a seat on: their unit's unit-wide ones + their department's."""
    fx = settings_store.fx_rates(settings_store.get_all(db))
    out = []
    for s in svc.available_subscriptions(db, user.employee):
        per_seat = Decimal(s.cost_per_cycle) / max(s.seats_total, 1)
        est = estimate_request_cost(per_seat, s.currency, s.billing_cycle, 1, fx)
        out.append(AvailableSubscriptionOut(
            subscription_id=s.id, vendor_id=s.vendor_id, vendor_name=s.vendor.name, plan_name=s.plan_name,
            owner_scope=s.owner_scope, owner_label=s.owner_label, seats_total=s.seats_total,
            seats_free=s.seats_free, billing_cycle=s.billing_cycle, cost_per_seat=q(per_seat), currency=s.currency,
            monthly_bdt_per_seat=est["monthly_bdt"],
            already_holding=any(a.employee_id == user.employee_id and a.status != AssignmentStatus.REVOKED
                                for a in s.assignments),
        ))
    return out


@router.post("/subscriptions/import", response_model=ImportResult)
async def import_subscriptions(request: Request, file: UploadFile = File(...), user: User = Depends(require_admin),
                               db: Session = Depends(get_db)):
    """Columns: vendor, plan_name, type, seats_total, cost_per_cycle, currency, billing_cycle, start_date,
    next_renewal_date, card_last4, account_email, unit (code), department (name), owner_scope (unit|department,
    default: department when a department is given), holder_codes (comma separated emp codes).
    Unknown vendors are created."""
    try:
        rows = read_rows(file.filename or "", await file.read())
    except ValueError as exc:
        raise bad_request(str(exc)) from None
    created, errors = 0, []
    for i, row in enumerate(rows, start=2):
        try:
            # validate and convert the whole row before writing anything
            vendor_name = str(row.get("vendor") or "").strip()
            plan = str(row.get("plan_name") or "").strip()
            if not vendor_name or not plan:
                raise ValueError("vendor and plan_name are required")
            cycle = str(row.get("billing_cycle") or "monthly").strip().lower()
            if cycle not in ("monthly", "yearly", "usage", "one_time"):
                raise ValueError(f"billing_cycle '{cycle}' is not valid")
            sub_type = str(row.get("type") or "individual").strip().lower()
            if sub_type not in ("individual", "team", "api_credit", "one_time"):
                raise ValueError(f"type '{sub_type}' is not valid")
            unit = unit_by_code(db, str(row.get("unit") or ""))
            if unit is None:
                raise ValueError(f"unit '{row.get('unit') or ''}' is not a known unit code")
            dept_name = str(row.get("department") or "").strip()
            scope = str(row.get("owner_scope") or ("department" if dept_name else "unit")).strip().lower()
            if scope not in ("unit", "department"):
                raise ValueError(f"owner_scope '{scope}' must be unit or department")
            if scope == "department" and not dept_name:
                raise ValueError("owner_scope 'department' needs a department name")
            seats = int(row.get("seats_total") or 1)
            cost_per_cycle = Decimal(str(row.get("cost_per_cycle") or "0"))
            start = _as_date(row.get("start_date")) or today()
            renewal = _as_date(row.get("next_renewal_date"))
            card = None
            if row.get("card_last4"):
                last4 = str(row["card_last4"]).strip().zfill(4)[-4:]
                card = db.query(Card).filter(Card.last4 == last4).first()

            dept = department_by_name(db, unit, dept_name, create=True) if scope == "department" else None
            vendor = db.query(Vendor).filter(func.lower(Vendor.name) == vendor_name.lower()).first()
            if vendor is None:
                vendor = Vendor(name=vendor_name, category="other")
                db.add(vendor)
                db.flush()
            sub = Subscription(
                vendor_id=vendor.id,
                plan_name=plan,
                type=sub_type,
                seats_total=seats,
                cost_per_cycle=cost_per_cycle,
                currency=str(row.get("currency") or "USD").strip().upper(),
                billing_cycle=cycle,
                start_date=start,
                next_renewal_date=renewal,
                card_id=card.id if card else None,
                account_email=(str(row["account_email"]).strip() if row.get("account_email") else None),
                owner_scope=scope,
                unit_id=unit.id,
                department_id=dept.id if dept else None,
            )
            db.add(sub)
            db.flush()
            for code in str(row.get("holder_codes") or "").split(","):
                code = code.strip()
                if not code:
                    continue
                emp = db.query(Employee).filter(Employee.emp_code == code).first()
                if emp is None:
                    errors.append({"row": i, "error": f"holder '{code}' not found (subscription still created)"})
                    continue
                sub.assignments.append(Assignment(employee_id=emp.id, start_date=sub.start_date))
            created += 1
        except (ValueError, InvalidOperation) as exc:
            errors.append({"row": i, "error": str(exc) or "invalid number"})
    audit.log(db, user, "subscription.import", "subscription", None, after={"created": created, "rows": len(rows)},
              ip=client_ip(request))
    db.commit()
    return ImportResult(created=created, errors=errors)


def _as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value if not hasattr(value, "date") else value.date()
    return date.fromisoformat(str(value).strip()[:10])


@router.get("/subscriptions/{sub_id}", response_model=SubscriptionDetail)
def get_subscription(sub_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return subscription_detail(get_or_404(db, Subscription, sub_id, "Subscription not found"))


@router.patch("/subscriptions/{sub_id}", response_model=SubscriptionOut)
def update_subscription(sub_id: int, data: SubscriptionUpdate, request: Request, user: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    sub = get_or_404(db, Subscription, sub_id, "Subscription not found")
    changes = no_null(data.model_dump(exclude_unset=True),
                      {"plan_name", "type", "seats_total", "cost_per_cycle", "currency", "billing_cycle",
                       "start_date", "status", "owner_scope", "unit_id"})
    _check_refs(db, card_id=changes.get("card_id"))
    if {"owner_scope", "unit_id", "department_id"} & set(changes):
        scope = changes.get("owner_scope", sub.owner_scope)
        unit_id = changes.get("unit_id") or sub.unit_id
        dept_id = changes["department_id"] if "department_id" in changes else sub.department_id
        if scope == OwnerScope.UNIT:
            dept_id = None
        _check_owner(db, scope, unit_id, dept_id)
        changes.update(owner_scope=scope, unit_id=unit_id, department_id=dept_id)
    if "seats_total" in changes and changes["seats_total"] < sub.seats_used:
        raise bad_request(f"{sub.seats_used} seats are in use — revoke assignments first")
    before = audit.snapshot(sub, list(changes))
    for k, v in changes.items():
        setattr(sub, k, v)
    audit.log(db, user, "subscription.update", "subscription", sub.id, before=before, after=changes,
              ip=client_ip(request))
    db.commit()
    db.refresh(sub)  # reload owner relationships after an ownership change
    return subscription_out(sub)


@router.post("/subscriptions/{sub_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(sub_id: int, data: CancelIn, request: Request, user: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    sub = get_or_404(db, Subscription, sub_id, "Subscription not found")
    if sub.status == SubscriptionStatus.CANCELLED:
        raise bad_request("Already cancelled")
    sub.status = SubscriptionStatus.CANCELLED
    sub.cancelled_on = data.cancelled_on or today()
    sub.next_renewal_date = None
    holders = []
    for a in sub.assignments:
        if a.status != AssignmentStatus.REVOKED:
            a.status = AssignmentStatus.REVOKED
            a.end_date = a.end_date if a.end_date and a.end_date < sub.cancelled_on else sub.cancelled_on
            holders.append(a.employee_id)
    audit.log(db, user, "subscription.cancel", "subscription", sub.id,
              after={"cancelled_on": sub.cancelled_on, "reason": data.reason}, ip=client_ip(request))
    users = db.query(User).filter(User.employee_id.in_(holders or [-1])).all()
    notify(db, users, "subscription.cancelled", f"{sub.vendor.name} {sub.plan_name} was cancelled",
           data.reason or "", "/my/subscriptions")
    db.commit()
    return subscription_out(sub)


@router.post("/subscriptions/{sub_id}/assignments", response_model=AssignmentOut, status_code=201)
def assign_seat(sub_id: int, data: AssignIn, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    sub = get_or_404(db, Subscription, sub_id, "Subscription not found")
    emp = get_or_404(db, Employee, data.employee_id, "Employee not found")
    if any(a.employee_id == emp.id and a.status != AssignmentStatus.REVOKED for a in sub.assignments):
        raise bad_request("This employee already holds a seat on this subscription")
    if not sub.available_to(emp):
        raise bad_request(f"{emp.name} is not in {sub.owner_label} — this subscription is not available to them")
    if sub.seats_free < 1:
        raise bad_request("No free seat — increase seats first")
    a = Assignment(employee_id=emp.id, start_date=data.start_date or today(), end_date=data.end_date)
    sub.assignments.append(a)
    db.flush()
    db.refresh(a)
    audit.log(db, user, "assignment.create", "subscription", sub.id, after={"employee_id": emp.id},
              ip=client_ip(request))
    db.commit()
    return assignment_out(a)


@router.delete("/subscriptions/{sub_id}/assignments/{assignment_id}", response_model=AssignmentOut)
def revoke_seat(sub_id: int, assignment_id: int, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    a = db.get(Assignment, assignment_id)
    if not a or a.subscription_id != sub_id:
        raise not_found("Assignment not found")
    if a.status == AssignmentStatus.REVOKED:
        raise bad_request("Already revoked")
    a.status = AssignmentStatus.REVOKED
    a.end_date = min(a.end_date, today()) if a.end_date else today()
    audit.log(db, user, "assignment.revoke", "subscription", sub_id, after={"employee_id": a.employee_id},
              ip=client_ip(request))
    db.commit()
    return assignment_out(a)


# ------------------------------------------------------------------ my subscriptions

@router.get("/my/subscriptions")
def my_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.serializers import handover_out
    from app.models import Handover, SubscriptionRequest

    rows = (
        db.query(Assignment)
        .filter(Assignment.employee_id == user.employee_id, Assignment.status != AssignmentStatus.REVOKED)
        .all()
    )
    out = []
    for a in rows:
        h = None
        if a.request_id:
            h = db.query(Handover).filter(Handover.request_id == a.request_id).first()
        req = db.get(SubscriptionRequest, a.request_id) if a.request_id else None
        out.append({
            "assignment_id": a.id,
            "subscription_id": a.subscription_id,
            "vendor_name": a.subscription.vendor.name,
            "plan_name": a.subscription.plan_name,
            "status": a.status,
            "start_date": a.start_date,
            "end_date": a.end_date,
            "next_renewal_date": a.subscription.next_renewal_date,
            "request_id": a.request_id,
            "req_no": req.req_no if req else None,
            "handover": handover_out(h),
        })
    # approved requests still waiting for handover / receipt
    pending = (
        db.query(SubscriptionRequest)
        .filter(SubscriptionRequest.employee_id == user.employee_id,
                SubscriptionRequest.status.in_(["approved", "handover_pending"]))
        .all()
    )
    return {
        "active": out,
        "pending_handover": [
            {"request_id": r.id, "req_no": r.req_no, "tool_name": r.tool_name, "plan_name": r.plan_name,
             "status": r.status, "handover": handover_out(r.handover)}
            for r in pending
        ],
    }


# ------------------------------------------------------------------ card charges

def _fx_default(db: Session, currency: str) -> Decimal:
    if currency == "BDT":
        return Decimal("1")
    return settings_store.fx_rates(settings_store.get_all(db)).get(currency) or Decimal("1")


@router.get("/charges", response_model=list[ChargeOut])
def list_charges(month: str | None = None, subscription_id: int | None = None, card_id: int | None = None,
                 expected: bool | None = None, reconciled: bool | None = None, unit_id: int | None = None,
                 department_id: int | None = None, anomaly: bool | None = None,
                 user: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(CardCharge)
    if month:  # YYYY-MM
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
        end = date(y + (m == 12), (m % 12) + 1, 1)
        query = query.filter(CardCharge.charge_date >= start, CardCharge.charge_date < end)
    if subscription_id:
        query = query.filter(CardCharge.subscription_id == subscription_id)
    if card_id:
        query = query.filter(CardCharge.card_id == card_id)
    if expected is not None:
        query = query.filter(CardCharge.is_expected.is_(expected))
    if reconciled is not None:
        query = query.filter(CardCharge.reconciled.is_(reconciled))
    if unit_id:
        query = query.filter(CardCharge.unit_id == unit_id)
    if department_id:
        query = query.filter(CardCharge.department_id == department_id)
    if anomaly is not None:
        query = query.filter(CardCharge.anomaly.is_(anomaly))
    return query.order_by(CardCharge.charge_date.desc(), CardCharge.id.desc()).limit(1000).all()


@router.post("/charges", response_model=ChargeOut, status_code=201)
def create_charge(data: ChargeIn, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    sub = get_or_404(db, Subscription, data.subscription_id, "Subscription not found")
    _check_refs(db, card_id=data.card_id)
    fx = data.fx_rate or _fx_default(db, data.currency)
    charge = CardCharge(**data.model_dump(exclude={"fx_rate"}), fx_rate=fx,
                        amount_bdt=charge_bdt(data.amount_original, fx, data.bank_fee_bdt))
    if charge.card_id is None:
        charge.card_id = sub.card_id
    # snapshot the owner so later ownership changes never rewrite payment history
    charge.unit_id = sub.unit_id
    charge.department_id = sub.department_id if sub.owner_scope == OwnerScope.DEPARTMENT else None
    if not data.is_expected:
        charge.anomaly_note = insights.charge_anomaly(sub, data.amount_original, data.currency)
        charge.anomaly = charge.anomaly_note is not None
    sub.charges.append(charge)  # keep an already-loaded sub.charges current
    db.flush()
    audit.log(db, user, "charge.create", "charge", charge.id,
              after={**data.model_dump(), "fx_rate": fx, "amount_bdt": charge.amount_bdt,
                     "anomaly": charge.anomaly}, ip=client_ip(request))
    if charge.anomaly:
        notify(db, dmd_users(db), "charge.anomaly",
               f"Unusual charge on {sub.vendor.name} {sub.plan_name}", charge.anomaly_note, "/charges?anomaly=true")
    _budget_check(db)
    budget.check_owner_budgets(db, sub.unit_id, charge.department_id)
    db.commit()
    return charge


@router.patch("/charges/{charge_id}", response_model=ChargeOut)
def update_charge(charge_id: int, data: ChargeUpdate, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    charge = get_or_404(db, CardCharge, charge_id, "Charge not found")
    changes = no_null(data.model_dump(exclude_unset=True),
                      {"charge_date", "amount_original", "currency", "fx_rate", "bank_fee_bdt", "is_expected",
                       "reconciled", "anomaly"})
    _check_refs(db, card_id=changes.get("card_id"))
    before = audit.snapshot(charge, [*changes, "amount_bdt"])
    for k, v in changes.items():
        setattr(charge, k, v)
    charge.amount_bdt = charge_bdt(charge.amount_original, charge.fx_rate, charge.bank_fee_bdt)
    audit.log(db, user, "charge.update", "charge", charge.id, before=before,
              after={**changes, "amount_bdt": charge.amount_bdt}, ip=client_ip(request))
    db.commit()
    return charge


@router.delete("/charges/{charge_id}", status_code=204)
def delete_charge(charge_id: int, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    charge = get_or_404(db, CardCharge, charge_id, "Charge not found")
    audit.log(db, user, "charge.delete", "charge", charge.id,
              before=audit.snapshot(charge, ["subscription_id", "charge_date", "amount_bdt"]), ip=client_ip(request))
    db.delete(charge)
    db.commit()


def _budget_check(db: Session) -> None:
    """Notify admins when month-to-date paid spend crosses 80% / 100% of the budget."""
    values = settings_store.get_all(db)
    budget = Decimal(values["monthly_budget_bdt"] or "0")
    if budget <= 0:
        return
    start = today().replace(day=1)
    spent = (
        db.query(func.coalesce(func.sum(CardCharge.amount_bdt), 0))
        .filter(CardCharge.charge_date >= start, CardCharge.is_expected.is_(False))
        .scalar()
    )
    pct = Decimal(spent) / budget * 100
    if pct >= 100:
        notify(db, admins(db), "budget.exceeded", f"Subscription budget exceeded: {pct:.0f}% used this month", "", "/")
    elif pct >= 80:
        notify(db, admins(db), "budget.warning", f"Subscription budget at {pct:.0f}% this month", "", "/", email=False)

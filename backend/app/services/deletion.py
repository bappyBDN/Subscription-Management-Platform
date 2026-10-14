"""Safe delete for master records.

A record is deleted for good only when nothing that is history points at it (requests, seats, approvals,
handovers, card charges, metered usage, audit entries). Plain links — someone's manager, a unit or department
head, a team leader — are cleared. Otherwise `DeleteBlocked` says what is in the way, and the record should
be deactivated instead, so cost reports and the audit trail stay complete.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    Assignment,
    AuditLog,
    Card,
    CardCharge,
    DailyCost,
    Department,
    Employee,
    Handover,
    Notification,
    OrgFunction,
    OrgUnit,
    OtpCode,
    Subscription,
    SubscriptionRequest,
    SubscriptionShare,
    Team,
    UsageDay,
    User,
    Vendor,
)
from app.services import audit


class DeleteBlocked(Exception):
    def __init__(self, what: str, reasons: list[str], instead: str = "Deactivate it instead."):
        self.reasons = reasons
        super().__init__(f"{what} cannot be deleted because it has {', '.join(reasons)}. {instead}")


def _blockers(db: Session, checks: list[tuple[str, type, object]]) -> list[str]:
    """checks: (label with {s} for the plural, model, filter condition) -> ["3 requests", ...]."""
    out = []
    for label, model, cond in checks:
        n = db.query(model).filter(cond).count()
        if n:
            out.append(f"{n} " + label.format(s="" if n == 1 else "s"))
    return out


# ------------------------------------------------------------------ people

def user_blockers(db: Session, user: User) -> list[str]:
    return _blockers(db, [
        ("audit log record{s}", AuditLog, AuditLog.user_id == user.id),
        ("approval decision{s}", Approval, Approval.approver_id == user.id),
        ("handover{s} set up by them", Handover, Handover.created_by_id == user.id),
    ])


def delete_user(db: Session, user: User) -> None:
    reasons = user_blockers(db, user)
    if reasons:
        raise DeleteBlocked("This login account", reasons,
                            "It has been used, so disable it instead (untick 'Account is active').")
    db.query(OtpCode).filter(OtpCode.user_id == user.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)


def delete_employee(db: Session, emp: Employee) -> None:
    reasons = _blockers(db, [
        ("request{s}", SubscriptionRequest, SubscriptionRequest.employee_id == emp.id),
        ("seat{s} (current or past)", Assignment, Assignment.employee_id == emp.id),
        ("handover{s} to collect", Handover, Handover.collector_id == emp.id),
    ])
    if emp.user is not None:
        reasons += [f"a login account with {r}" for r in user_blockers(db, emp.user)]
    if reasons:
        raise DeleteBlocked(f"Employee {emp.emp_code}", reasons, "Set their status to inactive instead.")
    # plain links are cleared, not blocking
    db.query(Employee).filter(Employee.manager_id == emp.id).update({Employee.manager_id: None},
                                                                    synchronize_session=False)
    db.query(OrgUnit).filter(OrgUnit.head_employee_id == emp.id).update({OrgUnit.head_employee_id: None},
                                                                        synchronize_session=False)
    db.query(Department).filter(Department.head_employee_id == emp.id).update(
        {Department.head_employee_id: None}, synchronize_session=False)
    db.query(Team).filter(Team.lead_employee_id == emp.id).update({Team.lead_employee_id: None},
                                                                  synchronize_session=False)
    db.query(OrgFunction).filter(OrgFunction.head_employee_id == emp.id).update(
        {OrgFunction.head_employee_id: None}, synchronize_session=False)
    if emp.user is not None:
        delete_user(db, emp.user)
        db.flush()
    db.delete(emp)


# ------------------------------------------------------------------ organisation

def _function_reasons(db: Session, fn_ids: list[int]) -> list[str]:
    ids = fn_ids or [-1]
    return _blockers(db, [
        ("employee{s}", Employee, Employee.function_id.in_(ids)),
        ("subscription{s}", Subscription, Subscription.function_id.in_(ids)),
        ("shared subscription{s}", SubscriptionShare, SubscriptionShare.function_id.in_(ids)),
        ("request{s}", SubscriptionRequest, SubscriptionRequest.function_id.in_(ids)),
    ])


def delete_function(db: Session, fn: OrgFunction) -> None:
    reasons = _function_reasons(db, [fn.id])
    if reasons:
        raise DeleteBlocked(f"Function {fn.name}", reasons)
    db.query(Team).filter(Team.function_id == fn.id).update({Team.function_id: None}, synchronize_session=False)
    db.delete(fn)


def _department_reasons(db: Session, dept_ids: list[int]) -> list[str]:
    ids = dept_ids or [-1]
    reasons = _blockers(db, [
        ("employee{s}", Employee, Employee.department_id.in_(ids)),
        ("subscription{s}", Subscription, Subscription.department_id.in_(ids)),
        ("shared subscription{s}", SubscriptionShare, SubscriptionShare.department_id.in_(ids)),
        ("request{s}", SubscriptionRequest, SubscriptionRequest.department_id.in_(ids)),
        ("card charge{s}", CardCharge, CardCharge.department_id.in_(ids)),
    ])
    if not reasons:  # anything still pointing at one of its functions
        fn_ids = [f for (f,) in db.query(OrgFunction.id).filter(OrgFunction.department_id.in_(ids)).all()]
        reasons = _function_reasons(db, fn_ids)
    return reasons


def _drop_department(db: Session, dept: Department) -> None:
    """Delete a department that has no history, with its (empty) functions."""
    fn_ids = [f.id for f in dept.functions]
    if fn_ids:
        db.query(Team).filter(Team.function_id.in_(fn_ids)).update({Team.function_id: None}, synchronize_session=False)
    for fn in list(dept.functions):
        db.delete(fn)
    db.flush()
    db.delete(dept)


def delete_department(db: Session, dept: Department) -> None:
    reasons = _department_reasons(db, [dept.id])
    if reasons:
        raise DeleteBlocked(f"Department {dept.name}", reasons)
    db.query(Team).filter(Team.department_id == dept.id).update({Team.department_id: None},
                                                                synchronize_session=False)
    _drop_department(db, dept)


def delete_team(db: Session, team: Team) -> None:
    reasons = _blockers(db, [("subscription{s}", Subscription, Subscription.team_id == team.id)])
    if reasons:
        raise DeleteBlocked(f"Team {team.name}", reasons)
    db.delete(team)


def delete_unit(db: Session, unit: OrgUnit) -> None:
    """Deletes the SBU with its (empty) departments, functions and teams."""
    dept_ids = [d.id for d in unit.departments]
    reasons = _blockers(db, [
        ("employee{s}", Employee, Employee.unit_id == unit.id),
        ("subscription{s}", Subscription, Subscription.unit_id == unit.id),
        ("request{s}", SubscriptionRequest, SubscriptionRequest.unit_id == unit.id),
        ("card charge{s}", CardCharge, CardCharge.unit_id == unit.id),
    ])
    if not reasons:  # anything still pointing at one of its departments (normally covered by the unit checks)
        reasons = _department_reasons(db, dept_ids)
    if reasons:
        raise DeleteBlocked(f"SBU {unit.code}", reasons)
    db.query(Team).filter(Team.unit_id == unit.id).delete(synchronize_session=False)
    for dept in list(unit.departments):
        _drop_department(db, dept)
    db.flush()
    db.delete(unit)


# ------------------------------------------------------------------ catalogue and register

def delete_vendor(db: Session, vendor: Vendor) -> None:
    reasons = _blockers(db, [
        ("subscription{s}", Subscription, Subscription.vendor_id == vendor.id),
        ("request{s}", SubscriptionRequest, SubscriptionRequest.vendor_id == vendor.id),
    ])
    if reasons:
        raise DeleteBlocked(f"Tool {vendor.name}", reasons)
    db.delete(vendor)  # its plans go with it


def delete_card(db: Session, card: Card) -> None:
    reasons = _blockers(db, [
        ("subscription{s}", Subscription, Subscription.card_id == card.id),
        ("card charge{s}", CardCharge, CardCharge.card_id == card.id),
    ])
    if reasons:
        raise DeleteBlocked(f"Card {card.label}", reasons)
    db.delete(card)


def delete_subscription(db: Session, sub: Subscription) -> None:
    reasons = _blockers(db, [
        ("seat{s} (current or past)", Assignment, Assignment.subscription_id == sub.id),
        ("card charge{s}", CardCharge, CardCharge.subscription_id == sub.id),
        ("request{s}", SubscriptionRequest, SubscriptionRequest.subscription_id == sub.id),
        ("handover{s}", Handover, Handover.subscription_id == sub.id),
        ("day{s} of metered usage", UsageDay, UsageDay.subscription_id == sub.id),
    ])
    if reasons:
        raise DeleteBlocked("This subscription", reasons, "Cancel it instead.")
    db.query(DailyCost).filter(DailyCost.subscription_id == sub.id).delete(synchronize_session=False)
    db.delete(sub)


def remove(db: Session, actor: User, entity: str, obj, delete_fn, label: str, ip: str | None) -> None:
    """Run `delete_fn`, audit it and commit. Raises DeleteBlocked when history (or any other row) still
    points at the record."""
    obj_id = obj.id
    try:
        delete_fn(db, obj)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DeleteBlocked(label, ["other records that still point at it"]) from None
    audit.log(db, actor, f"{entity}.delete", entity, obj_id, before={"name": label}, ip=ip)
    db.commit()

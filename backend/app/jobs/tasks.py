"""Scheduled jobs. Each function takes a session and the business date, so tests can call them directly."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.enums import AssignmentStatus, HandoverMethod, RequestStatus, SubscriptionStatus
from app.models import Assignment, CardCharge, DailyCost, Handover, Subscription, SubscriptionRequest, User
from app.services import cost, settings_store
from app.services.costs_db import load_subinfos
from app.services.mailer import send_email
from app.services.notify import admins, dmd_users, notify
from app.services.workflow import OPEN_STATUSES


def daily_cost(db: Session, day: date) -> int:
    """Store the accrued cost of `day` per subscription (run just after midnight for yesterday)."""
    fx = settings_store.fx_rates(settings_store.get_all(db))
    count = 0
    for sub in load_subinfos(db):
        dc = cost.daily_cost(sub, day, fx)
        row = db.query(DailyCost).filter_by(subscription_id=sub.id, cost_date=day).first()
        if row is None:
            row = DailyCost(subscription_id=sub.id, cost_date=day)
            db.add(row)
        row.amount_bdt = cost.q(dc.amount)
        row.estimated = dc.estimated
        count += 1
    db.commit()
    return count


def expected_charges(db: Session, day: date) -> int:
    """For renewals due on/before `day`: add an expected charge and roll the renewal date forward."""
    values = settings_store.get_all(db)
    fx = settings_store.fx_rates(values)
    subs = (
        db.query(Subscription)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.next_renewal_date.is_not(None),
                Subscription.next_renewal_date <= day,
                Subscription.billing_cycle.in_(["monthly", "yearly"]))
        .all()
    )
    for sub in subs:
        rate = Decimal("1") if sub.currency == "BDT" else fx.get(sub.currency, Decimal("1"))
        db.add(CardCharge(subscription_id=sub.id, card_id=sub.card_id, charge_date=sub.next_renewal_date,
                          amount_original=sub.cost_per_cycle, currency=sub.currency, fx_rate=rate,
                          amount_bdt=cost.charge_bdt(sub.cost_per_cycle, rate), is_expected=True,
                          reference="expected renewal"))
        step = 12 if sub.billing_cycle == "yearly" else 1
        sub.next_renewal_date = cost.add_months(sub.next_renewal_date, step)
    db.commit()
    return len(subs)


def renewal_reminders(db: Session, day: date) -> int:
    targets = {day + timedelta(days=7), day + timedelta(days=1)}
    subs = (
        db.query(Subscription)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.next_renewal_date.in_(sorted(targets)))
        .all()
    )
    for sub in subs:
        days_left = (sub.next_renewal_date - day).days
        holders = ", ".join(a.employee.name for a in sub.assignments if a.status != AssignmentStatus.REVOKED) or "no holders"
        notify(db, admins(db), "renewal.reminder",
               f"{sub.vendor.name} {sub.plan_name} renews in {days_left} day(s)",
               f"{sub.cost_per_cycle} {sub.currency} on {sub.next_renewal_date:%d %b %Y}. Users: {holders}.",
               f"/subscriptions/{sub.id}")
    db.commit()
    return len(subs)


def appointment_reminders(db: Session, now=None) -> int:
    now = now or utcnow()
    rows = (
        db.query(Handover)
        .join(SubscriptionRequest)
        .filter(Handover.method == HandoverMethod.APPOINTMENT, Handover.confirmed_at.is_not(None),
                Handover.reminder_sent_at.is_(None), SubscriptionRequest.status == RequestStatus.HANDOVER_PENDING,
                Handover.confirmed_at > now, Handover.confirmed_at <= now + timedelta(hours=1))
        .all()
    )
    for h in rows:
        req = h.request
        requester = db.query(User).filter(User.employee_id == req.employee_id).first()
        notify(db, [requester, *dmd_users(db)], "handover.reminder",
               f"In 1 hour: {req.employee.name} collects {req.tool_name} access",
               f"{h.confirmed_at:%H:%M} UTC, {h.location or 'DMD office'}", f"/requests/{req.id}")
        h.reminder_sent_at = now
    db.commit()
    return len(rows)


def escalations(db: Session, day: date) -> int:
    sla = int(settings_store.get_all(db)["approval_sla_days"])
    cutoff = utcnow() - timedelta(days=sla)
    rows = (
        db.query(SubscriptionRequest)
        .filter(SubscriptionRequest.status.in_([s for s in OPEN_STATUSES if s != RequestStatus.INFO_NEEDED]),
                SubscriptionRequest.status_changed_at < cutoff)
        .all()
    )
    for req in rows:
        if req.status == RequestStatus.PENDING_MANAGER:
            target = [db.query(User).filter(User.employee_id == req.employee.manager_id).first()]
        else:
            target = dmd_users(db)
        notify(db, target, "request.escalation", f"{req.req_no} has waited more than {sla} working days",
               f"{req.employee.name} — {req.tool_name} {req.plan_name}", f"/approvals/{req.id}")
    db.commit()
    return len(rows)


def expire_assignments(db: Session, day: date) -> int:
    """Seats whose end date has passed become revoke_pending so an admin removes access."""
    rows = (
        db.query(Assignment)
        .filter(Assignment.status == AssignmentStatus.ACTIVE, Assignment.end_date.is_not(None),
                Assignment.end_date <= day)
        .all()
    )
    for a in rows:
        a.status = AssignmentStatus.REVOKE_PENDING
    if rows:
        notify(db, admins(db), "assignment.expired", f"{len(rows)} seat(s) reached their end date",
               "Remove access or renew.", "/subscriptions", email=False)
    db.commit()
    return len(rows)


def dmd_digest(db: Session, day: date) -> int:
    values = settings_store.get_all(db)
    fx = settings_store.fx_rates(values)
    subs = load_subinfos(db)
    s = cost.summary(subs, day, fx, "accrued", values["week_start"], int(values["year_start_month"]),
                     Decimal(values["monthly_budget_bdt"]))
    pending = db.query(SubscriptionRequest).filter(
        SubscriptionRequest.status.in_([RequestStatus.PENDING_DMD, RequestStatus.ON_HOLD])).count()
    handovers = db.query(SubscriptionRequest).filter(
        SubscriptionRequest.status.in_([RequestStatus.APPROVED, RequestStatus.HANDOVER_PENDING])).count()
    body = (
        f"Spend today: BDT {s['today']['amount']}\n"
        f"This month: BDT {s['month']['amount']} (projected BDT {s['projected_month']})\n"
        f"This year: BDT {s['year']['amount']}\n"
        f"Waiting for your approval: {pending}\n"
        f"Handovers pending: {handovers}\n"
    )
    for user in dmd_users(db):
        send_email(user.employee.email, f"SMP daily digest — {day:%d %b %Y}", body)
    return len(dmd_users(db))


JOBS = {
    "daily-cost": lambda db, day: daily_cost(db, day - timedelta(days=1)),
    "expected-charges": expected_charges,
    "renewal-reminders": renewal_reminders,
    "appointment-reminders": lambda db, day: appointment_reminders(db),
    "escalations": escalations,
    "expire-assignments": expire_assignments,
    "dmd-digest": dmd_digest,
}

"""Smart insights: charge anomalies and savings opportunities."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.enums import AssignmentStatus, RequestStatus, SubscriptionStatus
from app.models import Subscription, SubscriptionRequest, VendorPlan
from app.services import settings_store
from app.services.cost import estimate_request_cost, q

ANOMALY_THRESHOLD = Decimal("0.15")  # 15% above the expected charge
CONSOLIDATE_MIN = 3                   # individual seats of one tool in one unit before suggesting a team plan
UNRECEIVED_DAYS = 30


def charge_anomaly(sub, amount_original: Decimal, currency: str) -> str | None:
    """Return a note when a recorded charge is more than 15% above what the subscription should cost."""
    if sub.billing_cycle not in ("monthly", "yearly") or currency != sub.currency:
        return None
    expected = Decimal(sub.cost_per_cycle or 0)
    if expected <= 0:
        return None
    amount = Decimal(amount_original)
    if amount > expected * (1 + ANOMALY_THRESHOLD):
        pct = (amount - expected) / expected * 100
        return f"Charged {amount} {currency}, expected {expected} {currency} (+{pct:.0f}%) — check for a plan change or extra seats"
    return None


def _monthly_bdt(cost_per_cycle, currency, cycle, seats, fx) -> Decimal:
    return estimate_request_cost(Decimal(cost_per_cycle), currency, cycle, seats, fx)["monthly_bdt"]


def savings(db: Session, unit_id: int | None = None) -> dict:
    """Savings opportunities, biggest first. unit_id limits to one unit."""
    fx = settings_store.fx_rates(settings_store.get_all(db))
    query = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE)
    if unit_id is not None:
        query = query.filter(Subscription.unit_id == unit_id)
    subs = query.all()
    items: list[dict] = []

    # 1. empty seats
    for s in subs:
        if s.billing_cycle not in ("monthly", "yearly") or s.seats_free <= 0:
            continue
        per_seat = Decimal(s.cost_per_cycle) / max(s.seats_total, 1)
        saving = _monthly_bdt(per_seat, s.currency, s.billing_cycle, s.seats_free, fx)
        items.append({
            "type": "empty_seats", "subscription_id": s.id, "owner": s.owner_label,
            "title": f"{s.seats_free} empty seat(s) on {s.vendor.name} {s.plan_name}",
            "detail": f"{s.seats_used} of {s.seats_total} seats used. Reduce seats or give them to people who asked.",
            "monthly_saving_bdt": saving,
        })

    # 2. seats of people who left / expired (revoke pending) still costing
    for s in subs:
        pending = [a for a in s.assignments if a.status == AssignmentStatus.REVOKE_PENDING]
        if not pending or s.billing_cycle not in ("monthly", "yearly"):
            continue
        per_seat = Decimal(s.cost_per_cycle) / max(s.seats_total, 1)
        items.append({
            "type": "revoke_pending", "subscription_id": s.id, "owner": s.owner_label,
            "title": f"{len(pending)} seat(s) to reclaim on {s.vendor.name} {s.plan_name}",
            "detail": "Holders left, changed team or their period ended: " + ", ".join(a.employee.name for a in pending),
            "monthly_saving_bdt": _monthly_bdt(per_seat, s.currency, s.billing_cycle, len(pending), fx),
        })

    # 3. many individual subscriptions of the same tool in one unit -> team plan
    groups: dict[tuple[int, int], list[Subscription]] = defaultdict(list)
    for s in subs:
        if s.type == "individual" and s.billing_cycle == "monthly":
            groups[(s.unit_id, s.vendor_id)].append(s)
    for (_, vendor_id), group in groups.items():
        seats = sum(s.seats_total for s in group)
        if len(group) < CONSOLIDATE_MIN:
            continue
        team_plan = (
            db.query(VendorPlan)
            .filter(VendorPlan.vendor_id == vendor_id, func.lower(VendorPlan.plan_name).like("%team%"))
            .first()
        )
        current = sum((_monthly_bdt(s.cost_per_cycle, s.currency, s.billing_cycle, 1, fx) for s in group), Decimal("0"))
        if team_plan:
            team_cost = _monthly_bdt(team_plan.default_cost, team_plan.currency, team_plan.billing_cycle, seats, fx)
            saving = current - team_cost
            detail = (f"{len(group)} separate {group[0].vendor.name} subscriptions ({seats} seats) cost BDT {current:,.0f}/month. "
                      f"'{team_plan.plan_name}' for {seats} seats is about BDT {team_cost:,.0f}/month and adds central admin.")
        else:
            saving = Decimal("0")
            detail = (f"{len(group)} separate {group[0].vendor.name} subscriptions in one unit — "
                      "a team/business plan would give one bill, central admin and easier seat moves.")
        items.append({
            "type": "consolidate", "subscription_id": None, "owner": group[0].unit_code,
            "title": f"Combine {len(group)} {group[0].vendor.name} subscriptions into a team plan",
            "detail": detail, "monthly_saving_bdt": max(saving, Decimal("0")),
        })

    # 4. approved access never confirmed after 30 days
    cutoff = utcnow() - timedelta(days=UNRECEIVED_DAYS)
    stale = db.query(SubscriptionRequest).filter(SubscriptionRequest.status == RequestStatus.HANDOVER_PENDING,
                                                 SubscriptionRequest.status_changed_at < cutoff)
    if unit_id is not None:
        stale = stale.filter(SubscriptionRequest.unit_id == unit_id)
    for r in stale.all():
        items.append({
            "type": "unconfirmed_access", "subscription_id": r.subscription_id, "owner": r.snapshot.get("unit"),
            "title": f"{r.req_no}: {r.employee.name} never confirmed {r.tool_name} access",
            "detail": f"Handover pending for more than {UNRECEIVED_DAYS} days — follow up or take the seat back.",
            "monthly_saving_bdt": Decimal("0"),
        })

    items.sort(key=lambda i: i["monthly_saving_bdt"], reverse=True)
    for i in items:
        i["monthly_saving_bdt"] = q(i["monthly_saving_bdt"])
    total = sum((i["monthly_saving_bdt"] for i in items), Decimal("0"))
    return {"items": items, "total_monthly_saving_bdt": q(total), "total_yearly_saving_bdt": q(total * 12)}

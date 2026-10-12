"""Demo data: python -m scripts.seed

Creates DMD Sir, a delegate, a manager and two employees (password for all: ChangeMe#2026),
a card, the common AI vendors with plans, and two running subscriptions with charges.
"""

from datetime import date, timedelta
from decimal import Decimal

import app.models  # noqa: F401
from app.core.clock import today
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Assignment, Card, CardCharge, Employee, Subscription, User, Vendor, VendorPlan
from app.services.cost import charge_bdt

PASSWORD = "ChangeMe#2026"

VENDORS = [
    ("ChatGPT", "ai", "https://chat.openai.com", [("Plus", "20", "monthly"), ("Team", "30", "monthly")]),
    ("Claude", "ai", "https://claude.ai", [("Pro", "20", "monthly"), ("Max", "100", "monthly"), ("Team", "30", "monthly")]),
    ("DeepSeek", "ai", "https://platform.deepseek.com", [("API credit", "10", "usage")]),
    ("Gemini", "ai", "https://gemini.google.com", [("Advanced", "20", "monthly")]),
    ("GitHub Copilot", "dev", "https://github.com/features/copilot", [("Pro", "10", "monthly")]),
    ("Midjourney", "design", "https://midjourney.com", [("Standard", "30", "monthly")]),
    ("Canva", "design", "https://canva.com", [("Pro", "120", "yearly")]),
    ("Grammarly", "productivity", "https://grammarly.com", [("Pro", "144", "yearly")]),
]


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Employee).first():
            print("Database already has data — seed skipped")
            return

        def emp(code, name, desig, dept, team, unit, manager=None, email=None):
            e = Employee(emp_code=code, name=name, designation=desig, department=dept, team=team, unit=unit,
                         manager_id=manager.id if manager else None, email=email or f"{code.lower()}@example.com")
            db.add(e)
            db.flush()
            return e

        dmd = emp("DMD001", "DMD Sir", "Deputy Managing Director", "Management", "Board", "BMD")
        pa = emp("BMD010", "Nusrat Jahan", "Executive Assistant", "Management", "DMD Office", "BMD", dmd)
        mgr = emp("AES100", "Rafiq Ahmed", "Head of IT", "IT", "Software", "AES", dmd)
        dev = emp("AES101", "Bappy Hossain", "Software Engineer", "IT", "Software", "AES", mgr)
        mkt = emp("BMD201", "Sadia Islam", "Marketing Executive", "Marketing", "Digital", "BMD", dmd)

        for e, roles, reveal in ((dmd, "dmd,employee", True), (pa, "delegate,employee", False),
                                 (mgr, "employee", False), (dev, "employee", False), (mkt, "employee", False)):
            db.add(User(employee_id=e.id, password_hash=hash_password(PASSWORD), roles=roles, can_reveal_vault=reveal))

        card = Card(label="DMD Sir — Visa", holder_name="DMD Sir", last4="4417")
        db.add(card)

        vendors = {}
        for name, cat, site, plans in VENDORS:
            v = Vendor(name=name, category=cat, website=site)
            v.plans = [VendorPlan(plan_name=p, default_cost=Decimal(c), currency="USD", billing_cycle=cy) for p, c, cy in plans]
            db.add(v)
            vendors[name] = v
        db.flush()

        t = today()
        start = (t.replace(day=1) - timedelta(days=60)).replace(day=5)
        claude = Subscription(vendor_id=vendors["Claude"].id, plan_name="Team", type="team", seats_total=3,
                              cost_per_cycle=Decimal("90"), currency="USD", billing_cycle="monthly", start_date=start,
                              next_renewal_date=date(t.year, t.month, 5) if t.day < 5 else _next_month_5(t),
                              card_id=card.id, account_email="ai-team@example.com", unit="AES", department="IT")
        chatgpt = Subscription(vendor_id=vendors["ChatGPT"].id, plan_name="Plus", seats_total=1,
                               cost_per_cycle=Decimal("20"), currency="USD", billing_cycle="monthly", start_date=start,
                               next_renewal_date=date(t.year, t.month, 5) if t.day < 5 else _next_month_5(t),
                               card_id=card.id, account_email="marketing@example.com", unit="BMD", department="Marketing")
        db.add_all([claude, chatgpt])
        db.flush()
        db.add_all([
            Assignment(subscription_id=claude.id, employee_id=dev.id, start_date=start),
            Assignment(subscription_id=claude.id, employee_id=mgr.id, start_date=start),
            Assignment(subscription_id=chatgpt.id, employee_id=mkt.id, start_date=start),
        ])
        rate = Decimal("122.50")
        charge_day = start
        while charge_day <= t:
            for sub in (claude, chatgpt):
                db.add(CardCharge(subscription_id=sub.id, card_id=card.id, charge_date=charge_day,
                                  amount_original=sub.cost_per_cycle, currency="USD", fx_rate=rate,
                                  bank_fee_bdt=Decimal("35"),
                                  amount_bdt=charge_bdt(sub.cost_per_cycle, rate, Decimal("35"))))
            charge_day = _next_month_5(charge_day)
        db.commit()
    print(f"Seeded. Log in as DMD001 / BMD010 / AES100 / AES101 / BMD201 with password {PASSWORD}")
    print("DMD and delegate logins need an email OTP — with no SMTP configured it is printed in the server log.")


def _next_month_5(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 5)


if __name__ == "__main__":
    main()

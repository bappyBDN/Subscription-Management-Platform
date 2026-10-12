"""Demo data: python -m scripts.seed

Creates units BMD and AES with departments and budgets, DMD Sir, a delegate, a unit/department head and
three employees (password for all: ChangeMe#2026), a card, the common AI vendors with plans, and three
running subscriptions (one unit-wide, two department-owned) with charges.
"""

from datetime import date, timedelta
from decimal import Decimal

import app.models  # noqa: F401
from app.core.clock import today
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (Assignment, Card, CardCharge, Department, Employee, OrgUnit, Subscription, User, Vendor,
                        VendorPlan)
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

        # ---- organization: units, departments, budgets
        bmd = OrgUnit(code="BMD", name="BMD", monthly_budget_bdt=Decimal("30000"))
        aes = OrgUnit(code="AES", name="AES", monthly_budget_bdt=Decimal("60000"))
        db.add_all([bmd, aes])
        db.flush()
        depts = {}
        for unit, name, budget in ((bmd, "Management", "10000"), (bmd, "Marketing", "15000"),
                                   (aes, "IT", "40000"), (aes, "Finance", "15000")):
            d = Department(unit_id=unit.id, name=name, monthly_budget_bdt=Decimal(budget), cost_center=f"{unit.code}-{name[:3].upper()}")
            db.add(d)
            depts[(unit.code, name)] = d
        db.flush()

        def emp(code, name, desig, unit, dept, team, manager=None):
            e = Employee(emp_code=code, name=name, designation=desig, unit_id=unit.id,
                         department_id=depts[(unit.code, dept)].id, team=team,
                         manager_id=manager.id if manager else None, email=f"{code.lower()}@example.com")
            db.add(e)
            db.flush()
            return e

        dmd = emp("DMD001", "DMD Sir", "Deputy Managing Director", bmd, "Management", "Board")
        pa = emp("BMD010", "Nusrat Jahan", "Executive Assistant", bmd, "Management", "DMD Office", dmd)
        mgr = emp("AES100", "Rafiq Ahmed", "Head of IT", aes, "IT", "Software", dmd)
        dev = emp("AES101", "Bappy Hossain", "Software Engineer", aes, "IT", "Software", mgr)
        fin = emp("AES301", "Karim Uddin", "Accounts Officer", aes, "Finance", "Accounts", dmd)
        mkt = emp("BMD201", "Sadia Islam", "Marketing Executive", bmd, "Marketing", "Digital", dmd)

        # heads: Rafiq heads AES unit and its IT department; Sadia heads Marketing
        aes.head_employee_id = mgr.id
        depts[("AES", "IT")].head_employee_id = mgr.id
        depts[("BMD", "Marketing")].head_employee_id = mkt.id

        for e, roles, reveal in ((dmd, "dmd,employee", True), (pa, "delegate,employee", False),
                                 (mgr, "employee", False), (dev, "employee", False), (fin, "employee", False),
                                 (mkt, "employee", False)):
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
        renew = date(t.year, t.month, 5) if t.day < 5 else _next_month_5(t)

        def sub(vendor, plan, seats, cost, unit, dept=None, sub_type="individual", email=None):
            s_ = Subscription(vendor_id=vendors[vendor].id, plan_name=plan, type=sub_type, seats_total=seats,
                              cost_per_cycle=Decimal(cost), currency="USD", billing_cycle="monthly", start_date=start,
                              next_renewal_date=renew, card_id=card.id, account_email=email,
                              owner_scope="department" if dept else "unit", unit_id=unit.id,
                              department_id=depts[(unit.code, dept)].id if dept else None)
            db.add(s_)
            db.flush()
            return s_

        # AES: Claude Team shared by the whole unit; Copilot owned by IT
        claude = sub("Claude", "Team", 3, "90", aes, sub_type="team", email="ai-team@example.com")
        copilot = sub("GitHub Copilot", "Pro", 1, "10", aes, "IT")
        # BMD: ChatGPT Plus owned by Marketing
        chatgpt = sub("ChatGPT", "Plus", 1, "20", bmd, "Marketing", email="marketing@example.com")
        for s_, holder in ((claude, dev), (claude, fin), (copilot, dev), (chatgpt, mkt)):
            s_.assignments.append(Assignment(employee_id=holder.id, start_date=start))

        rate = Decimal("122.50")
        charge_day = start
        while charge_day <= t:
            for s_ in (claude, copilot, chatgpt):
                db.add(CardCharge(subscription_id=s_.id, card_id=card.id, charge_date=charge_day,
                                  amount_original=s_.cost_per_cycle, currency="USD", fx_rate=rate,
                                  bank_fee_bdt=Decimal("35"),
                                  amount_bdt=charge_bdt(s_.cost_per_cycle, rate, Decimal("35")),
                                  unit_id=s_.unit_id, department_id=s_.department_id))
            charge_day = _next_month_5(charge_day)
        db.commit()
    print(f"Seeded. Log in as DMD001 / BMD010 / AES100 / AES101 / AES301 / BMD201 with password {PASSWORD}")
    print("DMD and delegate logins need an email OTP — with no SMTP configured it is printed in the server log.")


def _next_month_5(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 5)


if __name__ == "__main__":
    main()

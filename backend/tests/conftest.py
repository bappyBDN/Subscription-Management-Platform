import base64
import os
import re
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("VAULT_KEY", base64.b64encode(b"k" * 32).decode())

import pytest  # noqa: E402

try:  # the API tests need the full stack; the pure unit tests do not
    import bcrypt  # noqa: F401
    import jwt  # noqa: F401
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    HAVE_STACK = True
except ImportError:  # pragma: no cover
    HAVE_STACK = False

PASSWORD = "Secret#2026"

# Skip collecting the API test modules entirely when the stack is missing
collect_ignore_glob = [] if HAVE_STACK else ["test_api_*.py"]


if HAVE_STACK:
    import app.models  # noqa: F401
    from app.core.clock import today
    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app as fastapi_app
    from app.models import (Card, CardCharge, Department, Employee, OrgUnit, Subscription, User, Vendor,
                            VendorPlan)
    from app.services import mailer
    from app.services.cost import charge_bdt

    @pytest.fixture()
    def db():
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        session = Session()
        yield session
        session.close()
        engine.dispose()

    @pytest.fixture()
    def client(db):
        def _get_db():
            yield db

        fastapi_app.dependency_overrides[get_db] = _get_db
        mailer.OUTBOX.clear()
        with TestClient(fastapi_app) as c:
            yield c
        fastapi_app.dependency_overrides.clear()

    @pytest.fixture()
    def org(db):
        """Units AES and BMD with departments; DMD Sir, a delegate, an IT manager (also head of the AES unit
        and of IT) with two reports, a Finance employee in AES, and a Marketing employee in BMD."""
        aes = OrgUnit(code="AES", name="AES", monthly_budget_bdt=Decimal("20000"))
        bmd = OrgUnit(code="BMD", name="BMD")
        db.add_all([aes, bmd])
        db.flush()
        depts = {
            "it": Department(unit_id=aes.id, name="IT", monthly_budget_bdt=Decimal("12000")),
            "finance": Department(unit_id=aes.id, name="Finance"),
            "marketing": Department(unit_id=bmd.id, name="Marketing"),
            "management": Department(unit_id=bmd.id, name="Management"),
        }
        db.add_all(depts.values())
        db.flush()

        def emp(code, name, unit, dept, manager=None, team="Team"):
            e = Employee(emp_code=code, name=name, designation="Staff", unit_id=unit.id,
                         department_id=depts[dept].id, team=team,
                         manager_id=manager.id if manager else None, email=f"{code.lower()}@test.local")
            db.add(e)
            db.flush()
            return e

        dmd = emp("DMD1", "DMD Sir", bmd, "management")
        delegate = emp("PA1", "Delegate PA", bmd, "management", dmd)
        mgr = emp("M1", "Manager One", aes, "it", dmd, team="Software")
        staff = emp("E1", "Employee One", aes, "it", mgr, team="Software")
        other = emp("E2", "Other Team", bmd, "marketing", dmd)
        colleague = emp("C1", "Rahim Vai", aes, "it", mgr, team="Software")
        fin = emp("F1", "Finance One", aes, "finance", dmd)
        aes.head_employee_id = mgr.id
        depts["it"].head_employee_id = mgr.id
        users = {}
        for key, e, roles in (("dmd", dmd, "dmd,employee"), ("delegate", delegate, "delegate,employee"),
                              ("mgr", mgr, "employee"), ("staff", staff, "employee"), ("other", other, "employee"),
                              ("colleague", colleague, "employee"), ("fin", fin, "employee")):
            u = User(employee_id=e.id, password_hash=hash_password(PASSWORD), roles=roles,
                     can_reveal_vault=(key == "dmd"))
            db.add(u)
            users[key] = u
        claude = Vendor(name="Claude", category="ai")
        claude.plans = [VendorPlan(plan_name="Pro", default_cost=Decimal("20"), currency="USD", billing_cycle="monthly"),
                        VendorPlan(plan_name="Team", default_cost=Decimal("30"), currency="USD", billing_cycle="monthly")]
        chatgpt = Vendor(name="ChatGPT", category="ai")
        copilot = Vendor(name="GitHub Copilot", category="dev")
        card = Card(label="DMD Visa", holder_name="DMD Sir", last4="4417")
        db.add_all([claude, chatgpt, copilot, card])
        db.commit()
        return {"users": users, "emps": {"dmd": dmd, "delegate": delegate, "mgr": mgr, "staff": staff,
                                         "other": other, "colleague": colleague, "fin": fin},
                "units": {"aes": aes, "bmd": bmd}, "depts": depts,
                "claude": claude, "chatgpt": chatgpt, "copilot": copilot, "card": card}

    def make_subscription(db, org, vendor, plan, seats, cost, unit, dept=None, charge_fx=Decimal("120")):
        start = today().replace(day=1) - timedelta(days=40)
        sub = Subscription(vendor_id=vendor.id, plan_name=plan, type="team" if seats > 1 else "individual",
                           seats_total=seats, cost_per_cycle=Decimal(cost), currency="USD", billing_cycle="monthly",
                           start_date=start, next_renewal_date=today() + timedelta(days=7), card_id=org["card"].id,
                           owner_scope="department" if dept else "unit", unit_id=unit.id,
                           department_id=dept.id if dept else None)
        db.add(sub)
        db.flush()
        db.add(CardCharge(subscription_id=sub.id, card_id=org["card"].id, charge_date=start,
                          amount_original=Decimal(cost), currency="USD", fx_rate=charge_fx,
                          amount_bdt=charge_bdt(Decimal(cost), charge_fx), unit_id=sub.unit_id,
                          department_id=sub.department_id))
        db.commit()
        return sub

    @pytest.fixture()
    def subscription(db, org):
        """AES unit-wide Claude Team, 3 seats, USD 90/month (BDT 10,800 at 120)."""
        return make_subscription(db, org, org["claude"], "Team", 3, "90", org["units"]["aes"])

    @pytest.fixture()
    def it_subscription(db, org):
        """GitHub Copilot owned by AES / IT, 1 seat, USD 10/month."""
        return make_subscription(db, org, org["copilot"], "Pro", 1, "10", org["units"]["aes"], org["depts"]["it"])

    @pytest.fixture()
    def marketing_subscription(db, org):
        """ChatGPT Plus owned by BMD / Marketing."""
        return make_subscription(db, org, org["chatgpt"], "Plus", 1, "20", org["units"]["bmd"], org["depts"]["marketing"])

    def last_otp(email: str) -> str:
        for msg in reversed(mailer.OUTBOX):
            if msg["to"] == email:
                found = re.search(r"\b(\d{6})\b", msg["body"])
                if found:
                    return found.group(1)
        raise AssertionError(f"no OTP mailed to {email}")

    def login(client, code: str) -> dict:
        r = client.post("/api/auth/login", json={"username": code, "password": PASSWORD})
        assert r.status_code == 200, r.text
        body = r.json()
        if body["otp_required"]:
            r = client.post("/api/auth/verify-otp",
                            json={"otp_token": body["otp_token"], "code": last_otp(f"{code.lower()}@test.local")})
            assert r.status_code == 200, r.text
            body = r.json()
        return {"Authorization": f"Bearer {body['access_token']}"}

    @pytest.fixture()
    def auth(client, org):
        cache: dict[str, dict] = {}

        def _auth(key: str) -> dict:
            if key not in cache:
                cache[key] = login(client, org["emps"][key].emp_code)
            return cache[key]

        return _auth


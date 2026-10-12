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
    from app.models import Card, CardCharge, Employee, Subscription, User, Vendor, VendorPlan
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
        """DMD Sir, a delegate, a manager with one report, an employee without manager, a colleague."""

        def emp(code, name, unit="AES", manager=None, dept="IT", team="Software"):
            e = Employee(emp_code=code, name=name, designation="Staff", department=dept, team=team, unit=unit,
                         manager_id=manager.id if manager else None, email=f"{code.lower()}@test.local")
            db.add(e)
            db.flush()
            return e

        dmd = emp("DMD1", "DMD Sir", "BMD", dept="Management", team="Board")
        delegate = emp("PA1", "Delegate PA", "BMD", dmd, dept="Management", team="DMD Office")
        mgr = emp("M1", "Manager One", manager=dmd)
        staff = emp("E1", "Employee One", manager=mgr)
        other = emp("E2", "Other Team", "BMD", manager=dmd, dept="Marketing", team="Digital")
        colleague = emp("C1", "Rahim Vai", manager=mgr)
        users = {}
        for key, e, roles in (("dmd", dmd, "dmd,employee"), ("delegate", delegate, "delegate,employee"),
                              ("mgr", mgr, "employee"), ("staff", staff, "employee"), ("other", other, "employee"),
                              ("colleague", colleague, "employee")):
            u = User(employee_id=e.id, password_hash=hash_password(PASSWORD), roles=roles,
                     can_reveal_vault=(key == "dmd"))
            db.add(u)
            users[key] = u
        claude = Vendor(name="Claude", category="ai")
        claude.plans = [VendorPlan(plan_name="Pro", default_cost=Decimal("20"), currency="USD", billing_cycle="monthly")]
        chatgpt = Vendor(name="ChatGPT", category="ai")
        card = Card(label="DMD Visa", holder_name="DMD Sir", last4="4417")
        db.add_all([claude, chatgpt, card])
        db.commit()
        return {"users": users, "emps": {"dmd": dmd, "delegate": delegate, "mgr": mgr, "staff": staff,
                                         "other": other, "colleague": colleague},
                "claude": claude, "chatgpt": chatgpt, "card": card}

    @pytest.fixture()
    def subscription(db, org):
        start = today().replace(day=1) - timedelta(days=40)
        sub = Subscription(vendor_id=org["claude"].id, plan_name="Team", type="team", seats_total=3,
                           cost_per_cycle=Decimal("90"), currency="USD", billing_cycle="monthly", start_date=start,
                           next_renewal_date=today() + timedelta(days=7), card_id=org["card"].id,
                           unit="AES", department="IT")
        db.add(sub)
        db.flush()
        db.add(CardCharge(subscription_id=sub.id, card_id=org["card"].id, charge_date=start,
                          amount_original=Decimal("90"), currency="USD", fx_rate=Decimal("120"),
                          amount_bdt=charge_bdt(Decimal("90"), Decimal("120"))))
        db.commit()
        return sub

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


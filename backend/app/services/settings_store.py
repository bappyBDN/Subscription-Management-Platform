from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULTS: dict[str, str] = {
    "week_start": "sat",
    "year_start_month": "1",
    "monthly_budget_bdt": "0",
    "default_fx_rate_usd": "122.00",
    "default_fx_rate_cny": "17.00",
    "approval_sla_days": "2",
    "allow_urgent_override": "true",
}


def get_all(db: Session) -> dict[str, str]:
    values = dict(DEFAULTS)
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def put(db: Session, updates: dict[str, str]) -> dict[str, str]:
    for key, value in updates.items():
        if key not in DEFAULTS:
            raise KeyError(key)
        row = db.get(Setting, key)
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
    db.flush()
    return get_all(db)


def fx_rates(values: dict[str, str]) -> dict[str, Decimal]:
    return {"USD": Decimal(values["default_fx_rate_usd"]), "CNY": Decimal(values["default_fx_rate_cny"]),
            "BDT": Decimal("1")}


def as_bool(value: str) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}

"""Metered usage: daily cost of a pay-as-you-go API account, measured from the provider's balance.

DeepSeek has no usage-history API, only GET /user/balance. Each sync records the balance, and the drop
since the previous sync is the spend of the day the sync runs on — so run it at least once a day
(`python -m app.jobs deepseek-usage`). A rise in balance is a top-up, never negative spend.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import get_settings
from app.enums import SubscriptionStatus
from app.models import Subscription, UsageDay
from app.services import cost, settings_store

PROVIDERS = {"deepseek": "DeepSeek API"}
log = logging.getLogger("smp.usage")


class UsageError(Exception):
    pass


def fetch_deepseek_balances(api_key: str, base_url: str) -> dict[str, Decimal]:
    """Account balance per currency, e.g. {"USD": Decimal("41.27")}."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/user/balance",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
        balances = {str(i["currency"]).upper(): Decimal(str(i["total_balance"])) for i in body["balance_infos"]}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise UsageError("DeepSeek rejected the API key — check DEEPSEEK_API_KEY in backend/.env") from None
        raise UsageError(f"DeepSeek answered HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UsageError(f"Could not reach DeepSeek: {exc}") from None
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise UsageError("DeepSeek sent a balance this version does not understand") from None
    if not balances:
        raise UsageError("DeepSeek returned no balance for this account")
    return balances


def record_balance(db: Session, sub: Subscription, day: date, balance: Decimal, currency: str,
                   fx_rates: dict[str, Decimal]) -> UsageDay:
    """Store today's balance; the drop since the last recorded balance is added to `day`'s usage."""
    rate = fx_rates.get(currency)
    if not rate:
        raise UsageError(f"No exchange rate for {currency} — only USD, CNY and BDT accounts are supported")
    last = (db.query(UsageDay).filter(UsageDay.subscription_id == sub.id, UsageDay.usage_date <= day)
            .order_by(UsageDay.usage_date.desc()).first())
    row = last if last is not None and last.usage_date == day else None
    if row is None:
        row = UsageDay(subscription_id=sub.id, usage_date=day, currency=currency, amount_original=Decimal("0"),
                       topped_up=Decimal("0"))
        db.add(row)
    if last is None:
        pass  # first sync: a baseline, nothing to compare with yet
    elif last.currency != currency:  # the account switched currency: start again from this balance
        row.amount_original, row.topped_up = Decimal("0"), Decimal("0")
    else:
        drop = Decimal(last.balance_end) - balance
        if drop >= 0:
            row.amount_original = Decimal(row.amount_original) + drop
        else:
            row.topped_up = Decimal(row.topped_up) - drop
    row.currency = currency
    row.fx_rate = rate
    row.amount_bdt = cost.q(Decimal(row.amount_original) * rate)
    row.balance_end = balance
    row.synced_at = utcnow()
    db.flush()
    return row


def metered_subscription(db: Session, provider: str) -> Subscription | None:
    """One account, one subscription: the oldest active subscription metered by this provider."""
    return (db.query(Subscription)
            .filter(Subscription.usage_provider == provider, Subscription.status == SubscriptionStatus.ACTIVE)
            .order_by(Subscription.id).first())


def usage_out(row: UsageDay | None) -> dict | None:
    if row is None:
        return None
    return {"usage_date": row.usage_date, "amount_original": row.amount_original, "currency": row.currency,
            "fx_rate": row.fx_rate, "amount_bdt": row.amount_bdt, "balance": row.balance_end,
            "topped_up": row.topped_up, "synced_at": row.synced_at}


def status(db: Session) -> dict:
    sub = metered_subscription(db, "deepseek")
    last = None
    if sub is not None:
        last = (db.query(UsageDay).filter(UsageDay.subscription_id == sub.id)
                .order_by(UsageDay.usage_date.desc()).first())
    return {
        "provider": "deepseek",
        "key_configured": bool(get_settings().deepseek_api_key),
        "subscription_id": sub.id if sub else None,
        "subscription_name": f"{sub.vendor.name} {sub.plan_name}" if sub else None,
        "team_name": sub.team_name if sub else None,
        "last": usage_out(last),
    }


def sync_deepseek(db: Session, day: date) -> dict:
    """Read the DeepSeek balance and book the spend since the last sync on `day`."""
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise UsageError("DEEPSEEK_API_KEY is not set in backend/.env")
    sub = metered_subscription(db, "deepseek")
    if sub is None:
        raise UsageError("No active subscription has usage metering set to DeepSeek API")
    balances = fetch_deepseek_balances(settings.deepseek_api_key, settings.deepseek_api_url)
    currency = sub.currency if sub.currency in balances else next(iter(balances))
    row = record_balance(db, sub, day, balances[currency], currency,
                         settings_store.fx_rates(settings_store.get_all(db)))
    db.commit()
    return {"subscription_id": sub.id, **usage_out(row)}


def start_auto_sync() -> threading.Event | None:
    """Read the DeepSeek balance in the background while the app runs, so usage is booked on the day it
    happens without a cron job. Returns the event that stops it, or None when it is switched off."""
    settings = get_settings()
    if not settings.deepseek_api_key or settings.deepseek_sync_minutes <= 0:
        return None
    from app.core.clock import today
    from app.db.session import SessionLocal

    stop = threading.Event()

    def loop() -> None:
        while True:
            try:
                with SessionLocal() as db:
                    row = sync_deepseek(db, today())
                log.info("DeepSeek balance %s %s, used today %s", row["balance"], row["currency"],
                         row["amount_original"])
            except UsageError as exc:
                log.warning("DeepSeek usage not read: %s", exc)
            except Exception:  # never let a database or network hiccup end the loop
                log.exception("DeepSeek usage sync failed")
            if stop.wait(settings.deepseek_sync_minutes * 60):
                return

    threading.Thread(target=loop, name="deepseek-usage", daemon=True).start()
    return stop

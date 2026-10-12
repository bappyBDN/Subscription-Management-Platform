from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.catalog import Card, Vendor
from app.enums import AssignmentStatus, SubscriptionStatus
from app.models.people import Employee


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    plan_name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="individual")
    seats_total: Mapped[int] = mapped_column(Integer, default=1)
    cost_per_cycle: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    start_date: Mapped[date] = mapped_column(Date)
    next_renewal_date: Mapped[date | None] = mapped_column(Date, index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"))
    account_email: Mapped[str | None] = mapped_column(String(150))
    unit: Mapped[str | None] = mapped_column(String(10), index=True)
    department: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default=SubscriptionStatus.ACTIVE, index=True)
    cancelled_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    vendor: Mapped[Vendor] = relationship()
    card: Mapped[Card | None] = relationship()
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="subscription")
    charges: Mapped[list["CardCharge"]] = relationship(back_populates="subscription")

    @property
    def seats_used(self) -> int:
        return sum(1 for a in self.assignments if a.status != AssignmentStatus.REVOKED)

    @property
    def seats_free(self) -> int:
        return max(self.seats_total - self.seats_used, 0)


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=AssignmentStatus.ACTIVE)

    subscription: Mapped[Subscription] = relationship(back_populates="assignments")
    employee: Mapped[Employee] = relationship()


class CardCharge(TimestampMixin, Base):
    __tablename__ = "card_charges"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"))
    charge_date: Mapped[date] = mapped_column(Date, index=True)
    amount_original: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("1"))
    bank_fee_bdt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    amount_bdt: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    is_expected: Mapped[bool] = mapped_column(Boolean, default=False)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)

    subscription: Mapped[Subscription] = relationship(back_populates="charges")


class DailyCost(Base):
    __tablename__ = "daily_cost"
    __table_args__ = (UniqueConstraint("subscription_id", "cost_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    cost_date: Mapped[date] = mapped_column(Date, index=True)
    amount_bdt: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.enums import AssignmentStatus, OwnerScope, SubscriptionStatus
from app.models.catalog import Card, Vendor
from app.models.org import Department, OrgFunction, OrgUnit, Team
from app.models.people import Employee


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    plan_name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="individual")
    seats_total: Mapped[int] = mapped_column(Integer, default=1)
    # seats the owning team already uses whose holders are not recorded as assignments
    seats_unnamed: Mapped[int | None] = mapped_column(Integer, default=0)
    cost_per_cycle: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly")
    start_date: Mapped[date] = mapped_column(Date)
    next_renewal_date: Mapped[date | None] = mapped_column(Date, index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"))
    account_email: Mapped[str | None] = mapped_column(String(150))
    # ownership: the whole SBU, one department, one function, or shared by several (see `shares`)
    owner_scope: Mapped[str] = mapped_column(String(12), default=OwnerScope.UNIT)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)  # the SBU that buys it
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), index=True)
    # team-owned: only that team's members may request it and its cost is reported for the team, not per person
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    # daily cost is measured from the provider's API (e.g. "deepseek") instead of card charges
    usage_provider: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=SubscriptionStatus.ACTIVE, index=True)
    cancelled_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    vendor: Mapped[Vendor] = relationship()
    card: Mapped[Card | None] = relationship()
    org_unit: Mapped[OrgUnit] = relationship()
    org_department: Mapped[Department | None] = relationship()
    org_function: Mapped[OrgFunction | None] = relationship()
    team: Mapped[Team | None] = relationship()
    shares: Mapped[list["SubscriptionShare"]] = relationship(back_populates="subscription", cascade="all, delete-orphan",
                                                            order_by="SubscriptionShare.id")
    usage_days: Mapped[list["UsageDay"]] = relationship(back_populates="subscription", order_by="UsageDay.usage_date")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="subscription")
    charges: Mapped[list["CardCharge"]] = relationship(back_populates="subscription")

    @property
    def unit_code(self) -> str:
        return self.org_unit.code if self.org_unit else ""

    @property
    def department_name(self) -> str | None:
        return self.org_department.name if self.org_department else None

    @property
    def team_name(self) -> str | None:
        return self.team.name if self.team else None

    @property
    def function_name(self) -> str | None:
        return self.org_function.name if self.org_function else None

    @property
    def owner_label(self) -> str:
        if self.owner_scope == OwnerScope.SHARED:
            label = "Shared: " + ", ".join(s.label for s in self.shares)
        elif self.owner_scope == OwnerScope.FUNCTION and self.org_function:
            label = self.org_function.label
        elif self.owner_scope == OwnerScope.DEPARTMENT and self.org_department:
            label = f"{self.unit_code} / {self.org_department.name}"
        else:
            label = f"{self.unit_code} (SBU-wide)"
        if self.team:
            label = f"{label.removesuffix(' (SBU-wide)')} / {self.team.name} team"
        return label

    def available_to(self, employee: Employee) -> bool:
        """Who may request a seat: the owning team, function, department or SBU, or any sharer's people."""
        if self.team is not None:  # team-owned: the team's members only
            return self.team.has_member(employee)
        if self.owner_scope == OwnerScope.SHARED:
            return any(s.covers(employee) for s in self.shares)
        if self.owner_scope == OwnerScope.FUNCTION:
            return self.function_id is not None and self.function_id == employee.function_id
        if self.owner_scope == OwnerScope.DEPARTMENT:
            return self.department_id is not None and self.department_id == employee.department_id
        return self.unit_id == employee.unit_id

    @property
    def seats_used(self) -> int:
        named = sum(1 for a in self.assignments if a.status != AssignmentStatus.REVOKED)
        return named + (self.seats_unnamed or 0)

    @property
    def seats_free(self) -> int:
        return max(self.seats_total - self.seats_used, 0)


class SubscriptionShare(Base):
    """One sharer of a shared subscription: a whole department, or one function of it (any SBU).
    Each sharer pays for the seats its people hold; empty seats are split equally among the sharers."""

    __tablename__ = "subscription_shares"
    __table_args__ = (UniqueConstraint("subscription_id", "department_id", "function_id", name="uq_share"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), index=True)

    subscription: Mapped[Subscription] = relationship(back_populates="shares")
    department: Mapped[Department] = relationship()
    function: Mapped[OrgFunction | None] = relationship()

    @property
    def label(self) -> str:
        return self.function.label if self.function else self.department.label

    def covers(self, employee: Employee) -> bool:
        if self.function_id is not None:
            return employee.function_id == self.function_id
        return employee.department_id == self.department_id


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
    # owner at the time of payment (moving a subscription later never rewrites history)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_note: Mapped[str | None] = mapped_column(String(255))

    subscription: Mapped[Subscription] = relationship(back_populates="charges")


class DailyCost(Base):
    __tablename__ = "daily_cost"
    __table_args__ = (UniqueConstraint("subscription_id", "cost_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    cost_date: Mapped[date] = mapped_column(Date, index=True)
    amount_bdt: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)


class UsageDay(Base):
    """Measured usage of a metered subscription on one day, taken from the provider's account balance."""

    __tablename__ = "usage_days"
    __table_args__ = (UniqueConstraint("subscription_id", "usage_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    usage_date: Mapped[date] = mapped_column(Date, index=True)
    amount_original: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("1"))
    amount_bdt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    # balance last seen on this day; the next sync's spend is the drop from it
    balance_end: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    topped_up: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    synced_at: Mapped[datetime] = mapped_column(DateTime)

    subscription: Mapped[Subscription] = relationship(back_populates="usage_days")

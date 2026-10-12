from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.catalog import Vendor
from app.enums import RequestStatus
from app.models.people import Employee, User
from app.models.subscriptions import Subscription


class SubscriptionRequest(TimestampMixin, Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    req_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    type: Mapped[str] = mapped_column(String(20))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    other_tool_name: Mapped[str | None] = mapped_column(String(100))
    other_tool_url: Mapped[str | None] = mapped_column(String(255))
    plan_name: Mapped[str] = mapped_column(String(100))
    seats: Mapped[int] = mapped_column(Integer, default=1)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    needed_from: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    expected_use: Mapped[str | None] = mapped_column(Text)
    est_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # per seat per billing cycle
    est_cost_bdt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    est_cost_original: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    est_currency: Mapped[str | None] = mapped_column(String(3))
    est_billing_cycle: Mapped[str | None] = mapped_column(String(20))
    # requester's unit/department at submit time (for reporting); owner_scope = proposals only
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    owner_scope: Mapped[str | None] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.PENDING_MANAGER, index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime)

    employee: Mapped[Employee] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    subscription: Mapped[Subscription | None] = relationship()
    approvals: Mapped[list["Approval"]] = relationship(back_populates="request", order_by="Approval.id")
    handover: Mapped["Handover | None"] = relationship(back_populates="request", uselist=False)

    @property
    def tool_name(self) -> str:
        return self.vendor.name if self.vendor else (self.other_tool_name or "")


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    step: Mapped[str] = mapped_column(String(20))
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))

    request: Mapped[SubscriptionRequest] = relationship(back_populates="approvals")
    approver: Mapped[User] = relationship()


class Handover(TimestampMixin, Base):
    __tablename__ = "handovers"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), unique=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    method: Mapped[str] = mapped_column(String(20))
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    secret_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    login_email: Mapped[str | None] = mapped_column(String(150))
    login_url: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String(150))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    collector_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    collector_note: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    handed_over_at: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    request: Mapped[SubscriptionRequest] = relationship(back_populates="handover")
    subscription: Mapped[Subscription] = relationship()
    collector: Mapped[Employee | None] = relationship()

    @property
    def has_secret(self) -> bool:
        return self.secret_ciphertext is not None

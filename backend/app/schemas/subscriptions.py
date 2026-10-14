from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORM, Currency, Email, SafeText
from app.schemas.masters import CycleT

SubTypeT = Literal["individual", "team", "api_credit", "one_time"]
SubStatusT = Literal["active", "pending_payment", "paused", "cancelled", "expired"]
OwnerScopeT = Literal["unit", "department", "function", "shared"]
UsageProviderT = Literal["deepseek"]


class ShareIn(BaseModel):
    department_id: int
    function_id: int | None = None


class ShareOut(BaseModel):
    department_id: int
    department_name: str
    function_id: int | None
    function_name: str | None
    unit_code: str


class SubscriptionIn(BaseModel):
    vendor_id: int
    plan_name: str = Field(min_length=1, max_length=100)
    type: SubTypeT = "individual"
    seats_total: int = Field(default=1, ge=1, le=1000)
    seats_unnamed: int = Field(default=0, ge=0, le=1000)
    cost_per_cycle: Decimal = Field(ge=0)
    currency: Currency = "USD"
    billing_cycle: CycleT = "monthly"
    start_date: date
    next_renewal_date: date | None = None
    card_id: int | None = None
    account_email: Email | None = None
    owner_scope: OwnerScopeT = "unit"
    unit_id: int
    department_id: int | None = None
    function_id: int | None = None
    shares: list[ShareIn] = []
    team_id: int | None = None
    usage_provider: UsageProviderT | None = None
    status: SubStatusT = "active"
    notes: SafeText | None = None

    @model_validator(mode="after")
    def check_owner(self):
        if self.owner_scope == "department" and not self.department_id:
            raise ValueError("A department-owned subscription needs department_id")
        if self.owner_scope == "function" and not self.function_id:
            raise ValueError("A function-owned subscription needs function_id")
        if self.owner_scope == "shared" and len(self.shares) < 2:
            raise ValueError("A shared subscription needs at least two departments or functions")
        if self.owner_scope != "shared":
            self.shares = []
        if self.seats_unnamed > self.seats_total:
            raise ValueError("Seats in use cannot be more than the seats bought")
        return self


class SubscriptionUpdate(BaseModel):
    plan_name: str | None = None
    type: SubTypeT | None = None
    seats_total: int | None = Field(default=None, ge=1, le=1000)
    seats_unnamed: int | None = Field(default=None, ge=0, le=1000)
    cost_per_cycle: Decimal | None = Field(default=None, ge=0)
    currency: Currency | None = None
    billing_cycle: CycleT | None = None
    start_date: date | None = None
    next_renewal_date: date | None = None
    card_id: int | None = None
    account_email: Email | None = None
    owner_scope: OwnerScopeT | None = None
    unit_id: int | None = None
    department_id: int | None = None
    function_id: int | None = None
    shares: list[ShareIn] | None = None
    team_id: int | None = None
    usage_provider: UsageProviderT | None = None
    status: SubStatusT | None = None
    notes: SafeText | None = None


class CancelIn(BaseModel):
    cancelled_on: date | None = None
    reason: SafeText | None = None


class AssignIn(BaseModel):
    employee_id: int
    start_date: date | None = None
    end_date: date | None = None


class AssignmentOut(ORM):
    id: int
    subscription_id: int
    employee_id: int
    employee_name: str | None = None
    emp_code: str | None = None
    request_id: int | None
    start_date: date
    end_date: date | None
    status: str


class SubscriptionOut(ORM):
    id: int
    vendor_id: int
    vendor_name: str
    plan_name: str
    type: str
    seats_total: int
    seats_used: int
    seats_unnamed: int
    cost_per_cycle: Decimal
    currency: str
    billing_cycle: str
    start_date: date
    next_renewal_date: date | None
    card_id: int | None
    card_last4: str | None
    account_email: str | None
    owner_scope: str
    unit_id: int
    unit_code: str
    department_id: int | None
    department_name: str | None
    function_id: int | None
    function_name: str | None
    shares: list[ShareOut] = []
    team_id: int | None
    team_name: str | None
    usage_provider: str | None
    owner_label: str
    status: str
    cancelled_on: date | None
    notes: str | None


class SubscriptionDetail(SubscriptionOut):
    assignments: list[AssignmentOut] = []


class ChargeIn(BaseModel):
    subscription_id: int
    card_id: int | None = None
    charge_date: date
    amount_original: Decimal = Field(gt=0)
    currency: Currency = "USD"
    fx_rate: Decimal | None = Field(default=None, gt=0, description="Defaults to settings FX rate; 1 for BDT")
    bank_fee_bdt: Decimal = Field(default=Decimal("0"), ge=0)
    reference: SafeText | None = None
    is_expected: bool = False
    reconciled: bool = False


class ChargeUpdate(BaseModel):
    card_id: int | None = None
    charge_date: date | None = None
    amount_original: Decimal | None = Field(default=None, gt=0)
    currency: Currency | None = None
    fx_rate: Decimal | None = Field(default=None, gt=0)
    bank_fee_bdt: Decimal | None = Field(default=None, ge=0)
    reference: SafeText | None = None
    is_expected: bool | None = None
    reconciled: bool | None = None
    anomaly: bool | None = None
    anomaly_note: SafeText | None = None


class ChargeOut(ORM):
    id: int
    subscription_id: int
    card_id: int | None
    charge_date: date
    amount_original: Decimal
    currency: str
    fx_rate: Decimal
    bank_fee_bdt: Decimal
    amount_bdt: Decimal
    reference: str | None
    is_expected: bool
    reconciled: bool
    unit_id: int | None
    department_id: int | None
    anomaly: bool
    anomaly_note: str | None


class ImportResult(BaseModel):
    created: int
    errors: list[dict]


class AvailableSubscriptionOut(BaseModel):
    """A subscription the employee may request a seat on (v2 access rule)."""

    subscription_id: int
    vendor_id: int
    vendor_name: str
    plan_name: str
    owner_scope: str
    owner_label: str
    seats_total: int
    seats_free: int
    billing_cycle: str
    cost_per_seat: Decimal
    currency: str
    monthly_bdt_per_seat: Decimal
    already_holding: bool

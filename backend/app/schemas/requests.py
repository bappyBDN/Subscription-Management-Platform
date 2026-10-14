from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORM, Currency, Email, SafeText
from app.schemas.masters import CycleT

RequestTypeT = Literal["new", "renewal", "upgrade", "cancel", "proposal"]
DecisionT = Literal["recommend", "approve", "reject", "hold", "info", "resume", "override"]


class CostInputs(BaseModel):
    """Optional explicit cost — used for 'Other' tools or plans not in the catalogue."""

    est_cost_per_cycle: Decimal | None = Field(default=None, ge=0)
    est_currency: Currency | None = None
    est_billing_cycle: CycleT | None = None


class RequestIn(CostInputs):
    """v2: seat requests (new / renewal / upgrade / cancel) must point at a subscription the requester's
    unit or department owns. A tool the unit/department does not have yet is a `proposal`."""

    type: RequestTypeT = "new"
    subscription_id: int | None = Field(default=None, description="Subscription to get a seat on / renew / cancel")
    # proposals only
    vendor_id: int | None = None
    other_tool_name: str | None = Field(default=None, max_length=100)
    other_tool_url: str | None = Field(default=None, max_length=255)
    owner_scope: Literal["unit", "department", "function"] = Field(
        default="department", description="Proposal: should the new tool belong to the function, department or whole SBU")
    plan_name: str | None = Field(default=None, max_length=100, description="Filled from the subscription for seat requests")
    seats: int = Field(default=1, ge=1, le=100)
    duration_months: int | None = Field(default=None, description="1, 3, 6, 12 or null for open-ended")
    needed_from: date
    reason: SafeText = Field(min_length=30)
    expected_use: SafeText | None = None

    @model_validator(mode="after")
    def check(self):
        if self.duration_months not in (None, 1, 3, 6, 12):
            raise ValueError("duration_months must be 1, 3, 6, 12 or empty")
        if self.type == "proposal":
            if not self.vendor_id and not self.other_tool_name:
                raise ValueError("Choose a tool or enter the name of the new tool you propose")
            if not self.plan_name:
                raise ValueError("Enter the plan you propose")
        elif not self.subscription_id:
            raise ValueError("Choose one of the subscriptions available to your unit or department "
                             "(or raise a proposal for a new tool)")
        return self


class RequestUpdate(CostInputs):
    vendor_id: int | None = None
    other_tool_name: str | None = None
    other_tool_url: str | None = None
    plan_name: str | None = None
    seats: int | None = Field(default=None, ge=1, le=100)
    duration_months: int | None = None
    needed_from: date | None = None
    reason: SafeText | None = Field(default=None, min_length=30)
    expected_use: SafeText | None = None


class EstimateIn(CostInputs):
    vendor_id: int | None = None
    plan_name: str | None = None
    seats: int = 1


class EstimateOut(BaseModel):
    currency: str
    monthly_original: Decimal
    yearly_original: Decimal
    monthly_bdt: Decimal
    yearly_bdt: Decimal
    fx_rate: Decimal
    billing_cycle: str | None
    source: Literal["catalogue", "provided", "subscription", "unknown"]


class DecisionIn(BaseModel):
    decision: DecisionT
    comment: SafeText | None = None
    # DMD Sir may adjust before approving
    plan_name: str | None = None
    seats: int | None = Field(default=None, ge=1, le=100)
    duration_months: int | None = None


class BulkApproveIn(BaseModel):
    request_ids: list[int] = Field(min_length=1, max_length=100)
    comment: SafeText | None = None


class ApprovalOut(ORM):
    id: int
    step: str
    approver_id: int
    approver_name: str | None = None
    decision: str
    comment: str | None
    from_status: str
    to_status: str
    created_at: datetime


class HandoverBrief(BaseModel):
    id: int
    method: str
    has_secret: bool
    login_email: str | None
    login_url: str | None
    notes: str | None
    proposed_at: datetime | None
    confirmed_at: datetime | None
    location: str | None
    collector_id: int | None
    collector_name: str | None
    collector_note: str | None
    due_date: date | None
    handed_over_at: datetime | None
    received_at: datetime | None


class RequestOut(BaseModel):
    id: int
    req_no: str
    employee_id: int
    snapshot: dict
    type: str
    vendor_id: int | None
    tool_name: str
    other_tool_url: str | None
    plan_name: str
    seats: int
    duration_months: int | None
    needed_from: date
    reason: str
    expected_use: str | None
    est_cost_bdt: Decimal | None
    est_cost_original: Decimal | None
    est_currency: str | None
    est_billing_cycle: str | None
    owner_scope: str | None
    unit_id: int | None
    department_id: int | None
    function_id: int | None = None
    status: str
    subscription_id: int | None
    submitted_at: datetime
    status_changed_at: datetime
    waiting_days: int


class RequestDetail(RequestOut):
    approvals: list[ApprovalOut] = []
    handover: HandoverBrief | None = None
    allowed_actions: list[str] = []


class HandoverIn(BaseModel):
    method: Literal["vault", "appointment", "colleague"]
    subscription_id: int | None = Field(default=None, description="Existing subscription to give a seat on")
    # vault
    secret: str | None = Field(default=None, max_length=4000, description="Password, API key or token")
    login_email: Email | None = None
    login_url: str | None = None
    notes: SafeText | None = None
    # appointment
    confirmed_at: datetime | None = None
    location: str | None = None
    # colleague
    collector_id: int | None = None
    collector_note: SafeText | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def check(self):
        if self.method == "vault" and not self.secret:
            raise ValueError("Enter the password, API key or token for vault delivery")
        if self.method == "colleague" and not self.collector_id:
            raise ValueError("Choose the colleague who will hand over access")
        return self


class SlotIn(BaseModel):
    at: datetime
    location: str | None = None


class RevealIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class RevealOut(BaseModel):
    secret: str
    login_email: str | None
    login_url: str | None
    notes: str | None
    visible_seconds: int = 60


class RotateIn(BaseModel):
    secret: str = Field(min_length=1, max_length=4000)
    notes: SafeText | None = None


class FulfilIn(BaseModel):
    """Link an approved proposal to the subscription that was added to the register for it."""

    subscription_id: int

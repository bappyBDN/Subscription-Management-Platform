from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORM, Currency, Email

CycleT = Literal["monthly", "yearly", "usage", "one_time"]
CategoryT = Literal["ai", "design", "productivity", "dev", "other"]
RoleT = Literal["dmd", "delegate", "employee"]


class EmployeeIn(BaseModel):
    emp_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    designation: str | None = None
    team: str | None = None
    unit_id: int
    department_id: int | None = None
    manager_id: int | None = None
    email: Email | None = None
    phone: str | None = None


class EmployeeUpdate(BaseModel):
    name: str | None = None
    designation: str | None = None
    department_id: int | None = None
    team: str | None = None
    unit_id: int | None = None
    manager_id: int | None = None
    email: Email | None = None
    phone: str | None = None
    status: Literal["active", "inactive"] | None = None


class EmployeeOut(ORM):
    id: int
    emp_code: str
    name: str
    designation: str | None
    unit_id: int
    unit_code: str
    department_id: int | None
    department_name: str | None
    team: str | None
    manager_id: int | None
    email: str | None
    phone: str | None
    status: str


class UserIn(BaseModel):
    employee_id: int
    password: str = Field(min_length=8)
    roles: list[RoleT] = ["employee"]
    can_reveal_vault: bool = False


class UserUpdate(BaseModel):
    roles: list[RoleT] | None = None
    can_reveal_vault: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserOut(ORM):
    id: int
    employee_id: int
    roles: list[str] = Field(validation_alias="role_list")
    can_reveal_vault: bool
    is_active: bool


class PlanIn(BaseModel):
    plan_name: str
    default_cost: Decimal = Field(ge=0)
    currency: Currency = "USD"
    billing_cycle: CycleT = "monthly"


class PlanOut(ORM):
    id: int
    plan_name: str
    default_cost: Decimal
    currency: str
    billing_cycle: str


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: CategoryT = "ai"
    website: str | None = None
    active: bool = True
    plans: list[PlanIn] = []


class VendorUpdate(BaseModel):
    name: str | None = None
    category: CategoryT | None = None
    website: str | None = None
    active: bool | None = None


class VendorOut(ORM):
    id: int
    name: str
    category: str
    website: str | None
    active: bool
    plans: list[PlanOut] = []


class CardIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    holder_name: str = Field(min_length=1, max_length=120)
    last4: str = Field(pattern=r"^\d{4}$")
    active: bool = True


class CardUpdate(BaseModel):
    label: str | None = None
    holder_name: str | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    active: bool | None = None


class CardOut(ORM):
    id: int
    label: str
    holder_name: str
    last4: str
    active: bool


class SettingsIn(BaseModel):
    week_start: Literal["sat", "sun", "mon"] | None = None
    year_start_month: int | None = Field(default=None, ge=1, le=12)
    monthly_budget_bdt: Decimal | None = Field(default=None, ge=0)
    default_fx_rate_usd: Decimal | None = Field(default=None, gt=0)
    approval_sla_days: int | None = Field(default=None, ge=1, le=30)
    allow_urgent_override: bool | None = None


class UnitIn(BaseModel):
    code: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    head_employee_id: int | None = None
    monthly_budget_bdt: Decimal = Field(default=Decimal("0"), ge=0)
    active: bool = True


class UnitUpdate(BaseModel):
    name: str | None = None
    head_employee_id: int | None = None
    monthly_budget_bdt: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class DepartmentIn(BaseModel):
    unit_id: int
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=20)
    head_employee_id: int | None = None
    monthly_budget_bdt: Decimal = Field(default=Decimal("0"), ge=0)
    cost_center: str | None = Field(default=None, max_length=40)
    active: bool = True


class DepartmentUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    head_employee_id: int | None = None
    monthly_budget_bdt: Decimal | None = Field(default=None, ge=0)
    cost_center: str | None = None
    active: bool | None = None


class DepartmentOut(ORM):
    id: int
    unit_id: int
    name: str
    code: str | None
    head_employee_id: int | None
    monthly_budget_bdt: Decimal
    cost_center: str | None
    active: bool


class UnitOut(ORM):
    id: int
    code: str
    name: str
    head_employee_id: int | None
    monthly_budget_bdt: Decimal
    active: bool
    departments: list[DepartmentOut] = []

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class LoginIn(BaseModel):
    username: str = Field(description="Employee code or email")
    password: str


class LoginOut(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    otp_required: bool = False
    otp_token: str | None = None


class VerifyOtpIn(BaseModel):
    otp_token: str
    code: str = Field(min_length=6, max_length=6)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ManagerBrief(ORM):
    id: int
    emp_code: str
    name: str
    designation: str | None = None


class MeOut(BaseModel):
    user_id: int
    employee_id: int
    emp_code: str
    name: str
    designation: str | None
    unit_id: int
    unit: str
    department_id: int | None
    department: str | None
    function_id: int | None = None
    function: str | None = None
    team: str | None
    email: str | None
    phone: str | None
    roles: list[str]
    is_manager: bool
    heads_unit_ids: list[int]
    heads_department_ids: list[int]
    heads_function_ids: list[int] = []
    leads_team_ids: list[int]
    can_propose: bool
    can_reveal_vault: bool
    manager: ManagerBrief | None
    last_login_at: datetime | None

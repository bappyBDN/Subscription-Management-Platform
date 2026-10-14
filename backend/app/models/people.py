from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.enums import EmployeeStatus, Role


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    designation: Mapped[str | None] = mapped_column(String(100))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), index=True)
    team: Mapped[str | None] = mapped_column(String(100))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(150), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10), default=EmployeeStatus.ACTIVE)

    manager: Mapped["Employee | None"] = relationship(remote_side="Employee.id", foreign_keys=[manager_id])
    user: Mapped["User | None"] = relationship(back_populates="employee", uselist=False)
    org_unit: Mapped["OrgUnit"] = relationship(foreign_keys=[unit_id])  # noqa: F821
    org_department: Mapped["Department | None"] = relationship(foreign_keys=[department_id])  # noqa: F821
    org_function: Mapped["OrgFunction | None"] = relationship(foreign_keys=[function_id])  # noqa: F821

    @property
    def unit_code(self) -> str:
        return self.org_unit.code if self.org_unit else ""

    @property
    def department_name(self) -> str | None:
        return self.org_department.name if self.org_department else None

    @property
    def function_name(self) -> str | None:
        return self.org_function.name if self.org_function else None


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    roles: Mapped[str] = mapped_column(String(100), default=Role.EMPLOYEE)
    can_reveal_vault: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    employee: Mapped[Employee] = relationship(back_populates="user")

    @property
    def role_list(self) -> list[str]:
        return [r for r in (self.roles or "").split(",") if r]

    def has_role(self, *roles: str) -> bool:
        return any(r in self.role_list for r in roles)

    @property
    def is_dmd(self) -> bool:
        return self.has_role(Role.DMD)

    @property
    def is_admin(self) -> bool:
        """DMD or delegate — can maintain the register."""
        return self.has_role(Role.DMD, Role.DELEGATE)

    @property
    def needs_2fa(self) -> bool:
        return self.is_admin


class OtpCode(TimestampMixin, Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

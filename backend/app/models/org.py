"""Organization structure: SBUs (stored as `units`) > departments > functions, plus optional teams."""

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from app.db.base import Base, TimestampMixin


class OrgUnit(TimestampMixin, Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # use_alter: employees -> units and units -> employees form a cycle
    head_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_units_head_employee"))
    monthly_budget_bdt: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    departments: Mapped[list["Department"]] = relationship(back_populates="unit", order_by="Department.name")
    head: Mapped["Employee | None"] = relationship(foreign_keys=[head_employee_id])  # noqa: F821


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("unit_id", "name", name="uq_department_unit_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(20))
    head_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_departments_head_employee"))
    monthly_budget_bdt: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    cost_center: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    unit: Mapped[OrgUnit] = relationship(back_populates="departments")
    head: Mapped["Employee | None"] = relationship(foreign_keys=[head_employee_id])  # noqa: F821

    functions: Mapped[list["OrgFunction"]] = relationship(back_populates="department", order_by="OrgFunction.name")

    @property
    def label(self) -> str:
        return f"{self.unit.code} / {self.name}"


class OrgFunction(TimestampMixin, Base):
    """A function inside a department (e.g. AI Analytics inside Digital Transformation)."""

    __tablename__ = "functions"
    __table_args__ = (UniqueConstraint("department_id", "name", name="uq_function_department_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    head_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_functions_head_employee"))
    monthly_budget_bdt: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    department: Mapped[Department] = relationship(back_populates="functions")
    head: Mapped["Employee | None"] = relationship(foreign_keys=[head_employee_id])  # noqa: F821

    @property
    def unit_id(self) -> int:
        return self.department.unit_id

    @property
    def unit_code(self) -> str:
        return self.department.unit.code

    @property
    def department_name(self) -> str:
        return self.department.name

    @property
    def head_name(self) -> str | None:
        return self.head.name if self.head else None

    @property
    def members(self) -> int:
        from app.models.people import Employee

        return (object_session(self).query(Employee)
                .filter(Employee.function_id == self.id, Employee.status == "active").count())

    @property
    def label(self) -> str:
        return f"{self.department.unit.code} / {self.department.name} / {self.name}"


class Team(TimestampMixin, Base):
    """A named team inside a unit. Members are the unit's employees whose `team` field matches the name."""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("unit_id", "name", name="uq_team_unit_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), index=True)
    lead_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    unit: Mapped[OrgUnit] = relationship()
    department: Mapped[Department | None] = relationship()
    function: Mapped[OrgFunction | None] = relationship()
    lead: Mapped["Employee | None"] = relationship(foreign_keys=[lead_employee_id])  # noqa: F821

    @property
    def label(self) -> str:
        return f"{self.unit.code} / {self.name}"

    def has_member(self, employee: "Employee") -> bool:  # noqa: F821
        return (employee.unit_id == self.unit_id
                and (employee.team or "").strip().lower() == self.name.strip().lower())

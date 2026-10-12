"""Organization structure: units (BMD, AES, ...) and the departments inside them."""

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    @property
    def label(self) -> str:
        return f"{self.unit.code} / {self.name}"

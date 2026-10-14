"""Helpers for SBUs (units), departments, functions and teams."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums import EmployeeStatus
from app.models import Department, Employee, OrgFunction, OrgUnit, Team, User


class OrgError(ValueError):
    pass


def check_unit_department(db: Session, unit_id: int, department_id: int | None) -> tuple[OrgUnit, Department | None]:
    unit = db.get(OrgUnit, unit_id)
    if unit is None:
        raise OrgError("Unit not found")
    dept = None
    if department_id is not None:
        dept = db.get(Department, department_id)
        if dept is None:
            raise OrgError("Department not found")
        if dept.unit_id != unit.id:
            raise OrgError(f"Department '{dept.name}' belongs to another unit")
    return unit, dept


def check_function(db: Session, department_id: int | None, function_id: int | None) -> OrgFunction | None:
    """The function must exist and belong to the given department."""
    if function_id is None:
        return None
    fn = db.get(OrgFunction, function_id)
    if fn is None:
        raise OrgError("Function not found")
    if department_id is not None and fn.department_id != department_id:
        raise OrgError(f"Function '{fn.name}' belongs to another department")
    return fn


def unit_by_code(db: Session, code: str) -> OrgUnit | None:
    return db.query(OrgUnit).filter(func.upper(OrgUnit.code) == code.strip().upper()).first()


def department_by_name(db: Session, unit: OrgUnit, name: str, create: bool = False) -> Department | None:
    dept = (
        db.query(Department)
        .filter(Department.unit_id == unit.id, func.lower(Department.name) == name.strip().lower())
        .first()
    )
    if dept is None and create:
        dept = Department(name=name.strip())
        unit.departments.append(dept)  # keep an already-loaded unit.departments current
        db.flush()
    return dept


def function_by_name(db: Session, dept: Department, name: str, create: bool = False) -> OrgFunction | None:
    fn = (db.query(OrgFunction)
          .filter(OrgFunction.department_id == dept.id, func.lower(OrgFunction.name) == name.strip().lower())
          .first())
    if fn is None and create:
        fn = OrgFunction(name=name.strip())
        dept.functions.append(fn)
        db.flush()
    return fn


def headed_units(db: Session, user: User) -> list[int]:
    return [uid for (uid,) in db.query(OrgUnit.id).filter(OrgUnit.head_employee_id == user.employee_id).all()]


def headed_departments(db: Session, user: User) -> list[int]:
    return [did for (did,) in db.query(Department.id).filter(Department.head_employee_id == user.employee_id).all()]


def headed_functions(db: Session, user: User) -> list[int]:
    return [fid for (fid,) in db.query(OrgFunction.id).filter(OrgFunction.head_employee_id == user.employee_id).all()]


def cost_scope(db: Session, user: User) -> tuple[set[int] | None, set[int] | None]:
    """Which units / departments the user may see cost for.

    Returns (unit_ids, department_ids); (None, None) means everything (DMD Sir / delegate).
    A unit head sees the whole unit (all its departments); a department head sees that department.
    """
    if user.is_admin:
        return None, None
    units = set(headed_units(db, user))
    depts = set(headed_departments(db, user))
    if units:
        depts |= {d for (d,) in db.query(Department.id).filter(Department.unit_id.in_(units)).all()}
    return units, depts


def employee_ids_in(db: Session, unit_id: int | None = None, department_id: int | None = None) -> list[int]:
    q = db.query(Employee.id)
    if unit_id is not None:
        q = q.filter(Employee.unit_id == unit_id)
    if department_id is not None:
        q = q.filter(Employee.department_id == department_id)
    return [eid for (eid,) in q.all()]


def led_teams(db: Session, user: User) -> list[int]:
    return [tid for (tid,) in db.query(Team.id).filter(Team.lead_employee_id == user.employee_id,
                                                       Team.active.is_(True)).all()]


def team_scope(db: Session, user: User) -> set[int] | None:
    """Teams the user may see cost for; None means all (DMD Sir / delegate).
    A team leader sees their team, a unit head every team of the unit."""
    if user.is_admin:
        return None
    teams = set(led_teams(db, user))
    units = headed_units(db, user)
    if units:
        teams |= {t for (t,) in db.query(Team.id).filter(Team.unit_id.in_(units)).all()}
    return teams


def team_members(db: Session, team: Team) -> list[Employee]:
    return (db.query(Employee)
            .filter(Employee.unit_id == team.unit_id, Employee.status == EmployeeStatus.ACTIVE,
                    func.lower(func.trim(Employee.team)) == team.name.strip().lower())
            .order_by(Employee.name).all())

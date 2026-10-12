"""Units and departments (organization masters)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import bad_request, client_ip, get_current_user, get_or_404, no_null, require_admin
from app.db.session import get_db
from app.models import Department, Employee, OrgUnit, User
from app.schemas.masters import DepartmentIn, DepartmentOut, DepartmentUpdate, UnitIn, UnitOut, UnitUpdate
from app.services import audit

router = APIRouter(tags=["organization"])


def _check_head(db: Session, employee_id: int | None, unit_id: int | None = None) -> None:
    if employee_id is None:
        return
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise bad_request("Head employee not found")
    if unit_id is not None and emp.unit_id != unit_id:
        raise bad_request("The head must be an employee of the same unit")


@router.get("/units", response_model=list[UnitOut])
def list_units(include_inactive: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(OrgUnit)
    if not include_inactive:
        q = q.filter(OrgUnit.active.is_(True))
    return q.order_by(OrgUnit.code).all()


@router.post("/units", response_model=UnitOut, status_code=201)
def create_unit(data: UnitIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_head(db, data.head_employee_id)
    unit = OrgUnit(**{**data.model_dump(), "code": data.code.upper()})
    db.add(unit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("A unit with this code already exists") from None
    audit.log(db, user, "unit.create", "unit", unit.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return unit


@router.patch("/units/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, data: UnitUpdate, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    unit = get_or_404(db, OrgUnit, unit_id, "Unit not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "monthly_budget_bdt", "active"})
    if "head_employee_id" in changes:
        _check_head(db, changes["head_employee_id"], unit.id)
    before = audit.snapshot(unit, list(changes))
    for k, v in changes.items():
        setattr(unit, k, v)
    audit.log(db, user, "unit.update", "unit", unit.id, before=before, after=changes, ip=client_ip(request))
    db.commit()
    return unit


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(unit_id: int | None = None, include_inactive: bool = False,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Department)
    if unit_id:
        q = q.filter(Department.unit_id == unit_id)
    if not include_inactive:
        q = q.filter(Department.active.is_(True))
    return q.order_by(Department.unit_id, Department.name).all()


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(data: DepartmentIn, request: Request, user: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    unit = get_or_404(db, OrgUnit, data.unit_id, "Unit not found")
    _check_head(db, data.head_employee_id, data.unit_id)
    dept = Department(**data.model_dump())
    unit.departments.append(dept)  # keep an already-loaded unit.departments current
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This unit already has a department with that name") from None
    audit.log(db, user, "department.create", "department", dept.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return dept


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def update_department(department_id: int, data: DepartmentUpdate, request: Request,
                      user: User = Depends(require_admin), db: Session = Depends(get_db)):
    dept = get_or_404(db, Department, department_id, "Department not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "monthly_budget_bdt", "active"})
    if "head_employee_id" in changes:
        _check_head(db, changes["head_employee_id"], dept.unit_id)
    before = audit.snapshot(dept, list(changes))
    for k, v in changes.items():
        setattr(dept, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This unit already has a department with that name") from None
    audit.log(db, user, "department.update", "department", dept.id, before=before, after=changes,
              ip=client_ip(request))
    db.commit()
    return dept

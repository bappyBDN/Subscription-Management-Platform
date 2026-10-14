"""SBUs (units), departments and functions (organization masters)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import bad_request, client_ip, get_current_user, get_or_404, no_null, require_admin
from app.db.session import get_db
from app.models import Department, Employee, OrgFunction, OrgUnit, User
from app.schemas.masters import (DepartmentIn, DepartmentOut, DepartmentUpdate, FunctionIn, FunctionOut, FunctionUpdate,
                                 UnitIn, UnitOut, UnitUpdate)
from app.services import audit, deletion

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
    changes = no_null(data.model_dump(exclude_unset=True), {"code", "name", "monthly_budget_bdt", "active"})
    if "code" in changes:
        changes["code"] = changes["code"].upper()
    if "head_employee_id" in changes:
        _check_head(db, changes["head_employee_id"], unit.id)
    before = audit.snapshot(unit, list(changes))
    for k, v in changes.items():
        setattr(unit, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("Another SBU already uses that code") from None
    audit.log(db, user, "unit.update", "unit", unit.id, before=before, after=changes, ip=client_ip(request))
    db.commit()
    return unit


@router.delete("/units/{unit_id}", status_code=204)
def delete_unit(unit_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Only a unit with no employees, subscriptions, requests or charges; its empty departments and teams go too."""
    unit = get_or_404(db, OrgUnit, unit_id, "Unit not found")
    deletion.remove(db, user, "unit", unit, deletion.delete_unit, f"SBU {unit.code}", client_ip(request))


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


@router.delete("/departments/{department_id}", status_code=204)
def delete_department(department_id: int, request: Request, user: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    dept = get_or_404(db, Department, department_id, "Department not found")
    deletion.remove(db, user, "department", dept, deletion.delete_department, f"Department {dept.label}",
                    client_ip(request))


# ------------------------------------------------------------------ functions

@router.get("/functions", response_model=list[FunctionOut])
def list_functions(unit_id: int | None = None, department_id: int | None = None, include_inactive: bool = False,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(OrgFunction).join(Department)
    if unit_id:
        q = q.filter(Department.unit_id == unit_id)
    if department_id:
        q = q.filter(OrgFunction.department_id == department_id)
    if not include_inactive:
        q = q.filter(OrgFunction.active.is_(True))
    return q.order_by(Department.unit_id, Department.name, OrgFunction.name).all()


@router.post("/functions", response_model=FunctionOut, status_code=201)
def create_function(data: FunctionIn, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    dept = get_or_404(db, Department, data.department_id, "Department not found")
    _check_head(db, data.head_employee_id, dept.unit_id)
    fn = OrgFunction(**{**data.model_dump(), "name": data.name.strip()})
    dept.functions.append(fn)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This department already has a function with that name") from None
    audit.log(db, user, "function.create", "function", fn.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return fn


@router.patch("/functions/{function_id}", response_model=FunctionOut)
def update_function(function_id: int, data: FunctionUpdate, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    fn = get_or_404(db, OrgFunction, function_id, "Function not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "monthly_budget_bdt", "active"})
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if "head_employee_id" in changes:
        _check_head(db, changes["head_employee_id"], fn.unit_id)
    before = audit.snapshot(fn, list(changes))
    for k, v in changes.items():
        setattr(fn, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This department already has a function with that name") from None
    audit.log(db, user, "function.update", "function", fn.id, before=before, after=changes, ip=client_ip(request))
    db.commit()
    db.refresh(fn)
    return fn


@router.delete("/functions/{function_id}", status_code=204)
def delete_function(function_id: int, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    fn = get_or_404(db, OrgFunction, function_id, "Function not found")
    deletion.remove(db, user, "function", fn, deletion.delete_function, f"Function {fn.label}", client_ip(request))

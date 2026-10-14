"""Employees, users, vendors, cards and settings (units/departments live in org.py)."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import (
    bad_request,
    client_ip,
    forbidden,
    get_current_user,
    get_or_404,
    no_null,
    not_found,
    require_admin,
    require_dmd,
    visible_employee_ids,
)
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_db
from app.enums import EmployeeStatus, Role
from app.models import Card, Employee, User, Vendor, VendorPlan
from app.schemas.masters import (
    CardIn,
    CardOut,
    CardUpdate,
    EmployeeIn,
    EmployeeOut,
    EmployeeUpdate,
    PlanIn,
    PlanOut,
    SettingsIn,
    UserIn,
    UserOut,
    UserUpdate,
    VendorIn,
    VendorOut,
    VendorUpdate,
)
from app.schemas.subscriptions import ImportResult
from app.services import audit, deletion, settings_store
from app.services.importer import read_rows
from app.services.mailer import send_email
from app.services.org import (OrgError, check_function, check_unit_department, department_by_name, function_by_name,
                              unit_by_code)
from app.services.requests_service import mark_assignments_for_review

router = APIRouter(tags=["masters"])


# ------------------------------------------------------------------ employees

@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(q: str | None = None, status: str | None = "active", unit_id: int | None = None,
                   department_id: int | None = None, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    query = db.query(Employee)
    ids = visible_employee_ids(db, user)
    if ids is not None:
        query = query.filter(Employee.id.in_(ids))
    if status:
        query = query.filter(Employee.status == status)
    if unit_id:
        query = query.filter(Employee.unit_id == unit_id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(Employee.name).like(like), func.lower(Employee.emp_code).like(like)))
    return query.order_by(Employee.name).limit(500).all()


@router.get("/employees/directory", response_model=list[EmployeeOut])
def employee_directory(q: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Search any active employee by name or code (used to pick a collector)."""
    if not user.is_admin:
        raise forbidden()
    like = f"%{q.lower()}%"
    return (
        db.query(Employee)
        .filter(Employee.status == EmployeeStatus.ACTIVE)
        .filter(or_(func.lower(Employee.name).like(like), func.lower(Employee.emp_code).like(like)))
        .order_by(Employee.name)
        .limit(20)
        .all()
    )


def _check_org(db: Session, unit_id: int, department_id: int | None, function_id: int | None = None) -> None:
    if function_id is not None and department_id is None:
        raise bad_request("Choose the department before the function")
    try:
        check_unit_department(db, unit_id, department_id)
        check_function(db, department_id, function_id)
    except OrgError as exc:
        raise bad_request(str(exc)) from None


def _check_manager(db: Session, manager_id: int | None, self_id: int | None = None) -> None:
    if manager_id is None:
        return
    if manager_id == self_id:
        raise bad_request("An employee cannot report to themselves")
    if not db.get(Employee, manager_id):
        raise bad_request("Reporting manager not found")


@router.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(data: EmployeeIn, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    _check_manager(db, data.manager_id)
    _check_org(db, data.unit_id, data.department_id, data.function_id)
    emp = Employee(**data.model_dump())
    db.add(emp)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("Employee code or email already exists") from None
    audit.log(db, user, "employee.create", "employee", emp.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return emp


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, data: EmployeeUpdate, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, employee_id, "Employee not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "unit_id", "status"})
    if "manager_id" in changes:
        _check_manager(db, changes["manager_id"], emp.id)
    if {"unit_id", "department_id", "function_id"} & set(changes):
        new_unit = changes.get("unit_id", emp.unit_id)
        new_dept = changes["department_id"] if "department_id" in changes else (
            emp.department_id if new_unit == emp.unit_id else None)
        new_fn = changes["function_id"] if "function_id" in changes else (
            emp.function_id if new_dept == emp.department_id else None)
        _check_org(db, new_unit, new_dept, new_fn)
        changes.update(department_id=new_dept, function_id=new_fn)
    before = audit.snapshot(emp, list(changes))
    for key, value in changes.items():
        setattr(emp, key, value)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("Email already used by another employee") from None
    ip = client_ip(request)
    audit.log(db, user, "employee.update", "employee", emp.id, before=before, after=changes, ip=ip)
    if changes.get("status") == EmployeeStatus.INACTIVE and before.get("status") != EmployeeStatus.INACTIVE:
        mark_assignments_for_review(db, user, emp, "left / became inactive", ip)
    elif any(k in changes and changes[k] != before.get(k)
             for k in ("team", "department_id", "function_id", "manager_id", "unit_id")):
        mark_assignments_for_review(db, user, emp, "changed team or role", ip)
    db.commit()
    db.refresh(emp)  # reload unit/department relationships after a move
    return emp


def _guard_account(actor: User, target: User | None) -> None:
    if target is None:
        return
    if target.id == actor.id:
        raise bad_request("You cannot delete your own account")
    if target.is_admin and not actor.is_dmd:
        raise forbidden("Only DMD Sir can delete a DMD or delegate account")


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: int, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    """Only an employee with no history; their login account (if unused) goes too."""
    emp = get_or_404(db, Employee, employee_id, "Employee not found")
    _guard_account(user, emp.user)
    deletion.remove(db, user, "employee", emp, deletion.delete_employee, f"Employee {emp.emp_code} ({emp.name})",
                    client_ip(request))


@router.post("/employees/import", response_model=ImportResult)
async def import_employees(request: Request, file: UploadFile = File(...), user: User = Depends(require_admin),
                           db: Session = Depends(get_db)):
    """Columns: emp_code, name, designation, unit (SBU code), department (name), function (name), team,
    manager_code, email, phone.

    Existing employees (same emp_code) are updated; departments / functions that do not exist yet are
    created; managers are linked in a second pass.
    """
    try:
        rows = read_rows(file.filename or "", await file.read())
    except ValueError as exc:
        raise bad_request(str(exc)) from None
    created, errors, manager_links = 0, [], []
    for i, row in enumerate(rows, start=2):
        code = str(row.get("emp_code") or "").strip()
        name = str(row.get("name") or "").strip()
        unit = unit_by_code(db, str(row.get("unit") or ""))
        if not code or not name or unit is None:
            errors.append({"row": i, "error": "emp_code, name and a known SBU code are required"})
            continue
        dept_name = str(row.get("department") or "").strip()
        dept = department_by_name(db, unit, dept_name, create=True) if dept_name else None
        fn_name = str(row.get("function") or "").strip()
        fn = function_by_name(db, dept, fn_name, create=True) if dept and fn_name else None
        emp = db.query(Employee).filter(Employee.emp_code == code).first()
        values = {k: (str(row[k]).strip() if row.get(k) not in (None, "") else None)
                  for k in ("designation", "team", "email", "phone")}
        if emp is None:
            emp = Employee(emp_code=code, name=name, unit_id=unit.id, department_id=dept.id if dept else None,
                           function_id=fn.id if fn else None, **values)
            db.add(emp)
            created += 1
        else:
            emp.name, emp.unit_id, emp.department_id = name, unit.id, dept.id if dept else None
            emp.function_id = fn.id if fn else None
            for k, v in values.items():
                setattr(emp, k, v)
        manager_code = str(row.get("manager_code") or "").strip()
        if manager_code:
            manager_links.append((i, emp, manager_code))
    db.flush()
    for i, emp, manager_code in manager_links:
        mgr = db.query(Employee).filter(Employee.emp_code == manager_code).first()
        if mgr is None or mgr.id == emp.id:
            errors.append({"row": i, "error": f"manager_code '{manager_code}' not found"})
        else:
            emp.manager_id = mgr.id
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("Import failed: duplicate employee code or email in the file") from None
    audit.log(db, user, "employee.import", "employee", None, after={"created": created, "rows": len(rows)},
              ip=client_ip(request))
    db.commit()
    return ImportResult(created=created, errors=errors)


# ------------------------------------------------------------------ users

def _mail_credentials(emp: Employee, password: str, new_account: bool) -> None:
    intro = ("An SMP account has been created for you." if new_account
             else "Your SMP password has been reset by an administrator.")
    send_email(
        emp.email,
        "Your SMP sign-in details",
        f"Hello {emp.name},\n\n{intro}\n\n"
        f"Sign in at: {get_settings().frontend_origin}\n"
        f"Username: {emp.emp_code} (or {emp.email})\n"
        f"Password: {password}\n\n"
        "Please change this password after you sign in, using the key icon (Change password) at the top of the page.",
    )


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not user.is_dmd and set(data.roles) - {Role.EMPLOYEE}:
        raise forbidden("A delegate can only create employee accounts")
    emp = db.get(Employee, data.employee_id)
    if not emp:
        raise bad_request("Employee not found")
    if data.send_email and not emp.email:
        raise bad_request("This employee has no email address — add one or untick 'Email the password'")
    if db.query(User).filter(User.employee_id == data.employee_id).first():
        raise bad_request("This employee already has an account")
    roles = sorted(set(data.roles) | {Role.EMPLOYEE})
    new = User(employee_id=data.employee_id, password_hash=hash_password(data.password), roles=",".join(roles),
               can_reveal_vault=data.can_reveal_vault and user.is_dmd)
    db.add(new)
    db.flush()
    audit.log(db, user, "user.create", "user", new.id,
              after={"employee_id": new.employee_id, "roles": roles, "emailed": data.send_email},
              ip=client_ip(request))
    db.commit()
    if data.send_email:
        _mail_credentials(emp, data.password, new_account=True)
    return new


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, request: Request, user: User = Depends(require_dmd),
                db: Session = Depends(get_db)):
    target = get_or_404(db, User, user_id, "User not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"roles", "can_reveal_vault", "is_active"})
    notify = changes.pop("send_email", False) and bool(changes.get("password"))
    if notify and not target.employee.email:
        raise bad_request("This employee has no email address — add one or untick 'Email the password'")
    if "roles" in changes:
        roles = sorted(set(changes["roles"]) | {Role.EMPLOYEE})
        if target.id == user.id and Role.DMD not in roles:
            raise bad_request("You cannot remove your own DMD role")
        target.roles = ",".join(roles)
    if "can_reveal_vault" in changes:
        target.can_reveal_vault = changes["can_reveal_vault"]
    if "is_active" in changes:
        if target.id == user.id and not changes["is_active"]:
            raise bad_request("You cannot deactivate yourself")
        target.is_active = changes["is_active"]
    if changes.get("password"):
        target.password_hash = hash_password(changes["password"])
        target.failed_logins, target.locked_until = 0, None
    after = {k: v for k, v in changes.items() if k != "password"}
    if changes.get("password"):
        after.update(password_reset=True, emailed=notify)
    audit.log(db, user, "user.update", "user", target.id, after=after, ip=client_ip(request))
    db.commit()
    if notify:
        _mail_credentials(target.employee, changes["password"], new_account=False)
    return target


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Only a login account that has never been used; the employee stays."""
    target = get_or_404(db, User, user_id, "User not found")
    _guard_account(user, target)
    deletion.remove(db, user, "user", target, deletion.delete_user, f"The login account of {target.employee.name}",
                    client_ip(request))


# ------------------------------------------------------------------ vendors

@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(include_inactive: bool = False, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    query = db.query(Vendor)
    if not include_inactive:
        query = query.filter(Vendor.active.is_(True))
    return query.order_by(Vendor.name).all()


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(data: VendorIn, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if db.query(Vendor).filter(func.lower(Vendor.name) == data.name.lower()).first():
        raise bad_request("A tool with this name already exists")
    vendor = Vendor(**data.model_dump(exclude={"plans"}))
    vendor.plans = [VendorPlan(**p.model_dump()) for p in data.plans]
    db.add(vendor)
    db.flush()
    audit.log(db, user, "vendor.create", "vendor", vendor.id, after={"name": vendor.name}, ip=client_ip(request))
    db.commit()
    return vendor


@router.patch("/vendors/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: int, data: VendorUpdate, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    vendor = get_or_404(db, Vendor, vendor_id, "Tool not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "category", "active"})
    for k, v in changes.items():
        setattr(vendor, k, v)
    audit.log(db, user, "vendor.update", "vendor", vendor.id, after=changes, ip=client_ip(request))
    db.commit()
    return vendor


@router.post("/vendors/{vendor_id}/plans", response_model=PlanOut, status_code=201)
def add_plan(vendor_id: int, data: PlanIn, request: Request, user: User = Depends(require_admin),
             db: Session = Depends(get_db)):
    if not db.get(Vendor, vendor_id):
        raise not_found("Tool not found")
    plan = VendorPlan(vendor_id=vendor_id, **data.model_dump())
    db.add(plan)
    db.flush()
    audit.log(db, user, "vendor.plan_add", "vendor", vendor_id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return plan


@router.delete("/vendors/{vendor_id}/plans/{plan_id}", status_code=204)
def delete_plan(vendor_id: int, plan_id: int, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    plan = db.get(VendorPlan, plan_id)
    if not plan or plan.vendor_id != vendor_id:
        raise not_found("Plan not found")
    db.delete(plan)
    audit.log(db, user, "vendor.plan_delete", "vendor", vendor_id, before={"plan_name": plan.plan_name},
              ip=client_ip(request))
    db.commit()


@router.delete("/vendors/{vendor_id}", status_code=204)
def delete_vendor(vendor_id: int, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    vendor = get_or_404(db, Vendor, vendor_id, "Tool not found")
    deletion.remove(db, user, "vendor", vendor, deletion.delete_vendor, f"Tool {vendor.name}", client_ip(request))


# ------------------------------------------------------------------ cards

@router.get("/cards", response_model=list[CardOut])
def list_cards(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Card).order_by(Card.id).all()


@router.post("/cards", response_model=CardOut, status_code=201)
def create_card(data: CardIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    card = Card(**data.model_dump())
    db.add(card)
    db.flush()
    audit.log(db, user, "card.create", "card", card.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return card


@router.patch("/cards/{card_id}", response_model=CardOut)
def update_card(card_id: int, data: CardUpdate, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    card = get_or_404(db, Card, card_id, "Card not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"label", "holder_name", "last4", "active"})
    for k, v in changes.items():
        setattr(card, k, v)
    audit.log(db, user, "card.update", "card", card.id, after=changes, ip=client_ip(request))
    db.commit()
    return card


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    card = get_or_404(db, Card, card_id, "Card not found")
    deletion.remove(db, user, "card", card, deletion.delete_card, f"Card {card.label}", client_ip(request))


# ------------------------------------------------------------------ settings

@router.get("/settings")
def get_settings_values(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return settings_store.get_all(db)


@router.put("/settings")
def put_settings(data: SettingsIn, request: Request, user: User = Depends(require_dmd),
                 db: Session = Depends(get_db)):
    changes = {k: (str(v).lower() if isinstance(v, bool) else str(v))
               for k, v in data.model_dump(exclude_none=True).items()}
    before = settings_store.get_all(db)
    values = settings_store.put(db, changes)
    audit.log(db, user, "settings.update", "settings", None, before={k: before[k] for k in changes}, after=changes,
              ip=client_ip(request))
    db.commit()
    return values

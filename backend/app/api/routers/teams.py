"""Teams (who leads them, which subscriptions they own) and metered usage sync."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.deps import bad_request, client_ip, get_current_user, get_or_404, no_null, require_admin
from app.db.session import get_db
from app.models import Employee, OrgUnit, Team, User
from app.schemas.masters import TeamIn, TeamOut, TeamUpdate
from app.services import audit, deletion, usage
from app.services.org import OrgError, check_function, check_unit_department, team_members

router = APIRouter(tags=["teams"])


def team_out(db: Session, team: Team) -> TeamOut:
    return TeamOut(id=team.id, unit_id=team.unit_id, unit_code=team.unit.code, name=team.name,
                   department_id=team.department_id,
                   department_name=team.department.name if team.department else None,
                   function_id=team.function_id, function_name=team.function.name if team.function else None,
                   lead_employee_id=team.lead_employee_id, lead_name=team.lead.name if team.lead else None,
                   active=team.active, members=len(team_members(db, team)))


def _check_lead(db: Session, employee_id: int | None, unit_id: int) -> None:
    if employee_id is None:
        return
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise bad_request("Team leader not found")
    if emp.unit_id != unit_id:
        raise bad_request("The team leader must be an employee of the same unit")


def _check_department(db: Session, unit_id: int, department_id: int | None, function_id: int | None = None) -> int | None:
    """Validates the team's department / function; returns the department (taken from the function if set)."""
    try:
        fn = check_function(db, None, function_id)
        if fn is not None:
            if department_id is not None and fn.department_id != department_id:
                raise OrgError(f"Function '{fn.name}' belongs to another department")
            department_id = fn.department_id
        check_unit_department(db, unit_id, department_id)
    except OrgError as exc:
        raise bad_request(str(exc)) from None
    return department_id


@router.get("/teams", response_model=list[TeamOut])
def list_teams(unit_id: int | None = None, include_inactive: bool = False,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Team)
    if unit_id:
        q = q.filter(Team.unit_id == unit_id)
    if not include_inactive:
        q = q.filter(Team.active.is_(True))
    return [team_out(db, t) for t in q.order_by(Team.unit_id, Team.name).all()]


@router.post("/teams", response_model=TeamOut, status_code=201)
def create_team(data: TeamIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    get_or_404(db, OrgUnit, data.unit_id, "Unit not found")
    department_id = _check_department(db, data.unit_id, data.department_id, data.function_id)
    _check_lead(db, data.lead_employee_id, data.unit_id)
    team = Team(**{**data.model_dump(), "name": data.name.strip(), "department_id": department_id})
    db.add(team)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This unit already has a team with that name") from None
    audit.log(db, user, "team.create", "team", team.id, after=data.model_dump(), ip=client_ip(request))
    db.commit()
    return team_out(db, team)


@router.patch("/teams/{team_id}", response_model=TeamOut)
def update_team(team_id: int, data: TeamUpdate, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    team = get_or_404(db, Team, team_id, "Team not found")
    changes = no_null(data.model_dump(exclude_unset=True), {"name", "active"})
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if {"department_id", "function_id"} & set(changes):
        fn_id = changes["function_id"] if "function_id" in changes else team.function_id
        dept_id = changes["department_id"] if "department_id" in changes else team.department_id
        if "department_id" in changes and "function_id" not in changes and team.function_id is not None                 and team.function.department_id != dept_id:
            fn_id = None  # moved to another department: drop the old function
        changes.update(department_id=_check_department(db, team.unit_id, dept_id, fn_id), function_id=fn_id)
    if "lead_employee_id" in changes:
        _check_lead(db, changes["lead_employee_id"], team.unit_id)
    before = audit.snapshot(team, list(changes))
    for k, v in changes.items():
        setattr(team, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise bad_request("This unit already has a team with that name") from None
    audit.log(db, user, "team.update", "team", team.id, before=before, after=changes, ip=client_ip(request))
    db.commit()
    db.refresh(team)
    return team_out(db, team)


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(team_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Only a team that owns no subscriptions (members are matched by name, so nobody is affected)."""
    team = get_or_404(db, Team, team_id, "Team not found")
    deletion.remove(db, user, "team", team, deletion.delete_team, f"Team {team.name}", client_ip(request))


# ------------------------------------------------------------------ metered usage

@router.get("/usage/status")
def usage_status(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Whether DeepSeek metering is set up, and the last balance read."""
    return usage.status(db)


@router.post("/usage/sync")
def usage_sync(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Read the DeepSeek balance now and book the spend since the last sync on today."""
    try:
        result = usage.sync_deepseek(db, today())
    except usage.UsageError as exc:
        raise bad_request(str(exc)) from None
    audit.log(db, user, "usage.sync", "subscription", result["subscription_id"],
              after={"amount_original": result["amount_original"], "balance": result["balance"]},
              ip=client_ip(request))
    db.commit()
    return result

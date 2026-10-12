from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import forbidden, get_current_user
from app.db.session import get_db
from app.models import User
from app.services import insights
from app.services.org import cost_scope

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/savings")
def savings(unit_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Savings opportunities: empty seats, seats to reclaim, team-plan consolidation, unconfirmed access."""
    units, _ = cost_scope(db, user)
    if units is not None:  # not an admin
        if not units:
            raise forbidden("Savings insights are for DMD Sir, delegates and unit heads")
        if unit_id is None and len(units) == 1:
            unit_id = next(iter(units))
        if unit_id not in units:
            raise forbidden()
    return insights.savings(db, unit_id)

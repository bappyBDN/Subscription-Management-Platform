"""Request lifecycle state machine (pure, no database).

Actors:
  requester – the employee who raised the request
  manager   – the requester's reporting manager
  dmd       – DMD Sir
  admin     – DMD Sir or a delegate admin (handover steps)
"""

from dataclasses import dataclass

from app.enums import RequestStatus as S
from app.enums import RequestType


class WorkflowError(Exception):
    pass


@dataclass(frozen=True)
class Transition:
    to: S
    actors: frozenset[str]
    comment_required: bool = False


A = frozenset

TRANSITIONS: dict[S, dict[str, Transition]] = {
    S.PENDING_MANAGER: {
        "recommend": Transition(S.PENDING_DMD, A({"manager", "dmd"})),
        "reject": Transition(S.REJECTED, A({"manager", "dmd"}), comment_required=True),
        "info": Transition(S.INFO_NEEDED, A({"manager", "dmd"}), comment_required=True),
        "override": Transition(S.APPROVED, A({"dmd"}), comment_required=True),
        "withdraw": Transition(S.WITHDRAWN, A({"requester"})),
    },
    S.PENDING_DMD: {
        "approve": Transition(S.APPROVED, A({"dmd"})),
        "reject": Transition(S.REJECTED, A({"dmd"}), comment_required=True),
        "hold": Transition(S.ON_HOLD, A({"dmd"})),
        "info": Transition(S.INFO_NEEDED, A({"dmd"}), comment_required=True),
        "withdraw": Transition(S.WITHDRAWN, A({"requester"})),
    },
    S.ON_HOLD: {
        "resume": Transition(S.PENDING_DMD, A({"dmd"})),
        "approve": Transition(S.APPROVED, A({"dmd"})),
        "reject": Transition(S.REJECTED, A({"dmd"}), comment_required=True),
        "withdraw": Transition(S.WITHDRAWN, A({"requester"})),
    },
    S.INFO_NEEDED: {
        "resubmit": Transition(S.PENDING_MANAGER, A({"requester"})),
        "withdraw": Transition(S.WITHDRAWN, A({"requester"})),
    },
    S.APPROVED: {
        "set_handover": Transition(S.HANDOVER_PENDING, A({"admin"})),
        "auto_activate": Transition(S.ACTIVE, A({"system"})),
        "auto_end": Transition(S.ENDED, A({"system"})),
    },
    S.HANDOVER_PENDING: {
        "set_handover": Transition(S.HANDOVER_PENDING, A({"admin"})),
        "receive": Transition(S.ACTIVE, A({"requester"})),
    },
    S.ACTIVE: {
        "end": Transition(S.ENDED, A({"admin", "system"})),
    },
    S.REJECTED: {},
    S.WITHDRAWN: {},
    S.ENDED: {},
}

# Decisions an approver can send to POST /requests/{id}/decision
DECISIONS = {"recommend", "approve", "reject", "hold", "info", "resume", "override"}

OPEN_STATUSES = {S.PENDING_MANAGER, S.PENDING_DMD, S.ON_HOLD, S.INFO_NEEDED}


def transition(status: str, action: str, actors: set[str], comment: str | None = None) -> S:
    """Return the next status or raise WorkflowError.

    `actors` is every capacity the calling user holds for this request
    (e.g. {"manager", "dmd"} when DMD Sir is also the requester's manager).
    """
    try:
        current = S(status)
    except ValueError as exc:
        raise WorkflowError(f"Unknown status '{status}'") from exc
    options = TRANSITIONS.get(current, {})
    if action not in options:
        raise WorkflowError(f"Action '{action}' is not allowed when the request is '{current}'")
    t = options[action]
    if not (t.actors & actors):
        raise WorkflowError(f"You are not allowed to '{action}' this request")
    if t.comment_required and not (comment and comment.strip()):
        raise WorkflowError(f"A comment is required to '{action}'")
    return t.to


def initial_status(has_manager: bool) -> S:
    return S.PENDING_MANAGER if has_manager else S.PENDING_DMD


def after_approval_action(request_type: str) -> str | None:
    """What happens automatically right after approval."""
    if request_type == RequestType.RENEWAL:
        return "auto_activate"
    if request_type == RequestType.CANCEL:
        return "auto_end"
    return None  # new / upgrade wait for a handover


def step_for(status: str) -> str:
    return "manager" if status == S.PENDING_MANAGER else "dmd"

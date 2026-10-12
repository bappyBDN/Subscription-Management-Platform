import pytest

from app.enums import RequestStatus as S
from app.services import workflow
from app.services.workflow import WorkflowError


def test_manager_recommend_moves_to_dmd():
    assert workflow.transition(S.PENDING_MANAGER, "recommend", {"manager"}) == S.PENDING_DMD


def test_employee_cannot_recommend_own_request():
    with pytest.raises(WorkflowError):
        workflow.transition(S.PENDING_MANAGER, "recommend", {"requester"})


def test_manager_cannot_give_final_approval():
    with pytest.raises(WorkflowError):
        workflow.transition(S.PENDING_DMD, "approve", {"manager"})


def test_reject_requires_comment():
    with pytest.raises(WorkflowError):
        workflow.transition(S.PENDING_DMD, "reject", {"dmd"}, comment=" ")
    assert workflow.transition(S.PENDING_DMD, "reject", {"dmd"}, comment="No budget") == S.REJECTED


def test_hold_and_resume():
    assert workflow.transition(S.PENDING_DMD, "hold", {"dmd"}) == S.ON_HOLD
    assert workflow.transition(S.ON_HOLD, "resume", {"dmd"}) == S.PENDING_DMD


def test_info_then_resubmit_restarts_at_manager():
    assert workflow.transition(S.PENDING_DMD, "info", {"dmd"}, "Which team?") == S.INFO_NEEDED
    assert workflow.transition(S.INFO_NEEDED, "resubmit", {"requester"}) == S.PENDING_MANAGER


def test_withdraw_only_before_approval():
    assert workflow.transition(S.PENDING_DMD, "withdraw", {"requester"}) == S.WITHDRAWN
    with pytest.raises(WorkflowError):
        workflow.transition(S.APPROVED, "withdraw", {"requester"})


def test_override_needs_reason_and_dmd():
    with pytest.raises(WorkflowError):
        workflow.transition(S.PENDING_MANAGER, "override", {"dmd"})
    with pytest.raises(WorkflowError):
        workflow.transition(S.PENDING_MANAGER, "override", {"manager"}, "urgent")
    assert workflow.transition(S.PENDING_MANAGER, "override", {"dmd"}, "urgent client demo") == S.APPROVED


def test_handover_then_receive():
    assert workflow.transition(S.APPROVED, "set_handover", {"admin"}) == S.HANDOVER_PENDING
    assert workflow.transition(S.HANDOVER_PENDING, "receive", {"requester"}) == S.ACTIVE


def test_terminal_states_have_no_actions():
    for status in (S.REJECTED, S.WITHDRAWN, S.ENDED, S.FULFILLED):
        with pytest.raises(WorkflowError):
            workflow.transition(status, "approve", {"dmd"})


def test_initial_status_without_manager_goes_to_dmd():
    assert workflow.initial_status(True) == S.PENDING_MANAGER
    assert workflow.initial_status(False) == S.PENDING_DMD


def test_after_approval_by_type():
    assert workflow.after_approval_action("renewal") == "auto_activate"
    assert workflow.after_approval_action("cancel") == "auto_end"
    assert workflow.after_approval_action("new") is None


def test_proposal_is_fulfilled_by_admin():
    assert workflow.after_approval_action("proposal") is None
    assert workflow.transition(S.APPROVED, "fulfil", {"admin"}) == S.FULFILLED
    with pytest.raises(WorkflowError):
        workflow.transition(S.APPROVED, "fulfil", {"requester"})

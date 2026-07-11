import pytest

from app.schemas import AlertStatus, WorkflowAction
from app.workflow import WorkflowError, next_status


def test_happy_path_state_machine() -> None:
    status = AlertStatus.open
    status = next_status(status, WorkflowAction.assign)
    assert status == AlertStatus.assigned
    status = next_status(status, WorkflowAction.acknowledge)
    assert status == AlertStatus.acknowledged
    status = next_status(status, WorkflowAction.start_review)
    assert status == AlertStatus.under_review
    status = next_status(status, WorkflowAction.resolve)
    assert status == AlertStatus.resolved


def test_illegal_transition_is_rejected() -> None:
    with pytest.raises(WorkflowError):
        next_status(AlertStatus.open, WorkflowAction.resolve)

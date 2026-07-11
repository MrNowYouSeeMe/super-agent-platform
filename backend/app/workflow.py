from app.schemas import AlertStatus, WorkflowAction


class WorkflowError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[WorkflowAction, dict[AlertStatus, AlertStatus]] = {
    WorkflowAction.assign: {
        AlertStatus.open: AlertStatus.assigned,
        AlertStatus.assigned: AlertStatus.assigned,
    },
    WorkflowAction.acknowledge: {
        AlertStatus.assigned: AlertStatus.acknowledged,
    },
    WorkflowAction.start_review: {
        AlertStatus.acknowledged: AlertStatus.under_review,
    },
    WorkflowAction.escalate: {
        AlertStatus.acknowledged: AlertStatus.escalated,
        AlertStatus.under_review: AlertStatus.escalated,
    },
    WorkflowAction.resolve: {
        AlertStatus.under_review: AlertStatus.resolved,
        AlertStatus.escalated: AlertStatus.resolved,
    },
}


def next_status(current: AlertStatus, action: WorkflowAction) -> AlertStatus:
    target = ALLOWED_TRANSITIONS.get(action, {}).get(current)
    if target is None:
        raise WorkflowError(
            f"Action '{action.value}' is not allowed from status '{current.value}'."
        )
    return target

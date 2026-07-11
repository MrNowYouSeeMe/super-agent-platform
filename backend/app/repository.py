import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AlertModel, CaseEventModel
from app.schemas import (
    AlertResponse,
    AlertStatus,
    AnalysisResult,
    CaseEventResponse,
    WorkflowAction,
)
from app.workflow import WorkflowError, next_status


class NotFoundError(ValueError):
    pass


class VersionConflictError(ValueError):
    pass


def _severity(result: AnalysisResult) -> str:
    if result.classification.value == "data_quality_issue":
        return "medium"
    if result.shortage_eta_minutes is not None and result.shortage_eta_minutes <= 60:
        return "high"
    return "medium"


def _to_response(model: AlertModel) -> AlertResponse:
    return AlertResponse(
        alert_id=model.alert_id,
        analysis_id=model.analysis_id,
        agent_id=model.agent_id,
        classification=model.classification,
        severity=model.severity,
        affected_resource=model.affected_resource,
        affected_provider=model.affected_provider,
        shortage_eta_minutes=model.shortage_eta_minutes,
        confidence=model.confidence,
        recommendation=model.recommendation,
        owner=model.owner,
        status=AlertStatus(model.status),
        summary=model.summary,
        evidence=list(model.evidence or []),
        possible_normal_context=list(model.possible_normal_context or []),
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        case_events=[
            CaseEventResponse(
                event_id=event.event_id,
                action=event.action,
                actor=event.actor,
                actor_role=event.actor_role,
                from_status=event.from_status,
                to_status=event.to_status,
                note=event.note,
                created_at=event.created_at,
            )
            for event in model.case_events
        ],
    )


async def create_alert(
    session: AsyncSession,
    result: AnalysisResult,
) -> AlertResponse:
    existing = await session.scalar(
        select(AlertModel)
        .options(selectinload(AlertModel.case_events))
        .where(AlertModel.analysis_id == result.analysis_id)
    )
    if existing is not None:
        return _to_response(existing)

    alert_id = f"alert_{uuid.uuid4().hex[:16]}"
    model = AlertModel(
        alert_id=alert_id,
        analysis_id=result.analysis_id,
        agent_id=result.agent_id,
        classification=result.classification.value,
        severity=_severity(result),
        affected_resource=result.affected_resource,
        affected_provider=result.affected_provider,
        shortage_eta_minutes=result.shortage_eta_minutes,
        confidence=result.confidence,
        recommendation=result.recommendation.value,
        owner=result.recommended_owner,
        status=AlertStatus.open.value,
        summary=result.summary,
        evidence=result.evidence,
        possible_normal_context=result.possible_normal_context,
        version=1,
    )
    model.case_events.append(
        CaseEventModel(
            action="created",
            actor="Analysis Worker",
            actor_role="system",
            from_status=None,
            to_status=AlertStatus.open.value,
            note="Alert created from validated analysis output.",
        )
    )
    session.add(model)
    await session.commit()

    loaded = await get_alert_model(session, alert_id)
    return _to_response(loaded)


async def get_alert_model(session: AsyncSession, alert_id: str) -> AlertModel:
    model = await session.scalar(
        select(AlertModel)
        .options(selectinload(AlertModel.case_events))
        .where(AlertModel.alert_id == alert_id)
    )
    if model is None:
        raise NotFoundError("Alert was not found.")
    return model


async def get_alert(session: AsyncSession, alert_id: str) -> AlertResponse:
    return _to_response(await get_alert_model(session, alert_id))


async def list_alerts(
    session: AsyncSession,
    status_filter: AlertStatus | None = None,
) -> list[AlertResponse]:
    statement = (
        select(AlertModel)
        .options(selectinload(AlertModel.case_events))
        .order_by(AlertModel.created_at.desc())
        .limit(100)
    )
    if status_filter is not None:
        statement = statement.where(AlertModel.status == status_filter.value)
    models = list((await session.scalars(statement)).unique().all())
    return [_to_response(model) for model in models]


async def dashboard_counts(session: AsyncSession) -> tuple[int, int]:
    active = await session.scalar(
        select(func.count(AlertModel.alert_id)).where(
            AlertModel.status != AlertStatus.resolved.value
        )
    )
    reviewing = await session.scalar(
        select(func.count(AlertModel.alert_id)).where(
            AlertModel.status.in_(
                [
                    AlertStatus.acknowledged.value,
                    AlertStatus.under_review.value,
                    AlertStatus.escalated.value,
                ]
            )
        )
    )
    return int(active or 0), int(reviewing or 0)


async def transition_alert(
    session: AsyncSession,
    *,
    alert_id: str,
    action: WorkflowAction,
    actor: str,
    actor_role: str,
    note: str | None,
    expected_version: int,
    owner: str | None = None,
) -> AlertResponse:
    async with session.begin():
        model = await session.scalar(
            select(AlertModel)
            .where(AlertModel.alert_id == alert_id)
            .with_for_update()
        )
        if model is None:
            raise NotFoundError("Alert was not found.")
        if model.version != expected_version:
            raise VersionConflictError(
                f"Alert version changed from {expected_version} to {model.version}. Refresh and retry."
            )

        current = AlertStatus(model.status)
        target = next_status(current, action)

        if action == WorkflowAction.assign:
            if owner is None or len(owner.strip()) < 2:
                raise WorkflowError("Owner is required for assignment.")
            model.owner = owner.strip()

        model.status = target.value
        model.version += 1
        session.add(
            CaseEventModel(
                alert_id=alert_id,
                action=action.value,
                actor=actor,
                actor_role=actor_role,
                from_status=current.value,
                to_status=target.value,
                note=note,
            )
        )

    return _to_response(await get_alert_model(session, alert_id))

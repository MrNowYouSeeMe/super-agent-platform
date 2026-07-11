import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal, engine, get_session, init_db
from app.evaluation.router import router as evaluation_router
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.redis_jobs import RedisJobStore
from app.repository import (
    NotFoundError,
    VersionConflictError,
    dashboard_counts,
    get_alert,
    list_alerts,
    transition_alert,
)
from app.schemas import (
    AlertResponse,
    AlertStatus,
    AnalysisAccepted,
    AnalysisRequest,
    AnalysisSnapshot,
    AssignCommand,
    BalanceCard,
    DashboardResponse,
    DataFeed,
    DependencyHealth,
    HealthResponse,
    JobStatus,
    TransitionCommand,
    WorkflowAction,
)
from app.tracing import (
    configure_tracing,
    force_flush_tracing,
    instrument_fastapi,
)
from app.workflow import WorkflowError

configure_logging()
logger = logging.getLogger("superagent.api")
settings = get_settings()
configure_tracing(
    service_name=settings.otel_service_name,
    service_version="0.3.0",
    environment=settings.app_env,
    endpoint=settings.otel_exporter_otlp_traces_endpoint,
    sample_ratio=settings.otel_trace_sample_ratio,
    enabled=settings.otel_tracing_enabled,
    engine=engine,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    app.state.redis = redis
    app.state.jobs = RedisJobStore(redis)
    try:
        yield
    finally:
        await redis.aclose()
        force_flush_tracing()


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="Synthetic-data evaluation and measured analytics edition.",
    lifespan=lifespan,
)
app.include_router(evaluation_router)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Trace-ID", "Server-Timing"],
)
instrument_fastapi(app)


def jobs(request: Request) -> RedisJobStore:
    return request.app.state.jobs


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    postgres_status = "ok"
    redis_status = "ok"
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        postgres_status = "failed"
    try:
        await request.app.state.redis.ping()
    except Exception:
        redis_status = "failed"

    overall = "ok" if postgres_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        service=settings.app_name,
        version="0.3.0",
        environment=settings.app_env,
        dependencies=DependencyHealth(
            postgres=postgres_status,
            redis=redis_status,
        ),
    )


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def dashboard(
    session: AsyncSession = Depends(get_session),
) -> DashboardResponse:
    active_alerts, reviewing = await dashboard_counts(session)
    return DashboardResponse(
        agent_id="AGT-SYL-017",
        agent_name="Zindabazar Multi-Provider Outlet",
        shared_cash=BalanceCard(
            resource_id="shared_cash",
            label="Shared Physical Cash",
            balance=155000,
            safe_threshold=20000,
            status="pressure",
        ),
        provider_balances=[
            BalanceCard(
                resource_id="bkash",
                label="bKash E-Money",
                balance=48000,
                safe_threshold=15000,
                status="watch",
            ),
            BalanceCard(
                resource_id="nagad",
                label="Nagad E-Money",
                balance=96000,
                safe_threshold=15000,
                status="healthy",
            ),
            BalanceCard(
                resource_id="rocket",
                label="Rocket E-Money",
                balance=74000,
                safe_threshold=15000,
                status="healthy",
            ),
        ],
        active_alerts=active_alerts,
        cases_under_review=reviewing,
        data_feeds=[
            DataFeed(provider_id="bkash", label="bKash", status="fresh", age_minutes=4),
            DataFeed(provider_id="nagad", label="Nagad", status="conflicting", age_minutes=9),
            DataFeed(provider_id="rocket", label="Rocket", status="fresh", age_minutes=6),
        ],
    )


@app.post(
    "/api/v1/analyses",
    response_model=AnalysisAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    payload: AnalysisRequest,
    request: Request,
    store: RedisJobStore = Depends(jobs),
) -> AnalysisAccepted:
    analysis_id = await store.create_and_enqueue(
        payload,
        request_id=request.state.request_id,
    )
    return AnalysisAccepted(analysis_id=analysis_id, status=JobStatus.queued)


@app.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisSnapshot)
async def get_analysis(
    analysis_id: str,
    store: RedisJobStore = Depends(jobs),
) -> AnalysisSnapshot:
    snapshot = await store.get_snapshot(analysis_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Analysis was not found.")
    return snapshot


@app.get("/api/v1/analyses/{analysis_id}/events")
async def stream_events(
    analysis_id: str,
    request: Request,
    store: RedisJobStore = Depends(jobs),
) -> StreamingResponse:
    if await store.get_snapshot(analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analysis was not found.")

    async def generator():
        emitted = 0
        while True:
            if await request.is_disconnected():
                break
            snapshot = await store.get_snapshot(analysis_id)
            if snapshot is None:
                break
            for event in snapshot.events[emitted:]:
                yield "data: " + json.dumps(
                    event.model_dump(mode="json"), ensure_ascii=False
                ) + "\n\n"
                emitted += 1
            if (
                snapshot.status in {JobStatus.completed, JobStatus.failed}
                and emitted >= len(snapshot.events)
            ):
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/alerts", response_model=list[AlertResponse])
async def alerts(
    alert_status: AlertStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[AlertResponse]:
    return await list_alerts(session, alert_status)


@app.get("/api/v1/alerts/{alert_id}", response_model=AlertResponse)
async def alert_detail(
    alert_id: str,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    try:
        return await get_alert(session, alert_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def apply_transition(
    *,
    session: AsyncSession,
    alert_id: str,
    action: WorkflowAction,
    actor: str,
    actor_role: str,
    note: str | None,
    expected_version: int,
    owner: str | None = None,
) -> AlertResponse:
    try:
        return await transition_alert(
            session,
            alert_id=alert_id,
            action=action,
            actor=actor,
            actor_role=actor_role,
            note=note,
            expected_version=expected_version,
            owner=owner,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/alerts/{alert_id}/assign", response_model=AlertResponse)
async def assign_alert(
    alert_id: str,
    command: AssignCommand,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await apply_transition(
        session=session,
        alert_id=alert_id,
        action=WorkflowAction.assign,
        actor=command.actor,
        actor_role=command.actor_role,
        note=command.note,
        expected_version=command.expected_version,
        owner=command.owner,
    )


@app.post("/api/v1/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str,
    command: TransitionCommand,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await apply_transition(
        session=session,
        alert_id=alert_id,
        action=WorkflowAction.acknowledge,
        actor=command.actor,
        actor_role=command.actor_role,
        note=command.note,
        expected_version=command.expected_version,
    )


@app.post("/api/v1/alerts/{alert_id}/start-review", response_model=AlertResponse)
async def start_review(
    alert_id: str,
    command: TransitionCommand,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await apply_transition(
        session=session,
        alert_id=alert_id,
        action=WorkflowAction.start_review,
        actor=command.actor,
        actor_role=command.actor_role,
        note=command.note,
        expected_version=command.expected_version,
    )


@app.post("/api/v1/alerts/{alert_id}/escalate", response_model=AlertResponse)
async def escalate_alert(
    alert_id: str,
    command: TransitionCommand,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await apply_transition(
        session=session,
        alert_id=alert_id,
        action=WorkflowAction.escalate,
        actor=command.actor,
        actor_role=command.actor_role,
        note=command.note,
        expected_version=command.expected_version,
    )


@app.post("/api/v1/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    command: TransitionCommand,
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    return await apply_transition(
        session=session,
        alert_id=alert_id,
        action=WorkflowAction.resolve,
        actor=command.actor,
        actor_role=command.actor_role,
        note=command.note,
        expected_version=command.expected_version,
    )

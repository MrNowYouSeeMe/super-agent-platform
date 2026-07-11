import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from math import ceil
from typing import Literal, TypedDict

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "event",
            "analysis_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


configure_logging()
logger = logging.getLogger("superagent")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "event": "request_failed",
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "event": "request_completed",
            },
        )
        return response


class Language(str, Enum):
    english = "en"
    bangla = "bn"
    banglish = "banglish"


class Scenario(str, Enum):
    liquidity_anomaly = "liquidity_anomaly"
    normal_day = "normal_day"
    data_conflict = "data_conflict"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class EventStatus(str, Enum):
    completed = "completed"
    warning = "warning"
    failed = "failed"


class Classification(str, Enum):
    normal_operational_spike = "normal_operational_spike"
    data_quality_issue = "data_quality_issue"
    requires_review = "requires_review"


class Recommendation(str, Enum):
    monitor_more_frequently = "monitor_more_frequently"
    verify_provider_feed = "verify_provider_feed"
    request_approved_cash_support = "request_approved_cash_support"


class AnalysisRequest(BaseModel):
    agent_id: str = Field(
        default="AGT-SYL-017",
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    scenario: Scenario = Scenario.liquidity_anomaly
    language: Language = Language.banglish


class AnalysisAccepted(BaseModel):
    analysis_id: str
    status: JobStatus


class AnalysisEvent(BaseModel):
    sequence: int = Field(ge=1)
    stage: str
    label: str
    status: EventStatus
    detail: str | None = None
    metric: int | float | str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConfidenceAdjustment(BaseModel):
    reason: str
    impact: float


class AnalysisResult(BaseModel):
    analysis_id: str
    agent_id: str
    classification: Classification
    affected_resource: str
    affected_provider: str
    shortage_eta_minutes: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    confidence_adjustments: list[ConfidenceAdjustment]
    records_checked: int = Field(ge=0)
    supporting_claims: int = Field(ge=0)
    conflicting_records: int = Field(ge=0)
    evidence: list[str]
    possible_normal_context: list[str]
    recommendation: Recommendation
    recommended_owner: str
    summary: str
    safe_boundary: str


class AnalysisSnapshot(BaseModel):
    analysis_id: str
    status: JobStatus
    events: list[AnalysisEvent]
    result: AnalysisResult | None = None
    error: str | None = None


class BalanceCard(BaseModel):
    resource_id: str
    label: str
    balance: float
    safe_threshold: float
    status: Literal["healthy", "watch", "pressure"]
    currency: Literal["BDT"] = "BDT"


class DataFeed(BaseModel):
    provider_id: str
    label: str
    status: Literal["fresh", "delayed", "conflicting", "missing"]
    age_minutes: int


class DashboardResponse(BaseModel):
    agent_id: str
    agent_name: str
    shared_cash: BalanceCard
    provider_balances: list[BalanceCard]
    active_alerts: int
    cases_under_review: int
    data_feeds: list[DataFeed]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class Transaction(TypedDict):
    transaction_id: str
    provider: str
    transaction_type: str
    amount: float
    minutes_ago: int
    status: str


class JobRecord:
    def __init__(self, analysis_id: str):
        self.analysis_id = analysis_id
        self.status = JobStatus.queued
        self.events: list[AnalysisEvent] = []
        self.result: AnalysisResult | None = None
        self.error: str | None = None


class JobStore:
    def __init__(self):
        self.jobs: dict[str, JobRecord] = {}
        self.lock = asyncio.Lock()

    async def create(self) -> str:
        analysis_id = f"analysis_{uuid.uuid4().hex[:16]}"
        async with self.lock:
            self.jobs[analysis_id] = JobRecord(analysis_id)
        return analysis_id

    async def get(self, analysis_id: str) -> JobRecord | None:
        async with self.lock:
            return self.jobs.get(analysis_id)


store = JobStore()


def build_transactions(scenario: Scenario) -> tuple[list[Transaction], float, float, int, int, str | None]:
    if scenario == Scenario.normal_day:
        transactions: list[Transaction] = []
        for index in range(24):
            transactions.append(
                {
                    "transaction_id": f"NORMAL-{index:03d}",
                    "provider": ["bKash", "Nagad", "Rocket"][index % 3],
                    "transaction_type": "cash_out" if index % 2 == 0 else "cash_in",
                    "amount": float(2500 + (index % 4) * 500),
                    "minutes_ago": index + 1,
                    "status": "completed",
                }
            )
        return transactions, 245000, 20000, 0, 3, None

    repeated = [
        {
            "transaction_id": f"BK-REPEAT-{index:03d}",
            "provider": "bKash",
            "transaction_type": "cash_out",
            "amount": 12000.0,
            "minutes_ago": index + 1,
            "status": "completed",
        }
        for index in range(8)
    ]
    extra_out = [
        {
            "transaction_id": f"OUT-{index:03d}",
            "provider": ["bKash", "Nagad", "Rocket", "bKash"][index],
            "transaction_type": "cash_out",
            "amount": 4000.0,
            "minutes_ago": 10 + index,
            "status": "completed",
        }
        for index in range(4)
    ]
    cash_in = [
        {
            "transaction_id": f"IN-{index:03d}",
            "provider": ["Nagad", "Rocket", "bKash"][index % 3],
            "transaction_type": "cash_in",
            "amount": 5000.0 if index < 4 else 7000.0,
            "minutes_ago": 15 + index,
            "status": "completed",
        }
        for index in range(6)
    ]
    conflicts = 4 if scenario == Scenario.data_conflict else 2
    age = 47 if scenario == Scenario.data_conflict else 9
    return repeated + extra_out + cash_in, 155000, 20000, conflicts, age, "pre_eid_demand"


def summary(language: Language, classification: Classification, eta: int | None, confidence: float) -> str:
    percent = round(confidence * 100)
    if classification == Classification.normal_operational_spike:
        if language == Language.bangla:
            return f"à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦¡à§‡à¦Ÿà¦¾à§Ÿ à¦¨à¦¿à¦°à¦¾à¦ªà¦¦ à¦¸à§€à¦®à¦¾à¦° à¦®à¦§à§à¦¯à§‡ à¦•à¦¾à¦°à§à¦¯à¦•à§à¦°à¦® à¦¦à§‡à¦–à¦¾ à¦¯à¦¾à¦šà§à¦›à§‡à¥¤ à¦¬à¦¿à¦¶à§à¦¬à¦¾à¦¸à¦¯à§‹à¦—à§à¦¯à¦¤à¦¾ {percent}%à¥¤ à¦ªà¦°à§à¦¯à¦¬à§‡à¦•à§à¦·à¦£ à¦šà¦¾à¦²à¦¿à§Ÿà§‡ à¦¯à¦¾à¦“à§Ÿà¦¾ à¦‰à¦šà¦¿à¦¤à¥¤"
        if language == Language.banglish:
            return f"Current data-te operation safe threshold-er moddhe ache. Confidence {percent}%. Monitoring continue kora uchit."
        return f"Current operations remain within the safe threshold. Confidence is {percent}%. Continued monitoring is recommended."

    if classification == Classification.data_quality_issue:
        if language == Language.bangla:
            return f"à¦ªà§à¦°à§‹à¦­à¦¾à¦‡à¦¡à¦¾à¦° à¦¡à§‡à¦Ÿà¦¾à§Ÿ à¦¬à¦¿à¦²à¦®à§à¦¬ à¦“ à¦…à¦¸à¦™à§à¦—à¦¤à¦¿ à¦ªà¦¾à¦“à§Ÿà¦¾ à¦—à§‡à¦›à§‡à¥¤ à¦¬à¦¿à¦¶à§à¦¬à¦¾à¦¸à¦¯à§‹à¦—à§à¦¯à¦¤à¦¾ {percent}% à¦ à¦•à¦®à¦¾à¦¨à§‹ à¦¹à§Ÿà§‡à¦›à§‡à¥¤ à¦¡à§‡à¦Ÿà¦¾ à¦¯à¦¾à¦šà¦¾à¦‡ à¦ªà§à¦°à§Ÿà§‹à¦œà¦¨à¥¤"
        if language == Language.banglish:
            return f"Provider data-te delay ebong conflict detect hoyeche. Confidence {percent}% e reduce kora hoyeche. Provider feed verify kora proyojon."
        return f"Delayed and conflicting provider data was detected. Confidence was reduced to {percent}%. Verify the provider feed first."

    eta_text = str(eta) if eta is not None else "unknown"
    if language == Language.bangla:
        return f"à¦¶à§‡à§Ÿà¦¾à¦°à§à¦¡ à¦•à§à¦¯à¦¾à¦¶à§‡ à¦šà¦¾à¦ª à¦¶à¦¨à¦¾à¦•à§à¦¤ à¦¹à§Ÿà§‡à¦›à§‡à¥¤ à¦ªà§à¦°à¦¾à§Ÿ {eta_text} à¦®à¦¿à¦¨à¦¿à¦Ÿà§‡à¦° à¦®à¦§à§à¦¯à§‡ à¦¨à¦¿à¦°à¦¾à¦ªà¦¦ à¦¸à§€à¦®à¦¾à¦° à¦¨à¦¿à¦šà§‡ à¦¯à§‡à¦¤à§‡ à¦ªà¦¾à¦°à§‡à¥¤ à¦¬à¦¿à¦¶à§à¦¬à¦¾à¦¸à¦¯à§‹à¦—à§à¦¯à¦¤à¦¾ {percent}%à¥¤ à¦à¦Ÿà¦¿ à¦œà¦¾à¦²à¦¿à§Ÿà¦¾à¦¤à¦¿à¦° à¦¸à¦¿à¦¦à§à¦§à¦¾à¦¨à§à¦¤ à¦¨à§Ÿ; à¦®à¦¾à¦¨à¦¬ à¦ªà¦°à§à¦¯à¦¾à¦²à§‹à¦šà¦¨à¦¾ à¦ªà§à¦°à§Ÿà§‹à¦œà¦¨à¥¤"
    if language == Language.banglish:
        return f"Shared cash pressure detect hoyeche. Approximately {eta_text} minute-er moddhe safe threshold-er niche jete pare. Confidence {percent}%. Eta fraud verdict na; human review proyojon."
    return f"Shared-cash pressure was detected. The balance may cross the safe threshold in approximately {eta_text} minutes. Confidence is {percent}%. This is not a fraud verdict."


async def run_analysis(analysis_id: str, payload: AnalysisRequest) -> AnalysisResult:
    record = await store.get(analysis_id)
    if record is None:
        raise RuntimeError("Analysis not found")
    record.status = JobStatus.running
    sequence = 0
    delay = int(os.getenv("ANALYSIS_STAGE_DELAY_MS", "220")) / 1000

    async def publish(stage: str, label: str, event_status: EventStatus, detail: str | None = None, metric=None):
        nonlocal sequence
        sequence += 1
        record.events.append(
            AnalysisEvent(
                sequence=sequence,
                stage=stage,
                label=label,
                status=event_status,
                detail=detail,
                metric=metric,
            )
        )
        if delay > 0:
            await asyncio.sleep(delay)

    transactions, shared_cash, threshold, conflicts, feed_age, event_context = build_transactions(payload.scenario)

    await publish("problem_understood", "Understood the operational problem", EventStatus.completed)
    await publish("checks_created", "Created 5 analytical checks", EventStatus.completed, metric=5)

    valid = [
        tx for tx in transactions
        if tx["amount"] > 0
        and tx["transaction_type"] in {"cash_in", "cash_out"}
        and tx["provider"] in {"bKash", "Nagad", "Rocket"}
    ]
    await publish("records_validated", f"Checked {len(valid)} transaction records", EventStatus.completed, metric=len(valid))

    providers = {tx["provider"] for tx in valid}
    await publish("balances_reconciled", f"Reconciled {len(providers)} provider balances", EventStatus.completed, metric=len(providers))

    cash_out_total = sum(tx["amount"] for tx in valid if tx["transaction_type"] == "cash_out")
    cash_in_total = sum(tx["amount"] for tx in valid if tx["transaction_type"] == "cash_in")
    net_outflow = max((cash_out_total - cash_in_total) / 30, 0)
    eta = ceil((shared_cash - threshold) / net_outflow) if net_outflow > 0 else None
    await publish("liquidity_forecast", "Forecasted shared-cash pressure", EventStatus.completed, metric=eta or "not_reached")

    repeated_groups = Counter((tx["provider"], tx["transaction_type"], tx["amount"]) for tx in valid)
    repeated = max(
        (
            count
            for (provider, tx_type, amount), count in repeated_groups.items()
            if provider == "bKash" and tx_type == "cash_out" and amount >= 10000
        ),
        default=0,
    )
    bkash_out = sum(tx["amount"] for tx in valid if tx["provider"] == "bKash" and tx["transaction_type"] == "cash_out")
    contribution = round((bkash_out / cash_out_total) * 100) if cash_out_total else 0

    if payload.scenario == Scenario.normal_day:
        evidence = [
            "Cash-in and cash-out volumes remained near balance",
            "All provider feeds were fresh",
            "No repeated high-value cluster was detected",
            "Shared cash remained above the safe threshold",
        ]
    else:
        evidence = [
            f"{repeated} repeated high-value bKash cash-outs",
            f"bKash contributed {contribution}% of recent cash-out volume",
            f"Net shared-cash outflow was {round(net_outflow)} BDT per minute",
            f"Current shared cash was {round(shared_cash)} BDT",
            f"Safe threshold was {round(threshold)} BDT",
            f"Provider feed age was {feed_age} minutes",
            "Pre-Eid demand was considered as a possible normal explanation",
        ]

    await publish("evidence_collected", f"Found {len(evidence)} supporting claims", EventStatus.completed, metric=len(evidence))

    if conflicts:
        await publish("data_conflicts", f"Found {conflicts} conflicting records", EventStatus.warning, metric=conflicts)
    else:
        await publish("data_conflicts", "No conflicting records found", EventStatus.completed, metric=0)

    confidence = 0.92
    adjustments: list[ConfidenceAdjustment] = []
    if event_context:
        confidence -= 0.08
        adjustments.append(ConfidenceAdjustment(reason="pre_eid_demand_context", impact=-0.08))
    conflict_penalty = min(conflicts * 0.05, 0.25)
    if conflict_penalty:
        confidence -= conflict_penalty
        adjustments.append(ConfidenceAdjustment(reason="conflicting_records", impact=-conflict_penalty))
    if feed_age > 30:
        confidence -= 0.12
        adjustments.append(ConfidenceAdjustment(reason="delayed_provider_feed", impact=-0.12))
    confidence = round(max(min(confidence, 0.95), 0.20), 2)
    await publish("confidence_calculated", f"Calculated confidence at {round(confidence * 100)}%", EventStatus.warning if confidence < 0.70 else EventStatus.completed, metric=round(confidence * 100))

    if payload.scenario == Scenario.normal_day:
        classification = Classification.normal_operational_spike
        recommendation = Recommendation.monitor_more_frequently
        owner = "Outlet Operations"
        provider = "Multiple providers"
        resource = "shared_cash"
        context = ["Routine operational demand"]
    elif payload.scenario == Scenario.data_conflict:
        classification = Classification.data_quality_issue
        recommendation = Recommendation.verify_provider_feed
        owner = "Provider Operations Data Steward"
        provider = "Nagad"
        resource = "provider_data"
        context = ["Delayed provider synchronization", "Temporary reporting inconsistency"]
    else:
        classification = Classification.requires_review
        recommendation = Recommendation.request_approved_cash_support
        owner = "bKash Field Officer"
        provider = "bKash"
        resource = "shared_cash"
        context = ["Pre-Eid demand spike", "High legitimate merchant activity"]

    await publish("decision_generated", "Generated the safe recommendation", EventStatus.completed)

    result = AnalysisResult(
        analysis_id=analysis_id,
        agent_id=payload.agent_id,
        classification=classification,
        affected_resource=resource,
        affected_provider=provider,
        shortage_eta_minutes=eta,
        confidence=confidence,
        confidence_adjustments=adjustments,
        records_checked=len(valid),
        supporting_claims=len(evidence),
        conflicting_records=conflicts,
        evidence=evidence,
        possible_normal_context=context,
        recommendation=recommendation,
        recommended_owner=owner,
        summary=summary(payload.language, classification, eta, confidence),
        safe_boundary="Advisory decision support only. No transfer, blocking, wallet refill, accusation or final fraud determination is performed.",
    )
    sequence += 1
    record.events.append(
        AnalysisEvent(
            sequence=sequence,
            stage="analysis_completed",
            label="Completed the intelligence workflow",
            status=EventStatus.completed,
            detail="The schema-safe final result is ready.",
        )
    )
    record.result = result
    record.status = JobStatus.completed
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.background_tasks = set()
    yield
    for task in list(app.state.background_tasks):
        task.cancel()


app = FastAPI(
    title="SuperAgent Sentinel API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080").split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Server-Timing"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="SuperAgent Sentinel API",
        version="0.1.0",
        environment=os.getenv("APP_ENV", "development"),
    )


@app.get("/api/v1/dashboard", response_model=DashboardResponse)
async def dashboard() -> DashboardResponse:
    return DashboardResponse(
        agent_id="AGT-SYL-017",
        agent_name="Zindabazar Multi-Provider Outlet",
        shared_cash=BalanceCard(resource_id="shared_cash", label="Shared Physical Cash", balance=155000, safe_threshold=20000, status="pressure"),
        provider_balances=[
            BalanceCard(resource_id="bkash", label="bKash E-Money", balance=48000, safe_threshold=15000, status="watch"),
            BalanceCard(resource_id="nagad", label="Nagad E-Money", balance=96000, safe_threshold=15000, status="healthy"),
            BalanceCard(resource_id="rocket", label="Rocket E-Money", balance=74000, safe_threshold=15000, status="healthy"),
        ],
        active_alerts=2,
        cases_under_review=1,
        data_feeds=[
            DataFeed(provider_id="bkash", label="bKash", status="fresh", age_minutes=4),
            DataFeed(provider_id="nagad", label="Nagad", status="conflicting", age_minutes=9),
            DataFeed(provider_id="rocket", label="Rocket", status="fresh", age_minutes=6),
        ],
    )


@app.post("/api/v1/analyses", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(payload: AnalysisRequest, request: Request) -> AnalysisAccepted:
    analysis_id = await store.create()
    task = asyncio.create_task(run_analysis(analysis_id, payload))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return AnalysisAccepted(analysis_id=analysis_id, status=JobStatus.queued)


@app.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisSnapshot)
async def get_analysis(analysis_id: str) -> AnalysisSnapshot:
    record = await store.get(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis was not found.")
    return AnalysisSnapshot(
        analysis_id=record.analysis_id,
        status=record.status,
        events=record.events,
        result=record.result,
        error=record.error,
    )


@app.get("/api/v1/analyses/{analysis_id}/events")
async def stream_events(analysis_id: str, request: Request) -> StreamingResponse:
    if await store.get(analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analysis was not found.")

    async def generator():
        emitted = 0
        while True:
            if await request.is_disconnected():
                break
            record = await store.get(analysis_id)
            if record is None:
                break
            for event in record.events[emitted:]:
                yield "data: " + json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n\n"
                emitted += 1
            if record.status in {JobStatus.completed, JobStatus.failed} and emitted >= len(record.events):
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
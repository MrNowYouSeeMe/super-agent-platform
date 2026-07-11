from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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


class AlertStatus(str, Enum):
    open = "OPEN"
    assigned = "ASSIGNED"
    acknowledged = "ACKNOWLEDGED"
    under_review = "UNDER_REVIEW"
    escalated = "ESCALATED"
    resolved = "RESOLVED"


class WorkflowAction(str, Enum):
    assign = "assign"
    acknowledge = "acknowledge"
    start_review = "start_review"
    escalate = "escalate"
    resolve = "resolve"


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
    stage: str = Field(min_length=2, max_length=100)
    label: str = Field(min_length=2, max_length=200)
    status: EventStatus
    detail: str | None = Field(default=None, max_length=700)
    metric: int | float | str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ConfidenceAdjustment(BaseModel):
    reason: str
    impact: float


class AnalysisResult(BaseModel):
    analysis_id: str
    alert_id: str | None = None
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


class DependencyHealth(BaseModel):
    postgres: Literal["ok", "failed"]
    redis: Literal["ok", "failed"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    dependencies: DependencyHealth


class CaseEventResponse(BaseModel):
    event_id: int
    action: str
    actor: str
    actor_role: str
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class AlertResponse(BaseModel):
    alert_id: str
    analysis_id: str
    agent_id: str
    classification: str
    severity: Literal["low", "medium", "high"]
    affected_resource: str
    affected_provider: str
    shortage_eta_minutes: int | None
    confidence: float
    recommendation: str
    owner: str
    status: AlertStatus
    summary: str
    evidence: list[str]
    possible_normal_context: list[str]
    version: int
    created_at: datetime
    updated_at: datetime
    case_events: list[CaseEventResponse] = Field(default_factory=list)


class AssignCommand(BaseModel):
    actor: str = Field(min_length=2, max_length=100)
    actor_role: str = Field(min_length=2, max_length=80)
    owner: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=1)


class TransitionCommand(BaseModel):
    actor: str = Field(min_length=2, max_length=100)
    actor_role: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=1)

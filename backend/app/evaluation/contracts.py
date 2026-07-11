from pydantic import BaseModel, Field


class DatasetFileSummary(BaseModel):
    path: str
    rows: int = Field(ge=0)
    sha256: str


class DatasetSummary(BaseModel):
    dataset_version: str
    seed: int
    generated_at: str
    agents: int = Field(ge=1)
    providers: list[str]
    areas: list[str]
    start_at: str
    end_at: str
    interval_minutes: int = Field(ge=1)
    agent_rows: int = Field(ge=0)
    provider_rows: int = Field(ge=0)
    shortage_positive_rows: int = Field(ge=0)
    anomaly_positive_rows: int = Field(ge=0)
    data_quality_positive_rows: int = Field(ge=0)
    files: list[DatasetFileSummary]
    assumptions: list[str]
    limitations: list[str]


class ForecastMetrics(BaseModel):
    model: str
    mae_bdt: float = Field(ge=0)
    rmse_bdt: float = Field(ge=0)
    mape_percent: float = Field(ge=0)
    evaluated_rows: int = Field(ge=0)


class ClassificationMetrics(BaseModel):
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)


class ShortageMetrics(ClassificationMetrics):
    mean_lead_time_minutes: float = Field(ge=0)
    median_lead_time_minutes: float = Field(ge=0)


class EvaluationReport(BaseModel):
    report_version: str
    generated_at: str
    dataset_version: str
    seed: int
    split_strategy: str
    champion_forecast_model: str
    forecast_candidates: list[ForecastMetrics]
    shortage_detection: ShortageMetrics
    anomaly_detection: ClassificationMetrics
    data_quality_detection: ClassificationMetrics
    explanation_coverage: float = Field(ge=0, le=1)
    safe_language_coverage: float = Field(ge=0, le=1)
    evaluation_runtime_ms: float = Field(ge=0)
    measured_metrics_count: int = Field(ge=3)
    notes: list[str]
    limitations: list[str]

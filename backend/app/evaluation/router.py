from fastapi import APIRouter, HTTPException

from app.evaluation.contracts import DatasetSummary, EvaluationReport
from app.evaluation.service import load_dataset_summary, load_evaluation_report

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])

SERVICE_UNAVAILABLE_RESPONSES = {
    503: {
        "description": "The generated evaluation artifact is not available.",
    },
}


@router.get(
    "/dataset",
    responses=SERVICE_UNAVAILABLE_RESPONSES,
)
async def dataset_summary() -> DatasetSummary:
    try:
        return load_dataset_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/report",
    responses=SERVICE_UNAVAILABLE_RESPONSES,
)
async def evaluation_report() -> EvaluationReport:
    try:
        return load_evaluation_report()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

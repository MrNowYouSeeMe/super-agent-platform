from fastapi import APIRouter, HTTPException

from app.evaluation.contracts import DatasetSummary, EvaluationReport
from app.evaluation.service import load_dataset_summary, load_evaluation_report

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/dataset", response_model=DatasetSummary)
async def dataset_summary() -> DatasetSummary:
    try:
        return load_dataset_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/report", response_model=EvaluationReport)
async def evaluation_report() -> EvaluationReport:
    try:
        return load_evaluation_report()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

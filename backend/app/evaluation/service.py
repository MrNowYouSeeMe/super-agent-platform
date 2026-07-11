from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from app.evaluation.contracts import DatasetSummary, EvaluationReport

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
REPORT_DIR = PROJECT_ROOT / "artifacts" / "evaluation"


@lru_cache(maxsize=1)
def load_dataset_summary() -> DatasetSummary:
    path = DATA_DIR / "manifest.json"
    if not path.exists():
        raise FileNotFoundError("Synthetic dataset manifest is not available.")
    return DatasetSummary.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_evaluation_report() -> EvaluationReport:
    path = REPORT_DIR / "latest_metrics.json"
    if not path.exists():
        raise FileNotFoundError("Evaluation report is not available.")
    return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))

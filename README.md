# SuperAgent Sentinel

Phase 3 adds a reproducible synthetic multi-provider dataset, ground-truth labels, deterministic baseline evaluation, measured judge-facing metrics and an evaluation panel without changing the Phase 2 alert/workflow contracts.

## Current architecture

- React + Vite + TypeScript frontend
- FastAPI contract-safe API
- Redis analysis queue and persistent execution events
- Separate background worker
- PostgreSQL alerts, case state and audit history
- Docker Compose full stack
- Synthetic data and evaluation artifacts mounted read-only into the API container

## Phase 3 deliverables

- One shared physical-cash pool per outlet
- Separate bKash, Nagad and Rocket e-money balances
- 18 synthetic outlets across six areas
- 21 days of hourly history
- Chronological 70/15/15 train-validation-test split
- Ground truth for six-hour shortage risk, anomaly category and provider-feed quality
- Seasonal-naive, moving-average and EWMA forecasting baselines
- MAE, RMSE and zero-safe MAPE
- Shortage precision, recall, F1 and warning lead time
- Anomaly precision, recall, F1 and false-positive rate
- Data-quality detection and explanation/safe-language coverage

## Runtime

- Frontend: `http://127.0.0.1:8080`
- API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Evaluation report: `GET /api/v1/evaluation/report`
- Dataset summary: `GET /api/v1/evaluation/dataset`

## Reproduce the benchmark

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.evaluation.cli --project-root .. --agents 18 --days 21 --seed 20260711
```

OpenAI remains outside the core decision path. Phase 3 metrics apply to synthetic data only; anomalies are review signals and never fraud conclusions.

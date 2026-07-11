# Phase 3 Evaluation Protocol

The evaluation harness compares three deterministic forecast baselines: 24-hour seasonal naive, six-hour moving average and EWMA net change. The champion is selected by the lowest test MAE.

Measured outputs include MAE, RMSE, MAPE, shortage precision/recall/F1, warning lead time, anomaly precision/recall/F1/FPR, data-quality detection, explanation coverage and safe-language coverage.

The chronological split avoids random leakage from future periods into training. Results are reproducible from the documented seed. Metrics apply only to the generated synthetic benchmark.

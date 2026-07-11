# SuperAgent Sentinel — Phase 3 Evaluation

- Dataset: `phase3-synthetic-v1`
- Seed: `20260711`
- Split: `time_ordered_70_train_15_validation_15_test`
- Champion forecast: `moving_average_6h`

## Forecast candidates

| Model | MAE (BDT) | RMSE (BDT) | MAPE | Rows |
|---|---:|---:|---:|---:|
| seasonal_naive_24h | 8496.79 | 29145.75 | 10.08% | 1350 |
| moving_average_6h | 8480.81 | 29136.73 | 10.01% | 1350 |
| ewma_net_change | 8482.95 | 29144.0 | 10.02% | 1350 |

## Detection metrics

- Shortage precision/recall/F1: 0.9185/0.7613/0.8325
- Mean warning lead time: 64.26 minutes
- Anomaly precision/recall/F1: 0.8339/1.0/0.9094
- Anomaly false-positive rate: 0.0138
- Data-quality precision/recall/F1: 1.0/1.0/1.0
- Explanation coverage: 100.00%
- Safe-language coverage: 100.00%

## Responsible interpretation

These metrics validate a prototype on synthetic data. An anomaly is not proof of fraud, and every high-impact outcome remains under human review.

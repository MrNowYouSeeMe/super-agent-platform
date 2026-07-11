# SuperAgent Sentinel — Phase 3 Evaluation

- Dataset: `phase3-synthetic-v1`
- Seed: `20260711`
- Split: `time_ordered_70_train_15_validation_15_test`
- Champion forecast: `ewma_net_change`

## Forecast candidates

| Model | MAE (BDT) | RMSE (BDT) | MAPE | Rows |
|---|---:|---:|---:|---:|
| seasonal_naive_24h | 10179.63 | 31298.28 | 11.85% | 1350 |
| moving_average_6h | 8681.48 | 29074.42 | 12.24% | 1350 |
| ewma_net_change | 8445.92 | 29058.55 | 11.13% | 1350 |

## Detection metrics

- Shortage precision/recall/F1: 0.9025/0.8131/0.8555
- Mean warning lead time: 65.48 minutes
- Anomaly precision/recall/F1: 0.8339/1.0/0.9094
- Anomaly false-positive rate: 0.0138
- Data-quality precision/recall/F1: 1.0/1.0/1.0
- Explanation coverage: 100.00%
- Safe-language coverage: 100.00%

## Responsible interpretation

These metrics validate a prototype on synthetic data. An anomaly is not proof of fraud, and every high-impact outcome remains under human review.

## Limitations

- Results measure performance on reproducible synthetic data only.
- Injected anomalies are simplified and may overstate real-world separability.
- No real provider API, customer identity, settlement or regulatory claim is made.

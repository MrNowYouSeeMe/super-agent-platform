# Phase 3 Data and Simulation Note

## Boundary model

Each outlet has one shared physical-cash pool and three separate provider e-money balances. No cross-provider conversion, settlement or control is simulated.

## Dataset

- Version: `phase3-synthetic-v1`
- Seed: `20260711`
- Interval: hourly
- Agents: 18
- Providers: bKash, Nagad and Rocket (synthetic labels only; no real API use)
- Time split: 70% train, 15% validation and 15% test in chronological order

The generator creates routine demand, payday/weekend/festival context, liquidity pressure, high cash-out bursts, delayed feeds, missing feeds and conflicting feeds. Ground truth is included for shortage-within-six-hours, anomaly category and data-quality status.

## Responsible interpretation

An anomaly is a review signal, not proof of fraud. The benchmark uses synthetic data and cannot establish production accuracy. Every high-impact action remains human-controlled.

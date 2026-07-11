from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.metrics import evaluate_dataset
from app.evaluation.synthetic import SyntheticConfig, generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and evaluate Phase 3 synthetic data.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--agents", type=int, default=18)
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()

    data_dir = args.project_root / "data" / "synthetic"
    report_dir = args.project_root / "artifacts" / "evaluation"
    manifest = generate_dataset(
        data_dir,
        SyntheticConfig(agents=args.agents, days=args.days, seed=args.seed),
    )
    report = evaluate_dataset(data_dir, report_dir)

    print(
        json.dumps(
            {
                "dataset_version": manifest["dataset_version"],
                "agent_rows": manifest["agent_rows"],
                "provider_rows": manifest["provider_rows"],
                "champion_forecast_model": report["champion_forecast_model"],
                "forecast_mae_bdt": next(
                    item["mae_bdt"]
                    for item in report["forecast_candidates"]
                    if item["model"] == report["champion_forecast_model"]
                ),
                "anomaly_f1": report["anomaly_detection"]["f1"],
                "shortage_recall": report["shortage_detection"]["recall"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

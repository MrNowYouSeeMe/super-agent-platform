from pathlib import Path

from app.evaluation.metrics import evaluate_dataset
from app.evaluation.synthetic import SyntheticConfig, generate_dataset


def test_synthetic_dataset_is_reproducible_and_boundary_safe(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    config = SyntheticConfig(agents=4, days=8, seed=12345)

    manifest_a = generate_dataset(first, config)
    manifest_b = generate_dataset(second, config)

    assert manifest_a["agent_rows"] == manifest_b["agent_rows"]
    assert manifest_a["provider_rows"] == manifest_b["provider_rows"]
    assert manifest_a["files"][0]["sha256"] == manifest_b["files"][0]["sha256"]
    assert manifest_a["files"][1]["sha256"] == manifest_b["files"][1]["sha256"]
    assert manifest_a["providers"] == ["bKash", "Nagad", "Rocket"]
    assert manifest_a["shortage_positive_rows"] > 0
    assert manifest_a["anomaly_positive_rows"] > 0


def test_evaluation_produces_measured_metrics(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    report_dir = tmp_path / "reports"
    generate_dataset(data_dir, SyntheticConfig(agents=6, days=10, seed=2026))
    report = evaluate_dataset(data_dir, report_dir)

    assert report["measured_metrics_count"] >= 3
    assert len(report["forecast_candidates"]) == 3
    assert report["champion_forecast_model"] in {
        "seasonal_naive_24h",
        "moving_average_6h",
        "ewma_net_change",
    }
    assert 0 <= report["anomaly_detection"]["precision"] <= 1
    assert 0 <= report["anomaly_detection"]["recall"] <= 1
    assert 0 <= report["shortage_detection"]["recall"] <= 1
    assert report["explanation_coverage"] == 1.0
    assert report["safe_language_coverage"] == 1.0
    assert (report_dir / "latest_metrics.json").exists()
    assert (report_dir / "latest_report.md").exists()

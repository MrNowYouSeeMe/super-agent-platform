from fastapi.testclient import TestClient

from app.main import app


def test_health_and_dashboard():
    with TestClient(app) as client:
        health = client.get("/health")
        dashboard = client.get("/api/v1/dashboard")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Request-ID"]
    assert dashboard.status_code == 200
    assert len(dashboard.json()["provider_balances"]) == 3


def test_analysis_contract():
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/analyses",
            json={
                "agent_id": "AGT-TEST-001",
                "scenario": "liquidity_anomaly",
                "language": "banglish",
            },
        )
        analysis_id = started.json()["analysis_id"]

        for _ in range(50):
            snapshot = client.get(f"/api/v1/analyses/{analysis_id}").json()
            if snapshot["status"] == "completed":
                break
            import time
            time.sleep(0.05)

    result = snapshot["result"]
    assert result["classification"] == "requires_review"
    assert 45 <= result["shortage_eta_minutes"] <= 60
    assert "fraud verdict na" in result["summary"]
    assert result["conflicting_records"] == 2
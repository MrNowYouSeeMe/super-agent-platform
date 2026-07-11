import pytest

from app.analytics import run_analysis
from app.schemas import AnalysisRequest, Language, Scenario


@pytest.mark.asyncio
async def test_liquidity_analysis_remains_safe() -> None:
    events = []

    async def emit(event):
        events.append(event)

    result = await run_analysis(
        "analysis_test",
        AnalysisRequest(
            scenario=Scenario.liquidity_anomaly,
            language=Language.banglish,
        ),
        emit,
    )

    assert result.classification.value == "requires_review"
    assert result.shortage_eta_minutes is not None
    assert result.conflicting_records == 2
    assert "fraud verdict na" in result.summary
    assert "fraud_confirmed" not in result.model_dump_json()
    assert len(events) >= 8

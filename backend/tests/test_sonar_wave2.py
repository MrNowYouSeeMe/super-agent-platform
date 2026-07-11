import asyncio
import time
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.evaluation import router as evaluation_router
from app.main import (
    _analysis_event_stream,
    _stream_is_complete,
    app,
    stream_events,
)
from app.redis_jobs import RedisJobStore
from app.schemas import (
    AnalysisEvent,
    AnalysisSnapshot,
    EventStatus,
    JobStatus,
)


class _SlowRedis:
    async def brpop(self, _queue: str) -> None:
        await asyncio.sleep(1)
        return None


class _ResultRedis:
    async def brpop(self, _queue: str) -> tuple[str, str]:
        return ("queue", "analysis-1")


class _NoneRedis:
    async def brpop(self, _queue: str) -> None:
        return None


class _Request:
    def __init__(self, disconnected: bool = False) -> None:
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


class _SnapshotStore:
    def __init__(self, snapshot: AnalysisSnapshot | None) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def get_snapshot(
        self,
        _analysis_id: str,
    ) -> AnalysisSnapshot | None:
        self.calls += 1
        return self.snapshot


def _event() -> AnalysisEvent:
    return AnalysisEvent(
        sequence=1,
        stage="analysis_completed",
        label="Analysis completed",
        status=EventStatus.completed,
        detail="Worker completed safely.",
    )


def _snapshot(
    status: JobStatus = JobStatus.completed,
    events: list[AnalysisEvent] | None = None,
) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        analysis_id="analysis-1",
        status=status,
        events=events if events is not None else [_event()],
    )


async def _collect(stream: Any) -> list[str]:
    return [item async for item in stream]


def test_redis_pop_uses_application_timeout() -> None:
    store = RedisJobStore(cast(Any, _SlowRedis()))
    started = time.perf_counter()

    result = asyncio.run(store.pop_job(timeout=0.02))

    assert result is None
    assert time.perf_counter() - started < 0.5


def test_redis_pop_returns_job_and_handles_empty_result() -> None:
    result_store = RedisJobStore(cast(Any, _ResultRedis()))
    none_store = RedisJobStore(cast(Any, _NoneRedis()))

    assert asyncio.run(result_store.pop_job(timeout=0.2)) == "analysis-1"
    assert asyncio.run(none_store.pop_job(timeout=0.2)) is None


def test_stream_completion_rules() -> None:
    completed = _snapshot()
    running = _snapshot(status=JobStatus.running)

    assert _stream_is_complete(completed, emitted=1)
    assert not _stream_is_complete(completed, emitted=0)
    assert not _stream_is_complete(running, emitted=1)


def test_analysis_event_stream_emits_completed_snapshot() -> None:
    snapshot = _snapshot()
    request = _Request()
    store = _SnapshotStore(snapshot)

    output = asyncio.run(
        _collect(
            _analysis_event_stream(
                "analysis-1",
                cast(Any, request),
                cast(Any, store),
            )
        )
    )

    assert len(output) == 1
    assert output[0].startswith("data: ")
    assert '"stage": "analysis_completed"' in output[0]
    assert store.calls == 1


def test_analysis_event_stream_stops_for_missing_or_disconnected_client() -> None:
    missing_output = asyncio.run(
        _collect(
            _analysis_event_stream(
                "analysis-1",
                cast(Any, _Request()),
                cast(Any, _SnapshotStore(None)),
            )
        )
    )
    disconnected_store = _SnapshotStore(_snapshot())
    disconnected_output = asyncio.run(
        _collect(
            _analysis_event_stream(
                "analysis-1",
                cast(Any, _Request(disconnected=True)),
                cast(Any, disconnected_store),
            )
        )
    )

    assert missing_output == []
    assert disconnected_output == []
    assert disconnected_store.calls == 0


def test_stream_events_returns_sse_response() -> None:
    response = asyncio.run(
        stream_events(
            "analysis-1",
            cast(Any, _Request()),
            cast(Any, _SnapshotStore(_snapshot())),
        )
    )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"


def test_stream_events_rejects_missing_analysis() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            stream_events(
                "missing",
                cast(Any, _Request()),
                cast(Any, _SnapshotStore(None)),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Analysis was not found."


def test_evaluation_routes_return_generated_artifacts(monkeypatch: Any) -> None:
    dataset = cast(Any, object())
    report = cast(Any, object())

    monkeypatch.setattr(
        evaluation_router,
        "load_dataset_summary",
        lambda: dataset,
    )
    monkeypatch.setattr(
        evaluation_router,
        "load_evaluation_report",
        lambda: report,
    )

    assert asyncio.run(evaluation_router.dataset_summary()) is dataset
    assert asyncio.run(evaluation_router.evaluation_report()) is report


def test_evaluation_routes_map_missing_artifacts_to_503(
    monkeypatch: Any,
) -> None:
    def missing_dataset() -> Any:
        raise FileNotFoundError("dataset missing")

    def missing_report() -> Any:
        raise FileNotFoundError("report missing")

    monkeypatch.setattr(
        evaluation_router,
        "load_dataset_summary",
        missing_dataset,
    )
    monkeypatch.setattr(
        evaluation_router,
        "load_evaluation_report",
        missing_report,
    )

    with pytest.raises(HTTPException) as dataset_error:
        asyncio.run(evaluation_router.dataset_summary())

    with pytest.raises(HTTPException) as report_error:
        asyncio.run(evaluation_router.evaluation_report())

    assert dataset_error.value.status_code == 503
    assert report_error.value.status_code == 503


def test_openapi_documents_operational_error_responses() -> None:
    paths = app.openapi()["paths"]

    assert "404" in paths["/api/v1/analyses/{analysis_id}"]["get"]["responses"]
    assert "404" in paths["/api/v1/analyses/{analysis_id}/events"]["get"]["responses"]
    assert "503" in paths["/api/v1/evaluation/dataset"]["get"]["responses"]
    assert "503" in paths["/api/v1/evaluation/report"]["get"]["responses"]

    transition_paths = (
        "/api/v1/alerts/{alert_id}/assign",
        "/api/v1/alerts/{alert_id}/acknowledge",
        "/api/v1/alerts/{alert_id}/start-review",
        "/api/v1/alerts/{alert_id}/escalate",
        "/api/v1/alerts/{alert_id}/resolve",
    )

    for path in transition_paths:
        responses = paths[path]["post"]["responses"]
        assert {"404", "409", "422"} <= set(responses)


def test_return_annotations_still_generate_openapi_schemas() -> None:
    paths = app.openapi()["paths"]

    assert "200" in paths["/health"]["get"]["responses"]
    assert "200" in paths["/api/v1/dashboard"]["get"]["responses"]
    assert "202" in paths["/api/v1/analyses"]["post"]["responses"]
    assert "200" in paths["/api/v1/alerts"]["get"]["responses"]

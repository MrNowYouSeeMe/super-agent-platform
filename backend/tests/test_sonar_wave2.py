import asyncio
import time
from typing import Any, cast

from app.main import app
from app.redis_jobs import RedisJobStore


class _SlowRedis:
    async def brpop(
        self,
        _queue: str,
        *,
        timeout: int,
    ) -> None:
        assert timeout == 0
        await asyncio.sleep(1)
        return None


def test_redis_pop_uses_application_timeout() -> None:
    store = RedisJobStore(cast(Any, _SlowRedis()))
    started = time.perf_counter()

    result = asyncio.run(store.pop_job(timeout=0.02))

    assert result is None
    assert time.perf_counter() - started < 0.5


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

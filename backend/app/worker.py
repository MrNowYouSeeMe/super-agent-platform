import asyncio
import logging

from redis.asyncio import Redis

from app.analytics import run_analysis
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.logging_config import configure_logging
from app.redis_jobs import RedisJobStore
from app.repository import create_alert
from app.schemas import (
    AnalysisEvent,
    Classification,
    EventStatus,
    JobStatus,
)

configure_logging()
logger = logging.getLogger("superagent.worker")
settings = get_settings()


async def process_job(store: RedisJobStore, analysis_id: str) -> None:
    payload = await store.get_payload(analysis_id)
    if payload is None:
        await store.fail(analysis_id, "Analysis payload was not found.")
        return

    await store.set_status(analysis_id, JobStatus.running)
    sequence = 0

    async def emit(event: AnalysisEvent) -> None:
        nonlocal sequence
        sequence = max(sequence, event.sequence)
        await store.append_event(analysis_id, event)

    try:
        result = await run_analysis(analysis_id, payload, emit)

        if result.classification != Classification.normal_operational_spike:
            async with SessionLocal() as session:
                alert = await create_alert(session, result)
            result.alert_id = alert.alert_id
            sequence += 1
            await store.append_event(
                analysis_id,
                AnalysisEvent(
                    sequence=sequence,
                    stage="alert_persisted",
                    label="Created a persistent operational alert",
                    status=EventStatus.completed,
                    detail=f"Alert {alert.alert_id} is ready for human coordination.",
                ),
            )
        else:
            sequence += 1
            await store.append_event(
                analysis_id,
                AnalysisEvent(
                    sequence=sequence,
                    stage="no_alert_required",
                    label="No operational alert was required",
                    status=EventStatus.completed,
                    detail="Monitoring remains active without opening a case.",
                ),
            )

        sequence += 1
        await store.append_event(
            analysis_id,
            AnalysisEvent(
                sequence=sequence,
                stage="analysis_completed",
                label="Completed the intelligence workflow",
                status=EventStatus.completed,
                detail="The validated result and workflow state are ready.",
            ),
        )
        await store.complete(analysis_id, result)
        logger.info(
            "analysis_completed",
            extra={"event": "analysis_completed", "analysis_id": analysis_id},
        )
    except Exception:
        logger.exception(
            "analysis_failed",
            extra={"event": "analysis_failed", "analysis_id": analysis_id},
        )
        sequence += 1
        await store.append_event(
            analysis_id,
            AnalysisEvent(
                sequence=sequence,
                stage="analysis_failed",
                label="Analysis failed safely",
                status=EventStatus.failed,
                detail="No unsupported decision was returned.",
            ),
        )
        await store.fail(
            analysis_id,
            "Analysis failed safely. Check worker logs using the request ID.",
        )


async def main() -> None:
    await init_db()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    store = RedisJobStore(redis)
    logger.info("worker_ready", extra={"event": "worker_ready", "worker": "analysis"})

    try:
        while True:
            analysis_id = await store.pop_job(timeout=5)
            if analysis_id is not None:
                await process_job(store, analysis_id)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from redis.asyncio import Redis

from app.analytics import run_analysis
from app.config import get_settings
from app.db import SessionLocal, engine, init_db
from app.logging_config import configure_logging
from app.redis_jobs import RedisJobStore
from app.repository import create_alert
from app.schemas import (
    AnalysisEvent,
    Classification,
    EventStatus,
    JobStatus,
)
from app.tracing import (
    configure_tracing,
    extract_trace_context,
    force_flush_tracing,
)

configure_logging()
logger = logging.getLogger("superagent.worker")
settings = get_settings()
configure_tracing(
    service_name=settings.otel_service_name,
    service_version="0.3.0",
    environment=settings.app_env,
    endpoint=settings.otel_exporter_otlp_traces_endpoint,
    sample_ratio=settings.otel_trace_sample_ratio,
    enabled=settings.otel_tracing_enabled,
    engine=engine,
)
tracer = trace.get_tracer("superagent.worker")


async def process_job(store: RedisJobStore, analysis_id: str) -> None:
    carrier = await store.get_trace_context(analysis_id)
    parent_context = extract_trace_context(carrier)
    request_id = await store.get_request_id(analysis_id)

    with tracer.start_as_current_span(
        "analysis.process",
        context=parent_context,
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "redis",
            "messaging.operation.name": "process",
            "messaging.destination.name": settings.analysis_queue,
            "messaging.message.id": analysis_id,
            "superagent.analysis.id": analysis_id,
        },
    ) as process_span:
        payload = await store.get_payload(analysis_id)
        if payload is None:
            process_span.set_attribute("superagent.analysis.payload_found", False)
            await store.fail(analysis_id, "Analysis payload was not found.")
            return

        process_span.set_attribute(
            "superagent.analysis.scenario", payload.scenario.value
        )
        process_span.set_attribute(
            "superagent.analysis.language", payload.language.value
        )
        await store.set_status(analysis_id, JobStatus.running)
        sequence = 0

        async def emit(event: AnalysisEvent) -> None:
            nonlocal sequence
            sequence = max(sequence, event.sequence)
            process_span.add_event(
                event.stage,
                attributes={
                    "superagent.event.sequence": event.sequence,
                    "superagent.event.status": event.status.value,
                },
            )
            await store.append_event(analysis_id, event)

        try:
            with tracer.start_as_current_span("analysis.compute"):
                result = await run_analysis(analysis_id, payload, emit)

            process_span.set_attribute(
                "superagent.analysis.classification",
                result.classification.value,
            )
            process_span.set_attribute(
                "superagent.analysis.confidence", result.confidence
            )

            if result.classification != Classification.normal_operational_spike:
                with tracer.start_as_current_span("alert.persist"):
                    async with SessionLocal() as session:
                        alert = await create_alert(session, result)
                result.alert_id = alert.alert_id
                process_span.set_attribute(
                    "superagent.alert.id", alert.alert_id
                )
                sequence += 1
                await store.append_event(
                    analysis_id,
                    AnalysisEvent(
                        sequence=sequence,
                        stage="alert_persisted",
                        label="Created a persistent operational alert",
                        status=EventStatus.completed,
                        detail=(
                            f"Alert {alert.alert_id} is ready for human "
                            "coordination."
                        ),
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
                        detail=(
                            "Monitoring remains active without opening a case."
                        ),
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
                    detail=(
                        "The validated result and workflow state are ready."
                    ),
                ),
            )
            await store.complete(analysis_id, result)
            logger.info(
                "analysis_completed",
                extra={
                    "event": "analysis_completed",
                    "analysis_id": analysis_id,
                    "alert_id": result.alert_id,
                    "request_id": request_id,
                },
            )
        except Exception:
            logger.exception(
                "analysis_failed",
                extra={
                    "event": "analysis_failed",
                    "analysis_id": analysis_id,
                    "request_id": request_id,
                },
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
                "Analysis failed safely. Check worker logs using the trace ID.",
            )


async def main() -> None:
    await init_db()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    store = RedisJobStore(redis)
    logger.info(
        "worker_ready",
        extra={"event": "worker_ready", "worker": "analysis"},
    )

    try:
        while True:
            analysis_id = await store.pop_job(timeout=5)
            if analysis_id is not None:
                await process_job(store, analysis_id)
    finally:
        await redis.aclose()
        force_flush_tracing()


if __name__ == "__main__":
    asyncio.run(main())

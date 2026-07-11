from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("superagent.tracing")
_initialized = False
_fastapi_instrumented = False


def configure_tracing(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    endpoint: str,
    sample_ratio: float,
    enabled: bool,
    engine: AsyncEngine | None = None,
) -> None:
    global _initialized

    if _initialized or not enabled:
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment.name": environment,
            "telemetry.sdk.language": "python",
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(sample_ratio)),
    )
    exporter = OTLPSpanExporter(endpoint=endpoint, timeout=5)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    RedisInstrumentor().instrument()
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    _initialized = True
    logger.info(
        "tracing_configured",
        extra={
            "event": "tracing_configured",
            "otel_service_name": service_name,
            "otel_endpoint": endpoint,
            "otel_sample_ratio": sample_ratio,
        },
    )


def instrument_fastapi(app: Any) -> None:
    global _fastapi_instrumented

    if _fastapi_instrumented:
        return

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health",
    )
    _fastapi_instrumented = True


def inject_trace_context() -> dict[str, str]:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


def extract_trace_context(carrier: Mapping[str, str] | None):
    return propagate.extract(dict(carrier or {}))


def attach_trace_context(carrier: Mapping[str, str] | None):
    return otel_context.attach(extract_trace_context(carrier))


def detach_trace_context(token: object) -> None:
    otel_context.detach(token)


def current_trace_ids() -> tuple[str | None, str | None]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, None
    return (
        f"{span_context.trace_id:032x}",
        f"{span_context.span_id:016x}",
    )


def force_flush_tracing(timeout_millis: int = 5000) -> bool:
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if force_flush is None:
        return True
    return bool(force_flush(timeout_millis=timeout_millis))

import json
import logging
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = f"{span_context.trace_id:032x}"
            payload["span_id"] = f"{span_context.span_id:016x}"
            payload["trace_sampled"] = bool(span_context.trace_flags.sampled)

        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "event",
            "analysis_id",
            "alert_id",
            "worker",
            "error_category",
            "trace_id",
            "span_id",
            "otel_service_name",
            "otel_endpoint",
            "otel_sample_ratio",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__

        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.tracing import current_trace_ids

logger = logging.getLogger("superagent.request")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = (
            incoming
            if REQUEST_ID_PATTERN.fullmatch(incoming)
            else uuid.uuid4().hex
        )
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            trace_id, span_id = current_trace_ids()
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "method": request.method,
                    "path": request.url.path,
                    "event": "request_failed",
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        trace_id, span_id = current_trace_ids()
        response.headers["X-Request-ID"] = request_id
        if trace_id is not None:
            response.headers["X-Trace-ID"] = trace_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "trace_id": trace_id,
                "span_id": span_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "event": "request_completed",
            },
        )
        return response

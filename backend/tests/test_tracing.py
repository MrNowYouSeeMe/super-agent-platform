from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
)

from app.logging_config import JsonFormatter
from app.tracing import (
    current_trace_ids,
    extract_trace_context,
    inject_trace_context,
)


def valid_context() -> SpanContext:
    return SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )


def test_trace_context_round_trip() -> None:
    span = NonRecordingSpan(valid_context())
    with trace.use_span(span, end_on_exit=False):
        carrier = inject_trace_context()

    extracted = extract_trace_context(carrier)
    extracted_span = trace.get_current_span(extracted)
    context = extracted_span.get_span_context()

    assert carrier["traceparent"].startswith("00-")
    assert context.trace_id == valid_context().trace_id
    assert context.span_id == valid_context().span_id


def test_current_trace_ids() -> None:
    span = NonRecordingSpan(valid_context())
    with trace.use_span(span, end_on_exit=False):
        trace_id, span_id = current_trace_ids()

    assert trace_id == "1234567890abcdef1234567890abcdef"
    assert span_id == "1234567890abcdef"


def test_json_formatter_adds_trace_correlation() -> None:
    formatter = JsonFormatter()
    record = __import__("logging").LogRecord(
        name="test",
        level=20,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    span = NonRecordingSpan(valid_context())
    with trace.use_span(span, end_on_exit=False):
        rendered = formatter.format(record)

    assert '"trace_id": "1234567890abcdef1234567890abcdef"' in rendered
    assert '"span_id": "1234567890abcdef"' in rendered

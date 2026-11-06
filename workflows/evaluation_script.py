"""Evaluation script for the datetime_tool."""
from agent_with_telemetry import datetime_tool
from evaluation_utils import capture_spans, capture_logs


# Execute the tool (wrap it to capture the OpenTelemetry spans)
with (
    capture_spans() as span_capture,
    capture_logs() as log_capture
):
    result = datetime_tool()

#---------------
# Evaluate logs
#---------------
assert len(log_capture.records) == 1
record = log_capture.records[0]
assert record.levelname == "INFO"
assert record.getMessage() == "Datetime tool invoked."
tool_result = getattr(record, 'tool_result', None) # 'extra' are added as direct attributes to the LogRecord class
assert tool_result == result

#---------------
# Evaluate spans
#---------------
spans = span_capture.get_finished_spans()
assert len(spans) == 1
span = spans[0]
assert span.name == "execute_tool datetime_tool"
assert span.attributes
assert span.attributes['gen_ai.tool.call.result'] == result
duration_ms = ((span.end_time or 0) - (span.start_time or 0)) / 1e6
assert duration_ms >= 0 and duration_ms < 10 # duration should be less than 10 ms
print(f"Span duration (ms): {duration_ms}")


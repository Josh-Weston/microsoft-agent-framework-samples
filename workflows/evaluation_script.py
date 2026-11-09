"""Evaluation script for the datetime_tool."""
from agent_with_telemetry import datetime_tool
from evaluation_utils import capture_spans, capture_logs
from agent_with_telemetry import agent
import asyncio


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
print(f"Span duration (ms): {duration_ms}")
assert duration_ms >= 0 and duration_ms < 30 # duration should be less than 10 ms

#---------------
# Evaluate agent
#---------------

with (
    capture_spans() as span_capture,
    capture_logs() as log_capture
):
    result = asyncio.run(agent.run("What time is it right now?"))


assert len(log_capture.records) > 1
record = [record for record in log_capture.records if record.getMessage() == "Datetime tool invoked."]
assert len(record) == 1
record = record[0]
assert record.levelname == "INFO"
assert record.getMessage() == "Datetime tool invoked."
tool_result = getattr(record, 'tool_result', None) # 'extra' are added as direct attributes to the LogRecord class


all_spans = span_capture.get_finished_spans()
assert len(all_spans) > 1
spans = [span for span in all_spans if span.name == "execute_tool datetime_tool"]
assert len(spans) == 2 # the framework generates a span automatically
span = spans[0]
assert span.attributes
assert span.attributes['gen_ai.tool.name'] == "datetime_tool"
duration_ms = ((span.end_time or 0) - (span.start_time or 0)) / 1e6
print(f"Span duration (ms): {duration_ms}")
assert duration_ms >= 0 and duration_ms < 30 # duration should be less than 30 ms

print(result.messages[-1].text.lower())
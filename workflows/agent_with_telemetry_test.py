import logging
from agent_with_telemetry import datetime_tool

#----------------------------------
# Test a tool's logging capability
# This test leverage pytest's caplog fixture
#----------------------------------
def test_datetime_tool_emits_structured_log(caplog):
    # Tell caplog to capture INFO and above from your tool's logger
    with caplog.at_level(logging.INFO, logger="datetime_testing"):
        result = datetime_tool()

    # Filter logs we are interested in
    tool_logs = [r for r in caplog.records if getattr(r, "event", None) == "tool_call"]

    assert len(tool_logs) == 1
    record = tool_logs[0]

    # Inspect the LogRecord attributes directly
    assert record.levelname == "INFO"
    assert record.message == "Datetime tool invoked."
    assert record.tool_name == "datetime_tool"
    assert record.tool_result == result


#----------------------------------
# Test a tool's telemetry capability
# See conftest.py for how to implement the otel_spans fixture
#----------------------------------
def test_datetime_tool_telemetry(caplog, otel_spans):
    with caplog.at_level(logging.INFO):
        result = datetime_tool()

    # 1. Inspect the captured OpenTelemetry Span object
    spans = otel_spans.get_finished_spans()
    tool_spans = [s for s in spans if s.attributes.get("gen_ai.operation.name") == "execute_tool"]

    assert len(tool_spans) == 1
    span = tool_spans[0]

    assert span.name == "execute_tool datetime_tool"
    assert span.attributes["gen_ai.tool.name"] == "datetime_tool"
    assert span.attributes["gen_ai.tool.call.result"] == result
    assert span.status.is_ok

    # 2. Inspect the captured LogRecord object
    assert len(caplog.records) == 1
    assert caplog.records[0].tool_name == "datetime_tool"
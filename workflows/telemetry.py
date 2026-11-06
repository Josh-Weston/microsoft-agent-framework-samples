import json
from collections.abc import Callable, Sequence
import os

from agent_framework.observability import configure_otel_providers
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import (
    LogRecordExporter,
    LogRecordExportResult,
)
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    MetricsData,
)

def configure_ipc_telemetry(send: Callable[[bytes], None]) -> None:
    def publish(signal: str, records: list[str]) -> None:
        payload = {
            "type": "telemetry",
            "signal": signal,
            "records": [json.loads(record) for record in records],
        }
        send(json.dumps(payload).encode("utf-8"))

    class IPCSpanExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            publish("spans", [span.to_json() for span in spans])
            return SpanExportResult.SUCCESS

    class IPCLogExporter(LogRecordExporter):
        def export(
            self, batch: Sequence[ReadableLogRecord]
        ) -> LogRecordExportResult:
            publish("logs", [record.to_json() for record in batch])
            return LogRecordExportResult.SUCCESS

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            return True

        def shutdown(self) -> None:
            pass

    class IPCMetricExporter(MetricExporter):
        def export(
            self,
            metrics_data: MetricsData,
            timeout_millis: float = 10_000,
            **kwargs,
        ) -> MetricExportResult:
            publish("metrics", [metrics_data.to_json()])
            return MetricExportResult.SUCCESS

        def force_flush(self, timeout_millis: float = 10_000) -> bool:
            return True

        def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
            pass

    configure_otel_providers(
        enable_console_exporters=False,
        exporters=[
            IPCSpanExporter(),
            IPCLogExporter(),
            IPCMetricExporter(),
        ],
    )
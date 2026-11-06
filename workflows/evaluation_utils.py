from contextlib import contextmanager
import logging
from typing import Generator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

#--------------
# LOGGING UTILS
#--------------
class MemoryLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

@contextmanager
def capture_logs(
    logger_name: str | None = None,
    level: int = logging.INFO,
) -> Generator[MemoryLogHandler]:
    """Context manager to capture logs as objects and clean up afterward."""
    target_logger = logging.getLogger(logger_name)
    previous_level = target_logger.level

    handler = MemoryLogHandler()
    target_logger.setLevel(level)
    target_logger.addHandler(handler)
    try:
        yield handler
    finally:
        # Clean up so we don't leak handlers across multiple eval runs
        target_logger.removeHandler(handler)
        target_logger.setLevel(previous_level)

#------------
# OTEL UTILS
#------------

# Module-level singleton so we only register TracerProvider once per process
_span_exporter: InMemorySpanExporter | None = None

def get_span_exporter() -> InMemorySpanExporter:
    """Lazily initialize the in-memory span exporter once per process."""
    global _span_exporter
    if _span_exporter is None:
        _span_exporter = InMemorySpanExporter()

        # Reuse existing TracerProvider if already configured, or create one
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider()
            trace.set_tracer_provider(provider)

        provider.add_span_processor(SimpleSpanProcessor(_span_exporter))

    return _span_exporter


@contextmanager
def capture_spans() -> Generator[InMemorySpanExporter]:
    """Context manager to capture OpenTelemetry spans in evaluation scripts or tests."""
    exporter = get_span_exporter()
    exporter.clear()
    try:
        yield exporter
    finally:
        pass  # Keep spans available after the `with` block if needed, or clear on next call
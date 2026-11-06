import pytest
from evaluation_utils import capture_spans

@pytest.fixture
def otel_spans():
    """Provides in-memory OpenTelemetry spans for a single test."""
    with capture_spans() as exporter:
        yield exporter
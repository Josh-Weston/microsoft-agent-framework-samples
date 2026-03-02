import json
import asyncio

# Trace imports
from opentelemetry.trace import format_trace_id, format_span_id, set_tracer_provider, get_tracer_provider
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
# from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

# Metric imports
from opentelemetry.metrics import set_meter_provider, get_meter, get_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, PeriodicExportingMetricReader, MetricsData, NumberDataPoint, HistogramDataPoint

# Resource Imports
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME

from agent_framework.observability import enable_instrumentation
from agent_orchestration import sequential_orchestration

# Note: agent_framework.observability.create_resource() is a helper that adds some default attributes like service.name,
# but you can also create your own Resource with any attributes you want using opentelemetry.sdk.resources.Resource.create() as shown below.
resource = Resource.create({SERVICE_NAME: "python-ai-engine"})


# ---------------------------------------------------------
# TRACING IMPLEMENTATION
# ---------------------------------------------------------

class RealTimeSpanProcessor(SpanProcessor):
    """
    Intercepts spans exactly when they start and end, pushing real-time 
    events to the asyncio loop for instant UI updates.
    """

    def __init__(self, queue: asyncio.Queue[tuple[str, ReadableSpan]], loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop

    def on_start(self, span, parent_context=None):
        # We pass a tuple ("START", span) so the UI knows the state
        self.loop.call_soon_threadsafe(self.queue.put_nowait, ("START", span))

    def on_end(self, span):
        # Triggered when the tool or generation finishes
        self.loop.call_soon_threadsafe(self.queue.put_nowait, ("END", span))

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000):
        return True


def setup_tracing(queue: asyncio.Queue[tuple[str, ReadableSpan]], loop: asyncio.AbstractEventLoop):
    tracer_provider = TracerProvider(resource=resource)

    # Instantiate our custom bridge
    realtime_processor = RealTimeSpanProcessor(queue, loop)

    # Attach it using a SimpleSpanProcessor for immediate dispatch to the queue
    tracer_provider.add_span_processor(realtime_processor)

    set_tracer_provider(tracer_provider)

# ---------------------------------------------------------
# METRICS IMPLEMENTATION
# ---------------------------------------------------------


class IPCMetricExporter(MetricExporter):
    """
    Extracts aggregated metrics on a periodic basis and formats them
    to be pushed to the asyncio queue.
    """

    def __init__(self, queue: asyncio.Queue[tuple[str, MetricsData]], loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.queue = queue
        self.loop = loop

    def export(self, metrics_data, timeout_millis: float = 10_000, **kwargs) -> MetricExportResult:
        if self.loop.is_closed():
            return MetricExportResult.FAILURE

        self.loop.call_soon_threadsafe(
            self.queue.put_nowait, ("METRIC", metrics_data))
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30_000, **kwargs):
        pass

    def force_flush(self, timeout_millis: float = 30_000, **kwargs) -> bool:
        return True


def setup_metrics(queue: asyncio.Queue[tuple[str, MetricsData]], loop: asyncio.AbstractEventLoop):
    exporter = IPCMetricExporter(queue, loop)

    # The reader determines how often metrics are collected and exported.
    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=5000)

    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    set_meter_provider(meter_provider)

# ---------------------------------------------------------
# Consumers
# ---------------------------------------------------------


async def span_consumer(queue: asyncio.Queue[tuple[str, ReadableSpan]]):
    """
    Reads real-time span events, serializes them to standard JSON Lines,
    and prints them to stdout so the Golang parent process can read them.
    """
    try:
        while True:
            event_type, span = await queue.get()

            # ---------------------------------------------------------
            # Handle Traces (ReadableSpan)
            # ---------------------------------------------------------
            with open('./traces.jsonl', 'a') as f:
                f.write(span.to_json() + '\n\n')

            context = span.get_span_context()
            if not context or not context.is_valid:
                queue.task_done()
                continue

            trace_id_hex = format_trace_id(context.trace_id)
            span_id_hex = format_span_id(context.span_id)

            # OpenTelemetry attributes are already strictly typed (str, int, float, bool)
            attributes = dict(span.attributes or {})

            payload = {
                "ipc_type": "telemetry",
                "event": event_type,          # "START" or "END"
                "trace_id": trace_id_hex,
                "span_id": span_id_hex,
                "span_name": span.name,
                "attributes": attributes
            }

            # If the span is finished, calculate and append the duration
            if event_type == "END" and span.end_time and span.start_time:
                payload["duration_ms"] = (
                    span.end_time - span.start_time) / 1e6

            # Send through IPC
            json_line = json.dumps(payload)
            # print(json_line, flush=True)
            queue.task_done()

    except asyncio.CancelledError:
        pass


async def metrics_consumer(queue: asyncio.Queue[tuple[str, MetricsData]]):
    """
    Reads real-time metric events, serializes them to standard JSON Lines,
    and prints them to stdout so the Golang parent process can read them.
    """
    try:
        while True:
            event_type, metrics_data = await queue.get()
            print(metrics_data)
            for resource_metric in metrics_data.resource_metrics:
                resource_attrs = dict(
                    resource_metric.resource.attributes or {})
                for scope_metric in resource_metric.scope_metrics:
                    scope_name = scope_metric.scope.name
                    for metric in scope_metric.metrics:
                        for data_point in metric.data.data_points:
                            # Build a unified payload
                            payload = {
                                "ipc_type": "metric",
                                "metric_name": metric.name,
                                "meter_scope": scope_name,
                                "resource_attributes": resource_attrs,
                                "metric_attributes": dict(data_point.attributes or {})
                            }

                            if isinstance(data_point, NumberDataPoint):
                                payload["value"] = data_point.value
                            elif isinstance(data_point, HistogramDataPoint):
                                payload["sum"] = data_point.sum
                                payload["count"] = data_point.count
                            print(json.dumps(payload), flush=True)
    except asyncio.CancelledError:
        pass


async def main():
    # Grab the active loop that asyncio.run() just created
    loop = asyncio.get_running_loop()

    # Create the communication queue
    span_queue = asyncio.Queue[tuple[str, ReadableSpan]]()
    metrics_queue = asyncio.Queue[tuple[str, MetricsData]]()

    # Pass the queue and loop into the setup
    setup_tracing(span_queue, loop)
    setup_metrics(metrics_queue, loop)
    enable_instrumentation()

    # Start the background consumer tasks
    span_task = asyncio.create_task(span_consumer(span_queue))
    metrics_task = asyncio.create_task(metrics_consumer(metrics_queue))

    try:
        # Run the actual application logic
        await sequential_orchestration()
    except Exception as e:
        print(f"Agent orchestration failed: {e}")
    finally:
        trace_provider = get_tracer_provider()
        if isinstance(trace_provider, TracerProvider):
            trace_provider.shutdown()

        meter_provider = get_meter_provider()
        if isinstance(meter_provider, MeterProvider):
            meter_provider.shutdown()

        await span_queue.join()
        await metrics_queue.join()

        # Cancel the consumer tasks to allow the program to exit gracefully
        span_task.cancel()
        metrics_task.cancel()

        await asyncio.gather(span_task, metrics_task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())


# LEFT-OFF: potentially adding await aysncio.to_thread(trace_provider.shutdown) to free-up the main thread to process the metrics payload
# LEFT-OFF: OTEL runs background tasks that "wakeup" every 5 seconds to produce metrics, this is why it is not as easy as just awaiting the orchestrator
# LEFT-OFF: Is there another way other than asyncio.to_thread to "flush" the metrics?

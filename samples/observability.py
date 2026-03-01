import json
import asyncio
from opentelemetry.trace import format_trace_id, format_span_id, set_tracer_provider
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
# from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME
from agent_framework.observability import enable_instrumentation, create_resource
from samples.agent_orchestration import sequential_orchestration


# Note: agent_framework.observability.create_resource() is a helper that adds some default attributes like service.name,
# but you can also create your own Resource with any attributes you want using opentelemetry.sdk.resources.Resource.create() as shown below.
resource = Resource.create({SERVICE_NAME: "python-ai-engine"})


async def trace_consumer(queue: asyncio.Queue):
    """
    Reads real-time span events, serializes them to standard JSON Lines,
    and prints them to stdout so the Golang parent process can read them.
    """
    try:
        while True:
            event_type, span = await queue.get()

            # 1. Grab the context (which holds the IDs)
            context = span.get_span_context()
            if not context.is_valid:
                queue.task_done()
                continue

            # 2. Format IDs into standard hex strings for Go to parse easily
            trace_id_hex = format_trace_id(context.trace_id)
            span_id_hex = format_span_id(context.span_id)

            # OpenTelemetry attributes are already strictly typed (str, int, float, bool)
            attributes = dict(span.attributes or {})

            # 3. Construct the IPC message payload
            payload = {
                "ipc_type": "telemetry",
                "event": event_type,          # "START" or "END"
                "trace_id": trace_id_hex,
                "span_id": span_id_hex,
                "span_name": span.name,
                "attributes": attributes
            }

            # 4. If the span is finished, calculate and append the duration
            if event_type == "END" and span.end_time and span.start_time:
                payload["duration_ms"] = (
                    span.end_time - span.start_time) / 1e6

            # 5. Serialize to a single line and flush immediately to stdout
            # This ensures it crosses the IPC boundary without buffering delays
            json_line = json.dumps(payload)
            # print(json_line, flush=True)

            queue.task_done()

    except asyncio.CancelledError:
        pass


class RealTimeSpanProcessor(SpanProcessor):
    """
    Intercepts spans exactly when they start and end, pushing real-time 
    events to the asyncio loop for instant UI updates.
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop

    def on_start(self, span, parent_context=None):
        # Triggered the exact millisecond the LLM starts a tool or generation!
        # We pass a tuple ("START", span) so the UI knows the state
        self.loop.call_soon_threadsafe(self.queue.put_nowait, ("START", span))

    def on_end(self, span):
        # Triggered when the tool or generation finishes
        self.loop.call_soon_threadsafe(self.queue.put_nowait, ("END", span))

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000):
        return True


def setup_tracing(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    tracer_provider = TracerProvider(resource=resource)

    # Instantiate our custom bridge
    realtime_processor = RealTimeSpanProcessor(queue, loop)

    # Attach it using a SimpleSpanProcessor for immediate dispatch to the queue
    tracer_provider.add_span_processor(realtime_processor)

    set_tracer_provider(tracer_provider)


async def main():
    # Grab the active loop that asyncio.run() just created
    loop = asyncio.get_running_loop()

    # Create the communication queue
    telemetry_queue = asyncio.Queue()

    # Pass the queue and loop into the setup
    setup_tracing(telemetry_queue, loop)
    enable_instrumentation()

    # Start the background consumer task
    consumer_task = asyncio.create_task(trace_consumer(telemetry_queue))

    # Run the actual application logic
    await sequential_orchestration()

    # Clean up: wait for all spans to be processed, then cancel the listener
    await telemetry_queue.join()
    consumer_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())

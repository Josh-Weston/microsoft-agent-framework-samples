import datetime
import logging
from zoneinfo import ZoneInfo
from opentelemetry import trace
from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
import os

load_dotenv()

logger = logging.getLogger("datetime_testing") # supplies name of the current module
tracer = trace.get_tracer("datetime_testing") # supplies name of the current module

# ----------------------------------------------
# The tool provides OTEL and Logging integration
# ----------------------------------------------
def datetime_tool() -> str:
    """
    Get the current date and time in Nova Scotia (Atlantic Time).
    Use this tool to resolve relative time expressions like 'today', 'tomorrow', or 'next month'.

    Returns:
        The datetime as a string.
    """
    with tracer.start_as_current_span(
        "execute_tool datetime_tool",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "datetime_tool",
        },
    ) as span:
        ns_tz = ZoneInfo("America/Halifax")
        ns_now = datetime.datetime.now(ns_tz)
        result = ns_now.strftime("%A, %B %d, %Y %I:%M %p %Z")

        # Attach output to the span for agent evaluation / inspection
        span.set_attribute("gen_ai.tool.call.result", result)

        logger.info(
            "Datetime tool invoked.",
            extra={
                "event": "tool_call",
                "tool_name": "datetime_tool",
                "tool_result": result,
            },
        )

        return result

chat_client = OpenAIChatClient(
    base_url=os.getenv("FOUNDRY_OPENAI_BASE_URL"),
    api_key=os.getenv("FOUNDRY_API_KEY"),
    model=os.getenv("FOUNDRY_MODEL"),
)

agent = Agent(
    client=chat_client,
    name="Date Time Agent",
    description="An agent that provides the current date and time in Nova Scotia.",
    instructions="Use your tools to get the current date and time in Nova Scotia.",
    tools=[datetime_tool],
    context_providers=[],
)
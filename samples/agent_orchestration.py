import asyncio
import os
from typing import Annotated, cast
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv
load_dotenv()

if True:
    from agent_framework import tool, Agent, Message
    from agent_framework.orchestrations import SequentialBuilder
    from agent_framework.openai import OpenAIChatClient
    from agent_framework.observability import configure_otel_providers
    # Console exporters are enabled via the ENABLE_CONSOLE_EXPORTERS env var
    configure_otel_providers()


async def sequential_orchestration():

    class WeatherInfo(BaseModel):
        """Structured output format for weather information."""
        model_config = ConfigDict(extra="forbid")
        location: Annotated[str, Field(
            description="The location for which the weather information is provided.")]
        temperature: Annotated[str, Field(
            description="The current temperature in degrees Celsius, rounded to two decimal places (e.g., 15.31).")]
        description: Annotated[str, Field(
            description="A brief description of the current weather conditions.")]

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "WeatherInfo",
            "schema": WeatherInfo.model_json_schema(),
            "strict": True,
        },
    }

    @tool(name="get_weather", description="Get the weather for a given location.")
    def get_weather(
        location: Annotated[str, Field(description="The location to get the weather for.")],
    ) -> str:
        """Get the weather for a given location."""
        return f"The weather in {location} is cloudy with a high of -14.2165°C."

    # Note: can set the agent here for the entire client, or can set it per call in the options
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    tool_calling_agent = Agent(
        client=chat_client,
        instructions="Use the get_weather tool to get the weather for a given location.",
        name="Weather agent",
        description="An agent that can get the weather for a given location.",
        tools=[get_weather],
        default_options={
            "model_id": "openai/gpt-oss-20b:fireworks-ai",
        }
    )

    structured_output_agent = Agent(
        client=chat_client,
        instructions="Agent formats its input in a structured format",
        name="Structured output agent",
        description="An agent that can provide information in a structured format.",
        default_options={
            "model_id": "openai/gpt-oss-20b:fireworks-ai",
            "temperature": 0.3,
            "response_format": response_format,
        },
    )

    outputs: list[list[Message]] = []
    workflow = SequentialBuilder(
        participants=[tool_calling_agent, structured_output_agent]).build()

    # Note: this waits until the workflow is complete before yielding any events
    async for event in workflow.run("What is the weather in Halifax, Nova Scotia?", stream=True):
        if event.type == "output":
            outputs.append(cast(list[Message], event.data))

    if outputs:
        print("===== Final Conversation =====")
        for i, msg in enumerate(outputs[-1], start=1):
            name = msg.author_name or (
                "assistant" if msg.role == "assistant" else "user")
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

if __name__ == "__main__":
    asyncio.run(sequential_orchestration())

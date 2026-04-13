import asyncio
from typing import Annotated

import os
from agent_framework import Agent, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIChatCompletionClient  # for older models
from agent_framework.openai import OpenAIChatClient  # for newer models
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    # Extract the injected argument from the explicit context
    user_id = ctx.kwargs.get("user_id", "unknown")

    # Simulate using the user_id for logging or personalization
    print(f"Getting weather for user: {user_id}")

    return f"The weather in {location} is cloudy with a high of 15°C."


async def main() -> None:

    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        # model="openai/gpt-oss-120b:cerebras",
        model="google/gemma-4-31B-it:together",
    )

    agent = Agent(
        client=chat_client,
        name="WeatherAgent",
        instructions=(
            "You are a helpful weather assistant. "
            "CRITICAL: After you call a tool and receive the tool's result, "
            "you MUST write a final conversational response to the user summarizing the weather data. "
            "Never leave your final response blank."
        ),
        tools=[get_weather],
    )

    # Pass the runtime context explicitly when running the agent.
    response = await agent.run(
        "What is the weather like in Amsterdam?",
        function_invocation_kwargs={"user_id": "user_123"},
    )
    for message in response.messages:
        for content in message.contents:
            if content.type == "text_reasoning":
                print(f"Reasoning: {content.text}")

if __name__ == "__main__":
    asyncio.run(main())

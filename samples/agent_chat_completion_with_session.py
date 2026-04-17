"""Sessions allow for multiturn conversations
where the agent automatically presists the conversation history in-memory
"""

import asyncio
from typing import Annotated

import os
from agent_framework import Agent, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIChatCompletionClient  # for older models (e.g., oss-120b)
from agent_framework.openai import OpenAIChatClient  # for newer models
from agent_framework import InMemoryHistoryProvider
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is cloudy with a high of 15°C."


async def main() -> None:

    old_models = ["openai/gpt-oss-120b:sambanova"]
    new_models = ["google/gemma-4-31B-it:together"]

    # Note: Hugging Face Inference API is serverless and designed to be stateless; it does not store conversation sessions, user history, or context across API calls

    # OpenAIChatCompletionClient - sessions work as expected
    # OpenAIChatClient - must pass the additional_properties function

    chat_client = OpenAIChatCompletionClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        # model="openai/gpt-oss-120b:sambanova",
        model="google/gemma-4-31B-it:together",
        # additional_properties={"store": False}, # use in-memory store instead of server store
    )

    agent = Agent(
        client=chat_client,
        name="WeatherAgent",
        instructions=(
            "You are a helpful weather assistant with access to a get_weather tool for answering questions about the weather. "
        ),
        tools=[get_weather],
        # This won't work with OpenAIChatClient
        context_providers=[InMemoryHistoryProvider('memory', load_messages=True)], # will be added implicitly if not provided, but should add explicitly
        # additional_properties={"store": False},
    )

    ## Sessions
    session = agent.create_session()

    # Pass the runtime context explicitly when running the agent.
    result = await agent.run("My name is Josh. What is the weather like in Amsterdam?", session=session)
    print(f"Agent response: {result}")
    result = await agent.run("What do you remember about me?", session=session)
    print(f"Agent response: {result}")

    print(session.to_dict())
    
if __name__ == "__main__":
    asyncio.run(main())

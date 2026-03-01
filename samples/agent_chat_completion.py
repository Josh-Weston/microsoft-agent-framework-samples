import asyncio
import os
from typing import Annotated
from pydantic import Field
from agent_framework import tool, Agent, Message
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()


@tool(name="get_weather", description="Get the weather for a given location.", approval_mode='never_require')
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is cloudy with a high of 15°C."


async def basic_example():
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        # set the model here or can set it per call in the agent options
        model_id="openai/gpt-oss-20b:fireworks-ai",
    )

    msg = Message(
        "user", None, text="What is the weather in Montreal, Canada? Respond with just the weather")
    agent = Agent(client=chat_client, tools=[get_weather])
    response = await agent.run(msg)
    print(response)

if __name__ == "__main__":
    asyncio.run(basic_example())

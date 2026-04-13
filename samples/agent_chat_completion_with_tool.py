import asyncio
import os
from typing import Annotated
from pydantic import Field
from agent_framework import FunctionInvocationContext, tool, Agent, Message
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

load_dotenv()


@tool(name="get_weather", description="Get the weather for a given location.", approval_mode='never_require')
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    print(ctx)
    print(ctx.metadata)
    print(ctx.kwargs)
    return f"The weather in {location} is cloudy with a high of 15°C."


async def basic_example():
    chat_client = OpenAIChatCompletionClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        # set the model here or can set it per call in the agent options
        # model="openai/gpt-oss-20b:fireworks-ai",
        model="openai/gpt-oss-120b:cerebras",
    )
    msg = Message(
        "user", contents=["What is the weather in Montreal, Canada?"])
    agent = Agent(client=chat_client,
                  instructions="You are a helpful weather assistant.", tools=[get_weather])
    response = await agent.run(msg, function_invocation_kwargs={"user_id": "123"})
    print(response.to_dict())
    for message in response.messages:
        for content in message.contents:
            print(f"Content type: {content.type}")
            print(f"Content: {content}")
            if content.type == "text":
                print(f"Text: {content.text}")
            elif content.type == "data":
                print(f"Data URI: {content.uri}")
            elif content.type == "uri":
                print(f"External URI: {content.uri}")

if __name__ == "__main__":
    asyncio.run(basic_example())

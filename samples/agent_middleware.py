import asyncio
import os
from typing import Annotated
from pydantic import Field
from agent_framework import (
    FunctionInvocationContext,
    function_middleware,
    chat_middleware,
    agent_middleware,
    tool,
    Agent,
    Message,
    ChatResponse,
    MiddlewareTermination
)
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

load_dotenv()

# LEFT-OFF: this all works, but what is the order of execution?
# LEFT-OFF: prove the order of execution (it should go Agent middleware -> Chat middleware -> Function middleware -> tool execution -> Function middleware -> Chat middleware -> Agent middleware, but need to verify this is the case)

"""
Middleware order with mixed registration scopes:

Agent-level middleware wraps run-level middleware.
For agent middleware [A1, A2] and run middleware [R1, R2], execution order is: A1 -> A2 -> R1 -> R2 -> Agent -> R2 -> R1 -> A2 -> A1.
Function/chat middleware follows the same wrapping principle at tool/chat-call time.
"""


@tool(name="get_weather", description="Get the weather for a given location.", approval_mode='never_require')
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
    ctx: FunctionInvocationContext,
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is cloudy with a high of 15°C."


@function_middleware
async def overwrite_function_arguments(context, call_next):

    print("Middleware before function execution")
    # Inject additional arguments into the function invocation context
    # context.kwargs.setdefault("location", "Halifax, Canada")
    # context.kwargs["location"] = "Halifax, Canada"
    # print(context.arguments)
    # overwrite the location argument
    # Note: context.arguments = { 'location': 'Montreal, Canada' }
    # Note: the framework cleanses the arguments, so it will only pass 'location' downstream (you cannot add new properties to the arguments)
    # Note: use the metadata object to pass additional information downstream to middleware
    context.metadata["original_location"] = context.arguments.get('location')
    context.arguments["location"] = "Halifax, Canada"
    await call_next()


@function_middleware
async def overwrite_results(context, call_next):
    print("Middleware before function execution")
    await call_next()
    print("Middleware after function execution")
    # Overwrite the function result
    context.result = f"The weather in {context.metadata['original_location']} is sunny with a high of 25°C."


@chat_middleware
async def security_check(context, call_next):
    print("Chat middleware before agent run")
    blocked_terms = ['weathers']
    for message in context.messages:
        if message.text:
            message_lower = message.text.lower()
            if any(term in message_lower for term in blocked_terms):
                print(f"Blocked message due to security check: {message.text}")
                context.result = ChatResponse(
                    messages=[
                        Message(
                            role="assistant",
                            contents=[
                                f"Sorry, I cannot assist with that request due to security policies."]
                        )
                    ]
                )
                raise MiddlewareTermination
    # Continue if not blocked
    await call_next()


@chat_middleware
async def token_usage(context, call_next):
    print("Chat middleware for token usage before agent run")
    # Continue if not blocked
    await call_next()

    # How we can access the model, token usage, etc.
    if context.result is not None:
        print(context)


@agent_middleware
async def agent_logger(context, call_next):
    print(f"Agent middleware before agent run")
    await call_next()
    print(f"Agent middleware after agent run")


async def basic_example():
    chat_client = OpenAIChatCompletionClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        # set the model here or can set it per call in the agent options
        model="openai/gpt-oss-20b:fireworks-ai",
        # model="openai/gpt-oss-120b:cerebras",
    )
    msg = Message(
        "user", contents=["What is the weather in Montreal, Canada?"])
    agent = Agent(client=chat_client,
                  instructions="You are a helpful weather assistant.",
                  tools=[get_weather],
                  middleware=[
                      token_usage,
                      security_check,
                      agent_logger,
                      overwrite_function_arguments,
                      overwrite_results]
                  )
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

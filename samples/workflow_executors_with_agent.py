"""
Create executors for a workflow, along with an agent.
"""
import asyncio
import aiohttp
import os
from typing import TypedDict, Never
from agent_framework import AgentExecutorResponse, Message, Workflow, WorkflowBuilder, WorkflowContext, executor
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

from utils import is_agent_response, is_message, is_message_list

# See these notes: https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/_start-here/step1_executors_and_edges.py

# Ping the API, find the most current news article, retrieve its content, and have the agent summarize it.

APIResult = TypedDict(
    "APIResult",
    {
        "Contents": str,
        ":id": str,
        ":version": str,
        ":created_at": str,
        ":updated_at": str

    }
)


@executor(id="ping_open_data_portal_executor")
async def ping_open_data_portal(query: str, ctx: WorkflowContext[str]) -> None:
    url = 'https://data.novascotia.ca/api/v3/views/xcif-vvr3/query.json?query=SELECT Contents ORDER BY Timestamp DESC LIMIT 1'
    custom_headers = {
        'Content-Type': 'application/json',
        'X-App-Token': "jOwo2Djg6E4JL9lEgp7AIAFhC"
    }
    async with (
        aiohttp.ClientSession() as session,
        session.get(url, headers=custom_headers) as response
    ):
        if response.status == 200:
            data: list[APIResult] = await response.json()
            contents = data[0]["Contents"]
            # Extract the relevant information from the data
            # Send the contents to the next node in the workflow
            await ctx.send_message(contents)
        else:
            raise Exception(
                f"API request failed with status code {response.status}")


@executor(id="output_executor")
async def normalize_output(response: AgentExecutorResponse, ctx: WorkflowContext[Never, Message | None]) -> None:
    """
    Acts as an adapter to extract a clean list of messages from the raw agent execution.
    """
    # Extract all messages from the upstream agent (note: this only provides messages for the single upstream agent)
    clean_messages = response.full_conversation

    # Emit the clean list as the final output of the workflow
    # Yield the last message or None if there are no messages
    await ctx.yield_output(clean_messages[-1] if clean_messages else None)


def get_agent():
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    return chat_client.as_agent(
        instructions=(
            "You are a helpful assistant that summarizes news articles. "
            "You will be given the contents of a news article and you should provide a concise summary of the article. "
            "Be sure to capture the main points and key details in your summary."
        ),
        name="News Article Summarizer",
        tools=[],
        default_options={
            "model_id": "openai/gpt-oss-120b:cerebras",
        },
    )


def create_workflow() -> Workflow:
    article_agent = get_agent()
    return WorkflowBuilder(start_executor=ping_open_data_portal) \
        .add_edge(ping_open_data_portal, article_agent) \
        .add_edge(article_agent, normalize_output) \
        .build()


async def main():
    wf = create_workflow()
    # Note: cannot be None, has to be an empty string if not passing any input
    # No input needed since the ping_open_data_portal executor pulls the most recent article
    events = await wf.run("")
    outputs = events.get_outputs()
    for o in outputs:
        if is_agent_response(o):
            print("Agent executor response:")
            print(o)
        elif is_message(o):
            print("Message:")
            print(o.text)
        elif is_message_list(o):
            print("List of messages:")
            for msg in o:
                print(msg)
        else:
            print(f"Unknown output type: {type(o)}")

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())

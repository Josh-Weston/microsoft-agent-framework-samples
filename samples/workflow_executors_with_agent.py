"""
Create executors for a workflow, along with an agent.
"""
import asyncio
import aiohttp
from typing import Never
from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler, executor


# See these notes: https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/_start-here/step1_executors_and_edges.py


# LEFT-OFF: add an executor for pinging the open-data portal for information
# LEFT-OFF: pull the URL out
# LEFT-OFF: create another executor that takes the URL and uses it to pull data from the open-data portal
# LEFT-OFF: feed this data into our agent to summarize the results
# LEFT-OFF: agent returns its summarized response


# Ping the API, find the most current news article, retrieve its content, and have the agent summarize it.

# LEFT-OFF: need to get an APP Token for the Data Portal (check work laptop)

@executor(id="ping_open_data_portal_executor")
async def ping_open_data_portal(query: str, ctx: WorkflowContext[Never, str]) -> None:
    url = 'https://data.novascotia.ca/api/v3/views/xcif-vvr3/query.json'
    custom_headers = {
        'Content-Type': 'application/json',
        'X-App-Token': "YOURAPPTOKENHERE"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=custom_headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                print(f"Error: {response.status}")
                return None
            # code to handle the response and extract the relevant information

    # code to ping the open-data portal with the query and get the results
    results = f"Results for {query}"


# 1. Executor class without @handler types
class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler()
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        await ctx.send_message(result)

# 2. Executor class with @handler types


class LowerCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    # If we don't specify the input and output types, it will use instrospection to determine the types.
    @handler(input=str, output=str)
    async def to_lower_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.lower()
        await ctx.send_message(result)

# 3. Function-based executor using introspection
# WorflowContext[Never, str] means this executor does not send messages to downstream nodes and yields a workflow output of type str


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    result = text[::-1]
    # Yield the output - the workflow will complete when idle
    await ctx.yield_output(result)


def create_workflow() -> Workflow:
    upper_case_executor = UpperCase(id="upper_case_executor")
    lower_case_executor = LowerCase(id="lower_case_executor")

    return WorkflowBuilder(start_executor=upper_case_executor) \
        .add_edge(upper_case_executor, lower_case_executor) \
        .add_edge(lower_case_executor, reverse_text) \
        .build()


def create_simple_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=ping_open_data_portal).build()


async def main():
    # await ping_open_data_portal)
    wf = create_simple_workflow()
    # Note: cannot be None, has to be an empty string if not passing any input
    events = await wf.run("")
    # print(events.get_outputs())
    # events = await wf.run("heLLo World")
    print(events.get_outputs())
    print("Final state:", events.get_final_state())

if __name__ == "__main__":
    asyncio.run(main())

"""
Create executors for a workflow
"""
import asyncio
from typing import Never
from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler, executor


# See these notes: https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/_start-here/step1_executors_and_edges.py


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


async def main():
    wf = create_workflow()
    events = await wf.run("heLLo World")
    print(events.get_outputs())
    print("Final state:", events.get_final_state())

if __name__ == "__main__":
    asyncio.run(main())

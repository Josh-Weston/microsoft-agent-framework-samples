"""
Using Foundry + GPT model with a responses loop is much easier than using HuggingFace.

Note: the framework loop equivalent to my manual responses loop is found in:

C:\Users\JOSHUAS\dev\josh-weston\microsoft-agent-framework-samples\.venv\Lib\site-packages\agent_framework\_tools.py

Look for the `for attempt_idx in range(attempt_start, max_iterations):` loop in the `_tools.py` file.

"""

import asyncio
import os
from typing import Annotated

from sandbox import AgentSandbox
from agent_framework import tool
from agent_framework import Content
from agent_framework.openai import OpenAIChatClient  # Responses API
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

class BashResponse(BaseModel):
    exit_code: Annotated[str, Field(
        description="The exit code for the command. A code of 0 means the command was successful")]
    output: Annotated[str, Field(
        description="The output from running the command")]


def run_bash_in_sandbox(sandbox: AgentSandbox, command: str) -> BashResponse:
    result = sandbox.execute(command)
    return BashResponse(
        exit_code=str(result["exit_code"]),
        output=result["output"],
    )

def get_message(contents: list[Content]) -> str:
    if not contents:
        return ""

    combined = ""

    for c in contents:
        match(c.type):
            case 'function_call':
                combined += f"Function call: {c.arguments} "
            case 'function_result':
                combined += f"Function result: {c.result} "
            case 'text':
                combined += f"Text: {c.text} "
            case _:
                combined += f"{c.message} "

    return combined.strip()

def get_full_output(contents: list[Content]) -> str:
    if not contents:
        return ""

    return " ".join(str(c.to_dict()) for c in contents)

async def run_loop(user_prompt: str):

    base_url = os.getenv("AZURE_OPENAI_BASE_URL")
    if not base_url:
        raise ValueError("AZURE_OPENAI_BASE_URL environment variable is not set.")

    model = os.getenv("AZURE_MODEL")
    if not model:
        raise ValueError("AZURE_MODEL environment variable is not set.")

    openai_client = OpenAIChatClient(
        model=model,
        base_url=base_url,
        credential=DefaultAzureCredential()
    )

    # Boot the stateful container
    with AgentSandbox(image="python:3.14-slim") as sandbox:

        @tool(approval_mode="never_require", description="Execute a bash command in the sandbox environment")
        def execute_bash(
            command: Annotated[str, Field(description="The bash command to run")],
        ) -> BashResponse:
            return run_bash_in_sandbox(sandbox, command)

        agent = openai_client.as_agent(
            name="SandboxAssistant",
            instructions=(
                "You are an AI assistant. Use the bash tool to solve user requests. "
                "First try to write the bash command to a script and execute it. "
                "If an error occurs, try again by running the Python interpreter directly. "
                "Return the final answer in pirate speak."
            ),
            tools=[execute_bash],
        )
        response = await agent.run(user_prompt)

        with open('final_answer.txt', 'w', encoding='utf-8') as f:
            # f.write("\n".join([get_full_output(item.contents) for item in response.messages]))
            f.write("\n".join([get_message(item.contents) for item in response.messages]))
            # f.write("\n".join([" ".join(str(c.to_dict()) for c in item.contents) for item in response.messages]))

# Usage:
asyncio.run(run_loop(
    "Use your available tools to calculate the 10th Fibonacci number. Respond with the calculated number"))

# TODO: This is working as expected, now to create even more robust solution using the isolation environment
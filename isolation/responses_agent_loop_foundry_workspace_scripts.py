"""
This solution allows the agent CRUD access to a specific directory within a sandboxed environment,
enabling it to execute bash commands and interact with the file system safely.
"""

import asyncio
import os
from typing import Annotated

from sandbox_workspace import AgentSandbox
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

def write_file_in_sandbox(sandbox: AgentSandbox, path: str, content: str) -> BashResponse:
    result = sandbox.write_file(path, content)
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
            case 'text_reasoning':
                combined += f"Reasoning: {c.text} "
            case _:
                combined += f"{c.message} "

    return combined.strip()

def get_full_output(contents: list[Content]) -> str:
    if not contents:
        return ""

    return "\n".join(str(c.to_dict()) for c in contents)

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
        credential=DefaultAzureCredential(),
    )

    # Boot the stateful container
    with AgentSandbox(image="python:3.14-slim") as sandbox:

        @tool(approval_mode="never_require", description="Execute a bash command in the sandbox environment")
        def execute_bash(
            command: Annotated[str, Field(description="The bash command to run")],
        ) -> BashResponse:
            return run_bash_in_sandbox(sandbox, command)

        @tool(approval_mode="never_require", description="Write a file's full contents in the sandbox environment. Prefer this over execute_bash for creating/overwriting files since it avoids shell-quoting errors.")
        def write_file(
            path: Annotated[str, Field(description="The absolute or workdir-relative path of the file to write")],
            content: Annotated[str, Field(description="The full text content to write to the file")],
        ) -> BashResponse:
            return write_file_in_sandbox(sandbox, path, content)

        agent = openai_client.as_agent(
            name="SandboxAssistant",
            instructions=(
                "You are an AI assistant. Use your tools to solve the user's request. You have access to various scripts in the `/scripts` volume mounted at the root that you can use as needed."
            ),
            tools=[execute_bash, write_file],
            # reasoning must go in default_options (forwarded to the Responses API request);
            # additional_properties is just metadata stored on the agent and never sent to the model.
            default_options={
                "reasoning": {"effort": "high", "summary": "detailed"}
            }
        )
        # Note: the agent will send a single output with multiple tool_calls to the tools defined above.
        # This way, the tools can be executed in parallel if needed.
        response = await agent.run(user_prompt)
        with open('full_output.txt', 'w', encoding='utf-8') as f:
            f.write(get_full_output([c for item in response.messages for c in item.contents]))

# Usage:
asyncio.run(run_loop(
    # "Run a script that prints a message to the user."
    'Run a script that reverses the text "Hello, from MAF"'
))

# LEFT-OFF : Added reasoning step; look into the next evolution of this.
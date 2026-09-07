"""
This solution allows the agent to access a skill for understanding the skills. This is similar to tool calling, but
is more flexible than re-writing the application.
"""

import asyncio
import os
import shlex
from typing import Annotated

from sandbox_workspace_mounted import AgentSandbox
from agent_framework import tool, SkillsProvider, ToolApprovalMiddleware
from pathlib import Path
from agent_framework import Content
from agent_framework.openai import OpenAIChatClient  # Responses API
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from datetime import datetime, timezone

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

    dicts = []
    for c in contents:
        d = c.to_dict()
        # protected_data is OpenAI's encrypted reasoning payload, not human-readable; drop it from logs
        if d.get("protected_data"):
            d["protected_data"] = f"<redacted, {len(d['protected_data'])} chars>"
        dicts.append(d)

    return "\n".join(str(d) for d in dicts)

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


        MEMORY_PATH = "agent_memory.md"

        def append_memory_in_sandbox(
            sandbox: AgentSandbox, entry: str
        ) -> BashResponse:
            timestamp = datetime.now(timezone.utc).isoformat()
            content = f"\n\n## {timestamp}\n{entry.strip()}\n"
            result = sandbox.execute(
                f"printf %s {shlex.quote(content)} >> {shlex.quote(MEMORY_PATH)}"
            )
            return BashResponse(
                exit_code=str(result["exit_code"]),
                output=result["output"],
            )

        @tool(
            approval_mode="never_require",
            description=(
                "Append a concise durable-memory entry to agent_memory.md. "
                "Record significant results, decisions, changed files, and pending work. "
                "Do not record private reasoning."
            ),
        )
        def append_memory(
            entry: Annotated[str, Field(description="The durable-memory entry to append")]
        ) -> BashResponse:
            return append_memory_in_sandbox(sandbox, entry)

        # def write_memory_in_sandbox(
        #     sandbox: AgentSandbox, summary: str
        # ) -> BashResponse:
        #     return write_file_in_sandbox(sandbox, MEMORY_PATH, summary)

        # @tool(
        #     approval_mode="never_require",
        #     description=(
        #         "Replace the durable working-memory summary in agent_memory.md. "
        #         "Use it after completing a meaningful milestone or task. Include "
        #         "completed work, important results, decisions, and remaining work. "
        #         "Do not include private reasoning."
        #     ),
        # )
        # def write_memory(
        #     summary: Annotated[
        #         str,
        #         Field(description="The complete replacement working-memory summary")
        #     ],
        # ) -> BashResponse:
        #     return write_memory_in_sandbox(sandbox, summary)

        @tool(approval_mode="never_require", description="Write a file's full contents in the sandbox environment. Prefer this over execute_bash for creating/overwriting files since it avoids shell-quoting errors.")
        def write_file(
            path: Annotated[str, Field(description="The absolute or workdir-relative path of the file to write")],
            content: Annotated[str, Field(description="The full text content to write to the file")],
        ) -> BashResponse:
            return write_file_in_sandbox(sandbox, path, content)

        # How we can point to individual skills (the framework first checks for a SKILL.md to determine if we are pointing directly to a skill or to a catalogue of skills)
        skills_provider = SkillsProvider.from_paths(
            skill_paths=Path(__file__).parent / 'skills' / 'scripts',
        )

        agent = openai_client.as_agent(
            name="SandboxAssistant",
            instructions=(
                "You are an AI assistant. Use your tools to solve the user's request. "
                "You have access to various scripts in the `/scripts` volume mounted at "
                "the root that you can use as needed. You can write and read files from your "
                "current working directory, it is your personal workspace. First use the durable "
                "working memory and the current request to determine whether you can complete the task. "
                "Only consult the 'scripts' skill when the working memory does not contain enough "
                "information to complete the request and a script may be relevant. "
                "After completing a meaningful milestone, call append_memory with concise facts: "
                "completed work, key results, decisions, changed files, and pending work. "
                "Before your final response, call write_memory to consolidate the current durable state. "
                "Do not store private reasoning, raw chain-of-thought, secrets, or verbose tool output. "
                "Treat the memory as potentially stale and verify it when correctness matters."
            ),
            tools=[execute_bash, write_file, append_memory],
            context_providers=[skills_provider],
            # Required to avoid manual approval for skills
            middleware=[
                ToolApprovalMiddleware(
                    auto_approval_rules=[SkillsProvider.all_tools_auto_approval_rule]
                )
            ],
            # reasoning must go in default_options (forwarded to the Responses API request);
            # additional_properties is just metadata stored on the agent and never sent to the model.
            default_options={
                "reasoning": {"effort": "high", "summary": "detailed"}
            }
        )

        memory_path = Path(__file__).parent / "workspace" / "agent_memory.md"
        memory = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""

        prompt_with_memory = f"""Durable memory from prior work:
        {memory or "(none)"}

        Current request:
        {user_prompt}
        """

        # Load Memory


        # Note: the agent will send a single output with multiple tool_calls to the tools defined above.
        # This way, the tools can be executed in parallel if needed.
        # Middleware requires a session
        session = agent.create_session()
        response = await agent.run(prompt_with_memory, session=session)
        with open('full_output.txt', 'w', encoding='utf-8') as f:
            f.write(get_full_output([c for item in response.messages for c in item.contents]))

# Usage:
asyncio.run(run_loop(
    "Run a script to reverse the following text: 'Hello friends, how are you?'"
    # "Check my calendar for availability of September 8, 2026"
))
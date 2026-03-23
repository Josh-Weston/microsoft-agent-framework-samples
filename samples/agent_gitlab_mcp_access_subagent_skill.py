"""
Sample code for exposing MCP as a skill. This provides lazy loading to reduce
context length for the agent, which would otherwise always load the MCP tools into its context,
whether they are relevant or not.
"""
import asyncio
import os
from pathlib import Path
from agent_framework import Agent
# An OpenAIResponses compatible client
from agent_framework.openai import OpenAIChatClient
from agent_framework import MCPStdioTool, FileAgentSkillsProvider
from dotenv import load_dotenv
from pathlib import Path


async def main():
    load_dotenv()

    # Create an OpenAIResponses client
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    # Create a clean environment that silences NPM warnings
    safe_env = os.environ.copy()
    safe_env["npm_config_update_notifier"] = "false"
    safe_env["npm_config_loglevel"] = "error"

    # mcp_tool_def = MCPStdioTool(
    #     name="gitlab_api_tool",
    #     command="mcp-remote.cmd",
    #     args=[
    #         # "-y",
    #         # "--quiet",
    #         # "--debug",
    #         # "mcp-remote@latest",
    #         "https://gitlab.novascotia.ca/api/v4/mcp",
    #         "--static-oauth-client-metadata",
    #         # Escaping the quotes so Windows cmd.exe doesn't eat them
    #         # r"'{\"scope\": \"mcp\"}'",
    #         '{"scope": "mcp"}',
    #         # "--debug",
    #     ],
    #     env=safe_env
    # )

    # Walk up parent directories until pyproject.toml is found — that's the project root.
    project_root = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
    python_executable = project_root / ".venv" / "Scripts" / "python.exe"
    proxy_script = project_root / "samples" / "gitlab_proxy_wrapper.py"

    mcp_tool_def = MCPStdioTool(
        name="gitlab_api_tool",
        command=str(python_executable), # Call python
        args=[
            "-u", # Unbuffered output to ensure real-time streaming
            str(proxy_script)
        ], # Run our delay relay
        env=safe_env
    )

    skills_provider = FileAgentSkillsProvider(
        skill_paths=Path(__file__).parent / "skills"
    )

    # Stack the two contexts so they will automatically close
    async with mcp_tool_def as active_mcp_tool:
        print("✅ MCP Connection Established!")

        # Create a specialized agent that the primary agent can call if needed. This prevents injecting the entire MCP context
        # into the primary agent's context and instead allows the agent to call this skill when it determines it's necessary based on the user's request.
        gitlab_skill_agent = Agent(
            client=chat_client,
            name="gitlab_skill",
            description=(
                "Call this skill to interact with GitLab. You can search for repositories, "
                "read file contents, and check issues. Pass the user's exact request as the input."
            ),
            instructions="You are a GitLab specialist. Use your MCP tools to fulfill the user's request.",
            tools=[active_mcp_tool],
            default_options={"model_id": "openai/gpt-oss-120b:sambanova"},
        )

        primary_agent = Agent(
            client=chat_client,
            name="Primary Assistant",
            instructions=("""
You are a highly capable AI assistant designed to help users efficiently complete complex tasks.
You do not know how to do specialized tasks. You have access to a variety of specialized skills.
Whenever a user asks you to perform a task, use your skill-reading tools to find the relevant skill.Always review the SKILL.md file of a selected skill to understand the required workflow before taking action.
Only use the information provided in the SKILL.md file and any resources within the skill's references and assets folders to complete the task. Do not use any outside knowledge or information. Do not infer or assume any information that is not explicitly provided in the skill's resources.
"""
                          ),
            context_providers=[skills_provider],
            # Turn an agent into a tool that can be called by other agents
            tools=[gitlab_skill_agent.as_tool()],
            default_options={
                "model_id": "openai/gpt-oss-120b:sambanova",
            },
        )

        # LEFT-OFF: customizing the as_tool() name and description so it can be decoupled from the agent, effectively allowing the agent to run independently if needed.
        # LEFT-OFF: reading for message in primary_agent.messages: to show the changes in the primary_agent's context/conversation as it determines it needs to call the SKILL and tool

        # query1 = "What is my GitLab username and tell me about my account?"
        # print(f"\nUser: {query1}")
        # result1 = await agent.run(query1)
        # print(f"Agent: {result1.text}")

        # query2 = "List all the repositories I own on GitLab"
        # print(f"\nUser: {query2}")
        # result2 = await agent.run(query2)
        # print(f"Agent: {result2.text}")

        # query3 = "Tell me about the 'trigger' repository for the user 'Josh-Weston'"
        # print(f"\nUser: {query3}")
        # result3 = await agent.run(query3)
        # print(f"Agent: {result3.text}")

        # query4 = "For the user 'Josh-Weston', tell me about issue #69 in the 'trigger' repository?"
        # print(f"\nUser: {query4}")
        # result4 = await agent.run(query4)
        # print(f"Agent: {result4.text}")

        # query5 = " Which issue in the 'Josh-Weston/trigger' repository should be prioritized first?"
        query5 = " Which issue in the '2025-01 Nova Scotia Chatbot' repository should be prioritized first?"
        print(f"\nUser: {query5}")
        print("🤖 Sending prompt to agent...")
        result5 = await primary_agent.run(query5)
        print(f"Agent: {result5.text}")


if __name__ == "__main__":
    asyncio.run(main())

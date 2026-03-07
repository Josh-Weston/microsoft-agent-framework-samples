"""
Sample code for accessing GitHub using a personal access token with an agent.
"""
import asyncio
import os
import httpx
from agent_framework import Agent
# An OpenAIResponses compatible client
from agent_framework.openai import OpenAIChatClient
from agent_framework import MCPStreamableHTTPTool
from dotenv import load_dotenv


async def main():
    load_dotenv()

    # Create an OpenAIResponses client
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    http_client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {os.getenv('GITHUB_PAT')}"}
    )

    mcp_tool = MCPStreamableHTTPTool(
        name="github_api_tool",
        url="https://api.githubcopilot.com/mcp/",
        http_client=http_client,
    )

    # Stack the two contexts so they will automatically close
    async with http_client, mcp_tool:
        agent = Agent(
            client=chat_client,
            instructions=(
                "You are a helpful assistant that can help users interact with GitHub. "
                "You can search for repositories, read file contents, check issues, and more. "
                "Always be clear about what operations you're performing."
            ),
            name="GitHub API Agent",
            # context_providers = [skills_provider],
            tools=[mcp_tool],
            default_options={
                "model_id": "openai/gpt-oss-120b:cerebras",
            },
        )

        # query1 = "What is my GitHub username and tell me about my account?"
        # print(f"\nUser: {query1}")
        # result1 = await agent.run(query1)
        # print(f"Agent: {result1.text}")

        # query2 = "List all the repositories I own on GitHub"
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

        query5 = "For the user 'Josh-Weston', which issue in the 'trigger' repository should be prioritized first?"
        print(f"\nUser: {query5}")
        result5 = await agent.run(query5)
        print(f"Agent: {result5.text}")


if __name__ == "__main__":
    asyncio.run(main())

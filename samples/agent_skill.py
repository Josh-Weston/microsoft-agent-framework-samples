import asyncio
import os
from typing import Annotated, cast
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv
from tools.pdf import extract_text_from_pdf
load_dotenv()

if True:
    from agent_framework import Agent, FileAgentSkillsProvider
    from agent_framework.openai import OpenAIChatClient
    from agent_framework.observability import configure_otel_providers
    # Console exporters are enabled via the ENABLE_CONSOLE_EXPORTERS env var
    configure_otel_providers()


async def skills_example():

    # Note: can set the agent here for the entire client, or can set it per call in the options
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    agent_instructions = """
You are a highly capable AI assistant designed to help users efficiently complete complex tasks.

You have access to a variety of specialized skills. Before attempting to solve a user's request from your own knowledge, always check if you have a relevant skill in your toolkit.

Always review the SKILL.md file of a selected skill to understand the required workflow before taking action.
"""

    skills_agent = Agent(
        client=chat_client,
        instructions=agent_instructions,
        context_providers=[FileAgentSkillsProvider(
            skill_paths="samples/skills/")],
        tools=[extract_text_from_pdf],
        default_options={
            "model_id": "openai/gpt-oss-20b:fireworks-ai",
        },
    )

    result = await skills_agent.run(
        "Create a blog post from the product_summary in your skills folder")

    with open("blog_post.md", "w") as f:
        f.write(str(result))

if __name__ == "__main__":
    asyncio.run(skills_example())

# LEFT-OFF: The blog_post_template.md file and the SKILL.md file are not being used at all...

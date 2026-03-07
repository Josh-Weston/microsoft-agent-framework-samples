import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from tools.pdf import extract_text_from_pdf
from tools.submit_blog_post import submit_blog_post
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

Only use the information provided in the SKILL.md file and the resources within the skill's references and assets folders to complete the task. Do not use any outside knowledge or information. Do not infer or assume any information that is not explicitly provided in the skill's resources.
"""

    skills_provider = FileAgentSkillsProvider(
        skill_paths=Path(__file__).parent / "skills"
    )

    print(Path(__file__).parent / "skills")

    skills_agent = Agent(
        client=chat_client,
        instructions=agent_instructions,
        context_providers=[skills_provider],
        tools=[extract_text_from_pdf, submit_blog_post],
        default_options={
            "model_id": "openai/gpt-oss-120b:cerebras",
        },
    )

    response = await skills_agent.run(
        "Create a blog post using the template and information found in your skills directory. Follow the instructions in the SKILL.md file exactly. Ensure any mentions of Artificial Intelligence are added to a separate section. YOU MUST call the submit_blog_post tool with the final content - do not return the blog post content directly to me. Once you have successfully submitted the blog post using the submit_blog_post tool, report back that it was submitted successfully."
    )

    print(f"Agent response: {response}")

if __name__ == "__main__":
    asyncio.run(skills_example())

"""
Sequentially have one agent create a blog post using a skill and have another submit it using a tool
"""

from agent_framework.orchestrations import SequentialBuilder
from agent_framework.observability import configure_otel_providers
from agent_framework.openai import OpenAIChatClient
from agent_framework import Agent, FileAgentSkillsProvider, Message
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from tools.submit_blog_post import submit_blog_post
load_dotenv()

configure_otel_providers()


async def skills_example():

    # Note: can set the agent here for the entire client, or can set it per call in the options
    chat_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model_id="not_used",  # required but not used since we set the model in the agent options
    )

    writer_agent_instructions = \
        """
You are a highly capable AI assistant designed to help users efficiently complete complex tasks.

You have access to a variety of specialized skills. Before attempting to solve a user's request from your own knowledge, always check if you have a relevant skill in your toolkit.

Always review the SKILL.md file of a selected skill to understand the required workflow before taking action.

Only use the information provided in the SKILL.md file and the resources within the skill's references and assets folders to complete the task. Do not use any outside knowledge or information. Do not infer or assume any information that is not explicitly provided in the skill's resources.
"""

    skills_provider = FileAgentSkillsProvider(
        skill_paths=Path(__file__).parent / "skills"
    )

    print(Path(__file__).parent / "skills")

    writer_agent = Agent(
        name="Writer agent",
        client=chat_client,
        instructions=writer_agent_instructions,
        context_providers=[skills_provider],
        default_options={
            "model_id": "openai/gpt-oss-120b:cerebras",
        },
    )

    submit_instructions = \
        """
You are a highly capable AI assistant designed to submit blog posts on behalf of users.

Use the submit_blog_post tool to post the blog post created by the writer agent. Do not manipulate the content in any way. YOU MUST call the submit_blog_post tool with the final content - do not return the blog post content directly to me. Once you have successfully submitted the blog post using the submit_blog_post tool, report back that it was submitted successfully."

"""

    # Note: can also use chat_client.as_agent() to create agents with the same client configuration
    poster_agent = Agent(
        name="Poster agent",
        client=chat_client,
        instructions=submit_instructions,
        tools=[submit_blog_post],
        default_options={
            "model_id": "openai/gpt-oss-120b:cerebras",
        },
    )

    workflow = SequentialBuilder(
        participants=[writer_agent, poster_agent]).build()

    events = await workflow.run("Create a blog post using the template and information found in your skills directory. Follow the instructions in the SKILL.md file exactly. Ensure any mentions of Artificial Intelligence are added to a separate section.")

    # Note: to stream the events as they come in, set the stream parameter and use async for loop instead of awaiting the entire run
    # async for event in workflow.run(stream=True)

    # Message Class: https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.chatmessage?view=agent-framework-python-latest

    # Note: each message contains a contents property with unique content (e.g., funciton_call, function_result)
    # Note: "tool" is also a role (it returns function_result messages with the output of the tool call) ({'type': 'message', 'role': 'tool', 'contents': [{'type': 'function_result', 'call_id': 'ef2a15916', 'result': ...}]})
    # Note: this is why there are so many calls and outputs for the agents are calling tools - each tool call results in an extra message with the tool output
    # Note: since we are using an orchestration abstraction (SequentialBuilder), the output of one agent is passed as input to the next agent, so we get all the intermediate messages (not AgentExecutorRespons) in the workflow outputs
    outputs = events.get_outputs()[0]
    messages = [m for m in outputs if isinstance(m, Message)]
    print(f"Total messages: {len(messages)}")
    non_messages = [o for o in outputs if not isinstance(o, Message)]
    print(f"Total non-message outputs: {len(non_messages)}")

    for m in messages:
        print(f"{m.to_dict()}\n\n")
        name = m.author_name or (
            "assistant" if m.role == "assistant" else "user")
        print(f"{'-' * 60}\n[{name}]\n{m.text}")

if __name__ == "__main__":
    asyncio.run(skills_example())

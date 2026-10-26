from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.gemini import GeminiChatClient
import os
from dotenv import load_dotenv

load_dotenv()

def new_base_openai_agent(name: str, description: str, instructions: str):
    chat_client = OpenAIChatClient(
        base_url=os.getenv("FOUNDRY_OPENAI_BASE_URL"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        model=os.getenv("FOUNDRY_MODEL"),
    )

    agent = Agent(
        client=chat_client,
        name=name,
        description=description,
        instructions=instructions,
        tools=[],
        context_providers=[],
    )
    return agent

def new_base_gemini_agent(name: str, description: str, instructions: str):

    chat_client = GeminiChatClient(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model='gemini-3.6-flash',
    )

    agent = Agent(
        client=chat_client,
        name=name,
        description=description,
        instructions=instructions,
        tools=[],
        context_providers=[],
    )
    return agent

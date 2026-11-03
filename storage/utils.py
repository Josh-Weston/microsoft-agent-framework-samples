from agent_framework import Agent, ContextProvider
from agent_framework._clients import SupportsChatGetResponse
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient, OpenAIChatOptions
from agent_framework.gemini import GeminiChatClient
import os
from dotenv import load_dotenv

load_dotenv()

def new_openai_completion_client():
    return OpenAIChatCompletionClient(
        base_url=os.getenv("FOUNDRY_OPENAI_BASE_URL"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        model=os.getenv("FOUNDRY_MODEL"),
    )

def new_openai_responses_client():
    return OpenAIChatClient(
        base_url=os.getenv("FOUNDRY_OPENAI_BASE_URL"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        model=os.getenv("FOUNDRY_MODEL"),
    )

def _create_openai_agent(client: SupportsChatGetResponse[OpenAIChatOptions[None]], name: str, description: str, instructions: str, context_providers: list[ContextProvider] = []):
    return Agent(
        client=client,
        name=name,
        description=description,
        instructions=instructions,
        tools=[],
        context_providers=context_providers,
    )

def new_base_openai_responses_agent(name: str, description: str, instructions: str, context_providers: list[ContextProvider] = []):
    chat_client = new_openai_responses_client()
    agent = _create_openai_agent(chat_client, name, description, instructions, context_providers)
    agent.context_providers = context_providers
    return agent

def new_base_openai_completion_agent(name: str, description: str, instructions: str, context_providers: list[ContextProvider] = []):
    chat_client = new_openai_completion_client()
    agent = _create_openai_agent(chat_client, name, description, instructions, context_providers)
    agent.context_providers = context_providers
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


def new_gemini_openai_responses_agent(name: str, description: str, instructions: str):

    client = OpenAIChatClient(
        base_url=os.getenv("GOOGLE_OPENAI_BASE_URL"),
        api_key=os.getenv("GOOGLE_API_KEY"),
        model='gemini-3.6-flash',
    )

    agent = Agent(
        client=client,
        name=name,
        description=description,
        instructions=instructions,
        tools=[],
        context_providers=[],
    )
    return agent


def new_gemini_openai_chat_completion_agent(name: str, description: str, instructions: str):

    client = OpenAIChatCompletionClient(
        base_url=os.getenv("GOOGLE_OPENAI_BASE_URL"),
        api_key=os.getenv("GOOGLE_API_KEY"),
        model='gemini-3.6-flash',
    )

    agent = Agent(
        client=client,
        name=name,
        description=description,
        instructions=instructions,
        tools=[],
        context_providers=[],
    )
    return agent
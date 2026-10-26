# Multiturn conversations

You build the conversation once with core types, and each provider package converts it to its own request format. You don't build a separate conversation per provider.

## How the work is split

| Layer                               | Package                           | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Conversation model                  | **core** (`agent-framework-core`) | `Message` holds a role (`system`, `user`, `assistant`, `tool`) and a list of `Content` items: text, reasoning, images or files, function calls and function results. Everything returns as `ChatResponse.messages`, which are also `Message` objects.                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Client contract                     | **core**                          | `BaseChatClient.get_response` takes `Sequence[Message]` and passes it to the abstract `_inner_get_response`. Every provider implements the same signature.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Conversion to the provider's format | **each provider package**         | **OpenAI (Responses API):** `_prepare_messages_for_openai` turns messages into Responses `input` items (`message`, `function_call`, `function_call_output`).<br>**Anthropic:** `_prepare_messages_for_anthropic` moves the first system message into the `system` parameter and maps calls and results to `tool_use` / `tool_result`. It also adds a synthetic `"Continue"` user turn when the conversation ends on an assistant message, and defaults `max_tokens` to 1024.<br>**Gemini:** `_prepare_gemini_messages` collects system messages into `system_instruction`, maps `assistant` to `model`, and groups `tool` messages into user-role `functionResponse` parts. |

So you write one `list[Message]` and call `get_response` on each client. Ollama, Foundry and the OpenAI Chat Completions client follow the same pattern.

## Example: one conversation sent to OpenAI, Anthropic and Gemini

```python
import asyncio
import os
from typing import Annotated

from agent_framework import ChatResponse, Content, Message, tool
from agent_framework.anthropic import AnthropicClient
from agent_framework.gemini import GeminiChatClient
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()


@tool
def get_weather(city: Annotated[str, "City name"]) -> str:
    """Get the current weather for a city."""
    return f"18°C and sunny in {city}"


def build_conversation() -> list[Message]:
    """Provider-neutral multi-turn history, including a prior tool round-trip."""
    return [
        Message("system", ["You are a concise travel assistant."]),
        Message("user", ["I'm spending 3 days in Lisbon. What's the weather like?"]),
        Message("assistant", [
            Content.from_function_call(call_id="call_1", name="get_weather", arguments={"city": "Lisbon"}),
        ]),
        Message("tool", [Content.from_function_result(call_id="call_1", result="18°C and sunny in Lisbon")]),
        Message("assistant", ["It's 18°C and sunny in Lisbon — great walking weather."]),
        Message("user", ["Nice. Give me a day-by-day plan focused on food and history."]),
    ]


def portable(messages: list[Message]) -> list[Message]:
    """Drop provider-specific reasoning so one provider's output can be replayed to another."""
    return [
        Message(m.role, [c for c in m.contents if c.type != "text_reasoning"], author_name=m.author_name)
        for m in messages
    ]


async def main() -> None:
    clients = {
        "openai": OpenAIChatClient(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_MODEL")),
        "anthropic": AnthropicClient(api_key=os.getenv("ANTHROPIC_API_KEY"), model=os.getenv("ANTHROPIC_MODEL")),
        "gemini": GeminiChatClient(api_key=os.getenv("GOOGLE_API_KEY"), model="gemini-3.6-flash"),
    }

    base = build_conversation()
    # Each provider gets its own copy so the transcripts can diverge on later turns.
    transcripts = {name: list(base) for name in clients}
    options = {"max_tokens": 800, "tools": [get_weather]}

    async def ask(name: str) -> ChatResponse:
        return await clients[name].get_response(transcripts[name], options=options)

    results = await asyncio.gather(*(ask(n) for n in clients), return_exceptions=True)

    for name, result in zip(clients, results):
        print(f"\n===== {name} =====")
        if isinstance(result, Exception):
            print(f"ERROR: {result!r}")
            continue
        print(result.text)
        print("usage:", result.usage_details)
        transcripts[name].extend(result.messages)

    # Next turn: append the same user message to every transcript and call ask() again.
    for t in transcripts.values():
        t.append(Message("user", ["Swap day 2 for a day trip to Sintra."]))


if __name__ == "__main__":
    asyncio.run(main())
```

## Things to watch for when comparing providers

1. **Plain text is fully portable.** Text, images and function calls/results with matching `call_id`s convert cleanly for all three.
2. **Reasoning content is not portable.** OpenAI encrypted reasoning, Anthropic thinking signatures and Gemini thought signatures all travel in `Content.protected_data`. Anthropic turns any `text_reasoning` that has `protected_data` into a `thinking` block with a `signature`. That fails if the data came from another provider. Use a filter like `portable()` before feeding one provider's output to another.
3. **Put tool results in `Message("tool", ...)`.** Gemini only converts a `function_result` inside a tool-role message (or one carrying a raw Gemini part); anywhere else it skips it.
4. **Anthropic needs tools defined.** I'm going from my knowledge of Anthropic's API here, not this source: it rejects histories containing `tool_use` / `tool_result` blocks unless `tools` is defined. That's why the example passes `tools` for every provider. Because these clients run tools automatically, a model can also call `get_weather` again during the run.
5. **OpenAI defaults to server-side storage.** If you don't pass a `conversation_id` or `previous_response_id`, it replays your full local history without relying on server state, which is what you want for a fair comparison. Don't reuse the `conversation_id` it returns across providers.
6. **Shared options are translated per provider; extras aren't.** Common `ChatOptions` such as `max_tokens`, `temperature` and `tools` are translated for each provider (for example, `max_tokens` becomes `max_output_tokens` for OpenAI). Provider-specific settings like Anthropic `thinking` or Gemini `ThinkingConfig` belong in that provider's `*ChatOptions`, so build those per client.

If you'd rather work through `Agent`, you can pass the same `list[Message]` to `Agent(client=...).run(messages)` for each client. Calling `get_response` directly keeps the comparison simpler because no session or history provider is added.

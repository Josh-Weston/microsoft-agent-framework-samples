from typing import Any, TypeIs, cast
from agent_framework import Message, AgentResponse


def is_message(val: Any) -> TypeIs[Message]:
    return isinstance(val, Message)


def is_agent_response(val: Any) -> TypeIs[AgentResponse]:
    return isinstance(val, AgentResponse)


def is_message_list(val: Any) -> bool:
    if not isinstance(val, list):
        return False

    return all(isinstance(item, Message) for item in cast(list[Any], val))

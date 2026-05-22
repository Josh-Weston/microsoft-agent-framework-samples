from typing import Any, TypeIs, cast
from agent_framework import Message, AgentResponse, AgentResponseUpdate


def is_message(val: Any) -> TypeIs[Message]:
    return isinstance(val, Message)


def is_agent_response(val: Any) -> TypeIs[AgentResponse]:
    return isinstance(val, AgentResponse)


def is_agent_response_update(val: Any) -> TypeIs[AgentResponseUpdate]:
    return isinstance(val, AgentResponseUpdate)


def is_message_list(val: Any) -> bool:
    if not isinstance(val, list):
        return False

    return all(isinstance(item, Message) for item in cast(list[Any], val))

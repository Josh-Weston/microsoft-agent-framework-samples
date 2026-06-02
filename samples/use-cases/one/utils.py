from typing import Any, TypeIs, cast
from agent_framework import AgentExecutorResponse, Message, AgentResponse, AgentResponseUpdate, WorkflowEvent


def is_message(val: Any) -> TypeIs[Message]:
    return isinstance(val, Message)


def is_agent_response(val: Any) -> TypeIs[AgentResponse]:
    return isinstance(val, AgentResponse)


def is_agent_response_update(val: Any) -> TypeIs[AgentResponseUpdate]:
    return isinstance(val, AgentResponseUpdate)


def is_agent_executor_response(val: Any) -> TypeIs[AgentExecutorResponse]:
    return isinstance(val, AgentExecutorResponse)


def is_workflow_event(val: Any) -> bool:
    return isinstance(val, WorkflowEvent)


def extract_request_from_event(event: WorkflowEvent) -> str:
    if is_agent_executor_response(event.data):
        return event.data.agent_response.text

    if isinstance(event.data, str):
        return event.data

    return str(event.data)


def extract_response_from_event(event: WorkflowEvent) -> str:

    if is_agent_response_update(event.data):
        return event.data.text

    if is_agent_response(event.data):
        # The concatenated text of all messages in the response (use event.data.messages to get the individual messages)
        return event.data.text

    if is_agent_executor_response(event.data):
        return event.data.agent_response.text

    if isinstance(event.data, str):
        return event.data

    return str(event.data)


def is_message_list(val: Any) -> bool:
    if not isinstance(val, list):
        return False

    return all(isinstance(item, Message) for item in cast(list[Any], val))

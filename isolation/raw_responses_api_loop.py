"""
If you are interacting directly with the Responses API and dealing with the raw ResponseOutputItem Pydantic models,
you cannot pass them directly back into the API because the input expects strictly validated dictionaries,
not Python objects.

Note: this manual process is time-consuming and error-prone.

The following models won't work without fist parsing them into a dictionary and stripping away the extra fields that the Responses API doesn't accept:
- openai/gpt-oss-120b

The following models will work:
- 

Why gpt-oss-120b reasoning doesn't work:
Open Responses is an open-source extension of OpenAI's original Responses API.
To support multi-turn agentic loops, tool executions, and visibility into thinking states,
it streams a series of custom item types (such as reasoning data blocks). 

Why Gemma4 reasoning doesn't work:

When routing through Hugging Face Inference Providers (like Together AI, DeepInfra, Cerebras, etc.), your request is intercepted by a unified abstraction layer.
Because this serverless router completely strips extra_body arguments before sending the payload to the provider, your parameters are ignored.

Note: it is the inference provider's responsibility to implement the Responses API, and not all providers support the full spec. It is
the model provider's responsibility to train the model to output tokens that can be parsed into the Responses API's expected schema. Models can output
different delimiter tokens (e.g., <think>, <reason>, <tool>, etc.) that the provider must parse into the correct Responses API item types.

HuggingFace's Responses API is a partial implementation of OpenAI's Responses API (it's a translation layer):
- https://github.com/huggingface/responses.js
- https://huggingface.co/docs/inference-providers/en/guides/responses-api
- https://huggingface.co/docs/inference-providers/en/guides/gpt-oss

"""


import asyncio
import json
import os
from typing import cast
from sandbox import AgentSandbox
from agent_framework import tool
from agent_framework.openai import OpenAIChatClient  # Responses API
from openai.types.responses import ResponseInputItemParam, FunctionToolParam
from typing import Annotated
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class BashResponse(BaseModel):
    exit_code: Annotated[str, Field(
        description="The exit code for the command. A code of 0 means the command was successful")]
    output: Annotated[str, Field(
        description="The output from running the command")]


def run_bash_in_sandbox(sandbox: AgentSandbox, command: str) -> BashResponse:
    result = sandbox.execute(command)
    return BashResponse(
        exit_code=str(result["exit_code"]),
        output=result["output"],
    )


@tool(approval_mode="never_require", description="Execute the bash command in the sandbox environment")
def execute_bash(
    command: Annotated[str, Field(description="The bash command to run")],
) -> BashResponse:
    """Schema-only tool declaration for the manual tool interception loop."""
    raise NotImplementedError(
        "execute_bash is handled by the manual tool loop")


# Responses API requires the JSON specification, instead of the higher-level @tool approach
# Note: new providers require the full result of .to_json_schema_spec(), while others require just the 'function' property
execute_bash_schema: FunctionToolParam = cast(FunctionToolParam, {
    'type': 'function',
    **execute_bash.to_json_schema_spec()['function'],
})


async def run_loop(user_prompt: str):

    MODEL = os.getenv("HF_API_MODEL", "openai/gpt-oss-120b:baseten")
    openai_client = OpenAIChatClient(
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
        model=MODEL,
    )

    # Boot the stateful container
    with AgentSandbox(image="python:3.14-slim") as sandbox:

        # Initialize the conversation history
        messages: list[ResponseInputItemParam] = [
            {"role": "system", "content": "You are an AI assistant. Use the bash tool to solve user requests."},
            {"role": "user", "content": user_prompt},
        ]

        conversation: list[ResponseInputItemParam] = [*messages]
        response = None
        max_iterations = 10
        final_response = False
        # 3. The ReAct (Reason + Act) Loop
        while max_iterations > 0:
            # Ask the LLM what to do next
            response = await openai_client.client.responses.create(
                model=MODEL,
                instructions="Use the available tools to answer the user's questions. If an error occurs, try again.",
                input=conversation,
                tools=[execute_bash_schema],
            )

            # if response.error:
            #     with open('final_answer.txt', '+wt') as f:
            #         f.write(str(conversation))
            #     raise Exception(f"Error from the LLM: {response.error}")

            # if not response.output:
            #     with open('final_answer.txt', '+wt') as f:
            #         f.write(str(conversation))
            #     raise Exception("No output from the LLM. The model may have failed to respond.")

            tool_calls = []

            # Note: these gymnastics are required because of how HF implements the Responses API with gpt-oss-120b.
            for item in response.output:
                # Filter out internal noise the LLM doesn't need to see again
                if item.type in ["compaction", "mcp_approval_request", "mcp_approval_response", 'reasoning']:
                    continue

                # Check if the LLM decided to call a tool in this response
                if item.type == 'function_call':
                    tool_calls.append(item)

                # Use the built-in Pydantic dump to perfectly map the schema
                input_dict = item.model_dump(exclude_unset=True)
                conversation.append(cast(ResponseInputItemParam, input_dict))

            if final_response:
                break

            # If there are no tool calls, the LLM has provided its final text answer. Break the loop.
            if not tool_calls:
                break

            # Otherwise, process the tool calls
            for item in tool_calls:
                if item.name == 'execute_bash':
                    arguments = json.loads(item.arguments)
                    command = arguments.get('command')
                    if not command:
                        error_msg = "Error: 'command' argument is missing or empty. Please provide a valid bash command."
                        conversation.append({
                            'type': 'function_call_output',
                            'call_id': item.call_id,
                            'output': error_msg
                        })
                        continue

                    try:
                        result = run_bash_in_sandbox(sandbox, command)
                        if result.exit_code != '0' or not result.output:
                            raise Exception(
                                result.output if result.output else 'Failed with exit code {result.exit_code}')

                        # Append the successful output so the LLM can read it on the next iteration
                        conversation.append({
                            'type': 'function_call_output',
                            'call_id': item.call_id,
                            'output': result.output,
                        })

                        final_response = True

                    except Exception as e:
                        # Catch sandbox crashes and tell the LLM
                        conversation.append({
                            'type': 'function_call_output',
                            'call_id': item.call_id,
                            'output': f"Sandbox execution failed: {str(e)}"
                        })

            max_iterations -= 1

        # View the conversation thread
        with open('final_answer.txt', '+wt') as f:
            f.write(str(conversation))

# Usage:
asyncio.run(run_loop(
    "Use your available tools to calculate the 10th Fibonacci number. Respond with the calculated number"))

# LEFT-OFF: determine if the HF Responses API does actually support the previous_responses.id API
# LEFT-OFF: convert the function_call and function_call_output to regular outputs
# LEFT-OFF: this has been interesting, but once the above are fixed, MOVE ON WITH YOUR LIFE!

from agent_framework import AgentResponse
from pypdf import PdfReader
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Any, Never, cast
import asyncio
import pathlib
import os
from utils import extract_request_from_event, extract_response_from_event, is_agent_executor_response, is_agent_response, is_agent_response_update

import logging
logging.getLogger("agent_framework").setLevel(logging.ERROR)

if True:
    from agent_framework.openai import OpenAIChatCompletionClient
    from agent_framework.orchestrations import SequentialBuilder, AgentRequestInfoResponse
    from agent_framework import AgentExecutorResponse, ResponseStream, WorkflowEvent, WorkflowRunResult, executor, WorkflowContext, Message, SkillsProvider, Executor, handler, response_handler


class PermitData(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    # model_config = ConfigDict(extra="forbid")

    # Uncomment this to see the raw JSON being validated, which can be helpful for debugging issues with the LLM's output not matching the expected schema
    # @classmethod
    # def model_validate_json(cls, json_data, *, strict=None, extra=None, context=None, by_alias=None, by_name=None):
    #     print(f"[DEBUG] PermitData raw JSON: {json_data!r}")
    #     return super().model_validate_json(json_data, strict=strict, extra=extra, context=context, by_alias=by_alias, by_name=by_name)

    application_id: Annotated[str | None, Field(
        description="The unique identifier for the building permit application.")]
    submission_date: Annotated[str | None, Field(
        description="The date when the application was submitted.")]
    parcel_number: Annotated[str | None, Field(
        description="The parcel number associated with the building permit application.")]
    applicant_name: Annotated[str | None, Field(
        description="The name of the applicant for the building permit.")]
    estimated_cost: Annotated[str | None, Field(
        description="The estimated cost of the construction project as stated in the building permit application.")]
    application_signature: Annotated[str | None, Field(
        description="The signature of the applicant on the building permit application.")]
    application_signature_date: Annotated[str | None, Field(
        description="The date when the building permit application was signed by the applicant.")]
    contractor_name: Annotated[str | None, Field(
        description="The name of the contractor listed on the building permit application.")]


class ComplianceResult(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    # model_config = ConfigDict(extra="forbid")

    # Uncomment this to see the raw JSON being validated, which can be helpful for debugging issues with the LLM's output not matching the expected schema
    # @classmethod
    # def model_validate_json(cls, json_data, *, strict=None, extra=None, context=None, by_alias=None, by_name=None):
    #     print(f"[DEBUG] ComplianceResult raw JSON: {json_data!r}")
    #     return super().model_validate_json(json_data, strict=strict, extra=extra, context=context, by_alias=by_alias, by_name=by_name)

    # @classmethod
    # def model_validate(cls, obj: Any, *, strict: bool | None = None, extra=None, by_alias=None, by_name=None, from_attributes: bool | None = None, context: Any | None = None):
    #     print(f"[DEBUG] ComplianceResult raw Dict: {obj!r}")
    #     return super().model_validate(obj, strict=strict, extra=extra, by_alias=by_alias, by_name=by_name, from_attributes=from_attributes, context=context)

    compliant: Annotated[bool, Field(
        description="Whether the building permit application is compliant with the relevant building codes.")]
    reasons: Annotated[list[str], Field(
        description="The reasons for non-compliance if the application is not compliant.")]


# Note: the model AND model provider determine if the model allows for tool calls and structured output
# MODEL = "openai/gpt-oss-120b:ovhcloud"
MODEL = "openai/gpt-oss-120b:nscale"


@executor()
async def read_pdf(input_messages: Annotated[list[Message], Field(description="The input messages containing the path to the PDF file.")], ctx: WorkflowContext[str, Exception]):
    """
    read_pdf receives the path to a PDF file and retutrns the contents as text
    """
    file_path = pathlib.Path(input_messages[0].contents[0].text or "")
    try:
        reader = PdfReader(file_path)
        text = [page.extract_text() for page in reader.pages]
        await ctx.send_message("\n".join(text))
    except Exception as e:
        await ctx.yield_output(e)


def create_data_agent():
    chat_client = OpenAIChatCompletionClient(
        model="not_used",  # required but not used since we set the model in the agent options
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
    )

    return chat_client.as_agent(
        instructions=(
            "You are a building permit data extraction agent that extracts key information from the contents of text documents you receive."
            "You will be given the contents of a building permit document and you should provide a concise summary of the key information. "
        ),
        name="building_permit_data_extraction_agent",
        tools=[],
        default_options={
            "model": MODEL,
            "response_format": PermitData,
        },
    )


def create_compliance_agent():
    chat_client = OpenAIChatCompletionClient(
        model="not_used",  # required but not used since we set the model in the agent options
        base_url=os.getenv("HF_API_BASE_URL"),
        api_key=os.getenv("HF_API_KEY"),
    )

    skills_provider = SkillsProvider.from_paths(
        skill_paths=pathlib.Path(__file__).parent / "skills"
    )

    return chat_client.as_agent(
        instructions=(
            "You are a building permit compliance agent that determines whether a building permit application is compliant based on the extracted data from the application and the relevant building codes."
            "You will be given the extracted data from a building permit application and you should determine whether the application is compliant with the information in the building permit compliance skill."
            "You MUST use the load_skill tool to read the 'building-permit-compliance' skill before making any decisions."
        ),
        name="building_permit_compliance_agent",
        tools=[],
        context_providers=[skills_provider],
        default_options={
            "model": MODEL,
            "response_format": ComplianceResult,
        },
    )


@executor()
async def handle_compliance_decision(
        original_request: Annotated[AgentExecutorResponse, Field(description="The original request for compliance decision that the agent is responding to")],
        ctx: WorkflowContext[Never, str]
):
    """
    handle_compliance_decision handles the compliance decision made by the agent and sends the result back to the workflow context.
    """
    if isinstance(original_request.agent_response.value, ComplianceResult):
        # Note: casting here is the only way to narrow the value for the ComplianceResult type
        compliance_result = cast(
            ComplianceResult, original_request.agent_response.value)
        if compliance_result.compliant:
            await ctx.yield_output("The building permit application is compliant with the relevant building codes. Do you approve this decision? (y/N)")
        else:
            reasons = "\n".join(
                f"- {reason}" for reason in compliance_result.reasons)
            await ctx.yield_output(f"The building permit application is NOT compliant with the relevant building codes for the following reasons:\n{reasons}\nDo you approve this decision? (y/N)")

    # print("Inside of handler for compliance decision")
    # print(original_request)
    # await ctx.yield_output("Compliance decision received. Do you approve this decision? (y/N)")
    # try:
    #     # await ctx.send_message(f"Compliance decision for request: {original_request}")
    # except Exception as e:
    #     await ctx.yield_output(e)


def create_workflow():
    data_agent = create_data_agent()
    compliance_agent = create_compliance_agent()
    return (
        SequentialBuilder(
            participants=[read_pdf, data_agent,
                          compliance_agent, handle_compliance_decision],
            chain_only_agent_responses=True,
        )
        # .with_request_info(agents=[handle_compliance_decision])
        .build()
    )


# LEFT-OFF: the pieces are here for the simplified workflow, but I am not sure how to actually incorporate HITL without the verbosity.

async def process_event_stream(stream: ResponseStream[WorkflowEvent[Any], WorkflowRunResult]):
    responses: dict[str, str] = {}
    requests: dict[str, str] = {}
    output: str = ""
    async for event in stream:
        match event:
            case WorkflowEvent(type='request_info'):
                requests[event.request_id] = extract_request_from_event(event)
            case WorkflowEvent(type='output', executor_id='handle_compliance_decision'):
                output += extract_response_from_event(event)
            case _:
                pass
    if output:
        print(f"Agent response:\n\n{output}\n")

    for request_id, request_data in requests.items():
        agent_request = request_data
        # Get feedback on the agent's response (approve or request iteration)
        user_input = input(f"{agent_request} (y/N): ")
        responses[request_id] = user_input
    return responses if responses else None


async def main(file: str):
    wf = create_workflow()
    stream = wf.run(message=file, stream=True)
    pending_responses = await process_event_stream(stream)

    # Note: this is the standard pattern used in several Microsoft examples for handling HITL interactions.
    while pending_responses is not None:
        stream = wf.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)

if __name__ == "__main__":
    load_dotenv()
    # file = "samples/use-cases/one/files/permit_app_005.pdf"
    file = "samples/use-cases/one/files/permit_app_002.pdf"
    asyncio.run(main(file))

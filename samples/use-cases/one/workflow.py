from pypdf import PdfReader
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Any
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


class PermitDataWithContractorApproval(PermitData):
    contractor_approved: Annotated[bool, Field(
        description="Whether the contractor is approved for the building permit application.")]


class ComplianceResult(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    # model_config = ConfigDict(extra="forbid")

    # Uncomment this to see the raw JSON being validated, which can be helpful for debugging issues with the LLM's output not matching the expected schema
    # @classmethod
    # def model_validate_json(cls, json_data, *, strict=None, extra=None, context=None, by_alias=None, by_name=None):
    #     print(f"[DEBUG] ComplianceResult raw JSON: {json_data!r}")
    #     return super().model_validate_json(json_data, strict=strict, extra=extra, context=context, by_alias=by_alias, by_name=by_name)

    compliant: Annotated[bool, Field(
        description="Whether the building permit application is compliant with the relevant building codes.")]
    reasons: Annotated[list[str], Field(
        description="The reasons for non-compliance if the application is not compliant.")]


class ContractorApprovalResponse(BaseModel):
    approved: Annotated[bool, Field(
        description="Whether the contractor is on the auto-approved list for building permits.")]
    contractor_name: Annotated[str, Field(
        description="The name of the contractor being evaluated.")]


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


@executor()
async def stash_permit_data(input: AgentExecutorResponse, ctx: WorkflowContext[str, None]):
    """
    stash_permit_data receives the extracted permit data and stashes it in the workflow context for later use
    """
    permit_data = PermitData.model_validate_json(input.agent_response.text)
    ctx.set_state("permit_data", permit_data)
    await ctx.send_message(permit_data.model_dump_json())


# Note: the problem is the contractor approval agent receives all of the data, but it only outputs the contractor approval response, which is then sent to the contractor approval executor. The contractor approval executor checks if the contractor is approved, and if not, it requests info from the user about whether to proceed with the permit evaluation anyway. However, since the contractor approval agent's response only contains the approval status and contractor name, the executor does not have access to the rest of the permit data that it would need to include in the request for information to provide context to the user. One solution would be to include the relevant permit data in the agent's response so that it can be used in the executor's request for information.

def create_contractor_approval_agent():
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
            "You are a contractor approval agent. You MUST use the load_skill tool to read the "
            "'contractor-approval-list' skill before making any determination. "
            "After reading the skill, check if the contractor name from the permit data appears "
            "in the approved list, then output your ContractorApprovalResponse."
        ),
        name="contractor_approval_agent",
        tools=[],
        context_providers=[skills_provider],
        default_options={
            "model": MODEL,
            "response_format": ContractorApprovalResponse,
        },
    )


class ContractorApproval(Executor):
    def __init__(self):
        super().__init__(id="contractor_approval_executor")

    @handler
    async def handle_input(self, input: AgentExecutorResponse, ctx: WorkflowContext[str, str]) -> None:
        validated_input = ContractorApprovalResponse.model_validate_json(
            input.agent_response.text)

        permit_data: PermitData = ctx.get_state("permit_data")
        if not isinstance(permit_data, PermitData):
            await ctx.yield_output(ValueError("Permit data not found in context"))
            return

        if validated_input.approved:
            permit_data_with_approval = PermitDataWithContractorApproval(
                **permit_data.model_dump(), contractor_approved=True)
            # await ctx.send_message(input.with_text(permit_data_with_approval.model_dump_json())) # use this approach if we want to preserve the conversation history
            await ctx.send_message(permit_data_with_approval.model_dump_json())
        else:
            await ctx.request_info(
                request_data=f"Contractor {validated_input.contractor_name} is not approved. Do you want to proceed with the permit evaluation anyway?",
                response_type=str
            )

    @response_handler
    async def on_human_response(
        self,
        original_request: str,
        response: str,
        ctx: WorkflowContext[str, str],
    ) -> None:
        if response.lower() in ["yes", "y"]:
            permit_data: PermitData = ctx.get_state("permit_data")
            if not isinstance(permit_data, PermitData):
                await ctx.yield_output(ValueError("Permit data not found in context"))
                return
            permit_data_with_approval = PermitDataWithContractorApproval(
                **permit_data.model_dump(), contractor_approved=True)
            await ctx.send_message(permit_data_with_approval.model_dump_json())
        else:
            await ctx.yield_output("Permit evaluation halted due to contractor not being approved.")
            return


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


def create_workflow():
    data_agent = create_data_agent()
    contractor_approval_agent = create_contractor_approval_agent()
    contractor_approval_executor = ContractorApproval()
    compliance_agent = create_compliance_agent()
    return (
        SequentialBuilder(
            participants=[read_pdf, data_agent, stash_permit_data,
                          contractor_approval_agent, contractor_approval_executor, compliance_agent],
            chain_only_agent_responses=True,
        )
        # .with_request_info(agents=[contractor_approval_agent])
        .build()
        # WorkflowBuilder(start_executor=read_pdf)
        # .add_edge(read_pdf, data_agent)
        # .add_edge(data_agent, compliance_agent)
        # .build()
    )


async def process_event_stream(stream: ResponseStream[WorkflowEvent[Any], WorkflowRunResult]):
    responses: dict[str, str] = {}
    requests: dict[str, str] = {}
    output: str = ""
    async for event in stream:
        match event:
            case WorkflowEvent(type='request_info'):
                requests[event.request_id] = extract_request_from_event(event)
            case WorkflowEvent(type='output', executor_id='building_permit_compliance_agent'):
                output += extract_response_from_event(event)
            case WorkflowEvent(type='executor_completed', executor_id='contractor_approval_executor'):
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


# LEFT-OFF: test the conditionals, which allow for branching logic
"""
   workflow = (
        WorkflowBuilder(start_executor=spam_detection_agent)
        # Not spam path: transform response -> request for assistant -> assistant -> send email
        .add_edge(spam_detection_agent, to_email_assistant_request, condition=get_condition(False))
        .add_edge(to_email_assistant_request, email_assistant_agent)
        .add_edge(email_assistant_agent, handle_email_response)
        # Spam path: send to spam handler
        .add_edge(spam_detection_agent, handle_spam_classifier_response, condition=get_condition(True))
        .build()
    )
"""

# switch-case for cleaner three-way routing
"""
    workflow = (
        WorkflowBuilder(start_executor=store_email)
        .add_edge(store_email, spam_detection_agent)
        .add_edge(spam_detection_agent, to_detection_result)
        .add_switch_case_edge_group(
            to_detection_result,
            [
                # Explicit cases for specific decisions
                Case(condition=get_case("NotSpam"), target=submit_to_email_assistant),
                Case(condition=get_case("Spam"), target=handle_spam),
                # Default case catches anything that doesn't match above
                Default(target=handle_uncertain),
            ],
        )
        .add_edge(submit_to_email_assistant, email_assistant_agent)
        .add_edge(email_assistant_agent, finalize_and_send)
        .build()
    )
"""

# Multiselection pattern
"""
# One input → one or more outputs (dynamic fan-out)
.add_multi_selection_edge_group(
    source,
    [handler_a, handler_b, handler_c, handler_d],
    selection_func=intelligent_router,  # Returns list of target IDs
)
"""

# TODO: do a manual workflow build instead of the orchestrator
# TODO: figure out all of the events being passed around and how to plug into them
# TODO: figure out what makes the events different from the telemetry

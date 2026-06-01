from agent_framework import AgentExecutorResponse, ResponseStream, WorkflowEvent, WorkflowRunResult, executor, WorkflowContext, Message, SkillsProvider
from agent_framework.orchestrations import SequentialBuilder, AgentRequestInfoResponse
from agent_framework.openai import OpenAIChatCompletionClient
from pypdf import PdfReader
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Any
import asyncio
import pathlib
import os

from utils import is_agent_executor_response, is_agent_response, is_agent_response_update


class PermitData(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    # model_config = ConfigDict(extra="forbid")

    @classmethod
    def model_validate_json(cls, json_data, *, strict=None, extra=None, context=None, by_alias=None, by_name=None):
        print(f"[DEBUG] PermitData raw JSON: {json_data!r}")
        return super().model_validate_json(json_data, strict=strict, extra=extra, context=context, by_alias=by_alias, by_name=by_name)

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

    @classmethod
    def model_validate_json(cls, json_data, *, strict=None, extra=None, context=None, by_alias=None, by_name=None):
        print(f"[DEBUG] ComplianceResult raw JSON: {json_data!r}")
        return super().model_validate_json(json_data, strict=strict, extra=extra, context=context, by_alias=by_alias, by_name=by_name)

    compliant: Annotated[bool, Field(
        description="Whether the building permit application is compliant with the relevant building codes.")]
    reasons: Annotated[list[str], Field(
        description="The reasons for non-compliance if the application is not compliant.")]


class ContractorApprovalResponse(BaseModel):
    approved: Annotated[bool, Field(
        description="Whether the contractor is on the auto-approved list for building permits.")]
    contractor_name: Annotated[str, Field(
        description="The name of the contractor being evaluated.")]


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

# MODEL = "openai/gpt-oss-120b:cerebras"
# MODEL = "deepseek-ai/DeepSeek-V4-Pro:fireworks-ai"
MODEL = "Qwen/Qwen3.5-397B-A17B:together"
# MODEL = "Qwen/Qwen3-32B:groq"
# MODEL = "openai/gpt-oss-120b:sambanova"
# MODEL = "openai/gpt-oss-120b:ovhcloud"


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
# async def stash_
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
            "You are a contractor approval agent that determines whether a contractor is on the auto-approved list for building permits."
            "You will be given the name of a contractor and you should determine whether the contractor is on the auto-approved list."
            "Use your provided skills to check the contractor's approval status based on the name of the contractor. Always review the SKILL.md file of a selected skill to understand the required workflow before taking action."
            "If the contractor is not on the auto-approved list, you should yield a request for human approval before proceeding with the permit evaluation."
        ),
        name="contractor_approval_agent",
        tools=[],
        context_providers=[skills_provider],
        default_options={
            "model": MODEL,
            "response_format": ContractorApprovalResponse,
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

    # return chat_client.as_agent(
    #     instructions=(
    #         "You are a building permit compliance agent that determines whether a building permit application is compliant based on the extracted data from the application and the relevant building codes."
    #         "You will be given the extracted data from a building permit application and you should determine whether the application is compliant with the relevant building codes."
    #         "You do not know how to do specialized tasks. You have access to a variety of specialized skills."
    #         "Whenever a user asks you to perform a task, use your skill-reading tools to find the relevant skill. Always review the SKILL.md file of a selected skill to understand the required workflow before taking action."
    #         "Only use the information provided in the SKILL.md file and any resources within the skill's references and assets folders to complete the task. Do not use any outside knowledge or information. Do not infer or assume any information that is not explicitly provided in the skill's resources."
    #     ),
    #     name="building_permit_compliance_agent",
    #     tools=[],
    #     context_providers=[skills_provider],
    #     default_options={
    #         "model": "openai/gpt-oss-120b:cerebras",
    #         "response_format": ComplianceResult,
    #     },
    # )

    # LEFT-OFF: the "you must always ask for human input" creates an infinite loop
    # LEFT-OFF: reviewing more samples from Microsoft that use HITL without an executor (agent-only)

    return chat_client.as_agent(
        instructions=(
            "You are a building permit compliance agent that determines whether a building permit application is compliant based on the extracted data from the application and the relevant compliance checks."
            "You will be given the extracted data from a building permit application and you should determine whether the application is compliant with the relevant compliance checks."
            "You must always ask for human input to determine if the contractor is on the auto-approved list before proceeding with the permit evaluation. You should not proceed with the permit evaluation or reference any skills until you have received confirmation from the user about whether the contractor is approved or not."
            # "Determine the appropriate skills to reference based on the information provided in the building permit application. Always review the SKILL.md file of a selected skill to understand the required workflow before taking action."

            # "If a contractor is not on the auto-approved list, you should yield a request for human approval before proceeding with the permit evaluation."
            # "If the user confirms that the contractor is not approved, you can immediately determine that the application is not compliant."
            # "If the user confirms that the contractor is approved, then you should proceed with referencing the relevant skills to determine compliance based on the other extracted data."
        ),
        name="building_permit_compliance_agent",
        tools=[],
        default_options={
            "model": MODEL,
            "response_format": ComplianceResult,
        },
    )


def create_workflow():
    data_agent = create_data_agent()
    compliance_agent = create_compliance_agent()
    return (
        SequentialBuilder(
            participants=[read_pdf, data_agent, compliance_agent],
            chain_only_agent_responses=True,
        )
        .with_request_info(agents=[compliance_agent])
        .build()
        # WorkflowBuilder(start_executor=read_pdf)
        # .add_edge(read_pdf, data_agent)
        # .add_edge(data_agent, compliance_agent)
        # .build()
    )


async def process_event_stream(stream: ResponseStream[WorkflowEvent[Any], WorkflowRunResult]):
    responses: dict[str, AgentRequestInfoResponse] = {}
    requests: dict[str, AgentExecutorResponse] = {}
    async for event in stream:
        if event.type == "request_info" and is_agent_executor_response(event.data):
            requests[event.request_id] = event.data
        elif event.type == "output" and is_agent_response(event.data):
            # The output of the sequential workflow is a list of ChatMessages
            print("\n" + "=" * 60)
            print("WORKFLOW COMPLETE")
            print("=" * 60)
            print("Final output:")
            print(event)
            for message in event.data.messages:
                print(message.text)
                print(f"[{message.author_name or message.role}]: {message.text}")

    for request_id, request_data in requests.items():
        agent_request = request_data.agent_response.text
        print(
            f"Agent is requesting info with the following request: {agent_request}")
        # Get feedback on the agent's response (approve or request iteration)
        user_input = input("Your guidance (or 'skip' to approve): ")
        if user_input.lower() == "skip":
            user_input = AgentRequestInfoResponse.approve()
        else:
            user_input = AgentRequestInfoResponse.from_strings([
                user_input])
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

    # if event.type == "request_info" and is_agent_executor_response(event.data):
    #     print(f"Received request info event with data: {event.data}")
    #     if event.type == "output" and is_agent_response_update(event.data):
    #         print(event.data)
    #         # Note: it is common for several empty data.text events to be received while the LLM prepares a response.
    #         if event.data.text:
    #             agent_response += event.data.text
    # print(f"Final agent response:\n\n")
    # print(agent_response)

if __name__ == "__main__":
    load_dotenv()
    file = "samples/use-cases/one/files/permit_app_005.pdf"
    asyncio.run(main(file))


# LEFT-OFF: I think I need to catch-up the agent requests? user_input_requests

# LEFT-OFF: the deepseek model doesn't seem to be working at all (was returning HTML data from HuggingFace)

# LEFT-OFF: the agent asks a question without enough details, I respond with some guidance, but the agent is unaware of the context of its question
# LEFT-OFF: I still don't have the final output
# LEFT-OFF: reading the HITL section of the documentation; the agent sometimes "uses output" instead of "request_info"

from agent_framework import AgentExecutorResponse, ResponseStream, WorkflowEvent, WorkflowRunResult, executor, WorkflowContext, Message, SkillsProvider
from agent_framework.orchestrations import SequentialBuilder, AgentRequestInfoResponse
from agent_framework.openai import OpenAIChatClient
from pypdf import PdfReader
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Any
import asyncio
import pathlib
import os

from utils import is_agent_executor_response, is_agent_response, is_agent_response_update


class PermitData(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    model_config = ConfigDict(extra="forbid")
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
    chat_client = OpenAIChatClient(
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
            "model": "openai/gpt-oss-120b:cerebras",
            "response_format": PermitData,
        },
    )


class ComplianceResult(BaseModel):
    # Forbid extra fields to ensure strict adherence to the schema
    model_config = ConfigDict(extra="forbid")
    compliant: Annotated[bool, Field(
        description="Whether the building permit application is compliant with the relevant building codes.")]
    reasons: Annotated[list[str], Field(
        description="The reasons for non-compliance if the application is not compliant.")]


def create_compliance_agent():
    chat_client = OpenAIChatClient(
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

    return chat_client.as_agent(
        instructions=(
            "You are a building permit compliance agent that determines whether a building permit application is compliant based on the extracted data from the application and the relevant building codes."
            "You will be given the extracted data from a building permit application and you should determine whether the application is compliant with the relevant building codes."
            # LEFT-OFF: improving this to work better with the SKILL.md file (which has approved contractors listed)
            "You always ask the user if the contractor is a valid and approved contractor. If the user confirms that the contractor is not approved, you can immediately determine that the application is not compliant. If the user confirms that the contractor is approved, then you should proceed with referencing the relevant skills to determine compliance based on the other extracted data."
        ),
        name="building_permit_compliance_agent",
        tools=[],
        default_options={
            "model": "openai/gpt-oss-120b:cerebras",
            # "response_format": ComplianceResult,
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
            for message in event.data:
                print(f"[{message.author_name or message.role}]: {message.text}")

    async for event in stream:
        if event.type == "request_info" and is_agent_executor_response(event.data):
            agent_request = event.data.agent_response.text
            print(
                f"Agent is requesting info with the following request: {agent_request}")
            # Get feedback on the agent's response (approve or request iteration)
            user_input = input("Your guidance (or 'skip' to approve): ")
            if user_input.lower() == "skip":
                user_input = AgentRequestInfoResponse.approve()
            else:
                user_input = AgentRequestInfoResponse.from_strings([
                    user_input])
            responses[event.request_id] = user_input
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


# LEFT-OFF: the agent asks a question without enough details, I respond with some guidance, but the agent is unaware of the context of its question
# LEFT-OFF: I still don't have the final output
# LEFT-OFF: reading the HITL section of the documentation; the agent sometimes "uses output" instead of "request_info"

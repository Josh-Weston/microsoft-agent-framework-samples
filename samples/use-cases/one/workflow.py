from agent_framework import WorkflowBuilder, executor, WorkflowContext
from agent_framework.openai import OpenAIChatClient
from pypdf import PdfReader
from dotenv import load_dotenv
import asyncio
import pathlib
import os

from utils import is_agent_response_update


@executor()
async def read_pdf(path: str, ctx: WorkflowContext[str, Exception]):
    """
    read_pdf receives the path to a PDF file and retutrns the contents as text
    """
    file_path = pathlib.Path(path)
    # if not file_path.exists():
    #     await ctx.yield_output(FileNotFoundError(f"File not found: {file_path}"))
    #     return
    # if not file_path.is_file():
    #     await ctx.yield_output(ValueError(f"Path is not a file: {file_path}"))
    #     return

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
        name="Building Permit Data Extraction Agent",
        tools=[],
        default_options={
            "model": "openai/gpt-oss-120b:cerebras",
            # "model_id": "openai/gpt-oss-120b:novita",
        },
    )


def create_workflow():
    data_agent = create_data_agent()
    return (
        WorkflowBuilder(start_executor=read_pdf)
        .add_edge(read_pdf, data_agent)
        .build()
    )


async def main(file: str):
    wf = create_workflow()
    async for event in wf.run(message=file, stream=True):
        print(event)
        if event.type == "output" and is_agent_response_update(event.data):

            # Note: it is common for several empty data.text events to be received while the LLM prepares a response.
            if event.data.text:
                print(f"Agent response update: {event.data.text}")


if __name__ == "__main__":
    load_dotenv()
    file = "samples/use-cases/one/files/permit_app_005.pdf"
    asyncio.run(main(file))

# LEFT-OFF: this working, but output is difficult to understand to confirm if it is working or not

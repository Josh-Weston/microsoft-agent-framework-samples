"""This sample uses executors and is purely deterministic"""

from dataclasses import dataclass
from collections.abc import AsyncIterable

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
)
import asyncio


@dataclass
class NumberSignal:
    hint: str  # "init", "above", or "below"


class JudgeExecutor(Executor):
    def __init__(self, target_number: int):
        super().__init__(id="judge")
        self._target_number = target_number
        self._tries = 0

    @handler
    async def handle_guess(self, guess: int, ctx: WorkflowContext[int, str]) -> None:
        self._tries += 1
        if guess == self._target_number:
            await ctx.yield_output(f"{self._target_number} found in {self._tries} tries!")
        elif guess < self._target_number:
            await ctx.request_info(request_data=NumberSignal(hint="below"), response_type=int)
        else:
            await ctx.request_info(request_data=NumberSignal(hint="above"), response_type=int)

    @response_handler
    async def on_human_response(
        self,
        original_request: NumberSignal,
        response: int,
        ctx: WorkflowContext[int, str],
    ) -> None:
        await self.handle_guess(response, ctx)


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, int] | None:
    """Process events from the workflow stream to capture requests."""
    requests: list[tuple[str, NumberSignal]] = []
    async for event in stream:
        if event.type == "request_info":
            requests.append((event.request_id, event.data))
        elif event.type == "output":
            print(f"Workflow completed with output: {event.data}")

    # Handle any pending human feedback requests.
    if requests:
        responses: dict[str, int] = {}
        for request_id, request in requests:
            guess = int(
                input(f"Received hint '{request.hint}'. Please provide your next guess: "))
            responses[request_id] = guess
        return responses

    return None


async def main():
    # Initiate the first run of the workflow with an initial guess.
    # Runs are not isolated; state is preserved across multiple calls to run.
    judge = JudgeExecutor(target_number=42)
    workflow = WorkflowBuilder(start_executor=judge).build()
    starting_guess = 25
    stream = workflow.run(starting_guess, stream=True)

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

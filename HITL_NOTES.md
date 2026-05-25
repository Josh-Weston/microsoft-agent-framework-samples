# Overview

HITL is achieved through the request and response handling mechanism in workflows, which allows executors to send requests to external systems (such as human operators) and wait for their responses before proceeding with the workflow execution.

In Python, executors send requests using `ctx.request_info()` and handle responses with the `@response_handler` decorator.

When you pass the human feedback back into the loop using workflow.run(responses=pending_responses), you are not starting the workflow from scratch. Instead, the framework resumes execution from the exact point where the agent paused to wait for external input.

**Runs are not isolated; state is preserved across multiple calls to `workflow.run()`**

Once the human provides their input, the `while` loop triggers the workflow again using `stream = workflow.run(stream=True, responses=pending_responses)`.

- ID Matching: The `responses` dictionary maps the human's input to the unique `request_id` generated when the workflow paused.
- Automatic Routing: The framework uses this ID to automatically route the human's response back to the specific executor/agent that made the original request.
- The `@response_handler`: Inside the framework, this data is caught by the agent's `@response_handler` method. The agent digests the human feedback and picks up its logic from the exact line it left off.

When using `checkpoints`, **Any pending requests will be re-emitted as RequestInfoEvent objects, allowing you to capture and respond to them.**

Think of `workflow.run()` in an event-driven architecture not as a "start" command, but as a "tick forward" command. If no responses are provided, the workflow ticks forward until it finishes or hits a stopping point (a human request). If responses are provided, it injects those responses into the paused agents, unblocks them, and ticks forward again.

## Example

```
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

```

## Handling Requests and Responses

Executors can send requests directly without needing a separate component. When an executor calls `ctx.request_info()`, the workflow emits a `WorkflowEvent` with `type == "request_info"`.

Agents can use tools that require human approval before execution. When the agent attempts to call an approval-required tool, the workflow pauses and emits a `RequestInfoEvent` just like the `RequestPort` pattern, but the event payload contains a `type == "function_approval_request"` instead of a custom request type.

The `@response_handler` decorator automatically registers the method to handle responses for the specified request and response types. The framework matches incoming responses to the correct handler based on the type annotations of the `original_request` and `response` parameters.

You can name the first two parameters whatever you want, as in below:

```
@response_handler
async def on_human_feedback(
    self,
    agent_request: HumanFeedbackRequest,
    human_response: str,
    ctx: WorkflowContext[AgentExecutorRequest, str],
) -> None:
```

When you receive a response from an external system, send it back to the workflow using the `response` mechanism. The framework automatically routes the response to the executor's `@response_handler` method.

`workflow.run(stream=True, responses=pending_responses)`

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

Note: internally, the package uses the request_id UUID to map a caller-supplied response to the correct pending request. Workflow execution collects all `request_info` requests and pauses the workflow (completes the super step). Next, when `workflow.run()` is called again, a new super step is started and the responses are routed to the requestors. Only executors with pending messages re-run, plus any executors they activate downstream.

The workflow is a frozen request queue that only advances when you call run(), and HITL responses are just pre-loaded replies that unblock the specific executors waiting on them before the next tick.

In the case of an agent, the response is packaged as a message that is added to the existing conversation and the entire conversation is passed as inference. The agent knows to complete the conversation because the last message is a `request_info` or `tool_call` for which it has learned to use that content to respond to the original request.

## Functional API (Experimental)

The functional API is an alternative approach to creating workflows. It allows for writing more concise, procedural workflows instead of using the graph based (classes and declarative patterns). It appears to have all of the functionality of the builder API, but shouldn't be used in production until no longer experimental.

## with_request_info()

**Note:** The agent doesn't decide to use this. The framework automatically pauses for human input **before** the agent receives the conversations.

Enable request info before agents run in the workflow.

When enabled, the workflow pauses before each agent runs, emitting a RequestInfoEvent that allows the caller to review the conversation and optionally inject guidance before the agent responds. The caller provides input via the standard response_handler/request_info pattern.

```
   # Pause before all agents
   workflow = SequentialBuilder().participants([a1, a2]).with_request_info().build()

   # Pause only before specific agents
   workflow = (
       SequentialBuilder()
       .participants([drafter, reviewer, finalizer])
       .with_request_info(agents=[reviewer])  # Only pause before reviewer
       .build()
   )
```

**Note:** For a SequentialBuilder, it is a one-way street. There is no way to "re-run" a previous agent based on HITL feedback. For a "loop-back" approach, I would need to use a manual graph and conditionals to loop back to
the previous node.

`AgentRequestInfoResponse.approve()` is the same as skipping; it adds no notes to the existing conversation that is passed downstream.

Manual approach (without with_request_info): https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/human-in-the-loop/agents_with_HITL.py
Automatic approach (with with_request_info): https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/human-in-the-loop/sequential_request_info.py

#### Limitation of with_request_info() for response_format

See this issue: https://github.com/microsoft/agent-framework/issues/6366

When you **don't** use `with_request_info()`, the response_format is enforced by the LLM provider:

- Pre-flight: the framework takes that schema and injects it into the actual API payload sent to the provider.
- Post-flight: the framework uses "lazy evaluation" and relies entirely on the LLM provider's server-side enforcement.

When you **do** use `with_request_info()`, the same steps as above happens, but then the framework runs its own evaluation as
per below. The framework enforces the `response_format` provided to the agent.

See the file `agent_framework/_types.py` for `ChatResponse` class.

```
@property
def text(self) -> str:
    """Returns the concatenated text of all messages in the response."""
    return ("\n".join(message.text for message in self.messages if isinstance(message, Message))).strip()

@property
def value(self) -> ResponseModelT | None:
    """Get the parsed structured output value.

    If a response_format was provided and parsing hasn't been attempted yet,
    this will attempt to parse the text into the specified type.

    Raises:
        ValidationError: If the response text doesn't match the expected schema.
        ValueError: If the response text is not valid JSON for a non-Pydantic structured format.
    """
    if self._value_parsed:
        return self._value
    if self._response_format is not None:
        self._value = cast(ResponseModelT, _parse_structured_response_value(self.text, self._response_format))
        self._value_parsed = True
    return self._value
```

# Sequential

- By default, SequentialBuilder designates the last participant as the terminal output source (final_output_from). Only that participant's output surfaces as an "output" event.
- Setting `chain_only_agent_responses=True` configures all agents in the sequence to consume only the previous agent's response messages (instead of the full conversation (input + response messages))
- When a custom executor follows an agent in the sequence, its handler receives an `AgentExecutorResponse`(because agents are internally wrapped by AgentExecutor).
- A custom executor used as the last participant (terminator) must call `ctx.yield_output(AgentResponse(...))` so its output becomes the workflow's terminal output.
- A custom executor used as the first participant, must receive a `list[Message]` type as its first parameter. The messages can be read by unpacking the `Message` type, such as `input_messages[0].contents[0].text`
- The `SequentialBuilder` orchestration provides a convenient `chain_only_agent_responses` parameter that configures all agent participants to use `context_mode="last_agent"`, so each agent consumes only the previous agent's response messages. Normally, `context_mode="last_agent"` would need to be set for each agent individually.

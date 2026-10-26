## Question

At the database and implementation level, this still achieves the same thing. The user only needs to pass the previous_response_id to the server, which then "rebuilds" the conversation by walking back through the linked list. Then it calls the LLM with this message history, saves the new response in the database and returns it to the user.

## Answer

OpenAI doesn't publish how this works internally, but what you can observe matches it: walk the chain, rebuild the context, call the model, store the new items and return them. The two designs mainly differ in which pointer the client sends.

previous_response_id points to a node. It says exactly where the new turn attaches, so branching works without extra effort.
thread_id points to a container. It means "attach to whatever comes last," so branching needs extra information.

You don't have to pick one. Use both: keep the thread as the container for storage, listing and UI, and give messages a parent pointer so they form a tree inside the thread. ChatGPT's own data export appears to work this way: each conversation holds a map of message nodes with parent and child links, plus a current_node pointer.

Suggested shape
threads
id, title, created_at, active_leaf_id -- the "head" of the current branch

messages
id, thread_id, parent_id (nullable), role, content/items, created_at

runs
id, thread_id, input_message_id, status, model, started_at, ended_at, error
-- outputs are messages whose parent chain leads back to input_message_id

API behaviour

- POST /threads/{id}/messages without parent_id appends to active_leaf_id. This keeps your current simple behaviour.
- POST /threads/{id}/messages with parent_id starts a branch, for example to edit a message or regenerate a reply. The new leaf becomes active_leaf_id.
- To build the context, walk parent_id from the leaf back to the root. In SQL that's a recursive CTE, which is cheap at conversation scale.
- To show the thread, query WHERE thread_id = ? for all messages and render the active path. Sibling counts give you the "< 2/3 >" branch switcher.

## Things worth deciding early

- Concurrency. "Append to latest" causes a race if two requests land at once, or if a message arrives while a run is still in progress. Either lock one active run per thread, or have the client send the leaf it expects (expected_leaf_id) and reject or branch if it doesn't match. An explicit parent pointer avoids this problem, which is one reason OpenAI's design uses it.
- Runs vs. messages. Keep runs as execution records (status, timing, errors, tool calls) separate from the message tree. A failed or cancelled run shouldn't leave half-finished messages on the active path.
- Drag-and-drop. If users can reorder messages, the order can no longer come from parent links. Either treat a reorder as creating a new branch, so history stays immutable, or add an explicit position field and give up tree semantics for that thread. Treating it as a branch keeps things more consistent.
- Store items, not just text. Save tool calls, tool results and reasoning as typed items, like the Responses API does. That way any provider adapter can rebuild the context exactly.

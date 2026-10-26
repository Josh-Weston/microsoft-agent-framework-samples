# How MAF processes provider responses (OpenAIChatClient → Agent)

Reviewed against the installed packages: `agent-framework-core 1.22.0`, `agent-framework-openai 1.17.0`, `openai 2.38.0`.
All line references below point into `.venv/Lib/site-packages/`.

> **TL;DR** – MAF never hands you the provider's raw payload directly. The OpenAI SDK object is
> **parsed into framework `Content` items** by the provider client, those are **wrapped** in
> `ChatResponse` / `ChatResponseUpdate`, **merged / coalesced** by `_process_update` +
> `_finalize_response`, **augmented** by the function-invocation loop (tool calls + results,
> aggregated usage), and finally **re-wrapped** as `AgentResponse` / `AgentResponseUpdate` by the
> `Agent` (which adds `author_name` and drops `conversation_id` / `model` from the top level).
> The original provider object is always retained in `raw_representation` (one or more levels deep).

---

## 1. Component composition

`OpenAIChatClient` is not one class doing everything; it is a stack of **mixins resolved by Python's MRO**.
Each layer's `get_response()` calls `super().get_response()`, so a call travels left → right
through the bases and the response travels back right → left.

```mermaid
classDiagram
    direction LR
    class Agent {
      run()
    }
    class AgentMiddlewareLayer {
      run() agent middleware pipeline
    }
    class AgentTelemetryLayer {
      run() invoke_agent span
    }
    class RawAgent {
      run()
      _prepare_run_context()
      _call_chat_client()
      _parse_non_streaming_response()
      _parse_streaming_response()
    }
    class OpenAIChatClient
    class FunctionInvocationLayer {
      get_response() tool loop
    }
    class ChatMiddlewareLayer {
      get_response() chat middleware
    }
    class ChatTelemetryLayer {
      get_response() chat span
    }
    class RawOpenAIChatClient {
      _inner_get_response()
      _prepare_options()
      _parse_response_from_openai()
      _parse_chunk_from_openai()
      _finalize_response_updates()
    }
    class BaseChatClient {
      <<abstract>>
      get_response()
      _inner_get_response()*
      _finalize_response_updates()
    }
    class AsyncOpenAI {
      responses.create / parse / stream / retrieve
    }

    Agent --|> AgentMiddlewareLayer
    Agent --|> AgentTelemetryLayer
    Agent --|> RawAgent
    OpenAIChatClient --|> FunctionInvocationLayer
    OpenAIChatClient --|> ChatMiddlewareLayer
    OpenAIChatClient --|> ChatTelemetryLayer
    OpenAIChatClient --|> RawOpenAIChatClient
    RawOpenAIChatClient --|> BaseChatClient
    RawAgent --> OpenAIChatClient : self.client
    RawOpenAIChatClient --> AsyncOpenAI : self.client
```

| Class | File | Role |
|---|---|---|
| `OpenAIChatClient` | [agent_framework_openai/_chat_client.py#L4560](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L4560) | Public client. MRO: `FunctionInvocationLayer → ChatMiddlewareLayer → ChatTelemetryLayer → RawOpenAIChatClient → BaseChatClient`. `OTEL_PROVIDER_NAME = "openai"`. |
| `FunctionInvocationLayer` | [agent_framework/_tools.py#L5543](./.venv/Lib/site-packages/agent_framework/_tools.py#L5543) | Owns the tool-call loop: calls the model, runs local tools, re-calls the model, stitches all messages into one response. |
| `ChatMiddlewareLayer` | [agent_framework/_middleware.py#L1715](./.venv/Lib/site-packages/agent_framework/_middleware.py#L1715) | Runs chat middleware **per model call** (inside the tool loop). Pass-through if none configured. |
| `ChatTelemetryLayer` | [agent_framework/observability.py#L1894](./.venv/Lib/site-packages/agent_framework/observability.py#L1894) | OTel span + metrics per model call. **Observe-only** – does not mutate the response. Pass-through when observability is disabled. |
| `RawOpenAIChatClient` | [agent_framework_openai/_chat_client.py#L583](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L583) | Provider translation: MAF `Message`s → Responses API `input`, and Responses API output/events → MAF `Content`. `STORES_BY_DEFAULT = True`. |
| `BaseChatClient` | [agent_framework/_clients.py#L221](./.venv/Lib/site-packages/agent_framework/_clients.py#L221) | Abstract base. `get_response()` applies optional compaction then calls `_inner_get_response()`. Default finalizer = `ChatResponse.from_updates`. |
| `Agent` / `RawAgent` | [agent_framework/_agents.py#L1991](./.venv/Lib/site-packages/agent_framework/_agents.py#L1991) / [#L891](./.venv/Lib/site-packages/agent_framework/_agents.py#L891) | Session/context providers, option merging, and conversion `ChatResponse → AgentResponse`. |

### Instantiation (`OpenAIChatClient.__init__`)

`OpenAIChatClient.__init__` ([L4677](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L4677)) forwards everything to `super().__init__`, so each layer peels off its own kwargs:

1. `FunctionInvocationLayer.__init__` takes `function_invocation_configuration` + function middleware.
2. `ChatMiddlewareLayer.__init__` takes `middleware` → `self.chat_middleware`.
3. `ChatTelemetryLayer.__init__` creates token/duration histograms, sets `otel_provider_name`.
4. `RawOpenAIChatClient.__init__` ([L710](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L710)) calls `load_openai_service_settings(...)` which resolves env vars (`OPENAI_*` or `AZURE_OPENAI_*`) and builds an `AsyncOpenAI` / `AsyncAzureOpenAI` → stored in `self.client`. Stores `self.model`. If Azure, `OTEL_PROVIDER_NAME = "azure.ai.openai"`.
5. `BaseChatClient.__init__` ([L293](./.venv/Lib/site-packages/agent_framework/_clients.py#L293)) stores `additional_properties`, `compaction_strategy`, `tokenizer`.

> Note: `OpenAIChatClient` targets the **Responses API** (`client.responses.*`), not Chat Completions.

---

## 2. Non-streaming sequence (`await agent.run(...)`)

```mermaid
sequenceDiagram
    autonumber
    actor User as Your App
    participant AG as Agent (AgentMiddlewareLayer + AgentTelemetryLayer + RawAgent)
    participant CP as Context / History Providers
    participant FIL as FunctionInvocationLayer
    participant CML as ChatMiddlewareLayer
    participant CTL as ChatTelemetryLayer
    participant BCC as BaseChatClient.get_response
    participant RAW as RawOpenAIChatClient._inner_get_response
    participant SDK as AsyncOpenAI SDK
    participant API as OpenAI / Azure OpenAI Responses API

    User->>AG: run(messages, session, options)
    Note over AG: normalize_messages(): str/Content becomes Message(role=user)<br/>merge default_options + run options (None values stripped)<br/>may auto-inject InMemoryHistoryProvider
    AG->>CP: before_run() on each provider
    CP-->>AG: history messages, extra instructions, tools, middleware
    Note over AG: session_messages = history + input<br/>chat_options gains conversation_id (session.service_session_id), tools, instructions<br/>client_kwargs gains session + provider middleware
    AG->>FIL: client.get_response(session_messages, stream=False, options)

    Note over FIL: copy options, strip additional_function_arguments<br/>normalize tools, resolve pending approvals
    loop each model turn (max_iterations)
        FIL->>CML: super().get_response(prepared_messages)
        CML->>CML: run chat middleware (may rewrite messages/options or short-circuit)
        CML->>CTL: super().get_response()
        CTL->>CTL: open chat span, record input messages if sensitive data on
        CTL->>BCC: super().get_response()
        BCC->>BCC: optional compaction of messages
        BCC->>RAW: _inner_get_response(messages, options)
        Note over RAW: _validate_options(): range checks, tool normalisation<br/>_prepare_options(): drop unsupported keys (seed, stop, penalties...),<br/>rename max_tokens to max_output_tokens, conversation_id to previous_response_id or conversation,<br/>add include=reasoning.encrypted_content when not stored,<br/>Messages to input items (strip server-owned items when continuing),<br/>tools to OpenAI tool specs, response_format to text_format
        RAW->>SDK: responses.with_raw_response.create(stream=False, **run_options)
        SDK->>API: POST /responses
        API-->>SDK: HTTP 200 + JSON + headers
        SDK-->>RAW: raw_response, .parse() gives openai Response
        Note over RAW: _parse_response_from_openai():<br/>each output item becomes Content (text, text_reasoning, function_call, ...)<br/>ONE Message(role=assistant) holding all contents<br/>ChatResponse(response_id, created_at ISO str, model, usage_details,<br/>finish_reason, conversation_id, continuation_token, additional_properties=metadata,<br/>raw_representation=openai Response)<br/>model overwritten by x-ms-served-model header if present
        RAW-->>BCC: ChatResponse
        BCC-->>CTL: ChatResponse
        CTL->>CTL: record usage, duration, finish_reason, output messages on span
        CTL-->>CML: ChatResponse (unchanged)
        CML-->>FIL: ChatResponse (middleware may have replaced it)
        Note over FIL: aggregated_usage += response.usage_details
        alt response contains actionable function_call(s)
            FIL->>FIL: assign Content.id occurrence ids, run local tools (function middleware)
            Note over FIL: response.messages.append(Message(role=tool, function_result...))<br/>function_call_messages.extend(response.messages)<br/>next input = all messages, or only the tool message if conversation_id is set
        else no tool calls / approval request
            Note over FIL: exit loop
        end
    end
    Note over FIL: response.messages = [all prior assistant+tool messages] + final messages<br/>response.usage_details = SUM across all model turns<br/>internal conversation_id cleared<br/>fallback text added if iteration limit hit with nothing visible
    FIL-->>AG: ChatResponse (multi-message transcript)

    Note over AG: _parse_non_streaming_response():<br/>message.author_name = agent.name or UnnamedAgent (when None)<br/>session.service_session_id = response.conversation_id
    AG->>AG: _build_agent_response_from_chat_response()
    Note over AG: AgentResponse(messages SAME list objects, response_id, created_at,<br/>finish_reason, usage_details, continuation_token, additional_properties,<br/>raw_representation=ChatResponse)<br/>DROPPED at top level: conversation_id, model
    AG->>CP: after_run() (reverse order, e.g. history persistence)
    AG-->>User: AgentResponse
```

---

## 3. Streaming sequence (`agent.run(..., stream=True)`)

Streaming is where `_process_update` is used. Every layer wraps the stream in a `ResponseStream`
([_types.py#L4028](./.venv/Lib/site-packages/agent_framework/_types.py#L4028)), which records every update it yields
and, once exhausted, runs a **finalizer** that folds the recorded updates into a final response object.

```mermaid
sequenceDiagram
    autonumber
    actor User as Your App
    participant AG as Agent stream (map + hooks)
    participant FIL as FunctionInvocationLayer stream
    participant CTL as ChatMiddleware + ChatTelemetry
    participant RAW as RawOpenAIChatClient stream
    participant API as OpenAI Responses API (SSE)
    participant PU as _process_update + _finalize_response

    User->>AG: run(stream=True) returns ResponseStream[AgentResponseUpdate, AgentResponse]
    Note over AG: _prepare_run_context() same as non-streaming
    AG->>FIL: client.get_response(stream=True)
    FIL->>CTL: super().get_response(stream=True) (per model turn)
    CTL->>RAW: _inner_get_response(stream=True)
    RAW->>API: responses.with_raw_response.create(stream=True)
    Note over RAW: or responses.stream(text_format=...) when structured output is requested

    loop every SSE event
        API-->>RAW: event (response.created, output_text.delta, function_call_arguments.delta, response.completed, ...)
        Note over RAW: _parse_chunk_from_openai(event) gives ChatResponseUpdate:<br/>role=assistant, contents=[Content with merge_mode append or replace],<br/>response_id / conversation_id (only on created, in_progress, completed),<br/>model = client.model, then event.response.model on completed, then x-ms-served-model,<br/>usage Content(merge_mode=replace) only on response.completed,<br/>additional_properties = logprobs metadata, raw_representation = SSE event,<br/>NO message_id, NO author_name
        RAW-->>CTL: ChatResponseUpdate (recorded in inner ResponseStream._updates)
        CTL-->>FIL: same update (span activated around each pull)
        Note over FIL: function_call content gets Content.id occurrence id<br/>usage Content rewritten to CUMULATIVE usage across turns (replace)
        FIL-->>AG: ChatResponseUpdate
        Note over AG: map_chat_to_agent_update():<br/>AgentResponseUpdate(contents SAME list, role, author_name = update.author_name or agent.name,<br/>response_id, message_id, merge_mode, created_at, finish_reason, continuation_token,<br/>additional_properties, raw_representation = ChatResponseUpdate)<br/>DROPPED: conversation_id, model (still reachable via raw_representation)<br/>transform hook: session.service_session_id = raw.conversation_id
        AG-->>User: AgentResponseUpdate (yielded live, un-merged delta)
    end

    Note over RAW,PU: inner stream exhausted, FIL calls inner_stream.get_final_response()
    RAW->>RAW: _finalize_response_updates(): enrich Azure AI Search and MCP citations
    RAW->>PU: ChatResponse.from_updates(updates)
    PU-->>RAW: ChatResponse for this turn
    Note over RAW: mark completed computer calls, attach aggregated logprobs to first assistant text
    RAW-->>FIL: ChatResponse (turn)
    alt turn has actionable function_calls
        FIL->>FIL: execute tools locally
        FIL-->>AG: ChatResponseUpdate(role=tool, contents=[function_result...])
        AG-->>User: AgentResponseUpdate(role=tool)
        Note over FIL: loop: stream the next model turn
    end

    User->>AG: get_final_response() (or iteration ends)
    Note over AG,PU: Finalizers run inner to outer, each on ITS OWN recorded updates
    FIL->>PU: ChatResponse.from_updates(all ChatResponseUpdates across all turns)
    PU-->>FIL: ChatResponse (whole run)
    AG->>PU: AgentResponse.from_updates(all AgentResponseUpdates)
    PU-->>AG: AgentResponse
    Note over AG: _post_hook (result hook):<br/>author_name = agent.name or UnnamedAgent where None,<br/>session.service_session_id from raw updates' conversation_id,<br/>response_id = None if per-service-call persistence owns history,<br/>after_run() on context providers
    AG-->>User: AgentResponse (raw_representation = list of ChatResponseUpdate)
```

---

## 4. `_process_update` – the merge rules

[_types.py#L2457](./.venv/Lib/site-packages/agent_framework/_types.py#L2457). Shared by `ChatResponse.from_updates` and
`AgentResponse.from_updates` (and their `from_update_generator` async twins). It is called once per update and
**mutates the response in place**. `from_updates` then calls `_finalize_response` once at the end.

```mermaid
flowchart TD
    U[update] --> N{"response.messages empty?<br/>OR message_id differs from last message?<br/>OR author_name differs?<br/>OR update.role differs?"}
    N -- yes --> NM["append new Message('assistant', [])"]
    N -- no --> LM[reuse last Message]
    NM --> R
    LM --> R{"update.merge_mode == 'replace'?"}
    R -- yes --> CLR[message.contents.clear]
    R -- no --> CP
    CLR --> CP["copy author_name / role / message_id onto Message (if set)"]
    CP --> LOOP[for each content in update.contents]
    LOOP --> D{"dict without .type?"}
    D -- yes --> FD["Content.from_dict (invalid -> warning + SKIPPED)"]
    D -- no --> T
    FD --> T{content.type}
    T -- function_call --> FC["_merge_function_call_content:<br/>same call_id -> existing + content (concat args)<br/>no call_id -> merge with trailing function_call<br/>else append"]
    T -- usage --> US["NOT added to message.<br/>replace -> response.usage_details = copy<br/>else -> add_usage_details (sum)"]
    T -- anything else --> AP[message.contents.append - NO merging yet]
    FC --> RESP
    US --> RESP
    AP --> RESP["response-level fields (last non-None wins):<br/>response_id, created_at,<br/>additional_properties (merged, incoming wins),<br/>raw_representation list .append(update.raw_representation)<br/>ChatResponse: conversation_id, finish_reason, model<br/>AgentResponse: agent_id, finish_reason"]
    RESP --> CT{"update operation state"}
    CT -- terminal --> C1[continuation_token = None]
    CT -- in_progress --> C2[keep existing unless update carries one]
    CT -- unset --> C3[continuation_token = update.continuation_token]
```

### What `_process_update` changes vs. what the provider sent

| Aspect | Behaviour | Practical effect for your app |
|---|---|---|
| **Message boundaries** | New `Message` only when `message_id`, `author_name` or `role` changes. | `message_id` is optional and only present if the provider client (or your code) sets it. `OpenAIChatClient` (Responses API) leaves it `None`: the Responses API's per-item ids (`msg_…`, `fc_…`, `rs_…`) are kept per-`Content` in `additional_properties["openai"]["item_id"]` / `raw_representation`, not mapped to `message_id`. (By contrast `OpenAIChatCompletionClient` sets `message_id = chunk.id`.) With every update `role="assistant"`, *all* assistant output from one model turn (reasoning + text + tool calls) lands in **one** `Message`. A tool-result update (`role="tool"`) starts a new message; the next turn's assistant output starts another. Local ids may be added later by compaction (`msg_0`, `msg_1`, …) or the vector-store history provider (`uuid4`). |
| **Default role** | New message is created as `"assistant"` then overwritten by `update.role` if present. | Updates without a role are attributed to the assistant. |
| **`merge_mode="replace"` on the update** | Clears the current message's contents. | Rare for OpenAI (it uses *content-level* replace instead). |
| **Text / reasoning deltas** | Just **appended** as separate `Content` items here; merging is deferred to `_finalize_response`. | Intermediate state holds one `Content` per delta. |
| **Function-call argument deltas** | Merged immediately by `call_id` via `Content.__add__` (string args concatenated, dict args shallow-merged, `merge_mode="replace"` overwrites). | Parallel tool calls are kept separate by `call_id`. |
| **Usage** | **Removed** from message contents and folded into `response.usage_details` (summed, or replaced when `merge_mode="replace"`). | `UsageContent` that you saw in the stream is *not* in final `messages`. |
| **Dict contents** | Converted with `Content.from_dict`; unknown types are **logged and dropped**. | Silent data loss if a custom update carries an invalid dict. |
| **Response metadata** | `response_id`, `created_at`, `conversation_id`, `model`, `finish_reason`: **last non-None value wins**. `additional_properties` merged one level deep (incoming wins). | `model` ends up as the served model / completed-event model. |
| **`raw_representation`** | Coerced into a **list** and every update's raw object appended (including `None`). | Streaming `ChatResponse.raw_representation` = list of SSE events; streaming `AgentResponse.raw_representation` = list of `ChatResponseUpdate`. |
| **`continuation_token`** | Cleared on terminal events, retained while in progress. | Present only for background / long-running responses. |

### `_finalize_response` – post-processing after all updates

[_types.py#L2897](./.venv/Lib/site-packages/agent_framework/_types.py#L2897):

1. **`_coalesce_text_content(…, "text")`** ([L2741](./.venv/Lib/site-packages/agent_framework/_types.py#L2741)) – folds each *contiguous run* of `text` contents into one. A content with `merge_mode="replace"` resets the accumulated text (OpenAI's `response.output_text.done` carries the full text as `replace`, so the final text equals the server's final text rather than deltas + full text). Runs split when the "model output kind" changes (e.g. normal text vs **refusal**). Annotations concatenated; `additional_properties` first-chunk-wins per key; `raw_representation` becomes a flat list of the chunk raws (the **head chunk's raw is dropped**).
2. **`_coalesce_text_content(…, "text_reasoning")`** – same for reasoning, splitting on different reasoning `id`s and on reasoning-text vs reasoning-summary; keeps the latest `protected_data` (encrypted reasoning) and `status`.
3. **`_coalesce_code_interpreter_content`** – merges code-interpreter call/result chunks per `call_id`.
4. **`_coalesce_function_call_occurrences`** ([L2923](./.venv/Lib/site-packages/agent_framework/_types.py#L2923)) – merges function-call fragments sharing a `Content.id` even across messages, then **removes any message whose `contents` is empty** (e.g. the message created only by a `response.created` / usage-only update).
5. **`_clear_merge_mode`** – sets `merge_mode = None` on every content (recursively), since it is update-only state.

Structured output (`response.value`) is **lazy**: parsed on first access from the *last non-empty assistant message's text* using `response_format` (Pydantic `model_validate_json` or `json.loads`). A refusal yields `""` → `None`.

---

## 5. What gets added / removed / transformed – end-to-end ledger

### Outbound (request)

| Stage | Added | Removed / renamed |
|---|---|---|
| `RawAgent._prepare_run_context` ([_agents.py#L1523](./.venv/Lib/site-packages/agent_framework/_agents.py#L1523)) | History messages from providers; provider instructions appended to `instructions`; provider + MCP tools; `conversation_id` from `session.service_session_id`; `session` + middleware in `client_kwargs`. | `None` options stripped by `_merge_options`; internal loop marker removed. |
| `FunctionInvocationLayer.get_response` ([_tools.py#L6297](./.venv/Lib/site-packages/agent_framework/_tools.py#L6297)) | Messages are copied (caller's list not mutated). | `additional_function_arguments` removed from options. |
| `BaseChatClient.get_response` ([_clients.py#L486](./.venv/Lib/site-packages/agent_framework/_clients.py#L486)) | Compaction summaries (only when a compaction strategy / tokenizer is configured). | Compacted messages excluded. |
| `RawOpenAIChatClient._prepare_options` ([_chat_client.py#L1674](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L1674)) | `include: ["reasoning.encrypted_content"]` when not using service storage; `model` default from client; `instructions` passed through as the top-level Responses `instructions` field. | Drops `presence_penalty`, `frequency_penalty`, `logit_bias`, `seed`, `stop`. Renames `max_tokens → max_output_tokens`, `allow_multiple_tool_calls → parallel_tool_calls`, `conversation_id → previous_response_id` (`resp_*`) or `conversation` (`conv_*`). `response_format → text_format`. `verbosity → text.verbosity`. |
| `_prepare_message_for_openai` ([L1943](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L1943)) | Re-serialises reasoning items from encrypted payload (stateless mode). | When continuing a stored response: **skips** prior `function_call`, `text_reasoning`, shell/computer/MCP call items (server already has them). Local (non-hosted) approval request/response contents are never sent. |

### Inbound (response)

| Stage | Added | Removed / transformed |
|---|---|---|
| `_parse_response_from_openai` ([L3442](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L3442)) / `_parse_chunk_from_openai` ([L3825](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L3825)) | Normalised `finish_reason` (`stop`, `length`, `tool_calls`, `content_filter`); `conversation_id` (= `conversation.id` or **the response id** unless `store=False`); `continuation_token` for `queued`/`in_progress`; `usage_details` with canonical **and** `openai.*` keys (cached, reasoning tokens); citations → `Annotation` objects; refusal marked via `additional_properties`; logprobs under `additional_properties`. | OpenAI output items flattened into `Content`s in **one assistant `Message`**; `created_at` epoch → ISO-8601 string; `model` replaced by `x-ms-served-model` header (Azure). Unknown output/event types are **logged at debug and dropped**. SSE `error` events raise `ChatClientException`. |
| `RawOpenAIChatClient._finalize_response_updates` ([L1043](./.venv/Lib/site-packages/agent_framework_openai/_chat_client.py#L1043)) (stream only) | Azure AI Search / MCP citation enrichment; aggregated logprobs on first assistant text; computer calls marked completed. | — |
| `ChatTelemetryLayer` | Nothing on the response (span attributes / metrics only). | — |
| `FunctionInvocationLayer` | `Content.id` occurrence ids on function calls; `Message(role="tool")` with `function_result`s; all intermediate turns **prepended** to the final response; usage **summed across turns** (streaming: cumulative usage replace-updates + correction updates); fallback assistant text if limits hit; approval-request contents inserted next to their calls. | Internal/sentinel `conversation_id` cleared. Unexecutable calls dropped when `tool_choice="none"` after truncation. |
| `RawAgent` → `AgentResponse(Update)` | `author_name` on messages (`agent.name` or `"UnnamedAgent"`); `session.service_session_id` updated. | **`conversation_id` and `model` are not fields on `AgentResponse`/`AgentResponseUpdate`** – only reachable via `raw_representation`. `agent_id` is **not populated**. `response_id` set to `None` when per-service-call history persistence owns continuation. |

### Where to find the original provider payload

| You hold… | Path to raw OpenAI object |
|---|---|
| `AgentResponse` (non-stream) | `resp.raw_representation` → `ChatResponse` → `.raw_representation` → `openai.types.responses.Response` |
| `AgentResponse` (stream) | `resp.raw_representation` → `list[ChatResponseUpdate]` → each `.raw_representation` → SSE event object |
| `AgentResponseUpdate` | `upd.raw_representation` → `ChatResponseUpdate` → `.raw_representation` → SSE event |
| Any `Content` | `content.raw_representation` → the specific output part / item / event (merged text = list of chunk raws, minus the first) |

Serialisation note: `ChatResponse.to_dict()` excludes `raw_representation` **and** `additional_properties`; `AgentResponse.to_dict()` excludes only `raw_representation`.

---

## 6. Gotchas worth knowing when building on top of MAF

1. **Streamed updates are deltas, final response is merged.** What you print from `async for update in stream` is not the same shape as `await stream.get_final_response()` – e.g. you'll see `usage` contents and many small `text` contents in the stream, but one coalesced `text` and no `usage` content in the final messages.
2. **One assistant message per model turn** for `OpenAIChatClient` – because that client leaves `message_id` as `None` (the Responses API item ids are kept per-`Content` instead). If you need to split by output item, look at each `Content.raw_representation` / `additional_properties["openai"]["item_id"]`.
3. **`author_name` differs between stream and final** – streamed updates get `agent.name` (can be `None`); the final response backfills `"UnnamedAgent"`.
4. **`conversation_id` for the Responses API is the response id** (`resp_…`) unless a `conv_…` conversation is used, and it's `None` with `store=False`. It's stored on the session, not on `AgentResponse`.
5. **`usage_details` on the final response is the sum across every model call in the tool loop**, not just the last call.
6. **`message.text` joins text contents with a space; `response.text` joins messages with `"\n"` and strips** – and refusal text *is* included in `.text`.
7. **Unknown content dicts / OpenAI event types are silently dropped** (warning/debug log only).
8. Middleware can replace the response entirely: chat middleware sees **each model call's** `ChatResponse`; agent middleware sees the final `AgentResponse`. Telemetry never mutates.

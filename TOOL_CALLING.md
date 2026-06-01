# Tool calling with structured output

This works because modern LLMs has two different ways to respond: as a `tool_call` or as `content`

```
{
  "message": {
    "role": "assistant",
    "content": null, 
    "tool_calls": []
  },
  "finish_reason": "..."
}
```

The strict `response_format` you **only applies to the content field.**

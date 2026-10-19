See [this page](https://deepwiki.com/microsoft/agent-framework/3.2-provider-integrations) for an overview of how the
integrations work

# Agents

## OpenAI Compatible

Q: If I use the OpenAIChatClient and point it to a 3rd party provider will it standardize the responses back from the provider?
A: If the provider returns valid OpenAI-shaped JSON, your workflow code gets the same structure it would get from OpenAI

## Chat Completion

`result = agent.run('some prompt')`

`print(result)` = prints the concatenated msg.text for all messages returned
`for message in result.messages` = inspect each message (e.g., function_call, function_result, assistant response)

## Responses

# Workflows

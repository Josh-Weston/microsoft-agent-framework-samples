import json
import openai  # Or anthropic, etc.
from sandbox import AgentSandbox


def run_agent(user_prompt: str):
    client = openai.Client()

    # 1. Initialize the conversation history
    messages = [
        {"role": "system", "content": "You are an AI assistant. Use the bash tool to solve user requests."},
        {"role": "user", "content": user_prompt}
    ]

    # 2. Boot the stateful container
    with AgentSandbox(image="python:3.11-slim") as sandbox:

        # 3. The ReAct (Reason + Act) Loop
        while True:
            # Ask the LLM what to do next
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=[BASH_TOOL],
                tool_choice="auto"
            )

            message = response.choices[0].message
            messages.append(message)  # Save the LLM's reply to history

            # 4. Did the LLM decide to call our tool?
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "execute_bash":

                        # Dynamically extract the command the LLM generated
                        args = json.loads(tool_call.function.arguments)
                        agent_command = args["command"]

                        print(f"🤖 Agent is running: {agent_command}")

                        # Execute it in our Docker sandbox
                        result = sandbox.execute(agent_command)

                        # 5. Format the terminal output and send it back to the LLM
                        tool_response = (
                            f"Exit Code: {result['exit_code']}\n"
                            f"Output:\n{result['output']}"
                        )

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_response
                        })

                # The loop restarts, sending the terminal output back to the LLM so it can read it.
                continue

            # 6. If no tool calls were made, the LLM is done and talking directly to the user
            print(f"🤖 Final Answer: {message.content}")
            break


# Usage:
run_agent(
    "Create a python script that calculates the 10th Fibonacci number, then run it.")

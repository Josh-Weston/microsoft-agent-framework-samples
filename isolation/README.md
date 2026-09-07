
## Scripts

To execute scripts, the following needs to happen:

1) The agent needs to know the scripts exist. The scripts are disclosed as part of the SKILLS.md (e.g., "use /scripts/validate.py") to validate your work
2) The agent needs access to a tool for actually running the script.

Script running tools come in two flavours:

#### A. One tool per script

A tool is created for each script with the script path and the agent provides the arguments

```json
{
  "tool": "execute_script",
  "parameters": {
    "script_path": "/scripts/extract_regex.py",
    "arguments": [
      "--file", "clients.txt", 
      "--pattern", "email"
    ]
  }
}
```

#### B. One tool for all scripts (Unix Philosophy)

A general tool (e.g., Bash) is provided to the agent who then writes the bash commands for executing the script

```json
{
  "tool": "bash",
  "parameters": {
    "command": "unzip -q doc.docx -d unpacked/\nfind unpacked -type l -delete\npython scripts/merge_runs.py unpacked/"
  }
}
``` 

### Where to run the script

To provide an isolated environment to prevent the agent from crashing your system, you can leverage headless docker containers.

```python
import docker

client = docker.from_env()

# 1. Start a persistent container in the background
workspace = client.containers.run(
    "python:3.11-slim",
    command="tail -f /dev/null", # Keeps the container alive indefinitely
    detach=True,
    mem_limit="512m",       # Prevent the agent from crashing your host
    network_disabled=True   # Block external internet access for safety
)

# 2. The agent decides to run a command (e.g., from its tool output)
agent_command = "mkdir /app && echo 'print(\"Hello Agent\")' > /app/script.py && python /app/script.py"

# 3. Send the instruction to the container
exit_code, output = workspace.exec_run(f"bash -c '{agent_command}'")

# 4. Give the output back to the agent
print(output.decode('utf-8')) # Prints: Hello Agent

# 5. Clean up when the conversation ends
workspace.stop()
workspace.remove()
```

### (Good) Non-root user

```python
workspace = client.containers.run(
    "python:3.11-slim",
    command="tail -f /dev/null", 
    detach=True,
    mem_limit="512m",       
    network_disabled=True,
    user="1000:1000",       # Run as an arbitrary unprivileged user (UID 1000, GID 1000)
    working_dir="/tmp"      # Use /tmp as it is globally writable by default
)
```

### (Better) Non-root user (isolated to custom directory)

```python
# Pre-create the /app directory and grant ownership to UID 1000
workspace.exec_run("mkdir -p /app && chown -R 1000:1000 /app")

agent_command = "mkdir -p /app/test && echo 'print(\"Hello Agent\")' > /app/script.py && python /app/script.py"

# Send the instruction to the container as the non-root user
exit_code, output = workspace.exec_run(
    f"bash -c '{agent_command}'",
    user="1000:1000",
    workdir="/app"
)
```

### (Best) Read-Only Root

```python
workspace = client.containers.run(
    "python:3.11-slim",
    command="tail -f /dev/null", 
    detach=True,
    mem_limit="512m",       
    network_disabled=True,
    read_only=True,                     # Locks down the entire OS filesystem
    tmpfs={'/tmp': '', '/run': ''},     # Keeps required temp directories writable
    volumes={'/host/path/to/app': {'bind': '/app', 'mode': 'rw'}} # Only /app is writable
)
```


### How to prevent the agent from executing arbitrary commands

Attempting to filter or allowlist raw bash commands is a well-known anti-pattern in agent engineering. Bash is simply too expressive—if you try to block the rm command using regex, a hallucinating agent (or a malicious prompt injection) can bypass it entirely using hex encoding, variables, or base64 decoding (e.g., $(echo cm0gLXJmIC8= | base64 -d)).

Instead of trying to police the specific syntax the agent types, production systems use a defense-in-depth strategy. You let the agent "do its thing" freely, but you heavily restrict the arena it plays in.

Here is how you keep the agent on task and secure:

1. The Sandbox Security Boundary
Don't try to stop the agent from running a destructive command; make it so the destructive command has no impact.
    - Network Isolation: Cut off internet access (network_disabled=True in Docker) so the agent cannot download malware or exfiltrate data. If it needs API access, route it through a tightly controlled proxy.
    - Non-Root User: Never run the container as root. Create a limited user inside the Dockerfile so the agent cannot modify system binaries or install arbitrary packages.
    - Read-Only Mounts: If the agent needs to read your local database or codebase, mount those directories as read-only. Give the agent a designated /tmp/workspace where it is allowed to write.

2. Operational Guardrails
As you suggested, time and resource limits are critical to prevent the agent from getting lost or executing infinite loops.
    - Execution Timeouts: Enforce a strict timeout (e.g., 10-15 seconds) on exec_run. If a script hangs, kill the process and return a "Timeout Error" to the agent so it knows to try a different approach.
    - Loop Caps (Max Turns): LLMs can get stuck in "retry loops" where they fail, tweak a script slightly, fail again, and repeat forever. Cap the agent at 5 to 10 tool calls per user prompt. If it hits the cap, force it to stop and ask the user for help.
    - Output Truncation: If the agent runs cat massive_log.txt, it will flood its own context window and forget its original instructions. Truncate terminal outputs at ~2,000 characters.

3. The Tooling Pivot (When to abandon Bash)
If your use case strictly requires that the agent only performs a specific set of actions (e.g., checking Git status, running a test suite, and moving files), do not give it a generic bash tool.  Instead, provide discrete, explicit JSON tools. When you provide run_git_status() and run_test_suite() as exact functions, the agent is structurally constrained to the task and cannot hallucinate arbitrary Unix commands. Reserve the generic bash tool only for open-ended, exploratory agents (like general coding assistants).


## MAF Skills Provider (How it reads files)

When you point the AgentSkillsProvider (in C#) or SkillsProvider (in Python) to a directory, you do not need to manually build file-reading or script-executing tools. The framework automatically parses your directory structure and equips the agent with the necessary built-in tools.

Here is how the Microsoft Agent Framework handles the assets automatically:

- Skill Discovery (SKILL.md): The provider recursively scans your designated folders (up to two levels deep by default) looking for SKILL.md files. It extracts the YAML frontmatter (name, description, etc.) and automatically injects a summary of available skills into the agent's system prompt.
- Reading Instructions & Templates: The provider registers a built-in load_skill tool. The agent knows to use this tool when a user's prompt matches a skill's description, allowing it to pull the full contents of SKILL.md into its context window only when needed. It also registers tools to read resource files (like your .jinja templates and .csv references) out of the box, natively supporting extensions like .md, .json, .yaml, and .csv.
- Executing Scripts: If you initialize the provider with a script runner (e.g., passing SubprocessScriptRunner.RunAsync in C# or a script_runner protocol in Python), the provider automatically grants the agent a tool to execute the .py and .sh scripts found in the skill's /scripts subdirectory.
- Tool Approval Middleware: Because arbitrary file access and script execution carry security risks, MAF wraps these implicit tools in a Tool Approval Middleware. By default, tools that read resources might be auto-approved (via ReadOnlyToolsAutoApprovalRule), but executing your Python/Bash scripts requires explicit approval configuration before the agent can run them.  

Instead of writing custom execute_bash or read_file tools, you simply initialize the provider:

## Gotchas

- If file-based skills with scripts are provided but no script_runner is set, SkillsProvider raises an error when script execution is attempted.


## Responses Text Reasoning Protected Data

It exists purely so the conversation can continue statelessly across turns without OpenAI storing your conversation server-side: the model's actual internal reasoning trace gets encrypted with a key only OpenAI holds, and you're expected to just pass that blob back unchanged on the next request (the SDK does this for you automatically). OpenAI intentionally never exposes the raw chain-of-thought to developers — that's a deliberate product/safety decision, same as with o1/o3/gpt-5-family reasoning models generally.

You're note supposed to be able to read it.
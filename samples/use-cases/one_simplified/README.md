# Use Case 2: Cross-Departmental Policy Drafting

The Concept: Government policy is rarely written in a vacuum; it requires consensus from legal, financial, and subject matter experts.

The POC Scenario: Drafting a briefing note on a new provincial AI procurement standard.
Key AutoGen Patterns Explored: \* Group Chat Orchestration (Dynamic Speaker Selection): Instead of a linear sequence, agents converse in a shared room. AutoGen uses an internal manager to decide who speaks next based on the context of the conversation.

## How to build it locally:

Initialize three distinct agents with highly specific system prompts: a Legal Agent, a Financial Analyst Agent, and a Technology Policy Agent.

Set up an AutoGen GroupChat and a GroupChatManager.

Provide the starting prompt: "Draft a 2-page briefing note recommending local open-source LLMs over proprietary APIs. Consider legal risks, cost structures, and technical feasibility."

Watch your terminal as the agents autonomously debate. The Tech Agent will propose an idea, the Financial Agent might push back on compute costs, and they will iterate until a final document is synthesized.

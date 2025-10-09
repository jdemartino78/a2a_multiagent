# Multi-Tenant Architecture

This document details the multi-tenant architecture implemented in the `host_agent`.

## 1. Overview

The primary goal of this architecture is to allow the `host_agent` to securely and efficiently route incoming requests to the correct downstream agent, supporting both global agents (shared by all tenants) and tenant-specific agents (isolated to a single tenant).

## 2. Agent Discovery: The Agent Registry Service

The core of this architecture is a registry-based discovery mechanism.

- **Service:** `demo_agent_registry`
- **Function:** This web service acts as a dynamic database of all available downstream agents. The `host_agent` queries this service at startup to retrieve the agent cards for its specific `tenant_id`, which it then holds in memory for low-latency lookups.

### Agent Card Metadata

Each entry in the registry is an "agent card" JSON object that must contain specific metadata for the routing logic to function correctly:

1.  **`skills` Block:** Each skill must have a `description` and `examples`. The orchestrator LLM uses this text to decide which agent and skill is best suited for the user's prompt.
2.  **`tags` Object:** This is a critical object for routing. It must contain:
    -   `"type"`: A string that uniquely identifies the *type* of the agent (e.g., `"weather"`, `"calendar"`, `"horizon"`). This is the primary key the LLM uses for routing.
    -   `"tenant_id"`: **Required for tenant-specific agents.** This string identifies the tenant the agent belongs to (e.g., `"tenant-abc"`).

**Example Agent Cards:**

*A tenant-specific Horizon agent:*
```json
{
  "name": "Horizon Agent - Tenant ABC",
  "url": "http://localhost:10008",
  "description": "...",
  "skills": [ ... ],
  "tags": { "type": "horizon", "tenant_id": "tenant-abc" }
}
```

*A global Weather agent:*
```json
{
  "name": "Weather Agent",
  "url": "http://localhost:10001",
  "description": "...",
  "skills": [ ... ],
  "tags": { "type": "weather" }
}
```

## 3. Orchestration and Routing Logic

The routing logic is implemented in the `send_message` tool within `host_agent/routing_agent.py`.

1.  **LLM Decision:** The `host_agent`'s LLM first analyzes the user's prompt and the `skills` descriptions from all agent cards. It decides which agent *type* is the best fit and calls the `send_message` tool with the `agent_type` as an argument.

2.  **Filtering:** The `send_message` tool builds a filter query based on the `agent_type` (e.g., `{"type": "horizon"}`).

3.  **Conditional Tenant ID:** The tool then inspects its session state to see if a `tenant_id` was provided. If the `agent_type` is one that is known to be tenant-specific (e.g., "horizon"), the tool **appends the `tenant_id` to the filter query** (e.g., `{"type": "horizon", "tenant_id": "tenant-abc"}`).

4.  **Resolution:** The tool searches the in-memory list of agent cards with the final filter. This allows it to resolve the correct agent (e.g., finding the Horizon agent for "tenant-abc" on port 10008) and dispatch the message.

## 4. API: Tenant Identification

To support this logic, the `host_agent`'s API was modified.

- **File:** `host_agent/__main__.py`
- **Interface:** The Gradio UI at **http://localhost:8083** now provides a simple chat interface.

The `tenant_id` is passed as a command-line argument when starting the `host_agent`. This `tenant_id` is then stored in the session context and used for routing to tenant-specific agents.

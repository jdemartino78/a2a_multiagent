# Specification: Multi-Tenant Agent Orchestration

## 1. Overview

This document specifies the requirements for a multi-tenant agent orchestrator. The system is designed to have separate orchestrator instances for each tenant, with each instance configured at startup to route to the correct downstream, single-tenant agent.

## 2. Core Components

### 2.1. Orchestrator Agent (`host_agent`)

Each tenant will have their own instance of the orchestrator agent, which serves as the single entry point for all requests for that tenant. It is responsible for discovering and invoking the correct downstream agent.

### 2.2. Downstream Agents

The system includes multiple downstream agents. Some agents, like a "Horizon" agent, are single-tenant, meaning there is a unique deployment for each tenant. Other agents may be multi-tenant or single-instance.

## 3. Requirements

### 3.1. Service Discovery

- The orchestrator **must** have a mechanism to discover all available downstream agents.
- This discovery mechanism **must** support identifying agents based on metadata tags.
- The discovery mechanism **must not** rely on predictable URL patterns for security reasons.

### 3.2. Multi-Tenant Routing

- Each orchestrator instance **must** be configured with a specific `tenant_id` at startup via a command-line argument.
- The orchestrator **must** use its configured `tenant_id` to route requests to the correct single-tenant downstream agent instance.

### 3.3. Agent Registry

- To facilitate discovery, a central Agent Registry **must** be used.
- The registry **must** store "Agent Cards" for all available downstream agents.
- Each Agent Card in the registry **must** contain a `skills` array.
- Each `skill` in the array **must** contain a `tags` array of strings.
- These tags are used for routing and metadata, formatted as `"key:value"` strings.
- For tenant-specific skills, the `tags` array **must** include a `tenant_id` tag (e.g., `"tenant_id:tenant-abc"`).
- To differentiate skill types, the `tags` array **must** include a `type` tag (e.g., `"type:horizon"`).

### 3.4. Scalability

- The process of onboarding a new tenant **must not** require a code change to the orchestrator agent. It should be achievable by deploying a new, configured instance of the `host_agent` and adding a new entry to the Agent Registry.

### 3.5. Orchestration Logic

- The orchestrator agent's primary tool for delegation **must** be a `send_message` function.
- This function **must** take an `agent_type` (e.g., "horizon", "weather") as a parameter, which is determined by the orchestrator's LLM based on the user's prompt and the available agents' skills.
- The `send_message` function **must** implement conditional filtering logic:
    - It **must** first filter the agent registry by the provided `agent_type`.
    - If the `agent_type` is designated as tenant-specific, the function **must** then also filter by the `tenant_id` that the `host_agent` was configured with at startup.
    - If the `agent_type` is not tenant-specific (i.e., it is a "global" agent), it **must not** filter by `tenant_id`.
- This allows the orchestrator to resolve the correct agent URL for both single-tenant and global agents using a single, unified discovery mechanism.
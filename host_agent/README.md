# Host Agent

This agent acts as the central orchestrator and router for the multi-agent system.

## Function

The Host Agent exposes a single Gradio UI for users to interact with the entire system. Its primary responsibilities are:

1.  **Agent Discovery:** On startup, it queries a central "Demo Agent Registry" service to get a registry of all available downstream agents.

2.  **Orchestration:** It uses a Large Language Model to understand the user's prompt and select the appropriate downstream agent *type* based on skill descriptions in the registry.

3.  **Routing:** It uses a `send_message` tool to route the user's request to the correct agent. This routing logic is tenant-aware; if the request is for a tenant-specific agent type, it uses the `tenant_id` from the session context to select the correct agent instance.

4.  **Security:** It initiates the OAuth 2.0 flow when a user tries to access a secure agent for the first time.

## Session and Task Management

The host agent uses two persistence mechanisms to manage state:

1.  **Session State (`DatabaseSessionService`)**: The agent uses the ADK's `DatabaseSessionService` to persist session information, including the OAuth 2.0 `access_token`, to a local SQLite database file named `host_agent.db`. This is crucial for the OAuth flow, allowing the token received by the `/callback` web endpoint to be available to the agent runner in a subsequent turn.

2.  **Task State (`PersistentTaskStore`)**: The agent uses a custom `PersistentTaskStore` to manage the lifecycle of A2A tasks. When it delegates a task, it creates a local record and then updates it with the `remote_task_id` returned by the downstream agent. This linking is essential for maintaining a coherent view of the distributed operation and allows the agent to seamlessly resume operations after asynchronous events like user authentication.

## Running the Agent

For instructions on how to run this agent as part of the complete demo, please see the main [README.md](../../README.md) file.

---

For a complete technical breakdown of the multi-tenant architecture, please see [MULTI_TENANCY_README.md](./MULTI_TENANCY_README.md).

# Host Agent

This agent acts as the central orchestrator and router for the multi-agent system.

## Function

The Host Agent exposes a single Gradio UI for users to interact with the entire system. Its primary responsibilities are:

1.  **Agent Discovery:** On startup, it loads a registry of all available downstream agents from the `agent_registry.json` file.

2.  **Orchestration:** It uses a Large Language Model to understand the user's prompt and select the appropriate downstream agent *type* based on skill descriptions in the registry.

3.  **Routing:** It uses a `send_message` tool to route the user's request to the correct agent. This routing logic is tenant-aware; if the request is for a tenant-specific agent type, it uses the `tenant_id` from the session context to select the correct agent instance.

## API Usage

The agent runs a Gradio server at **http://localhost:8083**. It accepts a single JSON object with a `prompt` and a `session_context`.

**Example:**
```json
{
  "prompt": "What is the status of my order 123?",
  "session_context": {
    "tenant_id": "tenant-abc"
  }
}
```

---

For a complete technical breakdown of the multi-tenant architecture, please see [MULTI_TENANCY_README.md](./MULTI_TENANCY_README.md).

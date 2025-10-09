# Gemini Code Assistant Context: Multi-Agent Airbnb Planner

## 1. Project Overview

This is a Python-based multi-agent system designed to assist with trip planning. It demonstrates a secure, multi-tenant architecture where a central orchestrator routes user requests to a variety of specialized, downstream agents.

### Key Components:

*   **`host_agent`**: The central orchestrator and single entry point for users. It uses an LLM to understand user prompts and route them to the appropriate downstream agent. It also manages the security flow.
*   **Downstream Agents**:
    *   `airbnb_agent`: Searches for accommodations.
    *   `calendar_agent`: Checks the user's Google Calendar.
    *   `weather_agent`: Provides weather forecasts.
    *   `horizon_agent`: A sample tenant-specific agent for retrieving order status.
*   **`auth_lib`**: A shared library responsible for JWT validation, used by all downstream agents to secure their endpoints.
*   **`idp`**: A mock OAuth 2.0 Identity Provider that issues JWTs for authentication.
*   **`demo_agent_registry`**: A service that provides agent discovery capabilities to the `host_agent`.

### Architecture & Core Concepts:

*   **Multi-Tenancy**: The system is designed so that each tenant gets their own `host_agent` instance. This instance is configured with a `tenant_id` and routes requests to the correct downstream agent instance (e.g., a specific `horizon_agent` for that tenant).
*   **Service Discovery**: The `host_agent` discovers downstream agents by querying the `demo_agent_registry`. This allows for a decoupled and scalable system.
*   **Security**: The system is secured using OAuth 2.0. The `host_agent` initiates the authentication flow, and the downstream agents validate the JWTs using the shared `auth_lib`.
*   **State Persistence**: The `host_agent` uses the ADK's `DatabaseSessionService` to persist session state, including OAuth tokens, and a `PersistentTaskStore` to manage the state of long-running A2A tasks. Both services use a local SQLite database (`host_agent.db`). This ensures state is reliably shared between the web server and the agent runner.

## 2. Building and Running

### Installation

The project's dependencies are managed by `pyproject.toml`. Install them from the project root:

```bash
# It is recommended to use a virtual environment
pip install -e .
```

### Running the Full System

To run the demo, you must start the mock IDP, the agent registry, and all agents in separate terminals.

1.  **Set up the Identity Provider (IDP)**:
    *   The IDP requires a private key to sign JWTs and a public JWKS file for verification. Follow the detailed instructions in `README.md` under the "Configure the Identity Provider (IDP)" section to generate these keys and configure the `idp/.env` file.

2.  **Start the Services (from project root, each in a new terminal)**:

    ```bash
    # Terminal 1: Start the IDP
    python -m idp.app

    # Terminal 2: Start the Agent Registry
    python -m demo_agent_registry.app

    # Terminal 3: Start the Weather Agent
    python -m weather_agent

    # Terminal 4: Start the Calendar Agent
    python -m calendar_agent

    # Terminal 5: Start the Horizon Agent for a specific tenant
    python -m horizon_agent --port 10008 --tenant-id tenant-abc

    # Terminal 6: Start the Airbnb Agent
    python -m airbnb_agent

    # Terminal 7: Start the Host Agent
    python -m host_agent --port 8083
    ```

3.  **Interact with the System**:
    *   Open a browser and navigate to the `host_agent`'s Gradio UI at **http://localhost:8083**.

## 3. Development Conventions

### Authentication

*   All downstream agents **must** secure their `execute` methods by validating the JWT from the `Authorization` header.
*   This validation **must** be performed by calling the `is_token_valid` function from the shared `auth_lib.validator`.
*   For tenant-specific agents (like `horizon_agent`), the `required_tenant_id` parameter **must** be passed to `is_token_valid` to ensure the token's `tenant_id` claim matches the agent's configured tenant.

### Development Conventions

#### State Management

*   **ADK Session State**: Handled by `DatabaseSessionService`. State is **only** modified by calling `session_service.append_event(session, event)`, where the `event` contains an `EventActions` object with a `state_delta`. Direct modification of `session.state` followed by a "save" method is incorrect and will fail.
*   **A2A Task State**: Handled by the `PersistentTaskStore`. The state of a `Task` object is modified by setting the `task.status.state` attribute to a `TaskState` enum member (e.g., `TaskState.completed`). The top-level `task.state` attribute is deprecated.

#### Testing

The project has three sets of unit tests. To run all of them, use the following command from the project root:

```bash
python3 -m unittest auth_lib/test_validator.py host_agent/test_persistent_task_store.py host_agent/test_session_management.py host_agent/test_routing_agent.py
```

### Agent Structure

*   Each agent is a self-contained module in its own directory.
*   The core agent logic is typically found in `agent_executor.py` or a similarly named file within each agent's directory.

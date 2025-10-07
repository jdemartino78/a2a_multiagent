# Multi-Agent Airbnb Planner

This project implements a multi-agent system designed to assist with planning a trip. It features a central `host_agent` that acts as an orchestrator, routing user requests to a variety of specialized agents. The system has been refactored to support a secure, multi-tenant architecture.

## Architecture

The system now uses a registry-based discovery mechanism. The `host_agent` loads agent information from `host_agent/agent_registry.json` at startup. This file contains "agent cards" with metadata that the host agent's LLM uses to route requests to the appropriate downstream agent.

This architecture supports both global agents (like `weather_agent`) and tenant-specific agents (like `horizon_agent`). Each tenant gets their own instance of the `host_agent`, which is configured at startup with the appropriate `tenant_id`.

For a detailed explanation of the multi-tenancy architecture, see [`host_agent/MULTI_TENANCY_README.md`](./host_agent/MULTI_TENANCY_README.md).

## Getting Started

### 1. Installation

This project uses Python >=3.13 and manages dependencies via `pyproject.toml`. Install the necessary libraries by running the following command from the project root directory:

```bash
pip install -e .
```

### 2. Environment Variables

Ensure you have a `.env` file in the project root or have set the necessary environment variables for API keys (e.g., `GOOGLE_API_KEY`).

### 3. Running the Agents

To run the system, you must start all downstream agents and a `host_agent` instance for each tenant. Open a separate terminal for each of the following commands and run them from the project root directory.

**Terminal 1: Start the Weather Agent**
```bash
python -m weather_agent
```

**Terminal 2: Start the Calendar Agent**
```bash
python -m calendar_agent
```

**Terminal 3: Start the Horizon Agent for Tenant 'tenant-abc'**
```bash
python -m horizon_agent --port 10008
```

**Terminal 4: Start the Horizon Agent for Tenant 'tenant-xyz'**
```bash
python -m horizon_agent --port 10009
```

**Terminal 5: Start the Airbnb Agent**
```bash
python -m airbnb_agent
```

**Terminal 6: Start the Host Agent for Tenant 'tenant-abc'**
```bash
python -m host_agent --port 8083 --tenant-id tenant-abc
```

**Terminal 7: Start the Host Agent for Tenant 'tenant-xyz'**
```bash
python -m host_agent --port 8084 --tenant-id tenant-xyz
```

### 4. Interacting with the System

Once all agents are running, you can interact with the system via the Gradio UI for each tenant.

*   **For Tenant 'tenant-abc'**: Open your browser to **http://localhost:8083**
*   **For Tenant 'tenant-xyz'**: Open your browser to **http://localhost:8084**

You can now chat directly with the host agent for that tenant. For example, if you are on the UI for `tenant-abc`, you can ask:

```
What is the status of my order 123?
```

The host agent will automatically route your request to the correct `horizon_agent` for `tenant-abc`.

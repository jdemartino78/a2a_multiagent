# Horizon Agent

This agent is a sample tenant-specific service that provides information about orders.

## Function

The Horizon Agent is designed to simulate a service that would be used by a specific tenant (e.g., a specific company or user). It has a single tool, `get_order_status`, which returns mock data for an order.

In the multi-tenant architecture, multiple instances of the Horizon Agent are run on different ports, each representing a different tenant. The `host_agent` is responsible for routing requests to the correct instance based on the `tenant_id` provided in the user's request.

## Running the Agent

To run this agent for a specific tenant, you must provide a port number via the command line.

**Example for Tenant 'tenant-abc':**
```bash
python -m horizon_agent --port 10008
```

**Example for Tenant 'tenant-xyz':**
```bash
python -m horizon_agent --port 10009
```

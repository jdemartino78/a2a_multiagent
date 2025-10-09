# Horizon Agent

This agent is a sample tenant-specific service that provides information about orders.

## Function

The Horizon Agent is designed to simulate a service that would be used by a specific tenant (e.g., a specific company or user). It has a single tool, `get_order_status`, which returns mock data for an order.

In the multi-tenant architecture, an instance of the Horizon Agent is run for a specific tenant. The `host_agent` is responsible for routing requests to the correct instance based on the `tenant_id`.

## Running the Agent

For instructions on how to run this agent as part of the complete demo, please see the main [README.md](../../README.md) file.

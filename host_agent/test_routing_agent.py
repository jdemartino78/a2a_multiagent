import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a.types import (
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    TaskStatus,
)
from google.adk.tools.tool_context import ToolContext

from host_agent.persistent_task_store import PersistentTaskStore
from host_agent.routing_agent import AgentCard, RoutingAgent


class TestRoutingAgent(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_path = "test_routing_agent.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.task_store = PersistentTaskStore(db_path=self.db_path)

        # Mock Agent Cards with required fields
        self.weather_card = AgentCard(
            name="Weather Agent",
            url="http://weather.agent",
            description="Provides weather forecasts.",
            capabilities={},
            default_input_modes=[],
            default_output_modes=[],
            version="1.0",
            skills=[
                {
                    "id": "get_weather",
                    "name": "Get Weather",
                    "description": "Gets the weather.",
                    "tags": ["type:weather"],
                }
            ],
        )
        self.secure_horizon_card = AgentCard(
            name="Horizon Agent",
            url="http://horizon.agent",
            description="Secure order status agent.",
            capabilities={},
            default_input_modes=[],
            default_output_modes=[],
            version="1.0",
            skills=[
                {
                    "id": "get_order_status",
                    "name": "Get Order Status",
                    "description": "Gets order status.",
                    "tags": ["type:horizon", "tenant_id:tenant-abc"],
                }
            ],
            security={"authorization_uri": "http://idp/auth"},
        )
        self.all_cards = [self.weather_card, self.secure_horizon_card]

    async def asyncSetUp(self):
        self.routing_agent = await RoutingAgent.create(
            task_store=self.task_store, agent_cards=self.all_cards
        )



    @patch("host_agent.routing_agent.RemoteAgentConnections")
    async def test_send_message_to_global_agent(self, MockRemoteAgentConnections):
        """Verify that a task is sent to a non-secure, global agent."""
        mock_tool_context = MagicMock(spec=ToolContext)
        mock_tool_context.state = {}  # No tenant_id or access_token

        # Mock the remote connection's send_message method
        mock_connection_instance = MockRemoteAgentConnections.return_value
        mock_response_task = Task(
            id="remote-task-123",
            contextId="remote-context-456",
            request=MagicMock(),
            status=TaskStatus(state=TaskState.working),
        )
        mock_success_response = SendMessageSuccessResponse(result=mock_response_task)
        mock_send_response = SendMessageResponse(root=mock_success_response)
        mock_connection_instance.send_message = AsyncMock(
            return_value=mock_send_response
        )

        self.routing_agent.remote_agent_connections = {
            "Weather Agent": mock_connection_instance
        }

        await self.routing_agent.send_message(
            agent_type="weather",
            task="what is the weather in london",
            tool_context=mock_tool_context,
        )

        # Verify a task was created in the store
        tasks = await self.task_store.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].status.state, TaskState.submitted)

        # Verify send_message was called on the remote connection
        mock_connection_instance.send_message.assert_called_once()

    async def test_send_message_initiates_oauth_for_secure_agent(self):
        """Verify that the OAuth flow is started for a secure agent when no token is present."""
        mock_tool_context = MagicMock(spec=ToolContext)
        mock_tool_context.state = {"tenant_id": "tenant-abc"}  # Has tenant, no token

        result = await self.routing_agent.send_message(
            agent_type="horizon",
            task="check my order",
            tool_context=mock_tool_context,
        )

        # Verify a task was created
        tasks = await self.task_store.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        task_id = tasks[0].id

        # Verify the result is a redirect to the IDP
        self.assertIn("redirect_url", result)
        self.assertIn("state=", result["redirect_url"])
        self.assertEqual(result["task_id"], task_id)

    @patch("host_agent.routing_agent.RemoteAgentConnections")
    async def test_send_message_uses_existing_token(self, MockRemoteAgentConnections):
        """Verify that an existing access token is used for secure agents."""
        mock_tool_context = MagicMock(spec=ToolContext)
        mock_tool_context.state = {
            "tenant_id": "tenant-abc",
            "access_token": "test-token-123",
        }

        mock_connection_instance = MockRemoteAgentConnections.return_value
        mock_response_task = Task(
            id="remote-task-456",
            contextId="remote-context-789",
            request=MagicMock(),
            status=TaskStatus(state=TaskState.working),
        )
        mock_success_response = SendMessageSuccessResponse(result=mock_response_task)
        mock_send_response = SendMessageResponse(root=mock_success_response)
        mock_connection_instance.send_message = AsyncMock(
            return_value=mock_send_response
        )
        self.routing_agent.remote_agent_connections = {
            "Horizon Agent": mock_connection_instance
        }

        await self.routing_agent.send_message(
            agent_type="horizon",
            task="check my order",
            tool_context=mock_tool_context,
        )

        # Verify send_message was called with the correct auth header
        mock_connection_instance.send_message.assert_called_once()
        call_kwargs = mock_connection_instance.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer test-token-123")


if __name__ == "__main__":
    unittest.main()

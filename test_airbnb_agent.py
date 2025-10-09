# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from a2a.types import Message, Part, Task, TaskState, TaskStatus

from airbnb_agent.agent_executor import AirbnbAgentExecutor


class TestAirbnbAgentExecutor(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the AirbnbAgentExecutor."""

    def setUp(self):
        """Set up the test environment before each test."""
        self.mock_agent = MagicMock()
        self.mock_agent.stream.side_effect = self._mock_stream_gen
        with patch('airbnb_agent.airbnb_agent.AirbnbAgent') as mock_agent_class:
            mock_agent_class.return_value = self.mock_agent
            self.executor = AirbnbAgentExecutor(mcp_tools=[])

    async def _mock_stream_gen(self, *args, **kwargs):
        """A mock async generator to simulate the agent's stream method."""
        yield {"is_task_complete": True, "content": "Mocked response"}

    @patch("airbnb_agent.agent_executor.is_token_valid")
    async def test_execute_with_valid_token(self, mock_is_token_valid):
        """
        Verify that the executor proceeds when a valid token is provided.
        """
        # Arrange
        mock_is_token_valid.return_value = (True, "Token is valid.")
        mock_context = MagicMock()
        mock_context.call_context.state = {
            "headers": {"authorization": "Bearer valid_token"}
        }
        mock_context.message = Message(
            messageId=str(uuid.uuid4()),
            parts=[Part(text="Find an Airbnb")],
            role="user",
        )
        mock_context.current_task = Task(
            id="test_task_id",
            request=mock_context.message,
            contextId="test_context_id",
            status=TaskStatus(state=TaskState.submitted),
        )
        mock_event_queue = AsyncMock()

        # Act
        await self.executor.execute(mock_context, mock_event_queue)

        # Assert
        mock_is_token_valid.assert_called_once_with("valid_token")
        self.mock_agent.stream.assert_called_once()

    @patch("airbnb_agent.agent_executor.is_token_valid")
    async def test_execute_with_invalid_token(self, mock_is_token_valid):
        """
        Verify that the executor raises an exception for an invalid token.
        """
        # Arrange
        mock_is_token_valid.return_value = (False, "Token has expired.")
        mock_context = MagicMock()
        mock_context.call_context.state = {
            "headers": {"authorization": "Bearer invalid_token"}
        }
        mock_event_queue = AsyncMock()

        # Act & Assert
        with self.assertRaisesRegex(Exception, "Invalid token: Token has expired."):
            await self.executor.execute(mock_context, mock_event_queue)
        mock_is_token_valid.assert_called_once_with("invalid_token")

    async def test_execute_with_missing_header(self):
        """
        Verify that the executor raises an exception if the auth header is missing.
        """
        # Arrange
        mock_context = MagicMock()
        mock_context.call_context.state = {"headers": {}}
        mock_event_queue = AsyncMock()

        # Act & Assert
        with self.assertRaisesRegex(Exception, "Missing or invalid Authorization header."):
            await self.executor.execute(mock_context, mock_event_queue)

    async def test_execute_with_malformed_header(self):
        """
        Verify that the executor raises an exception for a malformed Bearer token.
        """
        # Arrange
        mock_context = MagicMock()
        mock_context.call_context.state = {
            "headers": {"authorization": "NotBearer invalid_token"}
        }
        mock_event_queue = AsyncMock()

        # Act & Assert
        with self.assertRaisesRegex(Exception, "Missing or invalid Authorization header."):
            await self.executor.execute(mock_context, mock_event_queue)


if __name__ == "__main__":
    unittest.main()

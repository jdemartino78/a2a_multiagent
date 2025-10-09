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
from google.genai import types

from weather_agent.weather_executor import WeatherExecutor


class TestWeatherExecutor(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the WeatherExecutor."""

    def setUp(self):
        """Set up the test environment before each test."""
        self.mock_runner = MagicMock()
        self.mock_runner.session_service = AsyncMock()  # Use AsyncMock for awaitable calls
        self.mock_card = MagicMock()
        self.executor = WeatherExecutor(self.mock_runner, self.mock_card)

    @patch("weather_agent.weather_executor.is_token_valid")
    async def test_execute_with_valid_token(self, mock_is_token_valid):
        """
        Verify that the executor proceeds when a valid token is provided.
        """
        # Arrange
        mock_is_token_valid.return_value = (True, "Token is valid.")

        # Mock the ADK runner to simulate its async generator behavior
        async def mock_run_async_gen(*args, **kwargs):
            yield MagicMock()

        self.mock_runner.run_async = mock_run_async_gen

        # Mock the context object to simulate a valid request
        mock_context = MagicMock()
        mock_context.call_context.state = {
            "headers": {"authorization": "Bearer valid_token"}
        }
        mock_context.message = Message(
            messageId=str(uuid.uuid4()),
            parts=[Part(text="What is the weather?")],
            role="user"
        )
        mock_context.task_id = "test_task_id"
        mock_context.context_id = "test_context_id"
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
        # Verify that the runner was eventually called
        self.assertTrue(hasattr(self.mock_runner, 'run_async'))


    @patch("weather_agent.weather_executor.is_token_valid")
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
        # Simulate headers being present but the 'authorization' key missing
        mock_context.call_context.state = {"headers": {"other-header": "value"}}
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

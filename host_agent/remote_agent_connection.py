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

"""
Manages A2A client connections and message sending to downstream agents.

This module provides a wrapper around the `a2a.client.A2AClient` to handle
the nuances of making both authenticated and unauthenticated requests.
"""

from collections.abc import Callable

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from dotenv import load_dotenv

load_dotenv()

# Type definitions for task update callbacks.
TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """
    Manages the connection and communication with a single downstream agent.

    This class encapsulates an `A2AClient` and provides a method to send
    messages, correctly handling the injection of authentication headers for
    secure agents.
    """

    def __init__(self, agent_card: AgentCard, agent_url: str):
        """
        Initializes the connection manager.

        Args:
            agent_card: The card of the downstream agent.
            agent_url: The URL of the downstream agent.
        """
        # A long-lived client for unauthenticated communication.
        self._httpx_client = httpx.AsyncClient(timeout=120)
        self.agent_client = A2AClient(
            self._httpx_client, agent_card, url=agent_url
        )
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        """Returns the agent card associated with this connection."""
        return self.card

    async def send_message(
        self, message_request: SendMessageRequest, headers: dict | None = None
    ) -> SendMessageResponse:
        """
        Sends a message to the downstream agent, handling authentication if required.

        Args:
            message_request: The A2A `SendMessageRequest` object to send.
            headers: An optional dictionary of headers. If it contains an
                     `Authorization` header, a temporary, authenticated client
                     will be used for this request.

        Returns:
            The `SendMessageResponse` from the downstream agent.
        """
        if headers:
            # CRITICAL: For authenticated requests, a new, temporary client
            # must be created. The `a2a.client.A2AClient` does not have a method
            # to add headers to an existing client instance. The underlying
            # `httpx.AsyncClient` must be initialized with the `Authorization`
            # header at creation time. This approach ensures that each secure
            # call uses the correct, fresh token provided for that specific request.
            authed_httpx_client = httpx.AsyncClient(
                timeout=120, headers=headers
            )
            agent_client = A2AClient(
                authed_httpx_client, self.card, url=self.card.url
            )
            return await agent_client.send_message(message_request)

        # For unauthenticated requests, use the default, long-lived client.
        return await self.agent_client.send_message(message_request)

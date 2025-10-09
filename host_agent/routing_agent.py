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
The primary orchestrator for the multi-agent system.

This module defines the RoutingAgent, which is responsible for discovering
downstream agents, routing user requests to the appropriate agent based on its
capabilities, and managing the security and task lifecycle for delegated
operations.
"""

import json
import logging
import os
import uuid
from urllib.parse import urlencode

import httpx
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    TaskStatus,
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext

from .persistent_task_store import PersistentTaskStore
from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class ExtendedAgentCard(AgentCard):
    """
    An extended AgentCard model to include non-standard `tags` and `security`
    fields, which are used for dynamic agent discovery and authentication routing.
    """
    tags: dict | None = None
    security: dict | None = None


class RoutingAgent:
    """
    The primary orchestrator responsible for routing requests to downstream agents.

    This agent discovers other agents via a registry service, uses an LLM to
    select the correct agent based on the user's prompt, and manages the
    A2A task lifecycle, including the OAuth 2.0 flow for secure agents.
    """

    def __init__(
        self,
        task_store: PersistentTaskStore,
        task_callback: TaskUpdateCallback | None = None,
    ):
        """
        Initializes the RoutingAgent.

        Args:
            task_store: An instance of PersistentTaskStore for managing task state.
            task_callback: An optional callback for handling task updates.
        """
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, ExtendedAgentCard] = {}
        self.agents_for_prompt: str = ""
        self.tenant_id: str | None = None
        self.task_store = task_store

    async def _async_init_components(
        self,
        agent_cards: list[ExtendedAgentCard] | None = None,
    ) -> None:
        """
        Asynchronously initializes connections to downstream agents and prepares
        prompt materials based on the discovered agent cards.

        Args:
            agent_cards: A list of agent cards fetched from the registry service.
        """
        if agent_cards:
            for card in agent_cards:
                try:
                    agent_url = str(card.url)
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=agent_url
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except Exception as e:
                    logging.error(
                        f"Failed to initialize connection for {card.name}: {e}"
                    )

        # Create a JSON string of agent details to be injected into the LLM prompt,
        # enabling the model to make informed routing decisions.
        agent_info = []
        for agent_detail_dict in self._internal_list_remote_agents():
            agent_info.append(json.dumps(agent_detail_dict))
        self.agents_for_prompt = "\n".join(agent_info)

    @classmethod
    async def create(
        cls,
        task_store: PersistentTaskStore,
        agent_cards: list[ExtendedAgentCard] | None = None,
        task_callback: TaskUpdateCallback | None = None,
        tenant_id: str | None = None,
    ) -> "RoutingAgent":
        """
        Factory method to create and asynchronously initialize a RoutingAgent.

        Args:
            task_store: The task store for state management.
            agent_cards: A list of discovered agent cards.
            task_callback: An optional callback for task updates.
            tenant_id: The tenant ID for this agent instance.

        Returns:
            A fully initialized RoutingAgent instance.
        """
        instance = cls(task_store, task_callback)
        instance.tenant_id = tenant_id
        await instance._async_init_components(agent_cards=agent_cards)
        return instance

    def create_agent(self) -> Agent:
        """
        Creates the ADK Agent instance with the necessary tools and instructions
        that define the agent's core routing logic.

        Returns:
            A configured ADK Agent.
        """
        return Agent(
            model="gemini-2.5-pro",
            name="Routing_agent",
            instruction=self.root_instruction,
            tools=[self.send_message, self.list_available_agents],
            description="This Routing agent orchestrates user requests by delegating them to specialized downstream agents.",
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        """
        Generates the root instruction prompt for the RoutingAgent's LLM.

        This prompt constrains the LLM to act as a pure router, either delegating
        the user's request via the `send_message` tool or providing a list of
        its capabilities via the `list_available_agents` tool.

        Args:
            context: The read-only context from the ADK.

        Returns:
            The formatted instruction string for the LLM.
        """
        return f"""
        ### Persona
        You are a specialized routing agent. You are not a conversationalist; you are a system component.

        ### Mission
        Your sole mission is to receive a user's request and either delegate it to a downstream agent or list your capabilities.

        ### Constraints
        - **DO NOT** respond to the user, engage in conversation, or ask clarifying questions unless it is the direct result of a tool output.
        - **DO NOT** attempt to answer the user's request yourself.
        - You **MUST** call the appropriate tool (`send_message` or `list_available_agents`). No other action is permitted.
        - You **MUST NOT** wrap the tool call in a `print()` statement.

        ### Instructions
        1.  **If the user asks about your capabilities (e.g., "what can you do?", "what agents do you have?"), you MUST use the `list_available_agents` tool.**
        2.  For any other request, you MUST delegate the task by calling the `send_message` tool.
        3.  To delegate, review the `Available Agents` list below and identify the single best `agent_type`.
        4.  Call `send_message` with two parameters:
            -   `agent_type`: The type you identified (e.g., "weather", "horizon").
            -   `task`: The user's original, unmodified request.

        ### Available Agents (for routing)
        {self.agents_for_prompt}
        """

    def _internal_list_remote_agents(self) -> list[dict]:
        """
        Generates a list of dictionaries containing agent details, which is
        injected into the LLM prompt for routing decisions.

        Returns:
            A list of dictionaries, each representing an agent's capabilities.
        """
        if not self.cards:
            return []

        remote_agent_info = []
        for card in self.cards.values():
            agent_info = {"name": card.name, "description": card.description}
            if card.skills:
                skills = [
                    skill.model_dump(exclude_none=True) for skill in card.skills
                ]
                agent_info["skills"] = skills
            remote_agent_info.append(agent_info)
        return remote_agent_info

    def list_available_agents(self) -> str:
        """
        Provides a user-friendly list of available agents and their capabilities.
        This tool is intended to be called when the user asks what the system can do.

        Returns:
            A formatted string listing the available agents.
        """
        if not self.cards:
            return "There are no agents available at the moment."

        summary = "I can connect you to the following agents:\n"
        for card in self.cards.values():
            summary += f"- **{card.name}:** {card.description}\n"
        return summary

    async def initiate_oauth_flow(
        self,
        agent_name: str,
        security_details: dict,
        task_id: str,
    ) -> dict:
        """
        Constructs the authorization URL to initiate the OAuth 2.0 flow.

        Args:
            agent_name: The name of the agent requiring authentication.
            security_details: The security scheme details from the agent's card.
            task_id: The ID of the local task, which is passed in the `state`
                     parameter to be recovered in the callback.

        Returns:
            A dictionary containing the `redirect_url` for the user.
        """
        auth_uri = security_details.get("authorization_uri")
        if not auth_uri:
            return {"error": "Authorization URI not found in security details."}

        redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:8083/callback")
        state_data = {"task_id": task_id}
        params = {
            "response_type": "code",
            "client_id": agent_name,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email api:read",
            "state": json.dumps(state_data),
        }
        authorization_url = f"{auth_uri}?{urlencode(params)}"
        return {"redirect_url": authorization_url, "task_id": task_id}

    def _find_agent_card_by_type(self, agent_type: str, state: dict) -> ExtendedAgentCard | None:
        """
        Finds a registered agent card that matches the required agent type and,
        if applicable, the tenant ID from the session state.

        Args:
            agent_type: The type of agent to find (e.g., "weather", "horizon").
            state: The current session state, which may contain a "tenant_id".

        Returns:
            The matching ExtendedAgentCard or None if not found.
        """
        filter_query = {"type": agent_type}

        # For agents designated as tenant-specific, the tenant_id from the
        # session must be added to the search query.
        tenant_specific_agents = ["horizon"]
        if agent_type in tenant_specific_agents:
            tenant_id = state.get("tenant_id")
            if not tenant_id:
                logging.warning(f"Tenant ID required for agent type '{agent_type}' but not found in session.")
                return None
            filter_query["tenant_id"] = tenant_id

        # Iterate through all registered agent cards to find a match based on the
        # tags defined in their skills.
        for card in self.cards.values():
            if not card.skills:
                continue
            for skill in card.skills:
                if not skill.tags:
                    continue

                # Convert the list of "key:value" tags into a dictionary for easy comparison.
                skill_tags_dict = {}
                for tag in skill.tags:
                    if ":" in tag:
                        key, value = tag.split(":", 1)
                        skill_tags_dict[key] = value

                # Check if the skill's tags are a superset of our filter query.
                # This allows us to match `{"type": "horizon", "tenant_id": "abc"}`
                # against a card with `{"type": "horizon", "tenant_id": "abc", "version": "2"}`.
                if filter_query.items() <= skill_tags_dict.items():
                    return card
        return None

    async def send_message(
        self, agent_type: str, task: str, tool_context: ToolContext
    ) -> str:
        """
        Sends a task to a remote agent, handling discovery, security, and lifecycle.

        This is the primary tool used by the LLM to delegate work. It follows these steps:
        1. Finds the correct agent card based on type and tenant.
        2. Creates and persists a local task to track the operation.
        3. Checks for security requirements and initiates OAuth if necessary.
        4. Sends the message to the remote agent according to the A2A spec.
        5. Processes the response and links the remote task ID to the local task.

        Args:
            agent_type: The type of agent to send the task to (e.g., "weather").
            task: The comprehensive task description for the agent.
            tool_context: The context provided by the ADK, containing session state.

        Returns:
            A string containing the resulting Task object (as JSON), a redirect
            dictionary for OAuth (as JSON), or an error message.
        """
        logging.info(f"Attempting to send task to agent of type: {agent_type}")
        logging.info(f"Task content: {task}")

        state = tool_context.state

        # 1. Find the correct agent card based on type and tenant.
        found_card = self._find_agent_card_by_type(agent_type, state)
        if not found_card:
            return f"I'm sorry, I can't find an agent with the type '{agent_type}'. Please choose from the available agent types."

        agent_name = found_card.name
        logging.info(f"Found matching agent '{agent_name}' for agent type '{agent_type}'")

        # 2. Create and persist a local task to track this operation. This is crucial
        # for managing state across asynchronous operations like OAuth.
        task_id = str(uuid.uuid4())
        context_id = state.get("context_id") or str(uuid.uuid4())
        state["context_id"] = context_id
        original_request = Message(
            role="user",
            parts=[Part(type="text", text=task)],
            messageId=str(uuid.uuid4()),
        )
        new_task = Task(
            id=task_id,
            contextId=context_id,
            request=original_request,
            status=TaskStatus(state=TaskState.submitted),
        )
        await self.task_store.save(new_task)

        # 3. Check for security requirements. If the agent is secure and there's
        # no access token in the session, initiate the OAuth flow.
        access_token = state.get("access_token")
        if found_card.security and not access_token:
            logging.info(f"Agent '{agent_name}' requires authentication. Initiating OAuth flow.")
            oauth_response = await self.initiate_oauth_flow(
                agent_name, found_card.security, task_id
            )
            return json.dumps(oauth_response)

        # 4. Get the connection for the target agent.
        state["active_agent"] = agent_name
        remote_connection = self.remote_agent_connections.get(agent_name)
        if not remote_connection:
            return f"Error: Client not available for {agent_name}"

        # 5. Prepare and send the message according to the A2A specification.
        # For new tasks, the `taskId` is omitted from the message, signaling the
        # remote agent that it needs to create a new task.
        message = Message(
            role="user",
            parts=[Part(type="text", text=task)],
            messageId=str(uuid.uuid4()),
            contextId=context_id,
        )
        message_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(message=message),
        )

        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        logging.info(
            f"--- Sending Payload to {agent_name} ---\n{message_request.model_dump_json(indent=2, exclude_none=True)}"
        )

        send_response: SendMessageResponse = await remote_connection.send_message(
            message_request=message_request, headers=headers
        )
        logging.info(
            f"--- Received Send Response from {agent_name} ---\n{send_response.model_dump_json(indent=2, exclude_none=True)}"
        )

        # 6. Process the response. Per the A2A spec, the response to a task-creating
        # message is a Task object. We extract the ID of this remote task and
        # link it to our local task record.
        if not isinstance(
            send_response.root, SendMessageSuccessResponse
        ) or not isinstance(send_response.root.result, Task):
            logging.error("Received a non-successful or non-task response.")
            await self.task_store.task_failed(
                task_id,
                Message(
                    messageId=str(uuid.uuid4()),
                    role="agent",
                    parts=[Part(type="text", text="Failed to send message")],
                ),
            )
            return ""

        remote_task = send_response.root.result
        await self.task_store.set_remote_task_id(task_id, remote_task.id)

        return remote_task.model_dump_json()


async def get_initialized_routing_agent_async(
    tenant_id: str | None = None,
) -> Agent:
    """
    Asynchronously creates and initializes the RoutingAgent for a specific tenant
    by fetching available agent cards from the agent registry service.

    Args:
        tenant_id: The ID of the tenant for which to initialize the agent.

    Returns:
        A fully configured and initialized ADK Agent, or None if initialization fails.
    """
    # Fetch agent cards from the demo agent registry service.
    async with httpx.AsyncClient() as client:
        params = {"tenant_id": tenant_id} if tenant_id else {}
        try:
            response = await client.get("http://localhost:5001/agents", params=params)
            response.raise_for_status()
            agent_cards_data = response.json()
        except (httpx.ConnectError, httpx.HTTPStatusError) as e:
            logging.error(f"Could not connect to Agent Registry at http://localhost:5001. Please ensure it is running. Error: {e}")
            return None

    agent_cards = [ExtendedAgentCard.model_validate(card) for card in agent_cards_data]

    task_store = PersistentTaskStore(db_path="host_agent.db")

    routing_agent_instance = await RoutingAgent.create(
        task_store=task_store, agent_cards=agent_cards, tenant_id=tenant_id
    )
    return routing_agent_instance.create_agent()

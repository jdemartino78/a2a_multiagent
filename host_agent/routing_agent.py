import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard as A2AAgentCard,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class AgentCard(A2AAgentCard):
    tags: dict | None = None

def convert_part(part: Part, tool_context: ToolContext):
    """Convert a part to text. Only text parts are supported."""
    if part.type == "text":
        return part.text

    return f"Unknown type: {part.type}"


def convert_parts(parts: list[Part], tool_context: ToolContext):
    """Convert parts to text."""
    rval = []
    for p in parts:
        rval.append(convert_part(p, tool_context))
    return rval


def create_send_message_payload(
    text: str, task_id: str | None = None, context_id: str | None = None
) -> dict[str, Any]:
    """Helper function to create the payload for sending a task."""
    payload: dict[str, Any] = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": text}],
            "messageId": uuid.uuid4().hex,
        },
    }

    if task_id:
        payload["message"]["taskId"] = task_id

    if context_id:
        payload["message"]["contextId"] = context_id
    return payload


class RoutingAgent:
    """The Routing agent.

    This is the agent responsible for choosing which remote seller agents to send
    tasks to and coordinate their work.
    """

    def __init__(
        self,
        task_callback: TaskUpdateCallback | None = None,
    ):
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        self._base_instruction: str = ""
        self.tenant_id: str | None = None

    async def _async_init_components(
        self,
        agent_cards: list[AgentCard] | None = None,
    ) -> None:
        """Asynchronous part of initialization."""
        if agent_cards:
            for card in agent_cards:
                try:
                    # The URL for the remote agent is in the card itself
                    agent_url = str(card.url)
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=agent_url
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except Exception as e:
                    print(
                        f"ERROR: Failed to initialize connection for {card.name}: {e}"
                    )

        # Populate self.agents using the logic from original __init__ (via list_remote_agents)
        agent_info = []
        for agent_detail_dict in self.list_remote_agents():
            agent_info.append(json.dumps(agent_detail_dict))
        self.agents = "\n".join(agent_info)

    @classmethod
    async def create(
        cls,
        agent_cards: list[AgentCard] | None = None,
        task_callback: TaskUpdateCallback | None = None,
        tenant_id: str | None = None,
    ) -> "RoutingAgent":
        """Create and asynchronously initialize an instance of the RoutingAgent."""
        instance = cls(task_callback)
        instance.tenant_id = tenant_id
        await instance._async_init_components(
            agent_cards=agent_cards
        )
        return instance

    def create_agent(self) -> Agent:
        """Create an instance of the RoutingAgent."""
        return Agent(
            model="gemini-2.5-pro",
            name="Routing_agent",
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            tools=[self.send_message],
            description="This Routing agent orchestrates the decomposition of the user asking for weather forecast or airbnb accommodation",
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        """Generate the root instruction for the RoutingAgent."""
        return f"""
        **Role:** You are an expert Routing Delegator. Your primary function is to accurately delegate user inquiries to the appropriate specialized remote agents based on their advertised skills.

        **Core Directives:**

        * **Current Date:** The current date is Thursday, October 2, 2025.
        * **Skill-based Delegation:** Your primary decision-making criterion for delegation is the `skills` advertised by each agent. You must select the agent whose skills best match the user\'s request.
        * **Task Delegation:** Utilize the `send_message` function to delegate tasks. You must specify the **type** of agent required by using the `agent_type` parameter (e.g., "weather", "horizon", "calendar").
        * **CRITICAL:** You MUST NOT wrap tool calls in `print()` statements. Call the function directly, for example: `send_message(...)`.
        * **Contextual Awareness for Remote Agents:** If a remote agent repeatedly requests user confirmation, assume it lacks access to the         full conversation history. In such cases, enrich the task description with all necessary contextual information relevant to that         specific agent.
        * **Autonomous Agent Engagement:** Never seek user permission before engaging with remote agents. If multiple agents are required to         fulfill a request, connect with them directly without requesting user preference or confirmation.
        * **Transparent Communication:** Always present the complete and detailed response from the remote agent to the user.
        * **User Confirmation Relay:** If a remote agent asks for confirmation, and the user has not already provided it, relay this         confirmation request to the user.

        **Agent Roster:**

        Here are the available agents and their skills:
        {self.agents}
        """

    def before_model_callback(self, callback_context: CallbackContext, llm_request):
        # To reduce log verbosity, we will not be logging the entire request.
        last_message = llm_request.contents[-1].parts[0].text
        logging.info(f"--- Host Agent Prompt ---\n{last_message}")
        state = callback_context.state
        if "session_active" not in state or not state["session_active"]:
            if "session_id" not in state:
                state["session_id"] = str(uuid.uuid4())
            state["session_active"] = True

    def list_remote_agents(self):
        """List the available remote agents you can use to delegate the task."""
        if not self.cards:
            return []

        remote_agent_info = []
        for card in self.cards.values():
            logging.info(
                f"--- Found Agent Card ---\n{card.model_dump_json(indent=2, exclude_none=True)}"
            )
            agent_info = {"name": card.name, "description": card.description}
            if card.skills:
                skills = []
                for skill in card.skills:
                    try:
                        skills.append(skill.model_dump(exclude_none=True))
                    except Exception:
                        skills.append(str(skill))
                agent_info["skills"] = skills
            remote_agent_info.append(agent_info)
        return remote_agent_info

    async def send_message(
        self, agent_type: str, task: str, tool_context: ToolContext
    ):
        """Sends a task to a remote agent based on its type and the session context.

        Args:
            agent_type: The type of agent to send the task to (e.g., "weather", "horizon", "calendar").
            task: The comprehensive task description for the agent.
            tool_context: The tool context this method runs in.

        Yields:
            A dictionary of JSON data.
        """
        logging.info(f"Attempting to send task to agent of type: {agent_type}")
        logging.info(f"Task content: {task}")

        state = tool_context.state
        filter_query = {"type": agent_type}

        tenant_specific_agents = ["horizon"]
        if agent_type in tenant_specific_agents:
            tenant_id = self.tenant_id
            if not tenant_id:
                raise ValueError(f"Tenant ID is required for agent type '{agent_type}' but was not found in session.")
            filter_query["tenant_id"] = tenant_id

        found_card = None
        for card in self.cards.values():
            if not card.skills:
                continue
            for skill in card.skills:
                if not skill.tags:
                    continue

                skill_tags_dict = {}
                for tag in skill.tags:
                    if ":" in tag:
                        key, value = tag.split(":", 1)
                        skill_tags_dict[key] = value

                if filter_query.items() <= skill_tags_dict.items():
                    found_card = card
                    break
            if found_card:
                break

        if not found_card:
            raise ValueError(f"Could not find a registered agent matching the query: {filter_query}")

        agent_name = found_card.name
        logging.info(f"Found matching agent '{agent_name}' for query {filter_query}")

        state["active_agent"] = agent_name
        client = self.remote_agent_connections.get(agent_name)

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        context_id = state.get("context_id") or str(uuid.uuid4())
        state["context_id"] = context_id

        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
                "contextId": context_id,
            },
        }

        logging.info(
            f"--- Sending Payload to {agent_name} ---\n{json.dumps(payload, indent=2)}"
        )

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )
        send_response: SendMessageResponse = await client.send_message(
            message_request=message_request
        )
        logging.info(
            f"--- Received Send Response from {agent_name} ---\n{send_response.model_dump_json(indent=2, exclude_none=True)}"
        )

        if not isinstance(send_response.root, SendMessageSuccessResponse) or not isinstance(send_response.root.result, Task):
            logging.error("Received a non-successful or non-task response.")
            return None

        logging.info(
            f"--- Returning Task from {agent_name} ---\n{send_response.root.result.model_dump_json(indent=2, exclude_none=True)}"
        )
        return send_response.root.result


async def get_initialized_routing_agent_async(tenant_id: str | None = None) -> Agent:
    """Asynchronously creates and initializes the RoutingAgent for a specific tenant."""
    # Load all agent cards from the registry file
    registry_path = os.path.join(os.path.dirname(__file__), 'agent_registry.json')
    with open(registry_path, 'r') as f:
        all_cards_data = json.load(f)

    # Filter the cards based on the tenant_id
    filtered_cards_data = []
    for card_data in all_cards_data:
        is_tenant_specific = False
        card_tenant_id = None

        if card_data.get("skills"):
            for skill in card_data["skills"]:
                if skill.get("tags"):
                    for tag in skill["tags"]:
                        if tag.startswith("tenant_id:"):
                            is_tenant_specific = True
                            card_tenant_id = tag.split(":", 1)[1]
                            break
                if is_tenant_specific:
                    break
        
        # Include the card if it's not tenant-specific, or if it matches the current tenant
        if not is_tenant_specific or (is_tenant_specific and card_tenant_id == tenant_id):
            filtered_cards_data.append(card_data)

    agent_cards = [AgentCard.model_validate(card) for card in filtered_cards_data]

    routing_agent_instance = await RoutingAgent.create(
        agent_cards=agent_cards, tenant_id=tenant_id
    )
    return routing_agent_instance.create_agent()

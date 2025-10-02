import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
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
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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

    async def _async_init_components(
        self,
        remote_agent_addresses: list[str] | None = None,
        remote_agent_base_urls: list[str] | None = None,
    ) -> None:
        """Asynchronous part of initialization."""
        if remote_agent_base_urls:
            async with httpx.AsyncClient(timeout=30) as client:
                for base_url in remote_agent_base_urls:
                    well_known_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
                    try:
                        response = await client.get(well_known_url)
                        response.raise_for_status()
                        card = AgentCard.model_validate(response.json())

                        remote_connection = RemoteAgentConnections(
                            agent_card=card, agent_url=base_url
                        )
                        self.remote_agent_connections[card.name] = remote_connection
                        self.cards[card.name] = card
                    except httpx.RequestError as e:
                        print(
                            f"ERROR: Failed to get agent card from {well_known_url}: {e}"
                        )
                    except Exception as e:
                        print(
                            f"ERROR: Failed to initialize connection for {base_url}: {e}"
                        )

        if remote_agent_addresses:
            # Use a single httpx.AsyncClient for all card resolutions for efficiency
            async with httpx.AsyncClient(timeout=30) as client:
                for address in remote_agent_addresses:
                    card_resolver = A2ACardResolver(
                        client, address
                    )  # Constructor is sync
                    try:
                        card = (
                            await card_resolver.get_agent_card()
                        )  # get_agent_card is async

                        remote_connection = RemoteAgentConnections(
                            agent_card=card, agent_url=address
                        )
                        self.remote_agent_connections[card.name] = remote_connection
                        self.cards[card.name] = card
                    except httpx.ConnectError as e:
                        print(f"ERROR: Failed to get agent card from {address}: {e}")
                    except Exception as e:  # Catch other potential errors
                        print(
                            f"ERROR: Failed to initialize connection for {address}: {e}"
                        )

        # Populate self.agents using the logic from original __init__ (via list_remote_agents)
        agent_info = []
        for agent_detail_dict in self.list_remote_agents():
            agent_info.append(json.dumps(agent_detail_dict))
        self.agents = "\n".join(agent_info)

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: list[str] | None = None,
        remote_agent_base_urls: list[str] | None = None,
        task_callback: TaskUpdateCallback | None = None,
    ) -> "RoutingAgent":
        """Create and asynchronously initialize an instance of the RoutingAgent."""
        instance = cls(task_callback)
        await instance._async_init_components(
            remote_agent_addresses, remote_agent_base_urls
        )
        return instance

    def create_agent(self) -> Agent:
        """Create an instance of the RoutingAgent."""
        return LlmAgent(
            model="gemini-2.5-pro",
            name="Routing_agent",
            static_instruction=self.static_instruction,
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            tools=[self.send_message],
            description="This Routing agent orchestrates the decomposition of the user asking for weather forecast or airbnb accommodation",
        )

    @property
    def static_instruction(self):
        return f"""
        **Role:** You are an expert Routing Delegator. Your primary function is to accurately delegate user inquiries to the appropriate specialized remote agents based on their advertised skills.

        **Core Directives:**

        * **Current Date:** The current date is Thursday, October 2, 2025.
        * **Skill-based Delegation:** Your primary decision-making criterion for delegation is the `skills` advertised by each agent. You must select the agent whose skills best match the user's request.
        * **Task Delegation:** Utilize the `send_message` function to assign actionable tasks to remote agents.
        * **CRITICAL:** You MUST NOT wrap tool calls in `print()` statements. Call the function directly, for example: `send_message(...)`.
        * **Contextual Awareness for Remote Agents:** If a remote agent repeatedly requests user confirmation, assume it lacks access to the         full conversation history. In such cases, enrich the task description with all necessary contextual information relevant to that         specific agent.
        * **Autonomous Agent Engagement:** Never seek user permission before engaging with remote agents. If multiple agents are required to         fulfill a request, connect with them directly without requesting user preference or confirmation.
        * **Transparent Communication:** Always present the complete and detailed response from the remote agent to the user.
        * **User Confirmation Relay:** If a remote agent asks for confirmation, and the user has not already provided it, relay this         confirmation request to the user.
        * **Focused Information Sharing:** Provide remote agents with only relevant contextual information. Avoid extraneous details.
        * **No Redundant Confirmations:** Do not ask remote agents for confirmation of information or actions.
        * **Tool Reliance:** Strictly rely on available tools to address user requests. Do not generate responses based on assumptions. If         information is insufficient, request clarification from the user.
        * **Prioritize Recent Interaction:** Focus primarily on the most recent parts of the conversation when processing requests.
        * **Active Agent Prioritization:** If an active agent is already engaged, route subsequent related requests to that agent using the         appropriate task update tool.

        **Agent Roster:**

        Here are the available agents and their skills:
        {self.agents}
        """

    def root_instruction(self, context: ReadonlyContext) -> str:
        """Generate the root instruction for the RoutingAgent."""
        current_agent = self.check_active_agent(context)
        return f"""
        * Currently Active Seller Agent: `{current_agent['active_agent']}`

        Based on the user query and the agents' skills, you have two options:
        1. If the user is asking a general question, or you can answer it directly, provide a direct response.
        2. If the user's query requires the expertise of a specialized agent, you MUST use the `send_message` tool to delegate the task to the most appropriate agent based on their skills.

        The `task` parameter in the `send_message` tool should be a clear and complete description of what the user wants, including all relevant information from the conversation.
        """

    def check_active_agent(self, context: ReadonlyContext):
        state = context.state
        if (
            "session_id" in state
            and "session_active" in state
            and state["session_active"]
            and "active_agent" in state
        ):
            return {"active_agent": f"{state['active_agent']}"}
        return {"active_agent": "None"}

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
                    # Assuming skill is a Pydantic model with name and description
                    try:
                        skills.append(skill.model_dump(exclude_none=True))
                    except Exception:
                        # If skill is not a model, it might be a dict or a string
                        skills.append(str(skill))
                agent_info["skills"] = skills
            remote_agent_info.append(agent_info)
        return remote_agent_info

    async def send_message(
        self, agent_name: str, task: str, tool_context: ToolContext
    ):
        """Sends a task to remote seller agent.

        This will send a message to the remote agent named agent_name.

        Args:
            agent_name: The name of the agent to send the task to.
            task: The comprehensive conversation context summary
                and goal to be achieved regarding user inquiry and purchase request.
            tool_context: The tool context this method runs in.

        Yields:
            A dictionary of JSON data.
        """
        logging.info(f"Sending task to agent: {agent_name}")
        logging.info(f"Task content: {task}")
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        state = tool_context.state
        state["active_agent"] = agent_name
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        context_id = state.get("context_id") or str(uuid.uuid4())
        state["context_id"] = context_id
        logging.info(f"Using context_id: {context_id}")

        message_id = ""
        metadata = {}
        if "input_message_metadata" in state:
            metadata.update(**state["input_message_metadata"])
            if "message_id" in state["input_message_metadata"]:
                message_id = state["input_message_metadata"]["message_id"]
        if not message_id:
            message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {"type": "text", "text": task}
                ],  # Use the 'task' argument here
                "messageId": message_id,
            },
        }

        if context_id:
            payload["message"]["contextId"] = context_id

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

        if not isinstance(send_response.root, SendMessageSuccessResponse):
            logging.error("received non-success response. Aborting get task ")
            return None

        if not isinstance(send_response.root.result, Task):
            logging.error("received non-task response. Aborting get task ")
            return None

        new_task_id = send_response.root.result.id
        if new_task_id:
            logging.info(f"Received new task_id: {new_task_id}")

        if send_response.root.result:
            logging.info(
                f"--- Returning Task from {agent_name} ---\n{send_response.root.result.model_dump_json(indent=2, exclude_none=True)}"
            )
        return send_response.root.result


def _get_initialized_routing_agent_sync() -> Agent:
    """Synchronously creates and initializes the RoutingAgent."""

    async def _async_main() -> Agent:
        routing_agent_instance = await RoutingAgent.create(
            remote_agent_base_urls=[
                os.getenv("AIR_AGENT_URL", "http://localhost:10002"),
                os.getenv("WEA_AGENT_URL", "http://localhost:10001"),
                os.getenv("CAL_AGENT_URL", "http://localhost:10007"),
            ]
        )
        return routing_agent_instance.create_agent()

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            print(
                f"Warning: Could not initialize RoutingAgent with asyncio.run(): {e}. "
                "This can happen if an event loop is already running (e.g., in Jupyter). "
                "Consider initializing RoutingAgent within an async function in your application."
            )
        raise


root_agent = _get_initialized_routing_agent_sync()

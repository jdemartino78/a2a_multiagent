# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os

import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .adk_agent_executor import ADKAgentExecutor
from .horizon_agent import root_agent

load_dotenv()

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"


def main():
    """Command Line Interface to start the Horizon Agent server."""
    parser = argparse.ArgumentParser(description="Start the Horizon Agent server.")
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="Hostname to bind the server to."
    )
    parser.add_argument(
        "--port", default=DEFAULT_PORT, type=int, help="Port to bind the server to."
    )
    parser.add_argument(
        "--log-level", default=DEFAULT_LOG_LEVEL, help="Uvicorn log level."
    )
    args = parser.parse_args()

    skill = AgentSkill(
        id="get_order_status",
        name="Get Order Status",
        description="Gets the status of a specific order.",
        tags=["orders"],
        examples=["What is the status of my order 123?"],
    )

    app_url = os.environ.get("APP_URL", f"http://{args.host}:{args.port}")

    agent_card = AgentCard(
        name="Horizon Agent",
        description="Agent that can check order status for the Horizon tenant.",
        url=app_url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    runner = Runner(
        app_name=agent_card.name,
        agent=root_agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    agent_executor = ADKAgentExecutor(runner, agent_card)

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    a2a_server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    asgi_app = a2a_server.build()

    uvicorn.run(
        app=asgi_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
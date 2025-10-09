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
    AuthorizationCodeOAuthFlow,
    OAuth2SecurityScheme,
    OAuthFlows,
)
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .weather_agent import create_weather_agent
from .weather_executor import WeatherExecutor

load_dotenv()

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 10001
DEFAULT_LOG_LEVEL = "info"


def main():
    parser = argparse.ArgumentParser(description="Start the Weather Agent server.")
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
        id="get_weather",
        name="Get Weather",
        description="Provides the weather forecast for a given city.",
        tags=["type:weather"],
        examples=["what is the weather in London?", "weather in Paris"],
    )

    app_url = os.environ.get("APP_URL", f"http://localhost:{args.port}")
    idp_url = os.environ.get("IDP_URL", "http://localhost:5000")

    oauth_scheme = OAuth2SecurityScheme(
        flows=OAuthFlows(
            authorizationCode=AuthorizationCodeOAuthFlow(
                authorizationUrl=f"{idp_url}/authorize",
                tokenUrl=f"{idp_url}/generate-token",
                scopes={
                    "openid": "OpenID Connect scope.",
                    "profile": "Read user profile.",
                    "email": "Read user email.",
                    "api:read": "Read API access.",
                },
            )
        )
    )

    agent_card = AgentCard(
        name="Weather Agent",
        description="Provides weather forecasts.",
        url=app_url,
        version="1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
        securitySchemes={"oauth2": oauth_scheme},
    )

    runner = Runner(
        app_name=agent_card.name,
        agent=create_weather_agent(),
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    agent_executor = WeatherExecutor(runner, agent_card)

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

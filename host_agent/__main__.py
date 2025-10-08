import argparse
import asyncio
import json
import sys
import traceback  # Import the traceback module
from collections.abc import AsyncIterator
from pprint import pformat

import gradio as gr
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from . import routing_agent

APP_NAME = "routing_app"
USER_ID = "default_user"
SESSION_ID = "default_session"

SESSION_SERVICE = InMemorySessionService()
GLOBAL_TENANT_ID = None  # Use a global for the static tenant ID
LAST_USER_MESSAGE = None


async def get_response_from_agent(
    message: str,
    history: list[gr.ChatMessage],
) -> AsyncIterator[gr.ChatMessage]:
    """Get response from host agent."""
    global LAST_USER_MESSAGE

    try:
        # Use the global tenant_id set at startup
        tenant_agent = await routing_agent.get_initialized_routing_agent_async(
            tenant_id=GLOBAL_TENANT_ID
        )
        tenant_runner = Runner(
            agent=tenant_agent,
            app_name=APP_NAME,
            session_service=SESSION_SERVICE,
        )

        if message.lower() == "done" and LAST_USER_MESSAGE:
            new_message_content = types.Content(
                role="user", parts=[types.Part(text=LAST_USER_MESSAGE)]
            )
            LAST_USER_MESSAGE = None
        else:
            new_message_content = types.Content(
                role="user", parts=[types.Part(text=message)]
            )

        event_iterator: AsyncIterator[Event] = tenant_runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=new_message_content,
        )

        async for event in event_iterator:
            print(f"--- Event ---\n{event}")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        formatted_call = f"""python
{pformat(part.function_call.model_dump(exclude_none=True), indent=2, width=80)}
"""
                        yield gr.ChatMessage(
                            role="assistant",
                            content=f"**Tool Call: {part.function_call.name}**\n{formatted_call}",
                        )
                    elif part.function_response:
                        response_content = part.function_response.response
                        if (
                            isinstance(response_content, dict)
                            and "response" in response_content
                        ):
                            formatted_response_data = response_content["response"]
                        else:
                            formatted_response_data = response_content
                        formatted_response = f"""json
{pformat(formatted_response_data, indent=2, width=80)}
"""
                        yield gr.ChatMessage(
                            role="assistant",
                            content=f"**Tool Response from {part.function_response.name}**\n{formatted_response}",
                        )

            if event.actions and event.actions.requested_auth_configs:
                LAST_USER_MESSAGE = message
                yield gr.ChatMessage(
                    role="assistant",
                    content="Authorization is required. Please complete the authorization and then type 'done' to continue.",
                )
                return

            if event.is_final_response():
                final_response_text = ""
                if event.content and event.content.parts:
                    final_response_text = "".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif event.actions and event.actions.escalate:
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"

                if final_response_text:
                    yield gr.ChatMessage(
                        role="assistant", content=final_response_text
                    )

    except Exception as e:
        print(f"Error in get_response_from_agent (Type: {type(e)}): {e}")
        traceback.print_exc()  # This will print the full traceback
        yield gr.ChatMessage(
            role="assistant",
            content="An error occurred while processing your request. Please check the server logs for details.",
        )


async def main():
    """Main gradio app."""
    global GLOBAL_TENANT_ID

    parser = argparse.ArgumentParser(description="A2A Host Agent")
    parser.add_argument(
        "--port", type=int, default=8083, help="Port to run the Gradio interface on"
    )
    parser.add_argument(
        "--tenant-id", type=str, help="The tenant ID to use for the session"
    )
    args = parser.parse_args()

    port = args.port
    GLOBAL_TENANT_ID = args.tenant_id

    print("Creating ADK session...")
    await SESSION_SERVICE.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    if GLOBAL_TENANT_ID:
        print(f"Session configured for tenant: {GLOBAL_TENANT_ID}")

    print("ADK session created successfully.")

    with gr.Blocks(theme=gr.themes.Ocean(), title="A2A Host Agent with Logo") as demo:
        gr.Image(
            "https://a2a-protocol.org/latest/assets/a2a-logo-black.svg",
            width=100,
            height=100,
            scale=0,
            show_label=False,
            show_download_button=False,
            container=False,
            show_fullscreen_button=False,
        )
        gr.ChatInterface(
            get_response_from_agent,
            title="A2A Host Agent",
            description="This assistant can help you to check weather and find airbnb accommodation",
        )

    print(f"Launching Gradio interface on port {port}...")
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=port,
    )
    print("Gradio application has been shut down.")


if __name__ == "__main__":
    asyncio.run(main())

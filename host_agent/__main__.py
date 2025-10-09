import argparse
import asyncio
import traceback
from collections.abc import AsyncIterator
from pprint import pformat
import json
import uuid

import gradio as gr
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from a2a.types import Task, TaskState

from . import routing_agent
from .persistent_task_store import PersistentTaskStore

APP_NAME = "routing_app"
USER_ID = "default_user"
SESSION_ID = "default_session"

DB_PATH = "host_agent.db"
SESSION_SERVICE = DatabaseSessionService(db_url=f"sqlite:///{DB_PATH}")
TASK_STORE = PersistentTaskStore(db_path=DB_PATH)
GLOBAL_TENANT_ID = None

# Create a single FastAPI app to host both Gradio and the callback endpoint.
app = FastAPI()


@app.get("/callback")
async def handle_callback(request: Request):
    """Handles the OAuth 2.0 callback."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return "Error: Missing code or state.", 400

    try:
        state_data = json.loads(state)
        task_id = state_data.get("task_id")
    except (json.JSONDecodeError, AttributeError):
        return "Error: Invalid state format.", 400

    if not task_id:
        return "Error: task_id not in state.", 400

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "http://localhost:5000/generate-token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:8083/callback",
                "client_id": "Horizon Agent - Tenant ABC",
                "client_secret": "horizon_secret_abc",
            },
        )

    if token_response.status_code != 200:
        return f"Error exchanging code for token: {token_response.text}", 400

    token_data = token_response.json()
    access_token = token_data.get("access_token")

    # Store the access token in the session state via an event
    session = await SESSION_SERVICE.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    auth_event = Event(
        id=str(uuid.uuid4()),
        invocation_id=str(uuid.uuid4()),
        author="system",
        actions=EventActions(state_delta={"access_token": access_token}),
    )
    await SESSION_SERVICE.append_event(session, auth_event)

    # Update the task status
    task = await TASK_STORE.get(task_id)
    if task:
        task.status.state = TaskState.working
        await TASK_STORE.save(task)

    return RedirectResponse(url="http://localhost:8083/")


@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    """Endpoint for the frontend to poll the task status."""
    task = await TASK_STORE.get_task(task_id)
    if not task:
        return JSONResponse(content={"error": "Task not found"}, status_code=404)
    return JSONResponse(content={"status": task.status.state.value})


async def get_response_from_agent(
    message: str,
    history: list[gr.ChatMessage],
) -> AsyncIterator[gr.ChatMessage]:
    """Get response from host agent."""
    try:
        tenant_agent = await routing_agent.get_initialized_routing_agent_async(
            tenant_id=GLOBAL_TENANT_ID
        )
        tenant_runner = Runner(
            agent=tenant_agent,
            app_name=APP_NAME,
            session_service=SESSION_SERVICE,
        )

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
                            and "redirect_url" in response_content
                        ):
                            redirect_url = response_content["redirect_url"]
                            task_id = response_content.get("task_id")
                            # This is where we need to trigger the polling on the frontend
                            yield gr.ChatMessage(
                                role="assistant",
                                content=f"Please authenticate to continue. [Follow this link]({redirect_url}). I will wait for you to complete the process.",
                                metadata={"task_id": task_id} # Pass task_id to frontend
                            )
                            return

                        if isinstance(response_content, Task):
                            task_id = response_content.id
                            yield gr.ChatMessage(
                                role="assistant",
                                content="I have started working on your request. I will let you know when I'm done.",
                                metadata={"task_id": task_id} # Pass task_id to frontend
                            )
                            return

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
        traceback.print_exc()
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

    print("Initializing ADK session...")
    session = await SESSION_SERVICE.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    if session is None:
        print("No existing session found. Creating a new one...")
        session = await SESSION_SERVICE.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
    else:
        print("Found existing session.")

    if GLOBAL_TENANT_ID:
        # Use an event to set/update the tenant_id in the session state
        tenant_event = Event(
            id=str(uuid.uuid4()),
            invocation_id=str(uuid.uuid4()),
            author="system",
            actions=EventActions(state_delta={"tenant_id": GLOBAL_TENANT_ID}),
        )
        await SESSION_SERVICE.append_event(session, tenant_event)
        print(f"Session configured for tenant: {GLOBAL_TENANT_ID}")

    print("ADK session initialized successfully.")

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
        chatbot = gr.Chatbot()
        chat_interface = gr.ChatInterface(
            get_response_from_agent,
            chatbot=chatbot,
            title="A2A Host Agent",
            description="This assistant can help you to check weather and find airbnb accommodation",
        )

        # Custom JavaScript for polling
        demo.load(
            None,
            None,
            js="""
            () => {
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.addedNodes.length) {
                            const lastMessage = chatbot.querySelector('.message-row:last-child');
                            if (lastMessage) {
                                const metadataElem = lastMessage.querySelector('[data-testid="bot"] .metadata');
                                if (metadataElem) {
                                    try {
                                        const metadata = JSON.parse(metadataElem.textContent);
                                        if (metadata.task_id) {
                                            pollTaskStatus(metadata.task_id);
                                        }
                                    } catch (e) {
                                        console.error('Error parsing metadata:', e);
                                    }
                                }
                            }
                        }
                    });
                });

                const chatbot = document.querySelector('#chatbot');
                if (chatbot) {
                    observer.observe(chatbot, { childList: true, subtree: true });
                }


                function pollTaskStatus(taskId) {
                    const interval = setInterval(async () => {
                        try {
                            const response = await fetch(`/task_status/${taskId}`);
                            if (response.ok) {
                                const data = await response.json();
                                if (data.status === 'working') {
                                    clearInterval(interval);
                                    // How to re-trigger the agent is the next challenge.
                                    // For now, we can just alert the user.
                                    alert('Authentication complete! Please re-enter your request.');
                                }
                            } else {
                                clearInterval(interval);
                            }
                        } catch (error) {
                            console.error('Polling error:', error);
                            clearInterval(interval);
                        }
                    }, 3000); // Poll every 3 seconds
                }
            }
            """
        )


    # Mount the Gradio app onto the FastAPI app
    gr.mount_gradio_app(app, demo, path="/")

    # Run the combined app with uvicorn
    print(f"Launching Gradio interface on port {port}...")
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()
    print("Gradio application has been shut down.")


if __name__ == "__main__":
    asyncio.run(main())

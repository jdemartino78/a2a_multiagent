# spec.md

(Sections 1 and 2 - No changes)

## 3. Security Model & Authentication Flow

End-to-end security is provided by OAuth 2.0, with session state managed by a persistent `DatabaseSessionService`. The asynchronous authentication flow is managed using the A2A Task Lifecycle.

### 3.1. Authentication Flow

1.  A user interacts with the `host_agent`'s Gradio UI.
2.  The `host_agent`'s LLM routes the request to the secure `horizon_agent`.
3.  The `send_message` tool checks the session state for an `access_token`.
4.  If no token is found, it initiates the OAuth 2.0 flow:
    a.  It creates a long-running A2A **Task** to represent the user's original request.
    b.  It returns a `redirect_url` to the user, pointing to the IDP.
5.  The user authenticates via the IDP and is redirected to the `host_agent`'s `/callback` endpoint.
6.  The `/callback` endpoint exchanges the authorization code for an `access_token` and writes it to the session state in the SQLite database.
7.  The user returns to the UI and sends a message (e.g., "done") to notify the agent that authentication is complete.
8.  The `host_agent` receives the new message and re-attempts the original task.
9.  The `send_message` tool, executing again, now finds the `access_token` in the session state.
10. It adds the token to an `Authorization` header and successfully calls the `horizon_agent`.

### 3.2. A2A Task Lifecycle for Asynchronous Operations

The system uses a stateful, persistent task management flow to handle long-running asynchronous operations like user authentication.

-   A `PersistentTaskStore`, backed by a SQLite database, is used to save and retrieve the state of every user request (`Task`).
-   When a secure agent requires authentication, the original task is saved with a `submitted` status.
-   After the user completes the OAuth 2.0 flow, the `/callback` endpoint retrieves the original task, updates its status to `working`, and saves the user's access token to the persistent session.
-   This robust, stateful mechanism allows the agent to seamlessly resume the user's original request without losing context.

### 3.3. Task Delegation and Linking

When the `host_agent` delegates a task to a downstream agent, it follows the A2A specification for task creation to ensure a robust, distributed system.

1.  **Local Task Creation**: The `host_agent` first creates a `Task` in its own `PersistentTaskStore`. This task represents the user's original request to the host.
2.  **Message without Task ID**: The `host_agent` sends a `message:send` request to the downstream agent. Crucially, this message **does not** contain a `taskId`.
3.  **Remote Task Creation**: The downstream agent receives this request and, per the A2A specification, creates a *new* task in its own task store.
4.  **Response with Task Object**: The downstream agent's immediate response to the `message:send` request is a `Task` object containing the `id` of the newly created remote task.
5.  **Linking**: The `host_agent` receives this response, extracts the `remote_task_id`, and updates its original, local `Task` record with this new ID. This creates a durable link between the parent task in the host and the child task in the downstream agent.

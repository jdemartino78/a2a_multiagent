# Calendar Agent

This agent helps with checking a user's availability using their Google Calendar. It is a remote agent that can be used by other agents.

## Getting started

1.  Create a `.env` file using the `.env.example` file as a template. This file should contain the necessary environment variables, such as your `GOOGLE_API_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`.

2.  Start the server from the root of the project:

    ```bash
    python3 -m calendar_agent --port 10007
    ```

    The agent will be available at `http://localhost:10007`.
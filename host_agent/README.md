# Host Agent

This agent acts as a user-facing interface, allowing users to interact with other agents to get information about weather and Airbnb accommodations.

## Getting started

1.  Create a `.env` file using the `example.env` file as a template. This file should contain the necessary environment variables, such as your `GOOGLE_API_KEY`.

2.  Start the server from the root of the project:

    ```bash
    python3 -m host_agent
    ```

    The agent will be available at `http://localhost:8083`.
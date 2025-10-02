# Weather Agent

This agent provides weather information for a given location. It is a remote agent that can be used by other agents.

## Getting started

1.  Create a `.env` file using the `example.env` file as a template. This file should contain the necessary environment variables, such as your `GOOGLE_API_KEY`.

2.  Start the server from the root of the project:

    ```bash
    python3 -m weather_agent --port 10001
    ```

    The agent will be available at `http://localhost:10001`.
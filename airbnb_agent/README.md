# Airbnb Agent

This agent helps with searching for Airbnb accommodations. It is a remote agent that can be used by other agents.

## Getting started

1.  Create a `.env` file using the `example.env` file as a template. This file should contain the necessary environment variables, such as your `GOOGLE_API_KEY`.

2.  Start the server from the root of the project:

    ```bash
    python3 -m airbnb_agent --port 10002
    ```

    The agent will be available at `http://localhost:10002`.

## Disclaimer

Important: The sample code provided is for demonstration purposes and illustrates the mechanics of the Agent-to-Agent (A2A) protocol. When building production applications, it is critical to treat any agent operating outside of your direct control as a potentially untrusted entity.

All data received from an external agent—including but not limited to its AgentCard, messages, artifacts, and task statuses—should be handled as untrusted input. For example, a malicious agent could provide an AgentCard containing crafted data in its fields (e.g., description, name, skills.description). If this data is used without sanitization to construct prompts for a Large Language Model (LLM), it could expose your application to prompt injection attacks. Failure to properly validate and sanitize this data before use can introduce security vulnerabilities into your application.

Developers are responsible for implementing appropriate security measures, such as input validation and secure handling of credentials to protect their systems and users.
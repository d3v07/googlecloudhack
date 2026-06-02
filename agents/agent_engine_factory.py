"""Factory for the Agent Engine ADK app."""

import os

from agents.agent import root_agent

APP_NAME = "gcrah_dbre_agent"


def build_adk_app(project: str | None = None, location: str | None = None):
    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=project or os.environ.get("GOOGLE_CLOUD_PROJECT", "local-ci"),
        location=location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    return agent_engines.AdkApp(agent=root_agent, app_name=APP_NAME)

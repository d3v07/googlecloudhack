"""Factory for the Agent Engine ADK app."""

import os

from agents.agent import AgentRole, build_agent

APP_NAME = "gcrah_dbre_agent"


def build_adk_app(
    project: str | None = None,
    location: str | None = None,
    role: AgentRole | str = AgentRole.FULL,
):
    import vertexai
    from vertexai import agent_engines

    role = AgentRole(role)
    vertexai.init(
        project=project
        or os.environ.get("GCRAH_AGENT_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT", "local-ci"),
        location=location
        or os.environ.get("GCRAH_AGENT_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    return agent_engines.AdkApp(agent=build_agent(role=role), app_name=f"{APP_NAME}_{role.value}")

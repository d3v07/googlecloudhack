"""Agent Engine source-deploy entrypoint for the DBRE ADK app."""

from agents.agent_engine_factory import build_adk_app


adk_app = build_adk_app()

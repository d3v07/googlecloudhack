"""Build the DBRE ADK agent: Python-native Mongo diagnosis tools plus the deterministic
ESR tool, under a phase gate. Model and connection come from the environment only.
"""

import os
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.gating import make_gate
from agents.native_mongo_tools import (
    compare_candidate_indexes,
    diagnose_candidate,
    explain_slow_query,
    rationalize_recommendation,
)
from agents.tools import diagnose_index
from controller.explain import get_connection_string
from controller.phases import Phase

# dev/CI default stays cheap; the demo runs gemini-3-flash-preview at location=global
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


class AgentRole(StrEnum):
    FULL = "full"
    DIAGNOSE = "diagnose"
    CANDIDATE = "candidate"
    RATIONALE = "rationale"


INSTRUCTIONS = {
    AgentRole.FULL: (
        "You are a MongoDB performance engineer. Use the native Mongo tools to read the "
        "slow query, compare candidates, diagnose the ESR-correct index, and explain the "
        "rationale. Return compact JSON with evidence, candidates, experiments, "
        "recommended_index, and rationale. Never create or drop an index during diagnosis."
    ),
    AgentRole.DIAGNOSE: (
        "You are the Diagnose Agent. Run explain_slow_query and diagnose_candidate. "
        "Return compact JSON with before evidence, diagnosis, and recommended_index. "
        "Never create or drop an index."
    ),
    AgentRole.CANDIDATE: (
        "You are the Candidate Agent. Run compare_candidate_indexes. Return compact JSON "
        "with candidate metrics and the winner. Never create or drop an index."
    ),
    AgentRole.RATIONALE: (
        "You are the Rationale Agent. Run rationalize_recommendation. Return compact JSON "
        "with recommended_index and rationale grounded in evidence. Never create or drop an index."
    ),
}

NATIVE_TOOL_FUNCTIONS = (
    explain_slow_query,
    compare_candidate_indexes,
    diagnose_candidate,
    rationalize_recommendation,
)

ROLE_TOOL_FUNCTIONS = {
    AgentRole.FULL: (*NATIVE_TOOL_FUNCTIONS, diagnose_index),
    AgentRole.DIAGNOSE: (explain_slow_query, diagnose_candidate),
    AgentRole.CANDIDATE: (compare_candidate_indexes,),
    AgentRole.RATIONALE: (rationalize_recommendation,),
}


def build_mcp_toolset(
    connection_string: str | None = None,
):  # pragma: no cover - live MCP (npx + mcp pkg)
    """Wire the published MongoDB MCP server over stdio. Imports are local so this
    module stays importable without the `mcp` package installed (CI)."""
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
    from mcp import StdioServerParameters

    conn = connection_string or get_connection_string()
    server_env = {**os.environ}
    if conn:
        server_env["MDB_MCP_CONNECTION_STRING"] = conn
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx", args=["-y", "mongodb-mcp-server"], env=server_env
            ),
            timeout=90,
        )
    )


def build_agent(
    phase: Phase = Phase.DIAGNOSE,
    extra_tools: Sequence[Any] = (),
    role: AgentRole | str = AgentRole.FULL,
) -> Agent:
    role = AgentRole(role)
    tools: list[Any] = [*(FunctionTool(tool) for tool in ROLE_TOOL_FUNCTIONS[role]), *extra_tools]
    return Agent(
        name=f"dbre_{role.value}_agent",
        model=MODEL,
        tools=tools,
        instruction=INSTRUCTIONS[role],
        before_tool_callback=make_gate(phase),
    )


root_agent = build_agent()

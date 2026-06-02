"""Build the DBRE ADK agent: the deterministic diagnosis tool + the MongoDB MCP
toolset, under a phase gate. Model and connection come from the environment only.
"""

import os
from collections.abc import Sequence
from typing import Any

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from agents.gating import make_gate
from agents.tools import diagnose_index
from controller.explain import get_connection_string
from controller.phases import Phase

# dev/CI default stays cheap; the demo runs gemini-3-flash-preview at location=global
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

INSTRUCTION = (
    "You are a MongoDB performance engineer. Read query plans with the explain tool, "
    "call diagnose_index to find the ESR-correct index, and recommend it. Never create "
    "or drop an index outside the verify phase."
)


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


def build_agent(phase: Phase = Phase.DIAGNOSE, extra_tools: Sequence[Any] = ()) -> Agent:
    tools: list[Any] = [FunctionTool(diagnose_index), *extra_tools]
    return Agent(
        name="dbre_agent",
        model=MODEL,
        tools=tools,
        instruction=INSTRUCTION,
        before_tool_callback=make_gate(phase),
    )

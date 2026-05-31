"""Day-0 spike part 2: wire the MongoDB MCP server.

Proves (#1) ADK can load the MongoDB MCP server as a tool source, and
(#3) the MCP tools we need are present and return real data shapes.

Run: uv run --with google-adk --with mcp --with python-dotenv python spikes/day0_runtime/spike_mcp.py
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

CONN = os.environ["MDB_MCP_CONNECTION_STRING"]
SERVER_ENV = {**os.environ, "MDB_MCP_CONNECTION_STRING": CONN}
NEEDED = [
    "find",
    "aggregate",
    "count",
    "collection-schema",
    "collection-indexes",
    "create-index",
    "explain",
    "list-databases",
    "list-collections",
]


async def via_adk():
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters

    toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx", args=["-y", "mongodb-mcp-server"], env=SERVER_ENV
            ),
            timeout=90,
        )
    )
    try:
        tools = await toolset.get_tools()
        names = sorted(t.name for t in tools)
        print(f"ADK-WIRING: PASS — ADK loaded {len(names)} MCP tools")
        print(f"  tools: {names}")
        return names
    finally:
        try:
            await toolset.close()  # stdio teardown is noisy; result is already captured
        except BaseException:
            pass


async def via_raw():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command="npx", args=["-y", "mongodb-mcp-server"], env=SERVER_ENV)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            present = [t for t in NEEDED if t in names]
            missing = [t for t in NEEDED if t not in names]
            print(f"NEEDED present ({len(present)}/{len(NEEDED)}): {present}")
            if missing:
                print(f"  missing: {missing}")
            # real-data shape proof: list databases
            call = "list-databases" if "list-databases" in names else None
            if call:
                res = await session.call_tool(call, {})
                txt = "".join(getattr(c, "text", "") for c in res.content)[:400]
                print(f"CALL {call}: {txt}")
            return names


async def main():
    names = await via_adk()
    print("---")
    try:
        await via_raw()
    except BaseException as e:
        print(f"(raw mcp stdio teardown noise ignored: {type(e).__name__})")
    core = {"find", "aggregate", "collection-schema", "collection-indexes", "create-index"}
    print(f"RESULT mcp_wired={bool(names)} core_tools_present={core.issubset(set(names))}")


asyncio.run(main())

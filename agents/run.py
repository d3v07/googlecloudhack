"""Live scripted driver: fetch a real explain for the #9 fixture query via the MongoDB
MCP server, then run the deterministic diagnosis on it.

Manual / integration — needs the MCP server (npx) and a Mongo connection string.
Run: uv run --with mcp --with python-dotenv python agents/run.py

The parsing + diagnosis logic lives in `agents.tools.diagnosis_from_explain` (unit-tested
offline); this module is only the MCP plumbing that fetches the explain document.
"""

import asyncio
import json
import os

from agents.tools import diagnosis_from_explain
from controller.explain import get_connection_string

DB = "sample_supplies"
COLL = "sales_agent_demo"
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20


async def fetch_explain(connection_string: str) -> dict:  # pragma: no cover - live MCP I/O
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_env = {**os.environ, "MDB_MCP_CONNECTION_STRING": connection_string}
    params = StdioServerParameters(
        command="npx", args=["-y", "mongodb-mcp-server"], env=server_env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "explain",
                {
                    "database": DB,
                    "collection": COLL,
                    "method": [
                        {
                            "name": "find",
                            "arguments": {
                                "filter": QUERY_FILTER,
                                "sort": {"saleDate": -1},
                                "limit": LIMIT,
                            },
                        }
                    ],
                },
            )
            text = "".join(getattr(chunk, "text", "") for chunk in result.content)
            return json.loads(text)


async def run_live() -> dict:  # pragma: no cover - live MCP I/O
    connection_string = get_connection_string()
    if not connection_string:
        raise RuntimeError("no Mongo connection string in env")
    explain = await fetch_explain(connection_string)
    return diagnosis_from_explain(explain, QUERY_FILTER, QUERY_SORT)


def main() -> None:  # pragma: no cover - live entrypoint
    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(asyncio.run(run_live()), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()

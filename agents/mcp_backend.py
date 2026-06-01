"""McpBackend: implements the Backend Protocol via the MongoDB MCP stdio server.

All live MCP I/O methods carry `# pragma: no cover - live MCP I/O` so the
offline unit-test coverage gate stays green without requiring `mcp` installed.
"""

import json
import os
from collections.abc import Sequence
from typing import Any

from controller.explain import walk_stages
from controller.schemas import Evidence, EvidenceMetrics

# re-export for callers that import constants from here
DB = "sample_supplies"
COLL = "sales_agent_demo"


def _parse_explain_to_evidence(
    raw: dict[str, Any],
    query_filter: dict[str, Any],
    query_sort: Sequence[tuple[str, int]],
    limit: int,
) -> Evidence:
    """Build an Evidence from a raw MCP explain result dict."""
    winning = raw["queryPlanner"]["winningPlan"]
    stats = raw["executionStats"]
    metrics = EvidenceMetrics(
        docs_examined=stats["totalDocsExamined"],
        docs_returned=stats["nReturned"],
        millis=float(stats.get("executionTimeMillis", 0)),
        total_keys_examined=stats["totalKeysExamined"],
        stages=tuple(walk_stages(winning)),
    )
    return Evidence(
        query={"filter": dict(query_filter), "sort": list(query_sort), "limit": limit},
        explain_plan=winning,
        metrics=metrics,
    )


class McpBackend:
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    async def explain(  # pragma: no cover - live MCP I/O
        self,
        query_filter: dict[str, Any],
        query_sort: Sequence[tuple[str, int]],
        limit: int,
        hint: str | None = None,
    ) -> Evidence:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        sort_dict = dict(query_sort)
        server_env = {**os.environ, "MDB_MCP_CONNECTION_STRING": self._connection_string}
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
                                    "filter": query_filter,
                                    "sort": sort_dict,
                                    "limit": limit,
                                },
                            }
                        ],
                    },
                )
                text = "".join(getattr(chunk, "text", "") for chunk in result.content)
                raw = json.loads(text)
        return _parse_explain_to_evidence(raw, query_filter, query_sort, limit)

    async def apply_index(self, keys: list[tuple[str, int]], name: str) -> None:  # pragma: no cover - live MCP I/O
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_env = {**os.environ, "MDB_MCP_CONNECTION_STRING": self._connection_string}
        params = StdioServerParameters(
            command="npx", args=["-y", "mongodb-mcp-server"], env=server_env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "create-index",
                    {"database": DB, "collection": COLL, "keys": keys, "name": name},
                )

    async def drop_index(self, name: str) -> None:  # pragma: no cover - live MCP I/O
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_env = {**os.environ, "MDB_MCP_CONNECTION_STRING": self._connection_string}
        params = StdioServerParameters(
            command="npx", args=["-y", "mongodb-mcp-server"], env=server_env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool(
                    "drop-index",
                    {"database": DB, "collection": COLL, "name": name},
                )

    def close(self) -> None:
        pass

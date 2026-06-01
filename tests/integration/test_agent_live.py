"""Live agent path: load the MongoDB MCP toolset and run a real explain through the
deterministic diagnosis. Skips without a Mongo connection string (CI) or the `mcp`
package. Needs npx + the seeded #9 fixture; run after `seed_demo_fixture.py --all`.
"""

import asyncio

import pytest

from controller.explain import get_connection_string

pytestmark = pytest.mark.skipif(
    get_connection_string() is None, reason="no Mongo connection string in env"
)


def test_mcp_toolset_loads_the_tools_we_need():
    pytest.importorskip("mcp")
    from agents.agent import build_mcp_toolset

    toolset = build_mcp_toolset()
    names = {tool.name for tool in asyncio.run(toolset.get_tools())}

    assert {"explain", "create-index"} <= names


def test_scripted_run_diagnoses_from_real_mcp_explain():
    pytest.importorskip("mcp")
    from agents.run import run_live

    diagnosis = asyncio.run(run_live())

    assert diagnosis["recommendation"]["index_spec"] == [
        ["storeLocation", 1],
        ["saleDate", -1],
        ["customer.age", 1],
    ]

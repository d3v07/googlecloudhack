"""Live agent path: drive a real explain through the MongoDB MCP server and run the
deterministic diagnosis. Skips without a Mongo connection string (CI). Needs npx + the
seeded #9 fixture; run after `seed_demo_fixture.py --all`.

`run_live()` uses raw stdio JSON-RPC + `proc.kill()` (no `mcp` ClientSession teardown to
hang), so this test is bounded and cannot hang the suite.
"""

import pytest

from controller.explain import get_connection_string

pytestmark = pytest.mark.skipif(
    get_connection_string() is None, reason="no Mongo connection string in env"
)


def test_scripted_run_diagnoses_from_real_mcp_explain():
    from agents.run import run_live

    diagnosis = run_live()

    assert diagnosis["recommendation"]["index_spec"] == [
        ["storeLocation", 1],
        ["saleDate", -1],
        ["customer.age", 1],
    ]
    assert diagnosis["finding"]["severity"] == "high"

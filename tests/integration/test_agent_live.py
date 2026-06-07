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
    # The agent fetches a real explain via the MongoDB MCP server (raw stdio JSON-RPC,
    # no hang) and recommends the ESR-correct index C. NOTE: the seeded collection has
    # BOTH indexes, so the unhinted optimizer already picks C → the live plan is
    # optimal (severity "low"); the blocking-sort trap delta is proven by the
    # deterministic E2E (test_e2e.py, via pymongo hints) and the #9 golden.
    from pymongo import MongoClient

    from controller.demo_fixture import COLL, DB

    names = set(MongoClient(get_connection_string())[DB][COLL].index_information().keys())
    if "esr_wrong_B" not in names or "esr_right_C" not in names:
        pytest.skip("legacy B/C fixture not seeded (workload baseline active)")

    from agents.run import run_live

    diagnosis = run_live()

    assert diagnosis["recommendation"]["index_spec"] == [
        ["storeLocation", 1],
        ["saleDate", -1],
        ["customer.age", 1],
    ]
    assert diagnosis["finding"]["severity"] in ("low", "high")
    # explain-derived: a real index name from the live winningPlan flowed through
    # (not the "explain" fallback used when no IXSCAN is present)
    assert diagnosis["finding"]["evidence_refs"] != ["explain"]

"""Integration test: live PymongoBackend run_remediation against the seeded fixture.

Skipped when MDB_MCP_CONNECTION_STRING / MONGODB_TARGET_URI is not set.
Assumes the fixture is already seeded (seed/seed_demo_fixture.py --all).
"""

import asyncio

import pytest

from controller.backends import PymongoBackend
from controller.explain import get_connection_string
from controller.orchestrator import INDEX_C_NAME, run_remediation
from controller.pack import pack_evidence_hash
from controller.schemas import EvidencePack, PackStatus

DB = "sample_supplies"
COLL = "sales_agent_demo"
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
NAMESPACE = f"{DB}.{COLL}"

pytestmark = pytest.mark.skipif(
    get_connection_string() is None,
    reason="no MongoDB connection string in environment",
)


def test_live_run_remediation_verified():
    conn = get_connection_string()
    backend = PymongoBackend(conn, DB, COLL)
    try:
        pack = asyncio.run(
            run_remediation(
                backend,
                run_id="integration-test-e2e",
                namespace=NAMESPACE,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                created_at="2026-06-01T00:00:00Z",
            )
        )
    finally:
        backend.close()

    assert pack.status is PackStatus.VERIFIED
    assert pack.after is not None
    assert pack.after.metrics.has_blocking_sort is False
    assert pack.before.metrics.total_keys_examined > pack.after.metrics.total_keys_examined
    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)

    EvidencePack.model_validate(pack.model_dump(mode="python"))


def test_scratch_index_cleaned_up_after_live_run():
    conn = get_connection_string()
    from pymongo import MongoClient

    client = MongoClient(conn)
    backend = PymongoBackend(conn, DB, COLL)
    try:
        asyncio.run(
            run_remediation(
                backend,
                run_id="integration-test-cleanup",
                namespace=NAMESPACE,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                created_at="2026-06-01T00:00:00Z",
            )
        )
    finally:
        backend.close()

    scratch_name = f"{INDEX_C_NAME}__scratch__integration-test-cleanup"
    index_names = list(client[DB][COLL].index_information().keys())
    client.close()
    assert scratch_name not in index_names

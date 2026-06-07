"""Integration test: live two-phase remediation against the seeded fixture.

Skipped when MDB_MCP_CONNECTION_STRING / MONGODB_TARGET_URI is not set.
Assumes the fixture is already seeded (seed/seed_demo_fixture.py --all).
"""

import asyncio

import pytest

from controller.backends import PymongoBackend
from controller.explain import get_connection_string
from controller.orchestrator import apply_and_verify, issue_approval_ticket, run_diagnosis
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


def test_live_two_phase_diagnose_then_approve_verify():
    conn = get_connection_string()
    from pymongo import MongoClient

    client = MongoClient(conn)
    seeded_indexes = set(client[DB][COLL].index_information().keys())
    if "esr_wrong_B" not in seeded_indexes or "esr_right_C" not in seeded_indexes:
        client.close()
        pytest.skip("legacy B/C fixture not seeded (workload baseline active)")

    backend = PymongoBackend(conn, DB, COLL)
    try:
        diagnosed = asyncio.run(
            run_diagnosis(
                backend,
                run_id="integration-test-e2e",
                namespace=NAMESPACE,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                created_at="2026-06-01T00:00:00Z",
            )
        )
        # DIAGNOSE is read-only: a DIAGNOSED pack, no decision, no after, and no mutation
        assert diagnosed.status is PackStatus.DIAGNOSED
        assert diagnosed.decision is None
        assert diagnosed.after is None
        assert diagnosed.before.metrics.has_blocking_sort is True
        assert set(client[DB][COLL].index_information().keys()) == seeded_indexes

        verified = asyncio.run(
            apply_and_verify(
                backend,
                diagnosed,
                issue_approval_ticket(
                    diagnosed,
                    evidence_hash=diagnosed.evidence_hash,
                    approver="integration-test",
                ),
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
            )
        )
    finally:
        backend.close()

    assert verified.status is PackStatus.VERIFIED
    assert verified.after is not None
    assert verified.after.metrics.has_blocking_sort is False
    assert verified.before.metrics.total_keys_examined > verified.after.metrics.total_keys_examined
    # the human-approved hash is unchanged from diagnosis (before + recommendation didn't change)
    assert verified.evidence_hash == diagnosed.evidence_hash
    assert verified.evidence_hash == pack_evidence_hash(verified.before, verified.recommendation)
    EvidencePack.model_validate(verified.model_dump(mode="python"))

    # the recommended index matched the seeded esr_right_C (conflict absorbed) — no junk left
    final_indexes = set(client[DB][COLL].index_information().keys())
    client.close()
    assert final_indexes == seeded_indexes

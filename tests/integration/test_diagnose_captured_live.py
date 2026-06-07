"""Live end-to-end proof of the captured-query remediation pipeline (gated on a real MongoDB
connection). Diagnoses a real ESR-trap query against its natural plan, then applies + verifies
the recommended index — asserting the after-evidence drops the blocking SORT and examines far
fewer docs. Resets the baseline afterward so the demo stays re-runnable.
"""

import asyncio
import os

import pytest

from controller.backends import PymongoBackend
from controller.orchestrator import apply_and_verify, issue_approval_ticket, run_diagnosis
from controller.schemas import PackStatus
from controller.workload import (
    APPLIED_INDEX_PREFIX,
    BASELINE_INDEXES,
    LEGACY_INDEX_NAMES,
    NAMESPACE,
    NAMESPACE_COLL,
    NAMESPACE_DB,
    PRESET_BY_KEY,
    build_query,
)

CONN = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_TARGET_URI")
pytestmark = pytest.mark.skipif(not CONN, reason="no live MongoDB connection configured")


def _reset_baseline(coll) -> None:
    for name in [ix["name"] for ix in coll.list_indexes()]:
        if name in LEGACY_INDEX_NAMES or name.startswith(APPLIED_INDEX_PREFIX):
            coll.drop_index(name)
    for keys, name in BASELINE_INDEXES:
        coll.create_index(keys, name=name)


@pytest.fixture()
def backend():
    from pymongo import MongoClient

    client = MongoClient(CONN)
    _reset_baseline(client[NAMESPACE_DB][NAMESPACE_COLL])
    be = PymongoBackend(CONN, NAMESPACE_DB, NAMESPACE_COLL)
    try:
        yield be
    finally:
        be.close()
        _reset_baseline(client[NAMESPACE_DB][NAMESPACE_COLL])
        client.close()


def test_captured_query_diagnose_apply_verify(backend) -> None:
    query_filter, query_sort, limit = build_query(PRESET_BY_KEY["denver_recent"].spec)

    pack = asyncio.run(
        run_diagnosis(
            backend,
            run_id="live-captured",
            namespace=NAMESPACE,
            query_filter=query_filter,
            query_sort=query_sort,
            limit=limit,
            current_index=None,  # natural plan of the real captured query
        )
    )
    assert pack.status is PackStatus.DIAGNOSED
    assert pack.before.metrics.has_blocking_sort is True
    assert pack.finding.severity.value == "high"
    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )

    ticket = issue_approval_ticket(
        pack, evidence_hash=pack.evidence_hash, approver="DBRE Operator", note=""
    )
    verified = asyncio.run(
        apply_and_verify(
            backend,
            pack,
            approval_ticket=ticket,
            query_filter=query_filter,
            query_sort=query_sort,
            limit=limit,
        )
    )
    assert verified.status is PackStatus.VERIFIED
    assert verified.after is not None
    assert verified.after.metrics.has_blocking_sort is False
    assert verified.after.metrics.docs_examined < pack.before.metrics.docs_examined

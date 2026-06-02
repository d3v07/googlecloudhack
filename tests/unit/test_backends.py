"""Unit tests for controller/backends.py and agents/mcp_backend.py."""

import asyncio

from controller.backends import FakeBackend, PymongoBackend
from controller.schemas import Evidence, EvidenceMetrics

QUERY_FILTER = {"storeLocation": "Denver"}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20


def _make_evidence() -> Evidence:
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan={"stage": "IXSCAN"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=2.0,
            total_keys_examined=20,
            stages=("FETCH", "IXSCAN"),
        ),
    )


# ---- FakeBackend -----------------------------------------------------------


def test_fake_backend_explain_returns_first_result():
    evidence = _make_evidence()
    backend = FakeBackend([evidence])

    result = asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))

    assert result is evidence


def test_fake_backend_explain_cycles_through_results():
    e1 = _make_evidence()
    e2 = _make_evidence()
    backend = FakeBackend([e1, e2])

    r1 = asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))
    r2 = asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))

    assert r1 is e1
    assert r2 is e2


def test_fake_backend_explain_falls_back_to_last_on_overflow():
    e1 = _make_evidence()
    e2 = _make_evidence()
    backend = FakeBackend([e1, e2])

    asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))
    asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))
    r3 = asyncio.run(backend.explain(QUERY_FILTER, QUERY_SORT, LIMIT))

    assert r3 is e2  # last element


def test_fake_backend_apply_index_records_spec():
    backend = FakeBackend([_make_evidence()])
    keys = [("storeLocation", 1), ("saleDate", -1)]

    asyncio.run(backend.apply_index(keys, "my_index"))

    assert backend.applied_indexes == [(keys, "my_index")]


def test_fake_backend_drop_index_records_name():
    backend = FakeBackend([_make_evidence()])

    asyncio.run(backend.drop_index("my_index"))

    assert "my_index" in backend.dropped_indexes


def test_fake_backend_close_is_noop():
    backend = FakeBackend([_make_evidence()])
    backend.close()  # must not raise


# ---- PymongoBackend construction (no real connection) ----------------------


def test_pymongo_backend_constructs_without_connecting():
    # MongoClient is lazy — does not connect on __init__
    backend = PymongoBackend("mongodb://localhost:27017", "testdb", "testcoll")
    backend.close()  # should not raise


# ---- McpBackend importable without `mcp` installed -------------------------


def test_mcp_backend_importable_without_mcp():
    # This confirms lazy imports inside methods work; `mcp` is not in dev deps
    from agents.mcp_backend import McpBackend

    backend = McpBackend("mongodb://localhost:27017")
    backend.close()  # no-op, must not raise
    assert backend._connection_string == "mongodb://localhost:27017"


def test_mcp_backend_parse_explain_to_evidence():
    """Pure parse helper must be unit-testable offline."""
    from agents.mcp_backend import _parse_explain_to_evidence

    raw = {
        "queryPlanner": {"winningPlan": {"stage": "FETCH", "inputStage": {"stage": "IXSCAN"}}},
        "executionStats": {
            "totalDocsExamined": 20,
            "nReturned": 20,
            "executionTimeMillis": 5,
            "totalKeysExamined": 20,
        },
    }
    evidence = _parse_explain_to_evidence(raw, QUERY_FILTER, QUERY_SORT, LIMIT)

    assert evidence.metrics.docs_examined == 20
    assert evidence.metrics.total_keys_examined == 20
    assert evidence.metrics.has_blocking_sort is False
    assert "IXSCAN" in evidence.metrics.stages

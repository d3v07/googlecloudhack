"""Live preset-explain contract (gated on a real MongoDB connection).

The ESR trap is an empirical property of the planner — a fake collection cannot prove it. This
test reseeds the workload baseline and asserts, against the real 300k-doc collection, that every
trap preset is forced into a blocking SORT (or COLLSCAN) and every healthy preset is served in
index order. Skipped automatically when no connection string is configured.
"""

import os

import pytest

from controller.explain import capture_evidence
from controller.workload import (
    APPLIED_INDEX_PREFIX,
    BASELINE_INDEXES,
    LEGACY_INDEX_NAMES,
    NAMESPACE_COLL,
    NAMESPACE_DB,
    PRESETS,
    SLOW_RATIO,
    build_query,
    slow_signal,
)

CONN = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_TARGET_URI")
pytestmark = pytest.mark.skipif(not CONN, reason="no live MongoDB connection configured")


@pytest.fixture(scope="module")
def collection():
    from pymongo import MongoClient

    client = MongoClient(CONN)
    coll = client[NAMESPACE_DB][NAMESPACE_COLL]
    for name in [ix["name"] for ix in coll.list_indexes()]:
        if name in LEGACY_INDEX_NAMES or name.startswith(APPLIED_INDEX_PREFIX):
            coll.drop_index(name)
    for keys, name in BASELINE_INDEXES:
        coll.create_index(keys, name=name)
    yield coll
    client.close()


@pytest.mark.parametrize("preset", list(PRESETS), ids=[p.key for p in PRESETS])
def test_preset_explain_contract(collection, preset) -> None:
    query_filter, query_sort, limit = build_query(preset.spec)
    evidence = capture_evidence(collection, query_filter, query_sort, limit, max_time_ms=5000)
    signal = slow_signal(evidence.metrics)
    if preset.intent == "trap":
        assert signal.is_slow, f"{preset.key}: expected slow"
        assert signal.blocking_sort or signal.collscan, f"{preset.key}: expected blocking sort"
    else:
        assert not signal.blocking_sort, f"{preset.key}: unexpected blocking sort"
        assert signal.ratio < SLOW_RATIO, f"{preset.key}: ratio {signal.ratio} >= {SLOW_RATIO}"

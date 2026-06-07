"""Live workload-service roundtrip (gated on a real MongoDB connection). Runs guided queries
through MongoWorkloadService — capturing real explain evidence to a query_log collection — and
asserts the evidence-ranked queue (Mongo-side sort + cap) returns the slow ones, ranked, with the
public shape. Uses an isolated test log collection so the demo's query_log is untouched.
"""

import os

import pytest

from api.workload import MongoWorkloadService
from controller.workload import (
    APPLIED_INDEX_PREFIX,
    BASELINE_INDEXES,
    LEGACY_INDEX_NAMES,
    NAMESPACE_COLL,
    NAMESPACE_DB,
    PRESET_BY_KEY,
)

CONN = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_TARGET_URI")
pytestmark = pytest.mark.skipif(not CONN, reason="no live MongoDB connection configured")


@pytest.fixture()
def service():
    from pymongo import MongoClient

    client = MongoClient(CONN)
    coll = client[NAMESPACE_DB][NAMESPACE_COLL]
    for name in [ix["name"] for ix in coll.list_indexes()]:
        if name in LEGACY_INDEX_NAMES or name.startswith(APPLIED_INDEX_PREFIX):
            coll.drop_index(name)
    for keys, name in BASELINE_INDEXES:
        coll.create_index(keys, name=name)
    log = client["dbre_state"]["query_log_test"]
    log.delete_many({})
    try:
        yield MongoWorkloadService(coll, log)
    finally:
        log.delete_many({})
        client.close()


def test_run_query_captures_attributes_and_ranks(service) -> None:
    service.run_query(
        PRESET_BY_KEY["online_recent"].spec,
        username="aakash.singh",
        display_name="Aakash Singh",
        preset="online_recent",
    )
    service.run_query(
        PRESET_BY_KEY["denver_recent"].spec,
        username="dev.trivedi",
        display_name="Dev Trivedi",
        preset="denver_recent",
    )
    service.run_query(
        PRESET_BY_KEY["denver_lookup"].spec,
        username="dev.trivedi",
        display_name="Dev Trivedi",
        preset="denver_lookup",
    )

    queue = service.list_slow_queries()

    # healthy lookup excluded; two traps present, ranked by evidence score (desc), public-shaped
    assert len(queue) == 2
    assert queue[0]["signal"]["score"] >= queue[1]["signal"]["score"]
    assert all(q["signal"]["is_slow"] for q in queue)
    assert all("_id" not in q and q["captured_id"] for q in queue)
    assert {q["user"]["display_name"] for q in queue} <= {"Aakash Singh", "Dev Trivedi"}

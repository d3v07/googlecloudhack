"""Live explain check against the seeded #9 fixture. Skips when there is no Mongo
connection string (CI) or the fixture/indexes are not present on the target cluster.
Run locally after `uv run python seed/seed_demo_fixture.py --all`.
"""

import pytest

from controller.explain import capture_evidence, get_connection_string

pytestmark = pytest.mark.skipif(
    get_connection_string() is None, reason="no Mongo connection string in env"
)

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]


def _collection():
    pymongo = pytest.importorskip("pymongo")
    client = pymongo.MongoClient(get_connection_string())
    return client, client["sample_supplies"]["sales_agent_demo"]


def test_b_blocks_sort_and_c_does_not_on_live_fixture():
    client, collection = _collection()
    try:
        indexes = collection.index_information()
        if "esr_wrong_B" not in indexes or "esr_right_C" not in indexes:
            pytest.skip("fixture indexes not present — run the seed script first")

        evidence_b = capture_evidence(collection, QUERY_FILTER, QUERY_SORT, 20, hint="esr_wrong_B")
        evidence_c = capture_evidence(collection, QUERY_FILTER, QUERY_SORT, 20, hint="esr_right_C")

        assert evidence_b.metrics.has_blocking_sort is True
        assert evidence_c.metrics.has_blocking_sort is False
        assert evidence_b.metrics.total_keys_examined > evidence_c.metrics.total_keys_examined
    finally:
        client.close()

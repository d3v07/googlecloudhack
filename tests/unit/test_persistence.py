from controller.diagnosis import diagnose
from controller.pack import build_pack
from controller.persistence import load_pack, read_pack, save_pack, write_pack
from controller.schemas import Evidence, EvidenceMetrics


def _pack():
    diagnosis = diagnose(
        {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}},
        [("saleDate", -1)],
        has_blocking_sort=True,
        current_index="esr_wrong_B",
    )
    before = Evidence(
        query={"filter": {"storeLocation": "Denver"}, "limit": 20},
        explain_plan={"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=20, docs_returned=20, millis=41, total_keys_examined=17209,
            stages=("FETCH", "SORT", "IXSCAN"),
        ),
    )
    return build_pack(
        run_id="run-001",
        namespace="sample_supplies.sales_agent_demo",
        created_at="2026-06-01T00:00:00Z",
        before=before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
    )


def test_local_file_round_trip(tmp_path):
    pack = _pack()

    path = write_pack(pack, tmp_path)
    loaded = read_pack(path)

    assert path.name == "run-001.json"
    assert loaded.model_dump(mode="json") == pack.model_dump(mode="json")


class _FakeCollection:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def replace_one(self, query, document, upsert=False):
        self.docs[query["run_id"]] = document

    def find_one(self, query, projection=None):
        return self.docs.get(query["run_id"])


def test_mongo_store_round_trip_with_fake_collection():
    collection = _FakeCollection()
    pack = _pack()

    save_pack(collection, pack)
    loaded = load_pack(collection, "run-001")

    assert loaded.model_dump(mode="json") == pack.model_dump(mode="json")


def test_load_missing_pack_returns_none():
    assert load_pack(_FakeCollection(), "nope") is None

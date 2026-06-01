from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import LocalFilePackStore, MongoPackStore, _EmptyPackStore, create_app
from controller.ledger import evidence_hash as compute_hash
from controller.persistence import write_pack
from controller.schemas import (
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    Finding,
    PackStatus,
    Recommendation,
    Severity,
)


def _minimal_pack(run_id: str, status: PackStatus = PackStatus.DIAGNOSED) -> EvidencePack:
    before = Evidence(
        query={"filter": {"x": 1}},
        explain_plan={"stage": "IXSCAN"},
        metrics=EvidenceMetrics(
            docs_examined=1,
            docs_returned=1,
            millis=0,
            total_keys_examined=1,
            stages=("IXSCAN",),
        ),
    )
    rec = Recommendation(index_spec=(("x", 1),), rationale="test")
    eh = compute_hash({"evidence": before, "recommendation": rec})
    return EvidencePack(
        run_id=run_id,
        namespace="db.coll",
        status=status,
        before=before,
        finding=Finding(problem="test", severity=Severity.LOW, evidence_refs=("x",)),
        recommendation=rec,
        evidence_hash=eh,
        created_at="2026-06-01T00:00:00Z",
    )


class FakePackStore:
    def __init__(self, packs: list[EvidencePack]) -> None:
        self._packs = {p.run_id: p for p in packs}

    def list_packs(self) -> list[EvidencePack]:
        return list(self._packs.values())

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return self._packs.get(run_id)

    def save_pack(self, pack: EvidencePack) -> None:
        self._packs[pack.run_id] = pack


_PACKS = [
    _minimal_pack("run-001", PackStatus.DIAGNOSED),
    _minimal_pack("run-002", PackStatus.APPROVED),
    _minimal_pack("run-003", PackStatus.VERIFIED),
]


@pytest.fixture()
def client() -> TestClient:
    store = FakePackStore(_PACKS)
    return TestClient(create_app(store))


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_packs_returns_all(client: TestClient) -> None:
    resp = client.get("/packs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    for item in data:
        assert "run_id" in item
        assert "version" in item
        assert "status" in item


def test_get_pack_known(client: TestClient) -> None:
    resp = client.get("/packs/run-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run-001"
    assert data["status"] == PackStatus.DIAGNOSED.value


def test_get_pack_unknown_returns_404(client: TestClient) -> None:
    resp = client.get("/packs/does-not-exist")
    assert resp.status_code == 404


def test_returned_packs_validate_as_evidence_pack(client: TestClient) -> None:
    resp = client.get("/packs")
    assert resp.status_code == 200
    for item in resp.json():
        validated = EvidencePack.model_validate(item)
        assert validated.run_id == item["run_id"]


def test_single_pack_validates_as_evidence_pack(client: TestClient) -> None:
    resp = client.get("/packs/run-002")
    assert resp.status_code == 200
    validated = EvidencePack.model_validate(resp.json())
    assert validated.run_id == "run-002"


class _FakeCollection:
    def __init__(self, packs: list[EvidencePack]) -> None:
        self._docs = {p.run_id: p.model_dump(mode="json") for p in packs}

    def find(self, projection: dict | None = None) -> list[dict]:
        return list(self._docs.values())

    def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        return self._docs.get(query["run_id"])

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        self._docs[query["run_id"]] = replacement


def test_mongo_pack_store_list() -> None:
    col = _FakeCollection(_PACKS)
    store = MongoPackStore(col)
    packs = store.list_packs()
    assert len(packs) == 3
    assert all(isinstance(p, EvidencePack) for p in packs)


def test_mongo_pack_store_get_known() -> None:
    col = _FakeCollection(_PACKS)
    store = MongoPackStore(col)
    pack = store.get_pack("run-001")
    assert pack is not None
    assert pack.run_id == "run-001"


def test_mongo_pack_store_get_missing() -> None:
    col = _FakeCollection(_PACKS)
    store = MongoPackStore(col)
    assert store.get_pack("missing") is None


def test_local_file_pack_store_list(tmp_path: Path) -> None:
    for pack in _PACKS:
        write_pack(pack, tmp_path)
    store = LocalFilePackStore(tmp_path)
    packs = store.list_packs()
    assert len(packs) == 3
    assert all(isinstance(p, EvidencePack) for p in packs)


def test_local_file_pack_store_get_known(tmp_path: Path) -> None:
    write_pack(_PACKS[0], tmp_path)
    store = LocalFilePackStore(tmp_path)
    pack = store.get_pack("run-001")
    assert pack is not None
    assert pack.run_id == "run-001"


def test_local_file_pack_store_get_missing(tmp_path: Path) -> None:
    store = LocalFilePackStore(tmp_path)
    assert store.get_pack("nonexistent") is None


def test_create_app_with_existing_packs_dir_uses_local_file_store(tmp_path: Path, monkeypatch) -> None:
    for pack in _PACKS[:1]:
        write_pack(pack, tmp_path)
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app) as c:
        resp = c.get("/packs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_store_raises_when_not_overridden() -> None:
    import pytest
    from api.routes import get_store
    with pytest.raises(NotImplementedError):
        get_store()


def test_create_app_with_missing_packs_dir_uses_empty_store(monkeypatch) -> None:
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_packs_dir_xyz")
    app = create_app()
    with TestClient(app) as c:
        assert c.get("/packs").json() == []
        assert c.get("/packs/any").status_code == 404


# --- approve/reject route tests ---

def _approval_client_and_store(pack: EvidencePack) -> tuple[TestClient, FakePackStore]:
    store = FakePackStore([pack])
    return TestClient(create_app(store)), store


def test_approve_transitions_to_approved() -> None:
    pack = _minimal_pack("run-approve")
    client, store = _approval_client_and_store(pack)
    resp = client.post("/packs/run-approve/approve", json={"evidence_hash": pack.evidence_hash})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == PackStatus.APPROVED.value
    assert data["decision"]["action"] == "approve"
    assert data["decision"]["evidence_hash"] == pack.evidence_hash
    # persisted in store
    assert store.get_pack("run-approve").status == PackStatus.APPROVED


def test_reject_transitions_to_rejected() -> None:
    pack = _minimal_pack("run-reject")
    client, store = _approval_client_and_store(pack)
    resp = client.post("/packs/run-reject/reject", json={"evidence_hash": pack.evidence_hash})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == PackStatus.REJECTED.value
    assert data["decision"]["action"] == "reject"
    assert store.get_pack("run-reject").status == PackStatus.REJECTED


def test_approve_unknown_run_id_returns_404() -> None:
    store = FakePackStore([])
    client = TestClient(create_app(store))
    resp = client.post("/packs/no-such-run/approve", json={"evidence_hash": "a" * 64})
    assert resp.status_code == 404


def test_approve_evidence_hash_mismatch_returns_409() -> None:
    pack = _minimal_pack("run-mismatch")
    client, _ = _approval_client_and_store(pack)
    resp = client.post("/packs/run-mismatch/approve", json={"evidence_hash": "b" * 64})
    assert resp.status_code == 409


def test_approve_already_approved_pack_returns_409() -> None:
    pack = _minimal_pack("run-already", status=PackStatus.APPROVED)
    client, _ = _approval_client_and_store(pack)
    resp = client.post("/packs/run-already/approve", json={"evidence_hash": pack.evidence_hash})
    assert resp.status_code == 409


# --- save_pack store-level tests ---

def test_mongo_pack_store_save_pack() -> None:
    pack = _minimal_pack("run-save-mongo")
    col = _FakeCollection([])
    store = MongoPackStore(col)
    store.save_pack(pack)
    assert col._docs["run-save-mongo"]["run_id"] == "run-save-mongo"


def test_local_file_pack_store_save_pack(tmp_path: Path) -> None:
    pack = _minimal_pack("run-save-file")
    store = LocalFilePackStore(tmp_path)
    store.save_pack(pack)
    retrieved = store.get_pack("run-save-file")
    assert retrieved is not None
    assert retrieved.run_id == "run-save-file"


def test_empty_pack_store_save_pack_raises() -> None:
    store = _EmptyPackStore()
    pack = _minimal_pack("run-empty")
    with pytest.raises(NotImplementedError):
        store.save_pack(pack)

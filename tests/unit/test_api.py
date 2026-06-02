from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import LocalFilePackStore, MongoPackStore, _EmptyPackStore, create_app
from controller.ledger import evidence_hash as compute_hash
from controller.persistence import write_pack
from controller.phases import Phase
from controller.schemas import (
    Decision,
    DecisionAction,
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
            docs_examined=1, docs_returned=1, millis=0, total_keys_examined=1, stages=("IXSCAN",)
        ),
    )
    rec = Recommendation(index_spec=(("x", 1),), rationale="test")
    eh = compute_hash({"evidence": before, "recommendation": rec})

    # build a status-consistent pack (the model now enforces status ⟺ decision/after)
    after: Evidence | None = None
    decision: Decision | None = None
    if status in (PackStatus.APPROVED, PackStatus.VERIFIED):
        after = before
        decision = Decision(action=DecisionAction.APPROVE, evidence_hash=eh, phase=Phase.APPROVE)
    elif status is PackStatus.REJECTED:
        decision = Decision(action=DecisionAction.REJECT, evidence_hash=eh, phase=Phase.APPROVE)

    return EvidencePack(
        run_id=run_id,
        namespace="db.coll",
        status=status,
        before=before,
        after=after,
        finding=Finding(problem="test", severity=Severity.LOW, evidence_refs=("x",)),
        recommendation=rec,
        decision=decision,
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


class FakeEngine:
    """In-memory stand-in for the live remediation engine — returns status-consistent packs
    keyed to the run_id so route logic is testable with no Mongo."""

    def __init__(self) -> None:
        self.diagnosed: list[str] = []
        self.applied: list[str] = []
        self.rejected: list[str] = []

    async def diagnose(self, run_id: str) -> EvidencePack:
        self.diagnosed.append(run_id)
        return _minimal_pack(run_id, PackStatus.DIAGNOSED)

    async def apply_and_verify(self, pack: EvidencePack) -> EvidencePack:
        self.applied.append(pack.run_id)
        return _minimal_pack(pack.run_id, PackStatus.VERIFIED)

    def reject(self, pack: EvidencePack) -> EvidencePack:
        self.rejected.append(pack.run_id)
        return _minimal_pack(pack.run_id, PackStatus.REJECTED)


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


def test_create_app_with_existing_packs_dir_uses_local_file_store(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    for pack in _PACKS[:1]:
        write_pack(pack, tmp_path)
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app) as c:
        resp = c.get("/packs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_store_raises_when_not_overridden() -> None:
    from api.routes import get_store

    with pytest.raises(NotImplementedError):
        get_store()


def test_create_app_with_missing_packs_dir_uses_empty_store(monkeypatch) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_packs_dir_xyz")
    app = create_app()
    with TestClient(app) as c:
        assert c.get("/packs").json() == []
        assert c.get("/packs/any").status_code == 404


# --- /decision route (approve applies+verifies via the engine; reject is a pure record) ---


def _decision_setup(pack: EvidencePack) -> tuple[TestClient, FakePackStore, FakeEngine]:
    store, engine = FakePackStore([pack]), FakeEngine()
    return TestClient(create_app(store, engine)), store, engine


def test_decision_approve_applies_and_returns_verified_pack() -> None:
    pack = _minimal_pack("run-dec")
    client, store, engine = _decision_setup(pack)
    resp = client.post(
        "/packs/run-dec/decision",
        json={"decision": "approve", "evidence_hash": pack.evidence_hash, "approver": "op"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == PackStatus.VERIFIED.value
    assert data["decision"]["action"] == "approve"
    assert engine.applied == ["run-dec"]  # the gated mutation went through the engine
    assert store.get_pack("run-dec").status == PackStatus.VERIFIED


def test_decision_reject_records_without_mutating() -> None:
    pack = _minimal_pack("run-dec2")
    client, _, engine = _decision_setup(pack)
    resp = client.post(
        "/packs/run-dec2/decision",
        json={"decision": "reject", "evidence_hash": pack.evidence_hash, "note": "wrong index"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == PackStatus.REJECTED.value
    assert engine.rejected == ["run-dec2"]
    assert engine.applied == []  # reject must not apply an index


def test_decision_unknown_run_id_returns_404_not_found() -> None:
    client, _, _ = _decision_setup(_minimal_pack("present"))
    resp = client.post(
        "/packs/nope/decision", json={"decision": "approve", "evidence_hash": "a" * 64}
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "not_found"}


def test_decision_stale_evidence_hash_returns_409_with_current_hash() -> None:
    pack = _minimal_pack("run-stale")
    client, _, engine = _decision_setup(pack)
    resp = client.post(
        "/packs/run-stale/decision", json={"decision": "approve", "evidence_hash": "b" * 64}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "stale_evidence_hash"
    assert body["current_hash"] == pack.evidence_hash
    assert engine.applied == []  # a stale hash must never trigger a mutation


def test_decision_already_decided_returns_409() -> None:
    pack = _minimal_pack("run-done", status=PackStatus.APPROVED)
    client, _, _ = _decision_setup(pack)
    resp = client.post(
        "/packs/run-done/decision",
        json={"decision": "approve", "evidence_hash": pack.evidence_hash},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "already_decided"


# --- POST /run route (#37 — DIAGNOSE-only, no mutation) ---


def test_run_with_explicit_run_id_persists_diagnosed_pack() -> None:
    store, engine = FakePackStore([]), FakeEngine()
    client = TestClient(create_app(store, engine))
    resp = client.post("/run", json={"run_id": "run-fixed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run-fixed"
    assert data["status"] == PackStatus.DIAGNOSED.value  # /run never mutates
    assert engine.diagnosed == ["run-fixed"]
    assert engine.applied == []
    assert store.get_pack("run-fixed") is not None


def test_run_generates_run_id_when_no_body() -> None:
    store, engine = FakePackStore([]), FakeEngine()
    client = TestClient(create_app(store, engine))
    resp = client.post("/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"].startswith("run-")
    assert engine.diagnosed == [data["run_id"]]
    assert store.get_pack(data["run_id"]) is not None


def test_run_returned_pack_validates_as_evidence_pack() -> None:
    client = TestClient(create_app(FakePackStore([]), FakeEngine()))
    resp = client.post("/run", json={})
    assert resp.status_code == 200
    EvidencePack.model_validate(resp.json())


def test_get_engine_raises_when_not_overridden() -> None:
    from api.routes import get_engine

    with pytest.raises(NotImplementedError):
        get_engine()


def test_api_server_does_not_import_agents_layer() -> None:
    """The read-API image packages only api/ + controller/ + contracts/ (see Dockerfile).
    _LiveEngine must source the demo fixture from controller/, never agents/, or the live
    endpoints raise ModuleNotFoundError in the container. Guards against re-coupling."""
    import inspect

    import api.server

    src = inspect.getsource(api.server)
    assert "from agents" not in src
    assert "import agents" not in src


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


# --- secrets module tests ---


def test_get_mongo_connection_string_returns_env_conn(monkeypatch) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("MDB_MCP_CONNECTION_STRING", "mongodb://localhost:27017")
    from api.secrets import get_mongo_connection_string

    assert get_mongo_connection_string() == "mongodb://localhost:27017"


def test_get_mongo_connection_string_raises_when_neither_set(monkeypatch) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.delenv("MDB_MCP_CONNECTION_STRING", raising=False)
    from api.secrets import get_mongo_connection_string

    with pytest.raises(RuntimeError, match="MONGO_SECRET_NAME"):
        get_mongo_connection_string()


def test_create_app_uses_local_file_path_when_no_mongo_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    for pack in _PACKS[:1]:
        write_pack(pack, tmp_path)
    monkeypatch.setenv("PACKS_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app) as c:
        resp = c.get("/packs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_app_uses_empty_store_when_no_mongo_secret_and_no_dir(monkeypatch) -> None:
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_secrets_test_xyz")
    app = create_app()
    with TestClient(app) as c:
        assert c.get("/packs").json() == []


# --- write-token auth (RUN_API_TOKEN gates the mutating endpoints) ---


def test_run_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("RUN_API_TOKEN", "s3cret")
    client = TestClient(create_app(FakePackStore([]), FakeEngine()))
    assert client.post("/run").status_code == 401  # missing
    assert client.post("/run", headers={"X-API-Token": "wrong"}).status_code == 401
    assert client.post("/run", headers={"X-API-Token": "s3cret"}).status_code == 200


def test_decision_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("RUN_API_TOKEN", "s3cret")
    pack = _minimal_pack("run-tok")
    client, _, engine = _decision_setup(pack)
    body = {"decision": "approve", "evidence_hash": pack.evidence_hash}
    assert client.post("/packs/run-tok/decision", json=body).status_code == 401
    assert engine.applied == []  # an unauthenticated write never reaches the engine
    ok = client.post("/packs/run-tok/decision", json=body, headers={"X-API-Token": "s3cret"})
    assert ok.status_code == 200


def test_writes_are_open_when_token_unset(monkeypatch) -> None:
    monkeypatch.delenv("RUN_API_TOKEN", raising=False)
    client = TestClient(create_app(FakePackStore([]), FakeEngine()))
    assert client.post("/run").status_code == 200  # gate is a no-op without the env var


def test_reads_never_require_token(monkeypatch) -> None:
    monkeypatch.setenv("RUN_API_TOKEN", "s3cret")
    client = TestClient(create_app(FakePackStore(_PACKS), FakeEngine()))
    assert client.get("/health").status_code == 200
    assert client.get("/packs").status_code == 200
    assert client.get("/packs/run-001").status_code == 200

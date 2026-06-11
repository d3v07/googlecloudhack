import pytest
from fastapi.testclient import TestClient

from api import memory as memory_module
from api.memory import (
    MemoryDocument,
    VoyageMemoryConfig,
    VoyageMemoryError,
    VoyageMemoryService,
)
from api.server import create_app
from controller.auth import Identity, make_session_token
from controller.ledger import evidence_hash
from controller.schemas import (
    ApprovalGate,
    ApprovalGateState,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    Finding,
    PackStatus,
    Recommendation,
    Severity,
)


@pytest.fixture(autouse=True)
def _clear_voyage_cache():
    """Isolate the module-level last-good Voyage cache between tests."""
    memory_module._VOYAGE_CACHE.clear()
    yield
    memory_module._VOYAGE_CACHE.clear()


def _minimal_pack(run_id: str = "run-memory") -> EvidencePack:
    before = Evidence(
        query={
            "filter": {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}},
            "sort": [("saleDate", -1)],
            "limit": 20,
        },
        explain_plan={"stage": "SORT", "inputStage": {"stage": "IXSCAN"}},
        metrics=EvidenceMetrics(
            docs_examined=1000,
            docs_returned=20,
            millis=12,
            total_keys_examined=1000,
            stages=("IXSCAN", "FETCH", "SORT"),
        ),
    )
    recommendation = Recommendation(
        index_spec=(("storeLocation", 1), ("saleDate", -1), ("customer.age", 1)),
        rationale="ESR order removes the blocking sort.",
    )
    hash_value = evidence_hash({"evidence": before, "recommendation": recommendation})
    return EvidencePack(
        run_id=run_id,
        namespace="sample.sales",
        status=PackStatus.DIAGNOSED,
        before=before,
        finding=Finding(
            problem="Query performs a blocking in-memory SORT.",
            severity=Severity.HIGH,
            evidence_refs=("explain",),
        ),
        recommendation=recommendation,
        approval_gate=ApprovalGate(
            gate_id=f"{run_id}:gate",
            state=ApprovalGateState.PENDING_APPROVAL,
            required_hash=hash_value,
            mutation_allowed=False,
        ),
        evidence_hash=hash_value,
        created_at="2026-06-01T00:00:00Z",
    )


class _Store:
    def __init__(self, packs: list[EvidencePack]) -> None:
        self._packs = {pack.run_id: pack for pack in packs}

    def list_packs(self) -> list[EvidencePack]:
        return list(self._packs.values())

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return self._packs.get(run_id)

    def save_pack(self, pack: EvidencePack) -> None:
        self._packs[pack.run_id] = pack


class _FakeVoyageClient:
    def __init__(self) -> None:
        self.embed_calls: list[tuple[list[str], str, str]] = []
        self.rerank_calls: list[tuple[str, list[str], str, int]] = []

    def embed(self, texts: list[str], *, model: str, input_type: str) -> list[list[float]]:
        self.embed_calls.append((texts, model, input_type))
        if input_type == "query":
            return [[1.0, 0.0]]
        return [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]][: len(texts)]

    def rerank(
        self, query: str, documents: list[str], *, model: str, top_k: int
    ) -> list[tuple[int, float]]:
        self.rerank_calls.append((query, documents, model, top_k))
        return [(1, 0.91), (0, 0.42)]


def test_memory_endpoint_returns_unconfigured_when_voyage_key_absent(monkeypatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "memory-secret")
    client = TestClient(create_app(_Store([_minimal_pack()])))
    dbre = make_session_token(Identity("dbre", "DBRE", "dbre"), "memory-secret")

    resp = client.get("/packs/run-memory/memory", headers={"Authorization": f"Bearer {dbre}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run-memory"
    assert body["status"] == "unconfigured"
    assert body["configured"] is False
    assert body["mutation_authority"] is False
    assert body["guidance"] == []
    assert body["models"] == {"embed": "voyage-4-lite", "rerank": "rerank-2.5-lite"}


def test_memory_endpoint_unknown_pack_returns_404(monkeypatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "memory-secret")
    client = TestClient(create_app(_Store([])))
    dbre = make_session_token(Identity("dbre", "DBRE", "dbre"), "memory-secret")

    resp = client.get("/packs/missing/memory", headers={"Authorization": f"Bearer {dbre}"})

    assert resp.status_code == 404


def test_memory_endpoint_requires_dbre_session(monkeypatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "memory-secret")
    client = TestClient(create_app(_Store([_minimal_pack()])))
    assert client.get("/packs/run-memory/memory").status_code == 401
    user = make_session_token(Identity("dev", "Dev", "user"), "memory-secret")
    assert (
        client.get("/packs/run-memory/memory", headers={"Authorization": f"Bearer {user}"})
    ).status_code == 403
    dbre = make_session_token(Identity("dbre", "DBRE", "dbre"), "memory-secret")
    assert (
        client.get("/packs/run-memory/memory", headers={"Authorization": f"Bearer {dbre}"})
    ).status_code == 200


def test_memory_service_prefilters_with_embeddings_and_reranks() -> None:
    docs = (
        MemoryDocument("doc-a", "Approval", "Hash gate review."),
        MemoryDocument("doc-b", "ESR", "Blocking SORT guidance."),
        MemoryDocument("doc-c", "Verify", "Re-explain after apply."),
    )
    fake = _FakeVoyageClient()
    service = VoyageMemoryService(
        VoyageMemoryConfig(
            api_key="test-key",
            embed_model="embed-test",
            rerank_model="rerank-test",
            top_k=2,
            prefilter_k=3,
            max_docs=3,
        ),
        client=fake,
        documents=docs,
    )

    response = service.lookup(_minimal_pack())

    assert response.status == "ok"
    assert response.configured is True
    assert [item.id for item in response.guidance] == ["doc-c", "doc-b"]
    assert [item.source for item in response.guidance] == ["voyage", "voyage"]
    assert fake.embed_calls[0][1:] == ("embed-test", "query")
    assert fake.embed_calls[1][1:] == ("embed-test", "document")
    assert fake.rerank_calls[0][2:] == ("rerank-test", 2)


def test_memory_service_returns_empty_when_docs_are_capped_to_zero() -> None:
    service = VoyageMemoryService(
        VoyageMemoryConfig(api_key="test-key", max_docs=0),
        client=_FakeVoyageClient(),
        documents=(MemoryDocument("doc", "Title", "Body"),),
    )

    response = service.lookup(_minimal_pack())

    assert response.status == "empty"
    assert response.guidance == []


def test_memory_service_falls_back_to_local_guidance_when_voyage_fails() -> None:
    class FailingVoyageClient:
        def embed(self, texts: list[str], *, model: str, input_type: str) -> list[list[float]]:
            raise VoyageMemoryError("network failure")

        def rerank(
            self, query: str, documents: list[str], *, model: str, top_k: int
        ) -> list[tuple[int, float]]:
            raise AssertionError("rerank should not run when embeddings fail")

    docs = (
        MemoryDocument("sort", "Blocking sort", "DBRE guidance for blocking SORT and ESR."),
        MemoryDocument("other", "Other", "Unrelated guidance."),
    )
    service = VoyageMemoryService(
        VoyageMemoryConfig(api_key="test-key", top_k=1, max_docs=2),
        client=FailingVoyageClient(),
        documents=docs,
    )

    response = service.lookup(_minimal_pack())

    assert response.status == "fallback"
    assert response.configured is True
    assert response.guidance[0].id == "sort"
    assert response.guidance[0].source == "local"
    assert response.message == "Voyage request failed; returned local guidance."


def test_memory_stays_out_of_evidence_pack_v1() -> None:
    # Sift Memory is out-of-band: it must never be a field of EvidencePack v1.
    assert "memory" not in EvidencePack.model_fields
    assert "guidance" not in EvidencePack.model_fields
    dumped = _minimal_pack().model_dump(mode="json")
    assert "memory" not in dumped
    assert "guidance" not in dumped

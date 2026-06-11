"""Read-only DBRE memory retrieval for Run Review.

Sift Memory is out-of-band presentation context. It is not part of EvidencePack v1 and
never changes diagnosis, approval, mutation, or verification decisions.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from controller.schemas import EvidencePack


class VoyageMemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoyageMemoryConfig:
    api_key: str = ""
    embed_model: str = "voyage-4-lite"
    rerank_model: str = "rerank-2.5-lite"
    top_k: int = 3
    prefilter_k: int = 8
    max_docs: int = 12
    namespace: str = "dbre-runbook"


@dataclass(frozen=True)
class MemoryDocument:
    id: str
    title: str
    text: str
    tags: tuple[str, ...] = ()


class MemoryGuidance(BaseModel):
    id: str
    title: str
    summary: str
    reason: str
    source: Literal["voyage", "local"]
    score: float = Field(ge=0)
    tags: list[str] = Field(default_factory=list)


class MemoryResponse(BaseModel):
    configured: bool
    run_id: str
    status: Literal["unconfigured", "ok", "empty", "fallback", "failed"]
    mutation_authority: bool = False
    guidance: list[MemoryGuidance] = Field(default_factory=list)
    models: dict[str, str]
    query: str | None = None
    namespace: str | None = None
    retrieved_at: str | None = None
    message: str | None = None


class VoyageClientProtocol(Protocol):
    def embed(self, texts: list[str], *, model: str, input_type: str) -> list[list[float]]: ...
    def rerank(
        self, query: str, documents: list[str], *, model: str, top_k: int
    ) -> list[tuple[int, float]]: ...


MEMORY_DOCUMENTS: tuple[MemoryDocument, ...] = (
    MemoryDocument(
        "blocking-sort-esr",
        "Blocking SORT with ESR index order",
        "When explain contains a blocking SORT, prefer a compound index ordered by equality "
        "fields first, sort fields next, and range fields last.",
        ("SORT", "ESR", "index"),
    ),
    MemoryDocument(
        "high-docs-examined",
        "High docs examined against a small result set",
        "A high docsExamined-to-returned ratio means the current index is not selective enough "
        "for the query shape. Verify docs examined, keys examined, or execution time improves.",
        ("docsExamined", "selectivity", "verification"),
    ),
    MemoryDocument(
        "hash-bound-approval",
        "Approval must bind to the evidence hash",
        "The operator approves the hash derived from before evidence and the recommendation. "
        "If the hash changes, reject the decision as stale and keep mutation blocked.",
        ("approval", "hash", "gate"),
    ),
    MemoryDocument(
        "verification-rail",
        "Strict verification rail",
        "Mark VERIFIED only when blocking SORT is gone, the selected index is evidenced in the "
        "plan, and at least one metric improves. Otherwise record failed checks.",
        ("verify", "SORT", "metrics"),
    ),
    MemoryDocument(
        "captured-query-natural-plan",
        "Captured queries diagnose their natural plan",
        "For real workload captures, diagnose the natural plan without forcing the old demo "
        "hint. The captured filter, sort, and limit drive the ESR candidate.",
        ("captured-query", "workload", "explain"),
    ),
    MemoryDocument(
        "index-backed-sort",
        "Index-backed sort is the intended after state",
        "Removing a blocking SORT does not mean results are unsorted. MongoDB can read the "
        "compound index in the requested order without materializing a blocking sort stage.",
        ("sort", "index", "after"),
    ),
    MemoryDocument(
        "rollback-visibility",
        "Show rollback visibility before automation",
        "Expose the rollback command or index name clearly in the evidence trail. Automatic "
        "rollback can wait; the operator still needs to see what would be reversed.",
        ("rollback", "audit", "operator"),
    ),
    MemoryDocument(
        "agent-read-only-boundary",
        "Agents recommend; controller decides",
        "Reasoning agents and read-only tools provide evidence and narrative context only. "
        "Deterministic Python validates, selects, hashes, applies after approval, and verifies.",
        ("agents", "read-only", "controller"),
    ),
)


class VoyageClient:
    def __init__(self, api_key: str, *, timeout: float = 12.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = Request(
            f"https://api.voyageai.com{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self._timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VoyageMemoryError("Voyage request failed") from exc

    def embed(self, texts: list[str], *, model: str, input_type: str) -> list[list[float]]:
        data = self._post(
            "/v1/embeddings",
            {"model": model, "input": texts, "input_type": input_type},
        )
        rows = data.get("data", [])
        embeddings: list[list[float]] = []
        for row in rows:
            embedding = row.get("embedding")
            if not isinstance(embedding, list):
                raise VoyageMemoryError("Voyage embedding response was malformed")
            embeddings.append([float(value) for value in embedding])
        return embeddings

    def rerank(
        self, query: str, documents: list[str], *, model: str, top_k: int
    ) -> list[tuple[int, float]]:
        data = self._post(
            "/v1/rerank",
            {"model": model, "query": query, "documents": documents, "top_k": top_k},
        )
        ranked: list[tuple[int, float]] = []
        for row in data.get("data", []):
            index = row.get("index")
            score = row.get("relevance_score", row.get("score", 0.0))
            if isinstance(index, int):
                ranked.append((index, float(score)))
        return ranked


# Last successful Voyage retrieval per run_id. The service is rebuilt per request and the
# free-tier Voyage key is rate-limited (3 RPM), so a transient 429 returns this real cached
# result instead of degraded local guidance.
_VOYAGE_CACHE: dict[str, "MemoryResponse"] = {}


class VoyageMemoryService:
    def __init__(
        self,
        config: VoyageMemoryConfig,
        *,
        client: VoyageClientProtocol | None = None,
        documents: tuple[MemoryDocument, ...] = MEMORY_DOCUMENTS,
    ) -> None:
        self._config = config
        self._client = client or VoyageClient(config.api_key)
        self._documents = documents

    def lookup(self, pack: EvidencePack) -> MemoryResponse:
        models = {"embed": self._config.embed_model, "rerank": self._config.rerank_model}
        if not self._config.api_key:
            return MemoryResponse(
                configured=False,
                run_id=pack.run_id,
                status="unconfigured",
                models=models,
                message="Sift Memory is not configured.",
            )

        query = build_memory_query(pack)
        docs = self._documents[: max(0, self._config.max_docs)]
        if not docs:
            return MemoryResponse(
                configured=True,
                run_id=pack.run_id,
                status="empty",
                models=models,
                query=query,
                namespace=self._config.namespace,
                retrieved_at=_now(),
                message="No Sift Memory documents are available.",
            )

        try:
            query_embedding = self._single_embedding(
                query, model=self._config.embed_model, input_type="query"
            )
            doc_embeddings = self._client.embed(
                [doc.text for doc in docs], model=self._config.embed_model, input_type="document"
            )
            prefiltered = sorted(
                enumerate(doc_embeddings),
                key=lambda pair: _cosine(query_embedding, pair[1]),
                reverse=True,
            )[: max(self._config.top_k, self._config.prefilter_k)]
            candidates = [docs[index] for index, _ in prefiltered]
            ranked = self._client.rerank(
                query,
                [doc.text for doc in candidates],
                model=self._config.rerank_model,
                top_k=self._config.top_k,
            )
            guidance = [
                _guidance(candidates[index], pack, score, source="voyage")
                for index, score in ranked[: self._config.top_k]
                if 0 <= index < len(candidates)
            ]
            response = MemoryResponse(
                configured=True,
                run_id=pack.run_id,
                status="ok" if guidance else "empty",
                guidance=guidance,
                models=models,
                query=query,
                namespace=self._config.namespace,
                retrieved_at=_now(),
                message=None if guidance else "No relevant Sift Memory guidance found.",
            )
            if guidance:
                _VOYAGE_CACHE[pack.run_id] = response
            return response
        except VoyageMemoryError:
            cached = _VOYAGE_CACHE.get(pack.run_id)
            if cached is not None:
                return cached
            guidance = [
                _guidance(doc, pack, 0.1, source="local") for doc in _local_docs(pack, docs)
            ]
            return MemoryResponse(
                configured=True,
                run_id=pack.run_id,
                status="fallback",
                guidance=guidance[: self._config.top_k],
                models=models,
                query=query,
                namespace=self._config.namespace,
                retrieved_at=_now(),
                message="Voyage request failed; returned local guidance.",
            )

    def _single_embedding(self, text: str, *, model: str, input_type: str) -> list[float]:
        rows = self._client.embed([text], model=model, input_type=input_type)
        if len(rows) != 1:
            raise VoyageMemoryError("Voyage returned an unexpected embedding count")
        return rows[0]


def get_memory_service() -> VoyageMemoryService:
    return VoyageMemoryService(
        VoyageMemoryConfig(
            api_key=os.getenv("VOYAGE_API_KEY", "").strip(),
            embed_model=os.getenv("VOYAGE_EMBED_MODEL", "voyage-4-lite"),
            rerank_model=os.getenv("VOYAGE_RERANK_MODEL", "rerank-2.5-lite"),
            top_k=_env_int("VOYAGE_MEMORY_TOP_K", 3),
            prefilter_k=_env_int("VOYAGE_MEMORY_PREFILTER_K", 8),
            max_docs=_env_int("VOYAGE_MEMORY_MAX_DOCS", 12),
        )
    )


def build_memory_query(pack: EvidencePack) -> str:
    before = pack.before.model_dump(mode="json")
    metrics = before["metrics"]
    trace = " | ".join(event.summary for event in pack.agent_trace[:4])
    return "\n".join(
        (
            f"namespace: {pack.namespace}",
            f"status: {pack.status.value}",
            f"finding: {pack.finding.problem}",
            f"severity: {pack.finding.severity.value}",
            f"query: {json.dumps(before['query'], sort_keys=True)}",
            f"metrics: docs_examined={metrics['docs_examined']} "
            f"docs_returned={metrics['docs_returned']} "
            f"keys_examined={metrics['total_keys_examined']} "
            f"millis={metrics['millis']} stages={','.join(metrics.get('stages', []))}",
            f"recommendation: {json.dumps(pack.recommendation.index_spec)}",
            f"rationale: {pack.recommendation.rationale}",
            f"trace: {trace}",
        )
    )


def _guidance(
    doc: MemoryDocument,
    pack: EvidencePack,
    score: float,
    *,
    source: Literal["voyage", "local"],
) -> MemoryGuidance:
    return MemoryGuidance(
        id=doc.id,
        title=doc.title,
        summary=doc.text,
        reason=_reason(doc, pack),
        source=source,
        score=max(0.0, score),
        tags=list(doc.tags),
    )


def _local_docs(pack: EvidencePack, docs: tuple[MemoryDocument, ...]) -> list[MemoryDocument]:
    tokens = set(build_memory_query(pack).lower().replace("_", " ").split())
    return sorted(
        docs,
        key=lambda doc: (
            len(tokens.intersection(doc.text.lower().split()))
            + (4 if pack.before.metrics.has_blocking_sort and "SORT" in doc.tags else 0)
        ),
        reverse=True,
    )[:3]


def _reason(doc: MemoryDocument, pack: EvidencePack) -> str:
    if pack.before.metrics.has_blocking_sort and ("SORT" in doc.tags or "sort" in doc.tags):
        return "This run has a blocking SORT in the before explain plan."
    if pack.before.metrics.docs_examined > max(pack.before.metrics.docs_returned * 100, 1000):
        return "This run has a high docs-examined to returned-docs ratio."
    if "approval" in doc.tags:
        return "This run is governed by a hash-bound approval gate."
    return "This guidance matches the selected run's evidence and recommendation context."


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _now() -> str:
    return datetime.now(UTC).isoformat()

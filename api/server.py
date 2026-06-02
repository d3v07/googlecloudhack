import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from api.routes import PackStore, Runner, get_runner, get_store, router
from controller.persistence import load_pack, read_pack, save_pack, write_pack
from controller.schemas import EvidencePack


class MongoPackStore:
    def __init__(self, collection: Any) -> None:
        self._col = collection

    def list_packs(self) -> list[EvidencePack]:
        docs = self._col.find(projection={"_id": False})
        return [EvidencePack.model_validate(doc) for doc in docs]

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return load_pack(self._col, run_id)

    def save_pack(self, pack: EvidencePack) -> None:
        save_pack(self._col, pack)


class LocalFilePackStore:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def list_packs(self) -> list[EvidencePack]:
        return [read_pack(p) for p in sorted(self._dir.glob("*.json"))]

    def get_pack(self, run_id: str) -> EvidencePack | None:
        path = self._dir / f"{run_id}.json"
        return read_pack(path) if path.exists() else None

    def save_pack(self, pack: EvidencePack) -> None:
        write_pack(pack, self._dir)


class _EmptyPackStore:
    def list_packs(self) -> list[EvidencePack]:
        return []

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return None

    def save_pack(self, pack: EvidencePack) -> None:
        raise NotImplementedError("_EmptyPackStore cannot persist packs")


class _LiveRunner:  # pragma: no cover - live
    """Runs the deterministic orchestrator over the preset demo fixture for POST /run.

    Holds only the connection string — the Mongo connection and the orchestrator/agents
    imports are deferred to run() so constructing it at create_app() does no I/O and can't
    regress the read endpoints. Narrator is intentionally off (the pack stays deterministic;
    narration would need Vertex IAM on the Cloud Run SA)."""

    def __init__(self, connection_string: str) -> None:
        self._conn = connection_string
        # serialize live runs within the instance — the deploy pins Cloud Run to
        # max-instances=1 so this in-process lock fully serializes /run, which lets the
        # pre-run sweep reclaim orphans without ever dropping a peer's in-flight scratch
        self._lock = asyncio.Lock()

    async def run(self, run_id: str) -> EvidencePack:
        from agents.demo import COLL, DB, LIMIT, QUERY_FILTER, QUERY_SORT
        from controller.backends import PymongoBackend
        from controller.orchestrator import INDEX_C_NAME, run_remediation

        async with self._lock:
            backend = PymongoBackend(self._conn, DB, COLL)
            try:
                await backend.drop_scratch_indexes(f"{INDEX_C_NAME}__scratch__")
                return await run_remediation(
                    backend,
                    run_id=run_id,
                    namespace=f"{DB}.{COLL}",
                    query_filter=QUERY_FILTER,
                    query_sort=QUERY_SORT,
                    limit=LIMIT,
                )
            finally:
                backend.close()


def create_app(store: PackStore | None = None, runner: Runner | None = None) -> FastAPI:
    app = FastAPI(title="GCRAH Evidence Pack API")

    if store is None:
        if os.getenv("MONGO_SECRET_NAME"):  # pragma: no cover - live
            from pymongo import MongoClient  # noqa: PLC0415

            from api.secrets import get_mongo_connection_string  # noqa: PLC0415

            conn = get_mongo_connection_string()
            collection = MongoClient(conn)["dbre_state"]["evidence_packs"]
            store = MongoPackStore(collection)
            if runner is None:
                runner = _LiveRunner(conn)
        else:
            packs_dir = Path(os.getenv("PACKS_DIR", "runs"))
            store = LocalFilePackStore(packs_dir) if packs_dir.exists() else _EmptyPackStore()

    app.dependency_overrides[get_store] = lambda: store
    if runner is not None:
        app.dependency_overrides[get_runner] = lambda: runner
    app.include_router(router)
    return app


app = create_app()

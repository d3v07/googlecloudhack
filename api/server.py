import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from api.agent_engine import AgentEngineDiagnosisClient
from api.routes import Engine, PackStore, get_engine, get_store, router
from controller.ledger_store import LedgerStore, MongoLedgerStore
from controller.orchestrator import ApprovalTicket, DiagnosisAgent
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


class _LiveEngine:  # pragma: no cover - live
    """Runs the remediation phases over the preset demo fixture against the live target
    collection. diagnose() is read-only; apply_and_verify() performs the human-approved
    index mutation; reject() is a pure record. The Mongo connection + orchestrator imports
    are deferred to call time so constructing it at create_app() does no I/O and can't
    regress the read endpoints. Imports stay within controller/ (packaged in the read-API
    image) — never the agents/ layer. Narrator is off (the pack stays deterministic;
    narration would need Vertex IAM on the Cloud Run SA)."""

    def __init__(
        self,
        connection_string: str,
        diagnosis_agent: DiagnosisAgent | None = None,
        ledger: LedgerStore | None = None,
    ) -> None:
        self._conn = connection_string
        self._diagnosis_agent = diagnosis_agent
        self._ledger = ledger

    def _backend(self):
        from controller.backends import PymongoBackend
        from controller.demo_fixture import COLL, DB

        return PymongoBackend(self._conn, DB, COLL)

    async def diagnose(self, run_id: str) -> EvidencePack:
        from controller.demo_fixture import COLL, DB, LIMIT, QUERY_FILTER, QUERY_SORT
        from controller.orchestrator import run_agent_diagnosis, run_diagnosis

        if self._diagnosis_agent is not None:
            return await run_agent_diagnosis(
                self._diagnosis_agent,
                run_id=run_id,
                namespace=f"{DB}.{COLL}",
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                ledger=self._ledger,
            )

        backend = self._backend()
        try:
            return await run_diagnosis(
                backend,
                run_id=run_id,
                namespace=f"{DB}.{COLL}",
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                ledger=self._ledger,
            )
        finally:
            backend.close()

    async def apply_and_verify(self, pack: EvidencePack, ticket: ApprovalTicket) -> EvidencePack:
        from controller.demo_fixture import LIMIT, QUERY_FILTER, QUERY_SORT
        from controller.orchestrator import apply_and_verify

        backend = self._backend()
        try:
            return await apply_and_verify(
                backend,
                pack,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
                approval_ticket=ticket,
                ledger=self._ledger,
            )
        finally:
            backend.close()

    def reject(
        self, pack: EvidencePack, *, approver: str = "dashboard-operator", note: str = ""
    ) -> EvidencePack:
        from controller.orchestrator import reject_pack

        return reject_pack(pack, approver=approver, note=note, ledger=self._ledger)


def create_app(store: PackStore | None = None, engine: Engine | None = None) -> FastAPI:
    app = FastAPI(title="GCRAH Evidence Pack API")

    if store is None:
        if os.getenv("MONGO_SECRET_NAME"):  # pragma: no cover - live
            from pymongo import MongoClient  # noqa: PLC0415

            from api.secrets import get_mongo_connection_string  # noqa: PLC0415

            conn = get_mongo_connection_string()
            state_db = MongoClient(conn)["dbre_state"]
            collection = state_db["evidence_packs"]
            store = MongoPackStore(collection)
            if engine is None:
                engine = _LiveEngine(
                    conn, AgentEngineDiagnosisClient.from_env(), MongoLedgerStore(state_db)
                )
        else:
            packs_dir = Path(os.getenv("PACKS_DIR", "runs"))
            store = LocalFilePackStore(packs_dir) if packs_dir.exists() else _EmptyPackStore()

    app.dependency_overrides[get_store] = lambda: store
    if engine is not None:
        app.dependency_overrides[get_engine] = lambda: engine
    app.include_router(router)
    return app


app = create_app()

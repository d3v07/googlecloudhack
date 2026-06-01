import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from api.routes import PackStore, get_store, router
from controller.persistence import load_pack, read_pack
from controller.schemas import EvidencePack


class MongoPackStore:
    def __init__(self, collection: Any) -> None:
        self._col = collection

    def list_packs(self) -> list[EvidencePack]:
        docs = self._col.find(projection={"_id": False})
        return [EvidencePack.model_validate(doc) for doc in docs]

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return load_pack(self._col, run_id)


class LocalFilePackStore:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def list_packs(self) -> list[EvidencePack]:
        return [read_pack(p) for p in sorted(self._dir.glob("*.json"))]

    def get_pack(self, run_id: str) -> EvidencePack | None:
        path = self._dir / f"{run_id}.json"
        return read_pack(path) if path.exists() else None


class _EmptyPackStore:
    def list_packs(self) -> list[EvidencePack]:
        return []

    def get_pack(self, run_id: str) -> EvidencePack | None:
        return None


def create_app(store: PackStore | None = None) -> FastAPI:
    app = FastAPI(title="GCRAH Evidence Pack API")

    if store is None:
        packs_dir = Path(os.getenv("PACKS_DIR", "runs"))
        store = LocalFilePackStore(packs_dir) if packs_dir.exists() else _EmptyPackStore()

    app.dependency_overrides[get_store] = lambda: store
    app.include_router(router)
    return app


app = create_app()

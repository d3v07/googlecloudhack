from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException

from controller.schemas import EvidencePack

router = APIRouter()


class PackStore(Protocol):
    def list_packs(self) -> list[EvidencePack]: ...
    def get_pack(self, run_id: str) -> EvidencePack | None: ...


def get_store() -> PackStore:
    raise NotImplementedError("store not configured")


StoreDep = Annotated[PackStore, Depends(get_store)]


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/packs")
def list_packs(store: StoreDep) -> list[dict]:
    return [pack.model_dump(mode="json") for pack in store.list_packs()]


@router.get("/packs/{run_id}")
def get_pack(run_id: str, store: StoreDep) -> dict:
    pack = store.get_pack(run_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"pack '{run_id}' not found")
    return pack.model_dump(mode="json")

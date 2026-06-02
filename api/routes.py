import os
import secrets
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from controller.schemas import EvidencePack, PackStatus

router = APIRouter()


def require_write_token(x_api_token: Annotated[str | None, Header()] = None) -> None:
    """Gate the mutating endpoints behind a shared secret when RUN_API_TOKEN is set. No-op
    when it's unset (local dev / CI). Reads (/health, /packs) are always public."""
    expected = os.environ.get("RUN_API_TOKEN")
    if expected and not (x_api_token and secrets.compare_digest(x_api_token, expected)):
        raise HTTPException(status_code=401, detail="invalid or missing API token")


class PackStore(Protocol):
    def list_packs(self) -> list[EvidencePack]: ...
    def get_pack(self, run_id: str) -> EvidencePack | None: ...
    def save_pack(self, pack: EvidencePack) -> None: ...


class Engine(Protocol):
    """Executes the remediation phases against the live target. diagnose() is read-only;
    apply_and_verify() performs the human-approved index mutation; reject() is a no-op record."""

    async def diagnose(self, run_id: str) -> EvidencePack: ...
    async def apply_and_verify(
        self, pack: EvidencePack, *, approver: str = "dashboard-operator", note: str = ""
    ) -> EvidencePack: ...
    def reject(
        self, pack: EvidencePack, *, approver: str = "dashboard-operator", note: str = ""
    ) -> EvidencePack: ...


def get_store() -> PackStore:
    raise NotImplementedError("store not configured")


def get_engine() -> Engine:
    raise NotImplementedError("engine not configured")


StoreDep = Annotated[PackStore, Depends(get_store)]
EngineDep = Annotated[Engine, Depends(get_engine)]


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


class RunRequest(BaseModel):
    run_id: str | None = None


@router.post("/run", dependencies=[Depends(require_write_token)])
async def trigger_run(store: StoreDep, engine: EngineDep, body: RunRequest | None = None) -> dict:
    """Trigger a DIAGNOSE-only live run over the preset demo fixture (#37). Returns a
    DIAGNOSED pack — NO database mutation happens here. The recommended index is applied only
    after a human approves via POST /packs/{run_id}/decision. Synchronous (a few seconds,
    longer on a cold start); pass {"run_id": "..."} only to pin the id."""
    run_id = (body.run_id if body else None) or f"run-{uuid4().hex[:8]}"
    pack = await engine.diagnose(run_id)
    store.save_pack(pack)
    return pack.model_dump(mode="json")


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    evidence_hash: str
    approver: str = "dashboard-operator"
    note: str = ""


@router.post("/packs/{run_id}/decision", dependencies=[Depends(require_write_token)])
async def decide_pack(run_id: str, body: DecisionRequest, store: StoreDep, engine: EngineDep):
    """The dashboard's approve/reject endpoint. On approve the recommended index is applied
    and the fix verified (the human-gated mutation); on reject the decision is recorded with
    no mutation. Returns the updated pack; 404 not_found / 409 already_decided |
    stale_evidence_hash otherwise. `approver`/`note` are accepted for the audit trail."""
    pack = store.get_pack(run_id)
    if pack is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    if pack.decision is not None or pack.status is not PackStatus.DIAGNOSED:
        return JSONResponse(
            status_code=409, content={"error": "already_decided", "status": pack.status.value}
        )
    if body.evidence_hash != pack.evidence_hash:
        return JSONResponse(
            status_code=409,
            content={"error": "stale_evidence_hash", "current_hash": pack.evidence_hash},
        )
    if body.decision == "approve":
        updated = await engine.apply_and_verify(pack, approver=body.approver, note=body.note)
    else:
        updated = engine.reject(pack, approver=body.approver, note=body.note)
    store.save_pack(updated)
    return updated.model_dump(mode="json")

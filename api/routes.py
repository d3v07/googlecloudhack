from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from controller.phases import Phase, assert_phase_transition
from controller.schemas import Decision, DecisionAction, EvidencePack, PackStatus

router = APIRouter()


class PackStore(Protocol):
    def list_packs(self) -> list[EvidencePack]: ...
    def get_pack(self, run_id: str) -> EvidencePack | None: ...
    def save_pack(self, pack: EvidencePack) -> None: ...


class ApprovalRequest(BaseModel):
    evidence_hash: str


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


def _apply_decision(
    run_id: str, action: DecisionAction, body: ApprovalRequest, store: PackStore
) -> dict:
    pack = store.get_pack(run_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"pack '{run_id}' not found")
    if pack.status != PackStatus.DIAGNOSED:
        raise HTTPException(status_code=409, detail=f"pack is already in status '{pack.status}'")
    if body.evidence_hash != pack.evidence_hash:
        raise HTTPException(status_code=409, detail="evidence_hash mismatch")

    assert_phase_transition(Phase.DIAGNOSE, Phase.APPROVE)
    decision = Decision(action=action, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE)
    new_status = PackStatus.APPROVED if action == DecisionAction.APPROVE else PackStatus.REJECTED
    updated = EvidencePack.model_validate(
        {**pack.model_dump(mode="python"), "status": new_status, "decision": decision}
    )
    store.save_pack(updated)
    return updated.model_dump(mode="json")


@router.post("/packs/{run_id}/approve")
def approve_pack(run_id: str, body: ApprovalRequest, store: StoreDep) -> dict:
    return _apply_decision(run_id, DecisionAction.APPROVE, body, store)


@router.post("/packs/{run_id}/reject")
def reject_pack(run_id: str, body: ApprovalRequest, store: StoreDep) -> dict:
    return _apply_decision(run_id, DecisionAction.REJECT, body, store)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    evidence_hash: str
    approver: str = "dashboard-operator"
    note: str = ""


@router.post("/packs/{run_id}/decision")
def decide_pack(run_id: str, body: DecisionRequest, store: StoreDep):
    """Single approve/reject endpoint the dashboard (#26) calls. Returns the updated
    pack on success; 404 not_found / 409 stale_evidence_hash | already_decided otherwise.
    `approver`/`note` are accepted for the audit trail (not yet persisted on Decision)."""
    pack = store.get_pack(run_id)
    if pack is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    if pack.status != PackStatus.DIAGNOSED:
        return JSONResponse(
            status_code=409, content={"error": "already_decided", "status": pack.status.value}
        )
    if body.evidence_hash != pack.evidence_hash:
        return JSONResponse(
            status_code=409,
            content={"error": "stale_evidence_hash", "current_hash": pack.evidence_hash},
        )
    action = DecisionAction.APPROVE if body.decision == "approve" else DecisionAction.REJECT
    return _apply_decision(run_id, action, ApprovalRequest(evidence_hash=body.evidence_hash), store)


class RunRequest(BaseModel):
    run_id: str | None = None


class Runner(Protocol):
    async def run(self, run_id: str) -> EvidencePack: ...


def get_runner() -> Runner:
    raise NotImplementedError("runner not configured")


RunnerDep = Annotated[Runner, Depends(get_runner)]


@router.post("/run")
async def trigger_run(store: StoreDep, runner: RunnerDep, body: RunRequest | None = None) -> dict:
    """Trigger a live agent run over the preset demo fixture (#37): runs the deterministic
    DIAGNOSE→VERIFY orchestrator, persists the resulting pack, and returns it. Synchronous —
    the live index build makes this a few-seconds call (longer on a cold start). `narrative`
    may be absent. No request body is needed; pass {"run_id": "..."} only to pin the id."""
    run_id = (body.run_id if body else None) or f"run-{uuid4().hex[:8]}"
    pack = await runner.run(run_id)
    store.save_pack(pack)
    return pack.model_dump(mode="json")

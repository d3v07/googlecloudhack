from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException
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

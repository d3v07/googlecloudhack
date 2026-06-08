import os
import secrets
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.auth import ROLE_DBRE, optional_dbre_identity, require_role
from api.memory import MemoryResponse, VoyageMemoryService, get_memory_service
from api.workload import WorkloadService, get_workload_service_optional
from controller.auth import Identity
from controller.orchestrator import ApprovalTicket, issue_approval_ticket
from controller.workload import WorkloadSpecError, assert_safe_query
from controller.schemas import ApprovalGateState, EvidencePack, PackStatus

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


@dataclass(frozen=True)
class QueryInput:
    """A real captured query to diagnose, in place of the preset demo fixture."""

    query_filter: dict
    query_sort: list[tuple[str, int]]
    limit: int


class Engine(Protocol):
    """Executes the remediation phases against the live target. diagnose() is read-only;
    apply_and_verify() performs the human-approved index mutation; reject() is a no-op record."""

    async def diagnose(self, run_id: str, query: QueryInput | None = None) -> EvidencePack: ...
    async def apply_and_verify(
        self, pack: EvidencePack, ticket: ApprovalTicket
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
MemoryDep = Annotated[VoyageMemoryService, Depends(get_memory_service)]


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


@router.get("/packs/{run_id}/memory", response_model=MemoryResponse)
def get_pack_memory(
    run_id: str,
    store: StoreDep,
    memory: MemoryDep,
    _identity: Annotated[Identity, Depends(require_role(ROLE_DBRE))],
) -> MemoryResponse:
    pack = store.get_pack(run_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"pack '{run_id}' not found")
    return memory.lookup(pack)


class RunRequest(BaseModel):
    run_id: str | None = None
    captured_query_id: str | None = None


WorkloadOptionalDep = Annotated[WorkloadService | None, Depends(get_workload_service_optional)]


@router.post("/run", dependencies=[Depends(require_write_token)])
async def trigger_run(
    store: StoreDep,
    engine: EngineDep,
    workload: WorkloadOptionalDep,
    _identity: Annotated[Identity | None, Depends(optional_dbre_identity)],
    body: RunRequest | None = None,
) -> dict:
    """Trigger a DIAGNOSE-only run. With a captured_query_id, diagnoses that real captured query
    against its natural plan; otherwise the preset demo fixture. NO mutation happens here — a human
    approves via POST /packs/{run_id}/decision before any index is applied. The DBRE role is
    enforced when SESSION_SECRET is configured."""
    run_id = (body.run_id if body else None) or f"run-{uuid4().hex[:8]}"
    captured_id = body.captured_query_id if body else None
    query: QueryInput | None = None
    if captured_id is not None:
        if workload is None:
            raise HTTPException(status_code=503, detail="workload service not configured")
        captured = workload.get_captured(captured_id)
        if captured is None:
            raise HTTPException(status_code=404, detail=f"captured query '{captured_id}' not found")
        spec = captured["query"]
        query = QueryInput(
            query_filter=dict(spec["filter"]),
            query_sort=[(field, int(direction)) for field, direction in spec["sort"]],
            limit=int(spec["limit"]),
        )
        try:
            assert_safe_query(query.query_filter, query.query_sort)
        except WorkloadSpecError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # A query with neither a filter nor a sort has no equality/sort/range structure, so the
        # ESR rule yields an empty index — undiagnosable. Reject cleanly rather than letting the
        # frozen Recommendation(min_length=1) raise a 500 deep in the controller/agent path.
        if not query.query_filter and not query.query_sort:
            raise HTTPException(
                status_code=422,
                detail="captured query has no filter or sort to index; nothing to diagnose",
            )
    pack = await engine.diagnose(run_id, query)
    store.save_pack(pack)
    return pack.model_dump(mode="json")


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    evidence_hash: str
    approver: str = "dashboard-operator"
    note: str = ""


@router.post("/packs/{run_id}/decision", dependencies=[Depends(require_write_token)])
async def decide_pack(
    run_id: str,
    body: DecisionRequest,
    store: StoreDep,
    engine: EngineDep,
    identity: Annotated[Identity | None, Depends(optional_dbre_identity)],
):
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
    if (
        pack.approval_gate is None
        or pack.approval_gate.state is not ApprovalGateState.PENDING_APPROVAL
    ):
        return JSONResponse(
            status_code=409,
            content={"error": "approval_gate", "detail": "pending approval gate required"},
        )
    # Authoritative approver: the verified DBRE session when configured, else the request body
    # (local/CI). The dashboard never decides who approved.
    approver = identity.display_name if identity is not None else body.approver
    if body.decision == "approve":
        try:
            ticket = issue_approval_ticket(
                pack,
                evidence_hash=body.evidence_hash,
                approver=approver,
                note=body.note,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=409, content={"error": "approval_gate", "detail": str(exc)}
            )
        updated = await engine.apply_and_verify(pack, ticket)
    else:
        try:
            updated = engine.reject(pack, approver=approver, note=body.note)
        except ValueError as exc:
            return JSONResponse(
                status_code=409, content={"error": "approval_gate", "detail": str(exc)}
            )
    store.save_pack(updated)
    return updated.model_dump(mode="json")

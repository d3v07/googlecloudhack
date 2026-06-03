from enum import StrEnum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from controller.phases import Phase


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


class AgentTraceStage(StrEnum):
    GATE = "gate"
    DETECT = "detect"
    DIAGNOSE = "diagnose"
    CANDIDATE = "candidate"
    RATIONALE = "rationale"
    APPROVE = "approve"
    APPLY = "apply"
    VERIFY = "verify"


class AgentTraceActor(StrEnum):
    APPROVAL_GATE = "approval_gate"
    AGENT_ENGINE = "agent_engine"
    DETERMINISTIC_CONTROLLER = "deterministic_controller"
    HUMAN = "human"


class AgentTraceStatus(StrEnum):
    OK = "ok"
    DRIFT = "drift"
    FAILED = "failed"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=repr))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


class EvidenceMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    docs_examined: int = Field(ge=0)
    docs_returned: int = Field(ge=0)
    millis: float = Field(ge=0)
    total_keys_examined: int = Field(ge=0)
    stages: tuple[str, ...] = ()

    @computed_field(return_type=bool)
    @property
    def has_blocking_sort(self) -> bool:
        return "SORT" in self.stages

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        # pydantic v2 omits computed_fields from model_json_schema; inject manually
        schema = handler(schema)
        schema.setdefault("properties", {})["has_blocking_sort"] = {
            "readOnly": True,
            "title": "Has Blocking Sort",
            "type": "boolean",
        }
        return schema


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: Mapping[str, Any] | str
    explain_plan: Mapping[str, Any]
    metrics: EvidenceMetrics

    @field_validator("query", "explain_plan", mode="after")
    @classmethod
    def freeze_payload(cls, value: Any) -> Any:
        return _freeze(value)

    @field_serializer("query", "explain_plan")
    def serialize_payload(self, value: Any) -> Any:
        return _thaw(value)


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    problem: str = Field(min_length=1)
    severity: Severity
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class Recommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    # ordered (field, direction) pairs — field ORDER is the recommendation (ESR), so a
    # dict would lose it under sorted-key hashing/serialization. Pairs stay ordered.
    index_spec: tuple[tuple[str, int], ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: DecisionAction
    evidence_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    phase: Phase


class Diagnosis(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding: Finding
    recommendation: Recommendation


class PackStatus(StrEnum):
    DIAGNOSED = "diagnosed"
    APPROVED = "approved"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ApprovalGateState(StrEnum):
    COLLECTING_EVIDENCE = "collecting_evidence"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    VERIFIED = "verified"


class PhaseTransition(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_phase: Phase | None = None
    to_phase: Phase
    note: str = ""


class AgentTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: AgentTraceStage
    actor: AgentTraceActor
    status: AgentTraceStatus
    summary: str = Field(min_length=1)
    tool: str | None = None
    ledger_ref: str | None = None


class ApprovalGate(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_id: str = Field(min_length=1)
    state: ApprovalGateState
    required_hash: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    approved_hash: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    approver: str | None = None
    mutation_allowed: bool = False
    ledger_ref: str | None = None


class EvidencePack(BaseModel):
    """Versioned, dashboard-facing run record. THE contract #10 consumes — frozen at v1.
    Read it via the published JSON Schema + the read endpoint; never import this module."""

    model_config = ConfigDict(frozen=True)

    version: Literal["v1"] = "v1"
    # constrained charset: run_id flows into a filesystem path (LocalFilePackStore) and a
    # Mongo query key, and POST /run accepts a client-supplied id — the pattern blocks
    # path traversal / injection at the contract boundary
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    namespace: str = Field(min_length=1)
    status: PackStatus
    before: Evidence
    after: Evidence | None = None
    finding: Finding
    recommendation: Recommendation
    decision: Decision | None = None
    phase_log: tuple[PhaseTransition, ...] = ()
    agent_trace: tuple[AgentTraceEvent, ...] = ()
    approval_gate: ApprovalGate | None = None
    evidence_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(min_length=1)

    narrative: str | None = None

    @model_validator(mode="after")
    def _evidence_hash_binds_before_and_recommendation(self) -> "EvidencePack":
        from controller.ledger import evidence_hash

        expected = evidence_hash({"evidence": self.before, "recommendation": self.recommendation})
        if self.evidence_hash != expected:
            raise ValueError(
                "evidence_hash must equal the hash of before-evidence and recommendation"
            )
        return self

    @model_validator(mode="after")
    def _decision_hash_binds_this_pack(self) -> "EvidencePack":
        if self.decision is not None and self.decision.evidence_hash != self.evidence_hash:
            raise ValueError("decision.evidence_hash must equal the pack's evidence_hash")
        return self

    @model_validator(mode="after")
    def _status_matches_decision_and_after(self) -> "EvidencePack":
        # status ⟺ (decision, after) must be internally consistent, so an impossible
        # pack (e.g. DIAGNOSED but already carrying a decision) can't slip past the
        # "already decided" guard and be decided a second time
        decided = self.decision is not None
        if self.status is PackStatus.DIAGNOSED:
            if decided or self.after is not None:
                raise ValueError("DIAGNOSED pack must have no decision and no after-evidence")
        elif self.status is PackStatus.REJECTED:
            if not decided or self.decision.action is not DecisionAction.REJECT:
                raise ValueError("REJECTED pack must carry a reject decision")
            if self.after is not None:
                raise ValueError("REJECTED pack must have no after-evidence")
        else:  # APPROVED | VERIFIED — applied, so an approve decision + after-evidence
            if not decided or self.decision.action is not DecisionAction.APPROVE:
                raise ValueError(f"{self.status.value} pack must carry an approve decision")
            if self.after is None:
                raise ValueError(f"{self.status.value} pack must have after-evidence")
        return self

    @model_validator(mode="after")
    def _approval_gate_matches_status(self) -> "EvidencePack":
        if self.approval_gate is None:
            return self
        gate = self.approval_gate
        if gate.required_hash is not None and gate.required_hash != self.evidence_hash:
            raise ValueError("approval_gate.required_hash must equal the pack's evidence_hash")
        if gate.approved_hash is not None and gate.approved_hash != self.evidence_hash:
            raise ValueError("approval_gate.approved_hash must equal the pack's evidence_hash")
        if gate.mutation_allowed:
            raise ValueError("persisted approval gate must not leave mutation_allowed=true")
        if self.status is PackStatus.DIAGNOSED:
            if gate.state is not ApprovalGateState.PENDING_APPROVAL:
                raise ValueError("DIAGNOSED pack must have a pending approval gate")
            if gate.required_hash is None or gate.approved_hash is not None:
                raise ValueError("pending approval gate must require only the current hash")
        elif self.status is PackStatus.REJECTED:
            if gate.state is not ApprovalGateState.REJECTED:
                raise ValueError("REJECTED pack must have a rejected approval gate")
            if gate.approver is None:
                raise ValueError("rejected approval gate must record the approver")
        elif self.status is PackStatus.VERIFIED:
            if gate.state is not ApprovalGateState.VERIFIED:
                raise ValueError("VERIFIED pack must have a verified approval gate")
            if gate.approved_hash is None or gate.approver is None:
                raise ValueError("verified approval gate must record the approved hash")
        else:
            if gate.state is not ApprovalGateState.APPROVED:
                raise ValueError("APPROVED pack must have an approved approval gate")
            if gate.approved_hash is None or gate.approver is None:
                raise ValueError("approved approval gate must record the approved hash")
        return self

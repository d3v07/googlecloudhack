"""DIAGNOSE → (human APPROVE) → VERIFY remediation flow, split so the database mutation
happens ONLY after an explicit human approval.

- run_diagnosis: read-only. Capture before-evidence (hinting the wrong index so the ESR
  trap is visible), derive the ESR recommendation, emit a DIAGNOSED pack — no decision,
  no mutation.
- apply_and_verify: the post-approval half. Apply the recommended index (the approved
  mutation) and measure the after-evidence.
- reject_pack: record a human rejection — no mutation, no after-evidence.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from controller.backends import Backend
from controller.diagnosis import diagnose
from controller.ledger_store import (
    APPLICATIONS,
    APPROVALS,
    CANDIDATES,
    EXPERIMENTS,
    SLOW_QUERIES,
    VERIFICATIONS,
    LedgerStore,
    record_id,
    write_application_records,
    write_diagnosis_records,
    write_gate_opened_record,
    write_rejection_records,
)
from controller.narrate import Narrator
from controller.pack import build_pack, pack_evidence_hash
from controller.phases import Phase, assert_phase_transition
from controller.schemas import (
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    ApprovalGate,
    ApprovalGateState,
    Decision,
    DecisionAction,
    Evidence,
    EvidencePack,
    PackStatus,
    PhaseTransition,
    Recommendation,
)

# fixture constants — match seed/seed_demo_fixture.py
INDEX_B_NAME = "esr_wrong_B"
INDEX_C_NAME = "esr_right_C"


@dataclass(frozen=True)
class DiagnosisAdvice:
    source: str
    narrative: str
    proposed_index: tuple[tuple[str, int], ...] = ()
    trace: tuple[AgentTraceEvent, ...] = ()


@dataclass(frozen=True)
class AgentDiagnosisResult:
    source: str
    before: Evidence
    narrative: str
    proposed_index: tuple[tuple[str, int], ...] = ()
    trace: tuple[AgentTraceEvent, ...] = ()


@dataclass(frozen=True)
class ApprovalTicket:
    run_id: str
    evidence_hash: str
    approver: str
    note: str
    gate_id: str


class DiagnosisAdvisor(Protocol):
    async def advise(
        self,
        *,
        run_id: str,
        namespace: str,
        query_filter: dict,
        query_sort: list[tuple[str, int]],
        limit: int,
        before,
    ) -> DiagnosisAdvice: ...


class DiagnosisAgent(Protocol):
    async def diagnose(
        self,
        *,
        run_id: str,
        namespace: str,
        query_filter: dict,
        query_sort: list[tuple[str, int]],
        limit: int,
    ) -> AgentDiagnosisResult: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _maybe_narrate(pack: EvidencePack, narrator: Narrator | None) -> EvidencePack:
    if narrator is None:
        return pack
    # narrate may do network I/O (Gemini) — keep it off the event loop
    narrative = await asyncio.to_thread(narrator.narrate, pack)
    return pack.model_copy(update={"narrative": narrative})


def _recommended_index_name(recommendation: Recommendation) -> str:
    parts = "_".join(f"{field}{direction}" for field, direction in recommendation.index_spec)
    return f"gcrah_rec_{parts}"[:120]


def _key_pattern_matches(
    key_pattern: Any,
    index_spec: tuple[tuple[str, int], ...],
) -> bool:
    if not isinstance(key_pattern, Mapping):
        return False
    try:
        observed = tuple((str(field), int(direction)) for field, direction in key_pattern.items())
    except (TypeError, ValueError):
        return False
    return observed == tuple((field, int(direction)) for field, direction in index_spec)


def _plan_evidences_index(
    plan: Any,
    index_spec: tuple[tuple[str, int], ...],
    index_name: str,
) -> bool:
    if isinstance(plan, Mapping):
        if plan.get("indexName") == index_name:
            return True
        if _key_pattern_matches(plan.get("keyPattern"), index_spec):
            return True
        return any(_plan_evidences_index(value, index_spec, index_name) for value in plan.values())
    if isinstance(plan, list | tuple):
        return any(_plan_evidences_index(value, index_spec, index_name) for value in plan)
    return False


def _metric_improved(before: Evidence, after: Evidence) -> bool:
    return (
        after.metrics.total_keys_examined < before.metrics.total_keys_examined
        or after.metrics.docs_examined < before.metrics.docs_examined
        or after.metrics.millis < before.metrics.millis
    )


def _verification_checks(
    before: Evidence,
    after: Evidence,
    recommendation: Recommendation,
    index_name: str,
) -> dict[str, bool]:
    return {
        "sort_removed": not after.metrics.has_blocking_sort,
        "selected_index_used": _plan_evidences_index(
            after.explain_plan, recommendation.index_spec, index_name
        ),
        "metric_improved": _metric_improved(before, after),
    }


def _verification_summary(checks: dict[str, bool]) -> str:
    if all(checks.values()):
        return (
            "Verified ESR fix: SORT removed, recommended index evidenced, "
            "and at least one metric improved."
        )
    failed: list[str] = []
    if not checks["sort_removed"]:
        failed.append("blocking SORT remains")
    if not checks["selected_index_used"]:
        failed.append("recommended index not evidenced in winning plan")
    if not checks["metric_improved"]:
        failed.append("no keys/docs/millis metric improved")
    return "Verification failed strict checks: " + "; ".join(failed) + "."


def _agent_phase_note(
    advice: DiagnosisAdvice | AgentDiagnosisResult | None,
    deterministic_index: tuple[tuple[str, int], ...],
) -> str:
    if advice is None:
        return ""
    if not advice.proposed_index:
        return f"agent_engine={advice.source}; proposed_index=none"
    if advice.proposed_index == deterministic_index:
        return f"agent_engine={advice.source}; proposed_index=accepted"
    return (
        f"agent_engine={advice.source}; proposed_index=ignored; "
        f"agent_proposed={list(advice.proposed_index)}"
    )


def _ledger_ref(collection: str, run_id: str, event: str) -> str:
    return f"{collection}/{record_id(run_id, event)}"


def _gate_id(run_id: str) -> str:
    return record_id(run_id, "gate")


def _gate_ledger_ref(run_id: str, event: str) -> str:
    return _ledger_ref(APPROVALS, run_id, f"gate:{event}")


def _approval_gate(
    *,
    run_id: str,
    state: ApprovalGateState,
    required_hash: str | None,
    approved_hash: str | None = None,
    approver: str | None = None,
    ledger_event: str,
    ledger_ref: str | None = None,
) -> ApprovalGate:
    return ApprovalGate(
        gate_id=_gate_id(run_id),
        state=state,
        required_hash=required_hash,
        approved_hash=approved_hash,
        approver=approver,
        mutation_allowed=False,
        ledger_ref=ledger_ref or _gate_ledger_ref(run_id, ledger_event),
    )


def _gate_trace(run_id: str, event: str, summary: str) -> AgentTraceEvent:
    return AgentTraceEvent(
        stage=AgentTraceStage.GATE,
        actor=AgentTraceActor.APPROVAL_GATE,
        status=AgentTraceStatus.OK,
        summary=summary,
        tool="approval_gate",
        ledger_ref=_gate_ledger_ref(run_id, event),
    )


def issue_approval_ticket(
    pack: EvidencePack,
    *,
    evidence_hash: str,
    approver: str,
    note: str = "",
) -> ApprovalTicket:
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only approve a DIAGNOSED pack, got '{pack.status}'")
    if pack.approval_gate is None:
        raise ValueError("approval ticket requires a pack with an approval gate")
    if pack.approval_gate.state is not ApprovalGateState.PENDING_APPROVAL:
        raise ValueError("approval ticket requires a pending approval gate")
    if pack.approval_gate.required_hash != evidence_hash:
        raise ValueError("approval ticket hash does not match the pending approval gate")
    if pack.evidence_hash != evidence_hash:
        raise ValueError("approval ticket hash does not match the pack evidence hash")
    return ApprovalTicket(
        run_id=pack.run_id,
        evidence_hash=evidence_hash,
        approver=approver,
        note=note,
        gate_id=pack.approval_gate.gate_id,
    )


def _assert_ticket_allows_apply(pack: EvidencePack, ticket: ApprovalTicket) -> None:
    if pack.approval_gate is None:
        raise ValueError("approval ticket requires a pack with an approval gate")
    if ticket.run_id != pack.run_id:
        raise ValueError("approval ticket run_id does not match the pack")
    if ticket.gate_id != pack.approval_gate.gate_id:
        raise ValueError("approval ticket gate_id does not match the pack")
    if ticket.evidence_hash != pack.evidence_hash:
        raise ValueError("approval ticket hash does not match the pack evidence hash")
    if pack.approval_gate.state is not ApprovalGateState.PENDING_APPROVAL:
        raise ValueError("approval ticket requires a pending approval gate")


def _validation_trace(
    *,
    source: str,
    proposed_index: tuple[tuple[str, int], ...],
    deterministic_index: tuple[tuple[str, int], ...],
) -> AgentTraceEvent:
    if not proposed_index:
        return AgentTraceEvent(
            stage=AgentTraceStage.DIAGNOSE,
            actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
            status=AgentTraceStatus.DRIFT,
            summary=f"{source} returned no index; deterministic ESR selected the winner.",
            tool="validate_agent_diagnosis",
        )
    if proposed_index == deterministic_index:
        return AgentTraceEvent(
            stage=AgentTraceStage.DIAGNOSE,
            actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
            status=AgentTraceStatus.OK,
            summary="Agent Engine proposal matched deterministic ESR validation.",
            tool="validate_agent_diagnosis",
        )
    return AgentTraceEvent(
        stage=AgentTraceStage.DIAGNOSE,
        actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
        status=AgentTraceStatus.DRIFT,
        summary="Agent Engine proposal drifted; deterministic ESR recommendation was used.",
        tool="validate_agent_diagnosis",
    )


def _diagnosis_trace(
    *,
    run_id: str,
    result: AgentDiagnosisResult | None,
    deterministic_index: tuple[tuple[str, int], ...],
    evidence_hash: str,
) -> tuple[AgentTraceEvent, ...]:
    trace: list[AgentTraceEvent] = [
        _gate_trace(
            run_id,
            "opened",
            "/run created a gated read-only run; mutation requires matching evidence hash approval.",
        )
    ]
    if result is None:
        trace.append(
            AgentTraceEvent(
                stage=AgentTraceStage.DIAGNOSE,
                actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
                status=AgentTraceStatus.OK,
                summary="Deterministic controller produced the local diagnosis.",
                tool="diagnose",
            )
        )
        trace.append(
            _gate_trace(
                run_id,
                "pending",
                f"Approval gate is pending for evidence hash {evidence_hash[:12]}.",
            )
        )
        return tuple(trace)
    refs = {
        AgentTraceStage.DETECT: _ledger_ref(SLOW_QUERIES, run_id, "diagnose:slow_query"),
        AgentTraceStage.CANDIDATE: _ledger_ref(CANDIDATES, run_id, "diagnose:candidate"),
        AgentTraceStage.DIAGNOSE: _ledger_ref(EXPERIMENTS, run_id, "diagnose:before"),
    }
    trace.extend(
        event.model_copy(update={"ledger_ref": event.ledger_ref or refs.get(event.stage)})
        for event in result.trace
    )
    trace.append(
        _validation_trace(
            source=result.source,
            proposed_index=result.proposed_index,
            deterministic_index=deterministic_index,
        )
    )
    trace.append(
        _gate_trace(
            run_id,
            "pending",
            f"Approval gate is pending for evidence hash {evidence_hash[:12]}.",
        )
    )
    return tuple(trace)


async def run_diagnosis(
    backend: Backend,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    created_at: str | None = None,
    narrator: Narrator | None = None,
    advisor: DiagnosisAdvisor | None = None,
    ledger: LedgerStore | None = None,
    current_index: str | None = INDEX_B_NAME,
) -> EvidencePack:
    """Read-only DIAGNOSE phase. Returns a DIAGNOSED pack with NO decision and NO mutation —
    the human approves (via the API) before anything is applied. The before-explain hints the
    wrong index so the ESR blocking-sort trap is visible in the evidence."""
    created_at = created_at or _now()
    write_gate_opened_record(
        ledger,
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
    )
    before = await backend.explain(query_filter, query_sort, limit, hint=current_index)
    advice = (
        await advisor.advise(
            run_id=run_id,
            namespace=namespace,
            query_filter=query_filter,
            query_sort=query_sort,
            limit=limit,
            before=before,
        )
        if advisor is not None
        else None
    )
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=before.metrics.has_blocking_sort,
        current_index=current_index,
    )
    pack_hash = pack_evidence_hash(before, diagnosis.recommendation)
    pack = build_pack(
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
        before=before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
        status=PackStatus.DIAGNOSED,
        phase_log=[
            PhaseTransition(
                from_phase=None,
                to_phase=Phase.DIAGNOSE,
                note=_agent_phase_note(advice, diagnosis.recommendation.index_spec),
            )
        ],
        narrative=advice.narrative if advice is not None else None,
        agent_trace=_diagnosis_trace(
            run_id=run_id,
            result=None
            if advice is None
            else AgentDiagnosisResult(
                source=advice.source,
                before=before,
                narrative=advice.narrative,
                proposed_index=advice.proposed_index,
                trace=advice.trace,
            ),
            deterministic_index=diagnosis.recommendation.index_spec,
            evidence_hash=pack_hash,
        ),
        approval_gate=_approval_gate(
            run_id=run_id,
            state=ApprovalGateState.PENDING_APPROVAL,
            required_hash=pack_hash,
            ledger_event="pending",
        ),
    )
    pack = await _maybe_narrate(pack, narrator)
    write_diagnosis_records(
        ledger,
        pack=pack,
        query_filter=query_filter,
        query_sort=query_sort,
        limit=limit,
        current_index=current_index,
    )
    return pack


async def run_agent_diagnosis(
    agent: DiagnosisAgent,
    *,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    created_at: str | None = None,
    narrator: Narrator | None = None,
    ledger: LedgerStore | None = None,
    current_index: str | None = INDEX_B_NAME,
) -> EvidencePack:
    created_at = created_at or _now()
    write_gate_opened_record(
        ledger,
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
    )
    result = await agent.diagnose(
        run_id=run_id,
        namespace=namespace,
        query_filter=query_filter,
        query_sort=query_sort,
        limit=limit,
    )
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=result.before.metrics.has_blocking_sort,
        current_index=current_index,
    )
    pack_hash = pack_evidence_hash(result.before, diagnosis.recommendation)
    pack = build_pack(
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
        before=result.before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
        status=PackStatus.DIAGNOSED,
        phase_log=[
            PhaseTransition(
                from_phase=None,
                to_phase=Phase.DIAGNOSE,
                note=_agent_phase_note(result, diagnosis.recommendation.index_spec),
            )
        ],
        agent_trace=_diagnosis_trace(
            run_id=run_id,
            result=result,
            deterministic_index=diagnosis.recommendation.index_spec,
            evidence_hash=pack_hash,
        ),
        approval_gate=_approval_gate(
            run_id=run_id,
            state=ApprovalGateState.PENDING_APPROVAL,
            required_hash=pack_hash,
            ledger_event="pending",
        ),
        narrative=result.narrative,
    )
    pack = await _maybe_narrate(pack, narrator)
    write_diagnosis_records(
        ledger,
        pack=pack,
        query_filter=query_filter,
        query_sort=query_sort,
        limit=limit,
        current_index=current_index,
        source="agent_engine_tool",
    )
    return pack


async def apply_and_verify(
    backend: Backend,
    pack: EvidencePack,
    approval_ticket: ApprovalTicket,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    narrator: Narrator | None = None,
    ledger: LedgerStore | None = None,
) -> EvidencePack:
    """Post-approval APPLY + VERIFY. Applies the recommended index (the human-approved
    mutation) and captures after-evidence. VERIFIED only if strict evidence checks pass:
    no blocking sort, selected index evidenced, and at least one metric improves. The
    evidence_hash is unchanged: it bound (before, recommendation) at diagnosis and neither
    changed, so the approved hash still holds."""
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only apply+verify a DIAGNOSED pack, got '{pack.status}'")
    _assert_ticket_allows_apply(pack, approval_ticket)

    phase_log = list(pack.phase_log)
    assert_phase_transition(Phase.DIAGNOSE, Phase.APPROVE)
    phase_log.append(PhaseTransition(from_phase=Phase.DIAGNOSE, to_phase=Phase.APPROVE))
    decision = Decision(
        action=DecisionAction.APPROVE, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE
    )

    assert_phase_transition(Phase.APPROVE, Phase.VERIFY)
    phase_log.append(PhaseTransition(from_phase=Phase.APPROVE, to_phase=Phase.VERIFY))
    agent_trace = [
        *pack.agent_trace,
        AgentTraceEvent(
            stage=AgentTraceStage.APPROVE,
            actor=AgentTraceActor.HUMAN,
            status=AgentTraceStatus.OK,
            summary=f"Approved by {approval_ticket.approver}.",
            ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:approval"),
        ),
        AgentTraceEvent(
            stage=AgentTraceStage.GATE,
            actor=AgentTraceActor.APPROVAL_GATE,
            status=AgentTraceStatus.OK,
            summary="Approval gate issued a one-time apply ticket.",
            tool="approval_gate",
            ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:approval"),
        ),
    ]

    index_keys = list(pack.recommendation.index_spec)
    index_name = _recommended_index_name(pack.recommendation)
    await backend.apply_index(index_keys, index_name)
    agent_trace.append(
        AgentTraceEvent(
            stage=AgentTraceStage.APPLY,
            actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
            status=AgentTraceStatus.OK,
            summary=f"Applied approved index {index_name}.",
            tool="apply_index",
            ledger_ref=_ledger_ref(APPLICATIONS, pack.run_id, "approve:application"),
        )
    )
    # hint by key pattern so verify uses the recommended index even if it already existed
    # under another name (the apply was a conflict-absorbed no-op)
    after = await backend.explain(query_filter, query_sort, limit, hint=index_keys)

    checks = _verification_checks(pack.before, after, pack.recommendation, index_name)
    status = PackStatus.VERIFIED if all(checks.values()) else PackStatus.APPROVED
    agent_trace.append(
        AgentTraceEvent(
            stage=AgentTraceStage.VERIFY,
            actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
            status=AgentTraceStatus.OK
            if status is PackStatus.VERIFIED
            else AgentTraceStatus.FAILED,
            summary=_verification_summary(checks),
            tool="explain",
            ledger_ref=_ledger_ref(VERIFICATIONS, pack.run_id, "verify:verification"),
        )
    )
    updated = build_pack(
        run_id=pack.run_id,
        namespace=pack.namespace,
        created_at=pack.created_at,
        before=pack.before,
        finding=pack.finding,
        recommendation=pack.recommendation,
        status=status,
        after=after,
        decision=decision,
        phase_log=phase_log,
        agent_trace=agent_trace,
        approval_gate=_approval_gate(
            run_id=pack.run_id,
            state=ApprovalGateState.VERIFIED
            if status is PackStatus.VERIFIED
            else ApprovalGateState.APPROVED,
            required_hash=pack.evidence_hash,
            approved_hash=approval_ticket.evidence_hash,
            approver=approval_ticket.approver,
            ledger_event="approval",
            ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:approval"),
        ),
        narrative=pack.narrative,
    )
    updated = await _maybe_narrate(updated, narrator)
    write_application_records(
        ledger,
        pack=updated,
        approver=approval_ticket.approver,
        note=approval_ticket.note,
        index_name=index_name,
    )
    return updated


def reject_pack(
    pack: EvidencePack,
    *,
    approver: str = "dashboard-operator",
    note: str = "",
    ledger: LedgerStore | None = None,
) -> EvidencePack:
    """Record a human rejection — no mutation, no after-evidence."""
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only reject a DIAGNOSED pack, got '{pack.status}'")
    if pack.approval_gate is None:
        raise ValueError("can only reject a pack with an approval gate")
    if pack.approval_gate.state is not ApprovalGateState.PENDING_APPROVAL:
        raise ValueError("can only reject a pack with a pending approval gate")
    assert_phase_transition(Phase.DIAGNOSE, Phase.APPROVE)
    decision = Decision(
        action=DecisionAction.REJECT, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE
    )
    rejected = build_pack(
        run_id=pack.run_id,
        namespace=pack.namespace,
        created_at=pack.created_at,
        before=pack.before,
        finding=pack.finding,
        recommendation=pack.recommendation,
        status=PackStatus.REJECTED,
        decision=decision,
        phase_log=[
            *pack.phase_log,
            PhaseTransition(from_phase=Phase.DIAGNOSE, to_phase=Phase.APPROVE),
        ],
        agent_trace=[
            *pack.agent_trace,
            AgentTraceEvent(
                stage=AgentTraceStage.APPROVE,
                actor=AgentTraceActor.HUMAN,
                status=AgentTraceStatus.OK,
                summary=f"Rejected by {approver}.",
                ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:rejection"),
            ),
            AgentTraceEvent(
                stage=AgentTraceStage.GATE,
                actor=AgentTraceActor.APPROVAL_GATE,
                status=AgentTraceStatus.OK,
                summary="Approval gate closed as rejected.",
                tool="approval_gate",
                ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:rejection"),
            ),
        ],
        approval_gate=_approval_gate(
            run_id=pack.run_id,
            state=ApprovalGateState.REJECTED,
            required_hash=pack.evidence_hash,
            approver=approver,
            ledger_event="rejection",
            ledger_ref=_ledger_ref(APPROVALS, pack.run_id, "approve:rejection"),
        ),
        narrative=pack.narrative,
    )
    write_rejection_records(ledger, pack=rejected, approver=approver, note=note)
    return rejected

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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

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
    write_rejection_records,
)
from controller.narrate import Narrator
from controller.pack import build_pack
from controller.phases import Phase, assert_phase_transition
from controller.schemas import (
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
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
) -> tuple[AgentTraceEvent, ...]:
    if result is None:
        return ()
    refs = {
        AgentTraceStage.DETECT: _ledger_ref(SLOW_QUERIES, run_id, "diagnose:slow_query"),
        AgentTraceStage.CANDIDATE: _ledger_ref(CANDIDATES, run_id, "diagnose:candidate"),
        AgentTraceStage.DIAGNOSE: _ledger_ref(EXPERIMENTS, run_id, "diagnose:before"),
    }
    trace = [
        event.model_copy(update={"ledger_ref": event.ledger_ref or refs.get(event.stage)})
        for event in result.trace
    ]
    trace.append(
        _validation_trace(
            source=result.source,
            proposed_index=result.proposed_index,
            deterministic_index=deterministic_index,
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
    current_index: str = INDEX_B_NAME,
) -> EvidencePack:
    """Read-only DIAGNOSE phase. Returns a DIAGNOSED pack with NO decision and NO mutation —
    the human approves (via the API) before anything is applied. The before-explain hints the
    wrong index so the ESR blocking-sort trap is visible in the evidence."""
    created_at = created_at or _now()
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
    current_index: str = INDEX_B_NAME,
) -> EvidencePack:
    created_at = created_at or _now()
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
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    narrator: Narrator | None = None,
    approver: str = "dashboard-operator",
    note: str = "",
    ledger: LedgerStore | None = None,
) -> EvidencePack:
    """Post-approval APPLY + VERIFY. Applies the recommended index (the human-approved
    mutation) and captures after-evidence. VERIFIED if the blocking sort is gone, else
    APPROVED (applied, didn't help). evidence_hash is unchanged: it bound (before,
    recommendation) at diagnosis and neither changed, so the approved hash still holds."""
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only apply+verify a DIAGNOSED pack, got '{pack.status}'")

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
            summary=f"Approved by {approver}.",
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

    status = PackStatus.VERIFIED if not after.metrics.has_blocking_sort else PackStatus.APPROVED
    agent_trace.append(
        AgentTraceEvent(
            stage=AgentTraceStage.VERIFY,
            actor=AgentTraceActor.DETERMINISTIC_CONTROLLER,
            status=AgentTraceStatus.OK
            if status is PackStatus.VERIFIED
            else AgentTraceStatus.FAILED,
            summary="Verified ESR fix."
            if status is PackStatus.VERIFIED
            else "Verification still has a blocking sort.",
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
        narrative=pack.narrative,
    )
    updated = await _maybe_narrate(updated, narrator)
    write_application_records(
        ledger,
        pack=updated,
        approver=approver,
        note=note,
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
        ],
        narrative=pack.narrative,
    )
    write_rejection_records(ledger, pack=rejected, approver=approver, note=note)
    return rejected

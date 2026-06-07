"""Unit tests for controller/orchestrator.py using FakeBackend (no I/O)."""

import asyncio

import pytest

from controller.backends import FakeBackend
from controller.ledger_store import CANDIDATES, EXPERIMENTS, FakeLedgerStore, SLOW_QUERIES
from controller.orchestrator import (
    AgentDiagnosisResult,
    ApprovalTicket,
    DiagnosisAdvice,
    apply_and_verify,
    issue_approval_ticket,
    reject_pack,
    run_agent_diagnosis,
    run_diagnosis,
)
from controller.pack import pack_evidence_hash
from controller.phases import InvalidPhaseTransition, Phase, assert_phase_transition
from controller.schemas import (
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    ApprovalGateState,
    DecisionAction,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    PackStatus,
)

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
NAMESPACE = "sample_supplies.sales_agent_demo"
RUN_ID = "test-run-1"
CREATED_AT = "2026-06-01T00:00:00Z"
WRONG_INDEX = {"storeLocation": 1, "customer.age": 1, "saleDate": -1}
RIGHT_INDEX = {"storeLocation": 1, "saleDate": -1, "customer.age": 1}


def _make_evidence(
    has_blocking_sort: bool,
    keys_examined: int | None = None,
    *,
    selected_index: bool = True,
    docs_examined: int = 20,
    millis: float | None = None,
) -> Evidence:
    keys = keys_examined if keys_examined is not None else (17000 if has_blocking_sort else 64)
    elapsed = millis if millis is not None else (41.0 if has_blocking_sort else 2.0)
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    ixscan = {
        "stage": "IXSCAN",
        "keyPattern": RIGHT_INDEX if selected_index and not has_blocking_sort else WRONG_INDEX,
        "indexName": "esr_right_C" if selected_index and not has_blocking_sort else "esr_wrong_B",
    }
    explain_plan = (
        {"stage": "FETCH", "inputStage": {"stage": "SORT", "inputStage": ixscan}}
        if has_blocking_sort
        else {"stage": "FETCH", "inputStage": ixscan}
    )
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan=explain_plan,
        metrics=EvidenceMetrics(
            docs_examined=docs_examined,
            docs_returned=20,
            millis=elapsed,
            total_keys_examined=keys,
            stages=stages,
        ),
    )


def _diagnose(backend: FakeBackend) -> EvidencePack:
    return asyncio.run(
        run_diagnosis(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )


class _WrongAdvisor:
    async def advise(self, **kwargs) -> DiagnosisAdvice:
        return DiagnosisAdvice(
            source="agent-engine-test",
            narrative="Agent proposes the obvious but wrong index.",
            proposed_index=(("storeLocation", 1), ("customer.age", 1), ("saleDate", -1)),
        )


class _NoIndexAdvisor:
    async def advise(self, **kwargs) -> DiagnosisAdvice:
        return DiagnosisAdvice(
            source="agent-engine-test",
            narrative="Agent explains the blocking sort without proposing keys.",
        )


class _CorrectAdvisor:
    async def advise(self, **kwargs) -> DiagnosisAdvice:
        return DiagnosisAdvice(
            source="agent-engine-test",
            narrative="Agent proposes the same ESR winner.",
            proposed_index=(("storeLocation", 1), ("saleDate", -1), ("customer.age", 1)),
        )


class _AgentDiagnosis:
    def __init__(
        self,
        *,
        before: Evidence,
        proposed_index=(("storeLocation", 1), ("saleDate", -1), ("customer.age", 1)),
    ) -> None:
        self.before = before
        self.proposed_index = proposed_index

    async def diagnose(self, **kwargs) -> AgentDiagnosisResult:
        return AgentDiagnosisResult(
            source="agent-engine-test",
            before=self.before,
            narrative="Agent Engine measured the blocking sort and recommended ESR index C.",
            proposed_index=self.proposed_index,
            trace=(
                AgentTraceEvent(
                    stage=AgentTraceStage.DETECT,
                    actor=AgentTraceActor.AGENT_ENGINE,
                    status=AgentTraceStatus.OK,
                    tool="explain_slow_query",
                    summary="Agent Engine captured slow-query evidence.",
                ),
            ),
        )


def _apply(backend: FakeBackend, pack: EvidencePack) -> EvidencePack:
    ticket = issue_approval_ticket(
        pack,
        evidence_hash=pack.evidence_hash,
        approver="dashboard-operator",
    )
    return asyncio.run(
        apply_and_verify(
            backend,
            pack,
            ticket,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
        )
    )


# --- run_diagnosis (read-only DIAGNOSE phase) ---


def test_diagnosis_is_diagnosed_with_no_decision_or_after():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True, keys_examined=17000)]))
    assert pack.status is PackStatus.DIAGNOSED
    assert pack.decision is None
    assert pack.after is None
    assert pack.approval_gate is not None
    assert pack.approval_gate.state is ApprovalGateState.PENDING_APPROVAL
    assert pack.approval_gate.required_hash == pack.evidence_hash
    assert pack.approval_gate.mutation_allowed is False


def test_diagnosis_trace_starts_and_ends_with_approval_gate():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True, keys_examined=17000)]))

    assert pack.agent_trace[0].stage is AgentTraceStage.GATE
    assert pack.agent_trace[0].actor is AgentTraceActor.APPROVAL_GATE
    assert pack.agent_trace[-1].stage is AgentTraceStage.GATE
    assert "pending" in pack.agent_trace[-1].summary.lower()


def test_diagnosis_does_not_mutate_the_collection():
    backend = FakeBackend([_make_evidence(has_blocking_sort=True)])
    _diagnose(backend)
    assert backend.applied_indexes == []
    assert backend.dropped_indexes == []


def test_diagnosis_evidence_hash_binds_before_and_recommendation():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True)]))
    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)


def test_diagnosis_phase_log_has_single_diagnose_entry():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True)]))
    assert [t.to_phase for t in pack.phase_log] == [Phase.DIAGNOSE]
    assert pack.phase_log[0].from_phase is None


def test_diagnosis_validates_against_schema():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True)]))
    EvidencePack.model_validate(pack.model_dump(mode="python"))


def test_diagnosis_created_at_defaults_to_now_when_not_provided():
    pack = asyncio.run(
        run_diagnosis(
            FakeBackend([_make_evidence(has_blocking_sort=True)]),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
        )
    )
    assert pack.created_at


def test_agent_engine_advice_adds_narrative_without_changing_winner():
    pack = asyncio.run(
        run_diagnosis(
            FakeBackend([_make_evidence(has_blocking_sort=True)]),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            advisor=_WrongAdvisor(),
        )
    )

    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)
    assert pack.narrative == "Agent proposes the obvious but wrong index."
    assert "agent_engine=agent-engine-test" in pack.phase_log[0].note
    assert "proposed_index=ignored" in pack.phase_log[0].note


def test_agent_engine_note_records_no_proposal():
    pack = asyncio.run(
        run_diagnosis(
            FakeBackend([_make_evidence(has_blocking_sort=True)]),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            advisor=_NoIndexAdvisor(),
        )
    )

    assert pack.phase_log[0].note == "agent_engine=agent-engine-test; proposed_index=none"


def test_agent_engine_note_records_matching_proposal_as_accepted():
    pack = asyncio.run(
        run_diagnosis(
            FakeBackend([_make_evidence(has_blocking_sort=True)]),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            advisor=_CorrectAdvisor(),
        )
    )

    assert pack.phase_log[0].note == "agent_engine=agent-engine-test; proposed_index=accepted"


def test_agent_led_diagnosis_builds_pack_from_agent_evidence():
    before = _make_evidence(has_blocking_sort=True, keys_examined=17209)
    pack = asyncio.run(
        run_agent_diagnosis(
            _AgentDiagnosis(before=before),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )

    assert pack.status is PackStatus.DIAGNOSED
    assert pack.before == before
    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)
    assert pack.agent_trace[0].actor is AgentTraceActor.APPROVAL_GATE
    assert pack.agent_trace[1].tool == "explain_slow_query"
    assert pack.agent_trace[-2].status is AgentTraceStatus.OK
    assert pack.agent_trace[-1].actor is AgentTraceActor.APPROVAL_GATE


def test_agent_led_diagnosis_records_drift_without_changing_winner():
    wrong_b = (("storeLocation", 1), ("customer.age", 1), ("saleDate", -1))
    pack = asyncio.run(
        run_agent_diagnosis(
            _AgentDiagnosis(before=_make_evidence(True, 17209), proposed_index=wrong_b),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )

    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert "proposed_index=ignored" in pack.phase_log[0].note
    assert pack.agent_trace[-2].status is AgentTraceStatus.DRIFT


def test_agent_led_diagnosis_writes_agent_sourced_ledger_records():
    ledger = FakeLedgerStore()
    asyncio.run(
        run_agent_diagnosis(
            _AgentDiagnosis(before=_make_evidence(True, 17209)),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            ledger=ledger,
        )
    )

    assert ledger.records[SLOW_QUERIES][f"{RUN_ID}:diagnose:slow_query"]["source"] == (
        "agent_engine_tool"
    )
    assert ledger.records[CANDIDATES][f"{RUN_ID}:diagnose:candidate"]["source"] == (
        "agent_engine_tool"
    )
    assert ledger.records[EXPERIMENTS][f"{RUN_ID}:diagnose:before"]["source"] == (
        "agent_engine_tool"
    )


# --- apply_and_verify (post-approval mutation) ---


def test_apply_and_verify_is_verified_when_strict_checks_pass():
    backend = FakeBackend([_make_evidence(True, 17000), _make_evidence(False, 20)])
    verified = _apply(backend, _diagnose(backend))
    assert verified.status is PackStatus.VERIFIED
    assert verified.after is not None
    assert verified.after.metrics.has_blocking_sort is False
    assert "recommended index evidenced" in verified.agent_trace[-1].summary


def test_apply_and_verify_is_approved_when_sort_remains():
    backend = FakeBackend([_make_evidence(True, 17000), _make_evidence(True, 9000)])
    result = _apply(backend, _diagnose(backend))
    assert result.status is PackStatus.APPROVED
    assert result.after is not None
    assert "blocking SORT remains" in result.agent_trace[-1].summary


def test_apply_and_verify_requires_selected_index_evidence():
    backend = FakeBackend(
        [
            _make_evidence(True, 17000),
            _make_evidence(False, 20, selected_index=False),
        ]
    )
    result = _apply(backend, _diagnose(backend))
    assert result.status is PackStatus.APPROVED
    assert "recommended index not evidenced" in result.agent_trace[-1].summary


def test_apply_and_verify_requires_metric_improvement():
    backend = FakeBackend(
        [
            _make_evidence(True, 100, millis=2.0),
            _make_evidence(False, 100, docs_examined=20, millis=2.0),
        ]
    )
    result = _apply(backend, _diagnose(backend))
    assert result.status is PackStatus.APPROVED
    assert "no keys/docs/millis metric improved" in result.agent_trace[-1].summary


def test_apply_and_verify_applies_the_recommended_index():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    pack = _diagnose(backend)
    _apply(backend, pack)
    assert len(backend.applied_indexes) == 1
    keys, name = backend.applied_indexes[0]
    assert keys == list(pack.recommendation.index_spec)
    assert name.startswith("gcrah_rec_")


def test_apply_and_verify_preserves_the_diagnosis_evidence_hash():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    pack = _diagnose(backend)
    verified = _apply(backend, pack)
    # the approved hash must equal what the human reviewed at diagnosis time
    assert verified.evidence_hash == pack.evidence_hash


def test_apply_and_verify_decision_is_approve_bound_to_hash():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    verified = _apply(backend, _diagnose(backend))
    assert verified.decision is not None
    assert verified.decision.action is DecisionAction.APPROVE
    assert verified.decision.evidence_hash == verified.evidence_hash
    assert verified.decision.phase is Phase.APPROVE
    assert verified.approval_gate is not None
    assert verified.approval_gate.state is ApprovalGateState.VERIFIED
    assert verified.approval_gate.approved_hash == verified.evidence_hash
    assert verified.approval_gate.mutation_allowed is False


def test_apply_and_verify_requires_an_approval_ticket_before_mutation():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    pack = _diagnose(backend)

    with pytest.raises(TypeError):
        asyncio.run(
            apply_and_verify(
                backend,
                pack,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
            )
        )
    assert backend.applied_indexes == []


def test_apply_and_verify_rejects_a_stale_approval_ticket_before_mutation():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    pack = _diagnose(backend)
    ticket = issue_approval_ticket(
        pack,
        evidence_hash=pack.evidence_hash,
        approver="operator",
    )
    stale = ticket.__class__(
        run_id=ticket.run_id,
        evidence_hash="b" * 64,
        approver=ticket.approver,
        note=ticket.note,
        gate_id=ticket.gate_id,
    )

    with pytest.raises(ValueError, match="ticket hash"):
        asyncio.run(
            apply_and_verify(
                backend,
                pack,
                stale,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
            )
        )
    assert backend.applied_indexes == []


def test_approval_ticket_issuer_rejects_ungated_and_non_pending_packs():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    ungated = pack.model_copy(update={"approval_gate": None})
    non_pending = pack.model_copy(
        update={
            "approval_gate": pack.approval_gate.model_copy(
                update={"state": ApprovalGateState.REJECTED, "approver": "op"}
            )
        }
    )

    with pytest.raises(ValueError, match="approval gate"):
        issue_approval_ticket(ungated, evidence_hash=ungated.evidence_hash, approver="op")
    with pytest.raises(ValueError, match="pending approval gate"):
        issue_approval_ticket(non_pending, evidence_hash=non_pending.evidence_hash, approver="op")
    with pytest.raises(ValueError, match="pending approval gate"):
        issue_approval_ticket(pack, evidence_hash="b" * 64, approver="op")


def test_approval_ticket_issuer_rejects_pack_hash_drift():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    drifted_hash = "b" * 64
    drifted = pack.model_copy(
        update={
            "approval_gate": pack.approval_gate.model_copy(update={"required_hash": drifted_hash})
        }
    )

    with pytest.raises(ValueError, match="pack evidence hash"):
        issue_approval_ticket(drifted, evidence_hash=drifted_hash, approver="op")


def test_apply_and_verify_rejects_ticket_identity_mismatches_before_mutation():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    base = issue_approval_ticket(pack, evidence_hash=pack.evidence_hash, approver="op")

    cases = [
        ApprovalTicket("other", base.evidence_hash, base.approver, base.note, base.gate_id),
        ApprovalTicket(base.run_id, base.evidence_hash, base.approver, base.note, "other-gate"),
    ]

    for ticket in cases:
        backend = FakeBackend([_make_evidence(False)])
        with pytest.raises(ValueError, match="does not match"):
            asyncio.run(
                apply_and_verify(
                    backend,
                    pack,
                    ticket,
                    query_filter=QUERY_FILTER,
                    query_sort=QUERY_SORT,
                    limit=LIMIT,
                )
            )
        assert backend.applied_indexes == []


def test_apply_and_verify_rejects_ungated_or_non_pending_pack_before_mutation():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    ticket = issue_approval_ticket(pack, evidence_hash=pack.evidence_hash, approver="op")
    ungated = pack.model_copy(update={"approval_gate": None})
    non_pending = pack.model_copy(
        update={
            "approval_gate": pack.approval_gate.model_copy(
                update={"state": ApprovalGateState.REJECTED, "approver": "op"}
            )
        }
    )

    for candidate, match in (
        (ungated, "approval gate"),
        (non_pending, "pending approval gate"),
    ):
        backend = FakeBackend([_make_evidence(False)])
        with pytest.raises(ValueError, match=match):
            asyncio.run(
                apply_and_verify(
                    backend,
                    candidate,
                    ticket,
                    query_filter=QUERY_FILTER,
                    query_sort=QUERY_SORT,
                    limit=LIMIT,
                )
            )
        assert backend.applied_indexes == []


def test_apply_and_verify_rejects_non_diagnosed_pack_before_mutation():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    verified = _apply(backend, _diagnose(backend))
    ticket = ApprovalTicket(
        run_id=verified.run_id,
        evidence_hash=verified.evidence_hash,
        approver="op",
        note="",
        gate_id=verified.approval_gate.gate_id,
    )

    with pytest.raises(ValueError, match="DIAGNOSED"):
        asyncio.run(
            apply_and_verify(
                FakeBackend([_make_evidence(False)]),
                verified,
                ticket,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
            )
        )


def test_apply_and_verify_phase_log_has_three_entries():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    verified = _apply(backend, _diagnose(backend))
    assert [t.to_phase for t in verified.phase_log] == [
        Phase.DIAGNOSE,
        Phase.APPROVE,
        Phase.VERIFY,
    ]


def test_apply_and_verify_appends_human_apply_and_verify_trace():
    backend = FakeBackend([_make_evidence(False)])
    pack = asyncio.run(
        run_agent_diagnosis(
            _AgentDiagnosis(before=_make_evidence(True)),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )
    verified = _apply(backend, pack)

    stages = [event.stage for event in verified.agent_trace]
    assert AgentTraceStage.APPROVE in stages
    assert AgentTraceStage.APPLY in stages
    assert AgentTraceStage.VERIFY in stages
    assert verified.agent_trace[-1].status is AgentTraceStatus.OK


def test_apply_and_verify_rejects_a_non_diagnosed_pack():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    verified = _apply(backend, _diagnose(backend))
    with pytest.raises(ValueError, match="DIAGNOSED"):
        _apply(backend, verified)


# --- reject_pack (no mutation) ---


def test_reject_pack_is_rejected_with_reject_decision_and_no_after():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    rejected = reject_pack(pack)
    assert rejected.status is PackStatus.REJECTED
    assert rejected.decision is not None
    assert rejected.decision.action is DecisionAction.REJECT
    assert rejected.decision.evidence_hash == pack.evidence_hash
    assert rejected.after is None


def test_reject_pack_phase_log_stops_at_approve():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    rejected = reject_pack(pack)
    assert [t.to_phase for t in rejected.phase_log] == [Phase.DIAGNOSE, Phase.APPROVE]


def test_reject_pack_rejects_a_non_diagnosed_pack():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    rejected = reject_pack(pack)
    with pytest.raises(ValueError, match="DIAGNOSED"):
        reject_pack(rejected)


def test_reject_pack_rejects_ungated_or_non_pending_pack():
    pack = _diagnose(FakeBackend([_make_evidence(True)]))
    ungated = pack.model_copy(update={"approval_gate": None})
    non_pending = pack.model_copy(
        update={
            "approval_gate": pack.approval_gate.model_copy(
                update={"state": ApprovalGateState.REJECTED, "approver": "op"}
            )
        }
    )

    with pytest.raises(ValueError, match="approval gate"):
        reject_pack(ungated)
    with pytest.raises(ValueError, match="pending approval gate"):
        reject_pack(non_pending)


# --- phase guard ---


def test_invalid_phase_transition_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.DIAGNOSE, Phase.VERIFY)


def test_invalid_phase_transition_from_verify_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.VERIFY, Phase.DIAGNOSE)

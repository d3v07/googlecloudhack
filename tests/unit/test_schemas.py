import pytest
from pydantic import ValidationError

from controller.ledger import evidence_hash
from controller.phases import Phase
from controller.schemas import (
    ApprovalGate,
    ApprovalGateState,
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    Decision,
    DecisionAction,
    Diagnosis,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    Finding,
    PackStatus,
    Recommendation,
    Severity,
)


def test_evidence_model_accepts_valid_input():
    evidence = Evidence(
        query={"tenant": 42},
        explain_plan={"stage": "IXSCAN"},
        metrics={"docs_examined": 3, "docs_returned": 1, "millis": 0.7, "total_keys_examined": 2},
    )

    assert evidence.metrics == EvidenceMetrics(
        docs_examined=3, docs_returned=1, millis=0.7, total_keys_examined=2
    )


def test_evidence_model_rejects_negative_metrics():
    with pytest.raises(ValidationError):
        Evidence(
            query="db.orders.find({tenant: 42})",
            explain_plan={"stage": "IXSCAN"},
            metrics={
                "docs_examined": -1,
                "docs_returned": 1,
                "millis": 0.7,
                "total_keys_examined": 2,
            },
        )


def test_has_blocking_sort_is_derived_from_stages():
    sorted_plan = EvidenceMetrics(
        docs_examined=20,
        docs_returned=20,
        millis=1,
        total_keys_examined=17209,
        stages=("FETCH", "SORT", "IXSCAN"),
    )
    streamed_plan = EvidenceMetrics(
        docs_examined=20,
        docs_returned=20,
        millis=1,
        total_keys_examined=64,
        stages=("LIMIT", "FETCH", "IXSCAN"),
    )

    assert sorted_plan.has_blocking_sort is True
    assert streamed_plan.has_blocking_sort is False


def test_evidence_freezes_set_values_to_sorted_sequence():
    evidence = Evidence(
        query={"tags": {"b", "a"}},
        explain_plan={"stage": "IXSCAN"},
        metrics=EvidenceMetrics(docs_examined=1, docs_returned=1, millis=0, total_keys_examined=1),
    )

    assert evidence.model_dump(mode="json")["query"]["tags"] == ["a", "b"]


def test_models_are_frozen():
    evidence = Evidence(
        query={"tenant": 42, "nested": {"status": "open"}, "stages": [{"name": "ixscan"}]},
        explain_plan={"stage": "IXSCAN", "inputStage": {"indexName": "tenant_1"}},
        metrics=EvidenceMetrics(
            docs_examined=3, docs_returned=1, millis=0.7, total_keys_examined=2
        ),
    )

    with pytest.raises(ValidationError):
        evidence.query = {"tenant": 99}
    with pytest.raises(TypeError):
        evidence.query["tenant"] = 99
    with pytest.raises(TypeError):
        evidence.query["nested"]["status"] = "closed"
    with pytest.raises(TypeError):
        evidence.query["stages"][0]["name"] = "collscan"
    with pytest.raises(TypeError):
        evidence.explain_plan["inputStage"]["indexName"] = "tenant_status"


def test_finding_recommendation_and_decision_validate():
    finding = Finding(problem="collection scan", severity=Severity.HIGH, evidence_refs=("abc",))
    recommendation = Recommendation(
        index_spec=(("tenant", 1), ("saleDate", -1), ("age", 1)), rationale="ESR order"
    )
    decision = Decision(
        action=DecisionAction.APPROVE,
        evidence_hash="a" * 64,
        phase=Phase.APPROVE,
    )

    assert finding.evidence_refs == ("abc",)
    assert recommendation.index_spec == (("tenant", 1), ("saleDate", -1), ("age", 1))
    assert decision.phase is Phase.APPROVE


def test_recommendation_index_spec_preserves_order_and_is_immutable():
    recommendation = Recommendation(
        index_spec=(("storeLocation", 1), ("saleDate", -1), ("customer.age", 1)),
        rationale="covers filter",
    )

    # order is preserved exactly (the ESR contract) and survives JSON serialization
    assert recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert recommendation.model_dump(mode="json")["index_spec"] == [
        ["storeLocation", 1],
        ["saleDate", -1],
        ["customer.age", 1],
    ]
    with pytest.raises(ValidationError):
        recommendation.index_spec = (("x", 1),)


def test_recommendation_rejects_empty_index_spec():
    with pytest.raises(ValidationError):
        Recommendation(index_spec=(), rationale="nothing to index")


def test_decision_rejects_invalid_hash():
    with pytest.raises(ValidationError):
        Decision(action=DecisionAction.APPROVE, evidence_hash="not-a-hash", phase=Phase.APPROVE)


def test_agent_trace_event_validates_and_serializes():
    event = AgentTraceEvent(
        stage=AgentTraceStage.DETECT,
        actor=AgentTraceActor.AGENT_ENGINE,
        status=AgentTraceStatus.OK,
        component="diagnose_agent",
        resource="projects/p/locations/us-central1/reasoningEngines/diagnose",
        tool="explain_slow_query",
        summary="Agent Engine captured slow-query evidence.",
        ledger_ref="slow_queries/run-1:diagnose:slow_query",
    )

    assert event.model_dump(mode="json") == {
        "stage": "detect",
        "actor": "agent_engine",
        "status": "ok",
        "summary": "Agent Engine captured slow-query evidence.",
        "component": "diagnose_agent",
        "resource": "projects/p/locations/us-central1/reasoningEngines/diagnose",
        "tool": "explain_slow_query",
        "ledger_ref": "slow_queries/run-1:diagnose:slow_query",
    }


def test_approval_gate_validates_and_is_immutable():
    gate = ApprovalGate(
        gate_id="run-1:gate",
        state=ApprovalGateState.PENDING_APPROVAL,
        required_hash="a" * 64,
        mutation_allowed=False,
        ledger_ref="approvals/run-1:gate:pending",
    )

    assert gate.model_dump(mode="json")["state"] == "pending_approval"
    with pytest.raises(ValidationError):
        gate.state = ApprovalGateState.APPROVED


def test_persisted_pack_rejects_mutation_allowed_gate():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="mutation_allowed"):
        EvidencePack(
            **base,
            status=PackStatus.DIAGNOSED,
            approval_gate=ApprovalGate(
                gate_id="r1:gate",
                state=ApprovalGateState.PENDING_APPROVAL,
                required_hash=eh,
                mutation_allowed=True,
            ),
        )


def test_agent_trace_requires_summary():
    with pytest.raises(ValidationError):
        AgentTraceEvent(
            stage=AgentTraceStage.DETECT,
            actor=AgentTraceActor.AGENT_ENGINE,
            status=AgentTraceStatus.OK,
            summary="",
        )


def test_diagnosis_composes_finding_and_recommendation():
    diagnosis = Diagnosis(
        finding=Finding(problem="blocking sort", severity=Severity.HIGH, evidence_refs=("x",)),
        recommendation=Recommendation(index_spec=(("a", 1),), rationale="esr"),
    )

    assert diagnosis.finding.severity is Severity.HIGH
    assert diagnosis.recommendation.index_spec == (("a", 1),)


# --- EvidencePack status ⟺ (decision, after) consistency (#4) ---


def _pack_parts():
    before = Evidence(
        query={"x": 1},
        explain_plan={"stage": "IXSCAN"},
        metrics=EvidenceMetrics(
            docs_examined=1, docs_returned=1, millis=0, total_keys_examined=1, stages=("IXSCAN",)
        ),
    )
    rec = Recommendation(index_spec=(("x", 1),), rationale="t")
    finding = Finding(problem="p", severity=Severity.LOW, evidence_refs=("x",))
    eh = evidence_hash({"evidence": before, "recommendation": rec})
    base = {
        "run_id": "r1",
        "namespace": "db.coll",
        "before": before,
        "finding": finding,
        "recommendation": rec,
        "evidence_hash": eh,
        "created_at": "2026-06-01T00:00:00Z",
    }
    return base, before, eh


def _approve(eh: str) -> Decision:
    return Decision(action=DecisionAction.APPROVE, evidence_hash=eh, phase=Phase.APPROVE)


def _reject(eh: str) -> Decision:
    return Decision(action=DecisionAction.REJECT, evidence_hash=eh, phase=Phase.APPROVE)


def _gate(
    eh: str,
    state: ApprovalGateState,
    *,
    approved_hash: str | None = None,
    approver: str | None = None,
) -> ApprovalGate:
    return ApprovalGate(
        gate_id="r1:gate",
        state=state,
        required_hash=eh,
        approved_hash=approved_hash,
        approver=approver,
        mutation_allowed=False,
    )


def test_diagnosed_pack_with_decision_is_rejected():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="DIAGNOSED"):
        EvidencePack(**base, status=PackStatus.DIAGNOSED, decision=_approve(eh))


def test_diagnosed_pack_with_after_is_rejected():
    base, before, _ = _pack_parts()
    with pytest.raises(ValidationError, match="DIAGNOSED"):
        EvidencePack(**base, status=PackStatus.DIAGNOSED, after=before)


def test_rejected_pack_without_decision_is_rejected():
    base, _, _ = _pack_parts()
    with pytest.raises(ValidationError, match="REJECTED"):
        EvidencePack(**base, status=PackStatus.REJECTED)


def test_rejected_pack_with_approve_decision_is_rejected():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="REJECTED"):
        EvidencePack(**base, status=PackStatus.REJECTED, decision=_approve(eh))


def test_rejected_pack_with_after_is_rejected():
    base, before, eh = _pack_parts()
    with pytest.raises(ValidationError, match="after-evidence"):
        EvidencePack(**base, status=PackStatus.REJECTED, after=before, decision=_reject(eh))


def test_approved_pack_without_decision_is_rejected():
    base, before, _ = _pack_parts()
    with pytest.raises(ValidationError, match="approve decision"):
        EvidencePack(**base, status=PackStatus.APPROVED, after=before)


def test_verified_pack_without_after_is_rejected():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="after-evidence"):
        EvidencePack(**base, status=PackStatus.VERIFIED, decision=_approve(eh))


def test_valid_lifecycle_states_are_accepted():
    base, before, eh = _pack_parts()
    EvidencePack(**base, status=PackStatus.DIAGNOSED)
    EvidencePack(**base, status=PackStatus.REJECTED, decision=_reject(eh))
    EvidencePack(**base, status=PackStatus.VERIFIED, after=before, decision=_approve(eh))


def test_evidence_pack_rejects_tampered_persisted_hash():
    base, _, _ = _pack_parts()
    with pytest.raises(ValidationError, match="before-evidence and recommendation"):
        EvidencePack(**(base | {"evidence_hash": "b" * 64}), status=PackStatus.DIAGNOSED)


def test_approval_gate_rejects_hash_mismatches():
    base, before, eh = _pack_parts()
    with pytest.raises(ValidationError, match="required_hash"):
        EvidencePack(
            **base,
            status=PackStatus.DIAGNOSED,
            approval_gate=_gate("b" * 64, ApprovalGateState.PENDING_APPROVAL),
        )
    with pytest.raises(ValidationError, match="approved_hash"):
        EvidencePack(
            **base,
            status=PackStatus.VERIFIED,
            after=before,
            decision=_approve(eh),
            approval_gate=_gate(
                eh, ApprovalGateState.VERIFIED, approved_hash="b" * 64, approver="op"
            ),
        )


def test_approval_gate_status_table_rejects_invalid_diagnosed_gate():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="pending approval gate"):
        EvidencePack(
            **base,
            status=PackStatus.DIAGNOSED,
            approval_gate=_gate(eh, ApprovalGateState.APPROVED, approved_hash=eh, approver="op"),
        )
    with pytest.raises(ValidationError, match="require only the current hash"):
        EvidencePack(
            **base,
            status=PackStatus.DIAGNOSED,
            approval_gate=ApprovalGate(
                gate_id="r1:gate",
                state=ApprovalGateState.PENDING_APPROVAL,
                mutation_allowed=False,
            ),
        )


def test_approval_gate_status_table_rejects_invalid_rejected_gate():
    base, _, eh = _pack_parts()
    with pytest.raises(ValidationError, match="rejected approval gate"):
        EvidencePack(
            **base,
            status=PackStatus.REJECTED,
            decision=_reject(eh),
            approval_gate=_gate(eh, ApprovalGateState.PENDING_APPROVAL),
        )
    with pytest.raises(ValidationError, match="record the approver"):
        EvidencePack(
            **base,
            status=PackStatus.REJECTED,
            decision=_reject(eh),
            approval_gate=_gate(eh, ApprovalGateState.REJECTED),
        )


def test_approval_gate_status_table_rejects_invalid_verified_gate():
    base, before, eh = _pack_parts()
    with pytest.raises(ValidationError, match="verified approval gate"):
        EvidencePack(
            **base,
            status=PackStatus.VERIFIED,
            after=before,
            decision=_approve(eh),
            approval_gate=_gate(eh, ApprovalGateState.APPROVED, approved_hash=eh, approver="op"),
        )
    with pytest.raises(ValidationError, match="record the approved hash"):
        EvidencePack(
            **base,
            status=PackStatus.VERIFIED,
            after=before,
            decision=_approve(eh),
            approval_gate=_gate(eh, ApprovalGateState.VERIFIED, approver="op"),
        )


def test_approval_gate_status_table_rejects_invalid_approved_gate():
    base, before, eh = _pack_parts()
    with pytest.raises(ValidationError, match="approved approval gate"):
        EvidencePack(
            **base,
            status=PackStatus.APPROVED,
            after=before,
            decision=_approve(eh),
            approval_gate=_gate(eh, ApprovalGateState.VERIFIED, approved_hash=eh, approver="op"),
        )
    with pytest.raises(ValidationError, match="record the approved hash"):
        EvidencePack(
            **base,
            status=PackStatus.APPROVED,
            after=before,
            decision=_approve(eh),
            approval_gate=_gate(eh, ApprovalGateState.APPROVED),
        )

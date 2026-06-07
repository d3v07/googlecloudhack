"""Layer-7 deterministic decision + execution rail — lock-in tests.

Covers: apply_and_verify VERIFIED/APPROVED status, ledger outcome records,
index-in-explain_plan honoring, metric surfacing, ESR recommendation immutability
against agent proposals, phase-gated write-tool blocking, and stale-ticket guard.
"""

import asyncio

import pytest

from agents.gating import make_gate
from controller.backends import FakeBackend
from controller.ledger_store import FakeLedgerStore, VERIFICATIONS
from controller.orchestrator import (
    AgentDiagnosisResult,
    ApprovalTicket,
    apply_and_verify,
    issue_approval_ticket,
    run_agent_diagnosis,
    run_diagnosis,
)
from controller.phases import Phase
from controller.schemas import (
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    Evidence,
    EvidenceMetrics,
    PackStatus,
)

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
NAMESPACE = "sample_supplies.sales_agent_demo"
RUN_ID = "vr-test-1"
CREATED_AT = "2026-06-07T00:00:00Z"

# Deterministic ESR winner for this query shape: Equality → Sort → Range
ESR_WINNER = (("storeLocation", 1), ("saleDate", -1), ("customer.age", 1))


def _evidence(
    has_blocking_sort: bool,
    *,
    keys_examined: int = 1000,
    docs_examined: int = 20,
    millis: float = 10.0,
    explain_plan: dict | None = None,
) -> Evidence:
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan=explain_plan or {"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=docs_examined,
            docs_returned=20,
            millis=millis,
            total_keys_examined=keys_examined,
            stages=stages,
        ),
    )


class _HintAwareFakeBackend:
    """FakeBackend variant whose explain() embeds the hint into the returned
    explain_plan so tests can assert the apply hint reached the backend call."""

    def __init__(self, explain_results: list[Evidence]) -> None:
        self._results = explain_results
        self._call_count = 0
        self.applied_indexes: list[tuple[list, str]] = []
        self.dropped_indexes: list[str] = []

    async def explain(self, query_filter, query_sort, limit, hint=None) -> Evidence:
        idx = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        base = self._results[idx]
        if hint is None:
            return base
        # Encode the hint into the explain_plan so the caller can verify it was used.
        if isinstance(hint, list):
            hint_plan = {"stage": "IXSCAN", "keyPattern": {k: v for k, v in hint}}
        else:
            hint_plan = {"stage": "IXSCAN", "keyPattern": {"hintName": hint}}
        return base.model_copy(update={"explain_plan": hint_plan})

    async def apply_index(self, keys: list, name: str) -> None:
        self.applied_indexes.append((keys, name))

    async def drop_index(self, name: str) -> None:
        self.dropped_indexes.append(name)

    def close(self) -> None:
        pass


def _diagnose(backend, ledger=None):
    return asyncio.run(
        run_diagnosis(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            ledger=ledger,
        )
    )


def _apply(backend, pack, ledger=None, *, approver="dashboard-operator", note=""):
    ticket = issue_approval_ticket(
        pack,
        evidence_hash=pack.evidence_hash,
        approver=approver,
        note=note,
    )
    return asyncio.run(
        apply_and_verify(
            backend,
            pack,
            ticket,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            ledger=ledger,
        )
    )


# ---------------------------------------------------------------------------
# Test 1: VERIFIED happy path — full conjunction held
# ---------------------------------------------------------------------------


def test_verified_happy_path_requires_sort_gone_and_records_passed_in_ledger():
    """VERIFIED happy path: all three checks pass.

    The three-check rail (orchestrator.py _verification_checks) gates VERIFIED on
    sort removed AND the recommended index evidenced in explain_plan AND a metric
    improved. This path holds all three: no sort, the full recommended index in
    explain_plan, and lower keys/docs/millis. Ledger records outcome='passed'.
    """
    ledger = FakeLedgerStore()
    before = _evidence(True, keys_examined=17000, docs_examined=17000, millis=250.0)
    after = _evidence(
        False,
        keys_examined=20,
        docs_examined=20,
        millis=2.0,
        explain_plan={
            "stage": "IXSCAN",
            "keyPattern": {"storeLocation": 1, "saleDate": -1, "customer.age": 1},
        },
    )
    backend = FakeBackend([before, after])

    pack = _diagnose(backend, ledger)
    verified = _apply(backend, pack, ledger)

    assert verified.status is PackStatus.VERIFIED
    assert verified.after is not None
    assert verified.after.metrics.has_blocking_sort is False

    verification = ledger.records[VERIFICATIONS][f"{RUN_ID}:verify:verification"]
    assert verification["outcome"] == "passed"


# ---------------------------------------------------------------------------
# Test 2: Failure path — blocking sort persists → APPROVED, not VERIFIED
# ---------------------------------------------------------------------------


def test_blocking_sort_persists_after_apply_yields_approved_not_verified():
    """When after-evidence still has a blocking SORT stage, status is APPROVED
    (the apply ran but verification failed), not VERIFIED. The VERIFY trace
    event must carry AgentTraceStatus.FAILED and the ledger outcome must be
    'failed'.
    """
    ledger = FakeLedgerStore()
    before = _evidence(True, keys_examined=17000)
    after = _evidence(True, keys_examined=16500)
    backend = FakeBackend([before, after])

    pack = _diagnose(backend, ledger)
    result = _apply(backend, pack, ledger)

    assert result.status is PackStatus.APPROVED
    assert result.after is not None
    assert result.after.metrics.has_blocking_sort is True

    verify_events = [e for e in result.agent_trace if e.stage is AgentTraceStage.VERIFY]
    assert len(verify_events) == 1
    assert verify_events[0].status is AgentTraceStatus.FAILED

    verification = ledger.records[VERIFICATIONS][f"{RUN_ID}:verify:verification"]
    assert verification["outcome"] == "failed"


# ---------------------------------------------------------------------------
# Test 3: Apply hint is honored by the backend — index evidenced in explain_plan
# ---------------------------------------------------------------------------


def test_recommended_index_is_evidenced_in_after_explain_plan():
    """apply_and_verify hints the after-explain by the recommended index key list.
    The hint-aware fake encodes the hint into explain_plan, proving the rail
    passed the correct key pattern to the backend's explain call.
    """
    before = _evidence(True, keys_examined=17000)
    # apply_and_verify makes exactly one explain() call (for after). The hint-aware
    # backend is only reached by that call (diagnosis uses a separate FakeBackend).
    after_base = _evidence(False, keys_examined=20)
    apply_backend = _HintAwareFakeBackend([after_base])

    pack = _diagnose(FakeBackend([before]), None)
    # Run apply_and_verify against the hint-aware backend so after.explain_plan
    # reflects the hint the rail actually supplied.
    ticket = issue_approval_ticket(pack, evidence_hash=pack.evidence_hash, approver="op")
    result = asyncio.run(
        apply_and_verify(
            apply_backend,
            pack,
            ticket,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
        )
    )

    assert result.after is not None
    assert result.status is PackStatus.VERIFIED
    plan = result.after.explain_plan
    # The hint was the recommended index keys list — the keyPattern encodes them.
    assert "keyPattern" in plan
    assert "storeLocation" in plan["keyPattern"]
    assert "saleDate" in plan["keyPattern"]


# ---------------------------------------------------------------------------
# Test 4: A metric actually improved on the happy path
# ---------------------------------------------------------------------------


def test_metric_improved_between_before_and_after_on_happy_path():
    """The rail surfaces before and after metrics faithfully. On a successful
    verification, total_keys_examined must decrease (the new index prunes scanned keys).
    """
    before = _evidence(True, keys_examined=17000, docs_examined=17000, millis=250.0)
    after = _evidence(False, keys_examined=20, docs_examined=20, millis=2.0)
    backend = FakeBackend([before, after])

    pack = _diagnose(backend)
    verified = _apply(backend, pack)

    assert verified.after is not None
    assert verified.after.metrics.total_keys_examined < verified.before.metrics.total_keys_examined
    assert verified.after.metrics.docs_examined < verified.before.metrics.docs_examined
    assert verified.after.metrics.millis < verified.before.metrics.millis


# ---------------------------------------------------------------------------
# Test 5: VERIFIED requires more than sort removal (three-check rail)
# ---------------------------------------------------------------------------


def test_verified_requires_metric_improvement_not_only_sort_removal():
    """Sort removed but NO metric improved (and the index not evidenced) -> APPROVED,
    not VERIFIED. The three-check rail requires sort_removed AND selected_index_used
    AND metric_improved; removing the blocking sort alone is not sufficient.
    """
    # after: sort gone, but metrics are identical to before — no improvement
    before = _evidence(True, keys_examined=17000, docs_examined=17000, millis=250.0)
    after = _evidence(False, keys_examined=17000, docs_examined=17000, millis=250.0)
    backend = FakeBackend([before, after])

    pack = _diagnose(backend)
    result = _apply(backend, pack)

    assert result.status is PackStatus.APPROVED


# ---------------------------------------------------------------------------
# Test 5: Deterministic ESR recommendation wins regardless of agent proposal
# ---------------------------------------------------------------------------


class _ConflictingAgent:
    """Agent that proposes a different (non-ESR) index from the ESR winner."""

    def __init__(self, before: Evidence) -> None:
        self._before = before

    async def diagnose(self, **kwargs) -> AgentDiagnosisResult:
        return AgentDiagnosisResult(
            source="conflicting-agent",
            before=self._before,
            narrative="Agent proposes the wrong (non-ESR) key order.",
            # Wrong order: E-R-S instead of E-S-R
            proposed_index=(("storeLocation", 1), ("customer.age", 1), ("saleDate", -1)),
            trace=(
                AgentTraceEvent(
                    stage=AgentTraceStage.DETECT,
                    actor=AgentTraceActor.AGENT_ENGINE,
                    status=AgentTraceStatus.OK,
                    tool="explain_slow_query",
                    summary="Agent captured before evidence.",
                ),
            ),
        )


def test_esr_recommendation_wins_even_when_agent_proposes_different_index():
    """Agents cannot select the winner. run_agent_diagnosis always resolves to the
    deterministic ESR recommendation, regardless of what the agent proposes.
    """
    before = _evidence(True, keys_examined=17000)
    pack = asyncio.run(
        run_agent_diagnosis(
            _ConflictingAgent(before),
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )

    assert pack.recommendation.index_spec == ESR_WINNER

    drift_events = [
        e
        for e in pack.agent_trace
        if e.status is AgentTraceStatus.DRIFT
        and e.actor is AgentTraceActor.DETERMINISTIC_CONTROLLER
    ]
    assert len(drift_events) == 1
    assert "drifted" in drift_events[0].summary.lower()

    assert "proposed_index=ignored" in pack.phase_log[0].note


# ---------------------------------------------------------------------------
# Test 6: Write tools blocked in DIAGNOSE phase
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def test_create_index_blocked_in_diagnose_phase():
    """create-index is a write tool; it must be blocked in the DIAGNOSE phase."""
    gate = make_gate(Phase.DIAGNOSE)
    result = gate(_FakeTool("create-index"), {}, None)

    assert result is not None
    assert result["blocked"] is True
    assert result["phase"] == "diagnose"


def test_drop_index_blocked_in_diagnose_phase():
    """drop-index is a write tool; it must be blocked in the DIAGNOSE phase."""
    gate = make_gate(Phase.DIAGNOSE)
    result = gate(_FakeTool("drop-index"), {}, None)

    assert result is not None
    assert result["blocked"] is True


def test_write_tools_blocked_in_approve_phase():
    """Write tools must also be blocked during the APPROVE (pre-mutation) phase."""
    gate = make_gate(Phase.APPROVE)
    assert gate(_FakeTool("create-index"), {}, None)["blocked"] is True
    assert gate(_FakeTool("drop-index"), {}, None)["blocked"] is True


def test_write_tools_allowed_only_in_verify_phase():
    """After apply_and_verify, the VERIFY phase is the only phase that permits
    create-index and drop-index.
    """
    verify_gate = make_gate(Phase.VERIFY)
    assert verify_gate(_FakeTool("create-index"), {}, None) is None
    assert verify_gate(_FakeTool("drop-index"), {}, None) is None


# ---------------------------------------------------------------------------
# Test 7: Stale/mismatched evidence_hash prevents apply_index from being called
# ---------------------------------------------------------------------------


def test_stale_ticket_hash_prevents_apply_index_from_being_called():
    """An approval ticket carrying a hash that does not match the pack's
    evidence_hash must cause apply_and_verify to raise before any mutation.
    The fake backend's apply_index must never be invoked.
    """
    before = _evidence(True, keys_examined=17000)
    after = _evidence(False, keys_examined=20)

    diag_backend = FakeBackend([before])
    pack = _diagnose(diag_backend)

    stale_ticket = ApprovalTicket(
        run_id=pack.run_id,
        evidence_hash="b" * 64,
        approver="operator",
        note="",
        gate_id=pack.approval_gate.gate_id,
    )

    apply_backend = FakeBackend([after])
    with pytest.raises(ValueError, match="ticket hash"):
        asyncio.run(
            apply_and_verify(
                apply_backend,
                pack,
                stale_ticket,
                query_filter=QUERY_FILTER,
                query_sort=QUERY_SORT,
                limit=LIMIT,
            )
        )

    assert apply_backend.applied_indexes == [], "apply_index must not be called on hash mismatch"

"""Unit tests for controller/orchestrator.py using FakeBackend (no I/O)."""

import asyncio

import pytest

from controller.backends import FakeBackend
from controller.orchestrator import apply_and_verify, reject_pack, run_diagnosis
from controller.pack import pack_evidence_hash
from controller.phases import InvalidPhaseTransition, Phase, assert_phase_transition
from controller.schemas import (
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


def _make_evidence(has_blocking_sort: bool, keys_examined: int = 1000) -> Evidence:
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan={"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=10.0,
            total_keys_examined=keys_examined,
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


def _apply(backend: FakeBackend, pack: EvidencePack) -> EvidencePack:
    return asyncio.run(
        apply_and_verify(
            backend, pack, query_filter=QUERY_FILTER, query_sort=QUERY_SORT, limit=LIMIT
        )
    )


# --- run_diagnosis (read-only DIAGNOSE phase) ---


def test_diagnosis_is_diagnosed_with_no_decision_or_after():
    pack = _diagnose(FakeBackend([_make_evidence(has_blocking_sort=True, keys_examined=17000)]))
    assert pack.status is PackStatus.DIAGNOSED
    assert pack.decision is None
    assert pack.after is None


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


# --- apply_and_verify (post-approval mutation) ---


def test_apply_and_verify_is_verified_when_sort_gone():
    backend = FakeBackend([_make_evidence(True, 17000), _make_evidence(False, 20)])
    verified = _apply(backend, _diagnose(backend))
    assert verified.status is PackStatus.VERIFIED
    assert verified.after is not None
    assert verified.after.metrics.has_blocking_sort is False


def test_apply_and_verify_is_approved_when_sort_remains():
    backend = FakeBackend([_make_evidence(True, 17000), _make_evidence(True, 9000)])
    result = _apply(backend, _diagnose(backend))
    assert result.status is PackStatus.APPROVED
    assert result.after is not None


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


def test_apply_and_verify_phase_log_has_three_entries():
    backend = FakeBackend([_make_evidence(True), _make_evidence(False)])
    verified = _apply(backend, _diagnose(backend))
    assert [t.to_phase for t in verified.phase_log] == [
        Phase.DIAGNOSE,
        Phase.APPROVE,
        Phase.VERIFY,
    ]


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


# --- phase guard ---


def test_invalid_phase_transition_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.DIAGNOSE, Phase.VERIFY)


def test_invalid_phase_transition_from_verify_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.VERIFY, Phase.DIAGNOSE)

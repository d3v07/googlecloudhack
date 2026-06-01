"""Unit tests for controller/orchestrator.py using FakeBackend (no I/O)."""

import asyncio

import pytest

from controller.backends import FakeBackend
from controller.orchestrator import INDEX_C_NAME, run_remediation
from controller.pack import pack_evidence_hash
from controller.phases import InvalidPhaseTransition, Phase, assert_phase_transition
from controller.schemas import (
    DecisionAction,
    EvidencePack,
    EvidenceMetrics,
    Evidence,
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


def _run(backend: FakeBackend) -> EvidencePack:
    return asyncio.run(
        run_remediation(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )


def test_happy_path_verified():
    before = _make_evidence(has_blocking_sort=True, keys_examined=17000)
    after = _make_evidence(has_blocking_sort=False, keys_examined=20)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert pack.status is PackStatus.VERIFIED
    assert pack.after is not None
    assert pack.after.metrics.has_blocking_sort is False


def test_pack_evidence_hash_consistency():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)


def test_pack_validates_against_schema():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    # round-trip via model_validate confirms schema integrity
    EvidencePack.model_validate(pack.model_dump(mode="python"))


def test_decision_is_auto_approved_with_correct_hash():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert pack.decision is not None
    assert pack.decision.action is DecisionAction.APPROVE
    assert pack.decision.evidence_hash == pack.evidence_hash
    assert pack.decision.phase is Phase.APPROVE


def test_phase_log_has_three_entries():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert len(pack.phase_log) == 3
    phases = [t.to_phase for t in pack.phase_log]
    assert phases == [Phase.DIAGNOSE, Phase.APPROVE, Phase.VERIFY]


def test_phase_log_first_entry_has_no_from_phase():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert pack.phase_log[0].from_phase is None


def test_scratch_index_cleaned_up():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    _run(backend)

    scratch_name = f"{INDEX_C_NAME}__scratch"
    assert scratch_name in backend.dropped_indexes


def test_after_still_has_sort_results_in_diagnosed():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=True)
    backend = FakeBackend([before, after])

    pack = _run(backend)

    assert pack.status is PackStatus.DIAGNOSED


def test_scratch_index_dropped_even_when_after_has_sort():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=True)
    backend = FakeBackend([before, after])

    _run(backend)

    scratch_name = f"{INDEX_C_NAME}__scratch"
    assert scratch_name in backend.dropped_indexes


def test_invalid_phase_transition_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.DIAGNOSE, Phase.VERIFY)


def test_invalid_phase_transition_from_verify_raises():
    with pytest.raises(InvalidPhaseTransition):
        assert_phase_transition(Phase.VERIFY, Phase.DIAGNOSE)


def test_apply_index_called_with_scratch_name():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    _run(backend)

    scratch_name = f"{INDEX_C_NAME}__scratch"
    applied_names = [name for _, name in backend.applied_indexes]
    assert scratch_name in applied_names


def test_created_at_defaults_to_now_when_not_provided():
    before = _make_evidence(has_blocking_sort=True)
    after = _make_evidence(has_blocking_sort=False)
    backend = FakeBackend([before, after])

    pack = asyncio.run(
        run_remediation(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            # no created_at — triggers the None branch
        )
    )

    assert pack.created_at  # non-empty timestamp generated

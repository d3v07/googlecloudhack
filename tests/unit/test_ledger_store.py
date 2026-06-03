import asyncio

import pytest

from controller.backends import FakeBackend
from controller.ledger_store import (
    APPLICATIONS,
    APPROVALS,
    CANDIDATES,
    DECISIONS,
    EVIDENCE_PACKS,
    EXPERIMENTS,
    FakeLedgerStore,
    MongoLedgerStore,
    SLOW_QUERIES,
    VERIFICATIONS,
    _write_approval_record,
    _write_decision_record,
    write_gate_pending_record,
)
from controller.orchestrator import (
    apply_and_verify,
    issue_approval_ticket,
    reject_pack,
    run_diagnosis,
)
from controller.schemas import Evidence, EvidenceMetrics, PackStatus

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
NAMESPACE = "sample_supplies.sales_agent_demo"
RUN_ID = "ledger-test"
CREATED_AT = "2026-06-01T00:00:00Z"


def _evidence(has_blocking_sort: bool, keys_examined: int) -> Evidence:
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan={"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=10,
            total_keys_examined=keys_examined,
            stages=stages,
        ),
    )


def _diagnose(backend: FakeBackend, ledger: FakeLedgerStore | None = None):
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


def _apply(
    backend: FakeBackend,
    pack,
    ledger: FakeLedgerStore | None = None,
    *,
    approver: str = "operator",
    note: str = "approved",
):
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


def test_diagnosis_writes_slow_query_candidate_experiment_and_pack_records():
    ledger = FakeLedgerStore()
    pack = _diagnose(FakeBackend([_evidence(True, 17209)]), ledger)

    assert set(ledger.records[SLOW_QUERIES]) == {f"{RUN_ID}:diagnose:slow_query"}
    assert set(ledger.records[CANDIDATES]) == {f"{RUN_ID}:diagnose:candidate"}
    assert set(ledger.records[EXPERIMENTS]) == {f"{RUN_ID}:diagnose:before"}
    assert set(ledger.records[APPROVALS]) == {
        f"{RUN_ID}:gate:opened",
        f"{RUN_ID}:gate:pending",
    }
    assert set(ledger.records[EVIDENCE_PACKS]) == {RUN_ID}
    assert ledger.records[EVIDENCE_PACKS][RUN_ID]["status"] == PackStatus.DIAGNOSED.value
    assert ledger.records[CANDIDATES][f"{RUN_ID}:diagnose:candidate"]["index_spec"] == [
        ["storeLocation", 1],
        ["saleDate", -1],
        ["customer.age", 1],
    ]
    assert (
        ledger.records[SLOW_QUERIES][f"{RUN_ID}:diagnose:slow_query"]["evidence_hash"]
        == pack.evidence_hash
    )
    assert ledger.records[SLOW_QUERIES][f"{RUN_ID}:diagnose:slow_query"]["source"] == (
        "deterministic_esr"
    )
    assert ledger.records[CANDIDATES][f"{RUN_ID}:diagnose:candidate"]["source"] == (
        "deterministic_esr"
    )
    assert ledger.records[EXPERIMENTS][f"{RUN_ID}:diagnose:before"]["source"] == (
        "deterministic_esr"
    )


def test_diagnosis_ledger_writes_are_idempotent_for_retry():
    ledger = FakeLedgerStore()
    _diagnose(FakeBackend([_evidence(True, 17209)]), ledger)
    _diagnose(FakeBackend([_evidence(True, 17209)]), ledger)

    assert {collection: len(records) for collection, records in ledger.records.items()} == {
        SLOW_QUERIES: 1,
        CANDIDATES: 1,
        EXPERIMENTS: 1,
        DECISIONS: 0,
        EVIDENCE_PACKS: 1,
        APPROVALS: 2,
        APPLICATIONS: 0,
        VERIFICATIONS: 0,
    }


def test_gate_pending_write_is_noop_without_ledger():
    diagnosed = _diagnose(FakeBackend([_evidence(True, 17209)]))

    assert write_gate_pending_record(None, pack=diagnosed) is None


def test_reject_writes_decision_rejection_and_updated_pack_records():
    ledger = FakeLedgerStore()
    diagnosed = _diagnose(FakeBackend([_evidence(True, 17209)]))
    rejected = reject_pack(diagnosed, ledger=ledger, approver="judge", note="not safe")

    decision = ledger.records[DECISIONS][f"{RUN_ID}:approve:decision"]
    approval = ledger.records[APPROVALS][f"{RUN_ID}:approve:rejection"]
    assert rejected.status is PackStatus.REJECTED
    assert decision["action"] == "reject"
    assert decision["decision_evidence_hash"] == diagnosed.evidence_hash
    assert approval["approver"] == "judge"
    assert approval["note"] == "not safe"
    assert ledger.records[EVIDENCE_PACKS][RUN_ID]["status"] == PackStatus.REJECTED.value


def test_approve_writes_decision_approval_application_verification_and_pack_records():
    ledger = FakeLedgerStore()
    backend = FakeBackend([_evidence(True, 17209), _evidence(False, 64)])
    diagnosed = _diagnose(backend)
    verified = _apply(backend, diagnosed, ledger)

    assert verified.status is PackStatus.VERIFIED
    assert (
        ledger.records[DECISIONS][f"{RUN_ID}:approve:decision"]["decision_evidence_hash"]
        == diagnosed.evidence_hash
    )
    assert ledger.records[APPROVALS][f"{RUN_ID}:approve:approval"]["action"] == "approve"
    assert ledger.records[APPLICATIONS][f"{RUN_ID}:approve:application"]["status"] == "applied"
    assert ledger.records[VERIFICATIONS][f"{RUN_ID}:verify:verification"]["outcome"] == "passed"
    assert ledger.records[EVIDENCE_PACKS][RUN_ID]["status"] == PackStatus.VERIFIED.value


def test_failed_verification_records_failed_outcome():
    ledger = FakeLedgerStore()
    backend = FakeBackend([_evidence(True, 17209), _evidence(True, 16000)])
    diagnosed = _diagnose(backend)
    result = _apply(backend, diagnosed, ledger)

    assert result.status is PackStatus.APPROVED
    verification = ledger.records[VERIFICATIONS][f"{RUN_ID}:verify:verification"]
    assert verification["outcome"] == "failed"
    assert verification["after"]["has_blocking_sort"] is True


def test_approval_ledger_writes_are_idempotent_for_retry():
    ledger = FakeLedgerStore()
    diagnosed = _diagnose(FakeBackend([_evidence(True, 17209)]))
    _apply(FakeBackend([_evidence(False, 64)]), diagnosed, ledger)
    _apply(FakeBackend([_evidence(False, 64)]), diagnosed, ledger)

    assert len(ledger.records[DECISIONS]) == 1
    assert len(ledger.records[APPROVALS]) == 1
    assert len(ledger.records[APPLICATIONS]) == 1
    assert len(ledger.records[VERIFICATIONS]) == 1


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def replace_one(self, query: dict, document: dict, upsert: bool = False) -> None:
        self.docs[query["_id"]] = document


class _FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        self.collections.setdefault(name, _FakeCollection())
        return self.collections[name]


def test_mongo_ledger_store_upserts_by_deterministic_id():
    database = _FakeDatabase()
    store = MongoLedgerStore(database)

    store.upsert(SLOW_QUERIES, "run-1:diagnose:slow_query", {"run_id": "run-1", "value": 1})
    store.upsert(SLOW_QUERIES, "run-1:diagnose:slow_query", {"run_id": "run-1", "value": 2})

    docs = database.collections[SLOW_QUERIES].docs
    assert list(docs) == ["run-1:diagnose:slow_query"]
    assert docs["run-1:diagnose:slow_query"] == {
        "_id": "run-1:diagnose:slow_query",
        "run_id": "run-1",
        "value": 2,
    }


def test_decision_and_approval_record_guards_require_decided_pack():
    ledger = FakeLedgerStore()
    diagnosed = _diagnose(FakeBackend([_evidence(True, 17209)]))

    with pytest.raises(ValueError, match="decision record"):
        _write_decision_record(ledger, diagnosed)
    with pytest.raises(ValueError, match="approval record"):
        _write_approval_record(ledger, diagnosed, approver="op", note="")

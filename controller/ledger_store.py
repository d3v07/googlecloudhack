from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from controller.schemas import DecisionAction, Evidence, EvidencePack, PackStatus

SLOW_QUERIES = "slow_queries"
CANDIDATES = "candidates"
EXPERIMENTS = "experiments"
DECISIONS = "decisions"
EVIDENCE_PACKS = "evidence_packs"
APPROVALS = "approvals"
APPLICATIONS = "applications"
VERIFICATIONS = "verifications"

LEDGER_COLLECTIONS = (
    SLOW_QUERIES,
    CANDIDATES,
    EXPERIMENTS,
    DECISIONS,
    EVIDENCE_PACKS,
    APPROVALS,
    APPLICATIONS,
    VERIFICATIONS,
)


class LedgerStore(Protocol):
    def upsert(self, collection: str, record_id: str, document: Mapping[str, Any]) -> None: ...


class FakeLedgerStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, dict[str, Any]]] = {
            collection: {} for collection in LEDGER_COLLECTIONS
        }

    def upsert(self, collection: str, record_id: str, document: Mapping[str, Any]) -> None:
        self.records.setdefault(collection, {})[record_id] = {"_id": record_id, **dict(document)}


class MongoLedgerStore:
    def __init__(self, database: Any) -> None:
        self._db = database

    def upsert(self, collection: str, record_id: str, document: Mapping[str, Any]) -> None:
        self._db[collection].replace_one(
            {"_id": record_id}, {"_id": record_id, **dict(document)}, upsert=True
        )


def record_id(run_id: str, event: str) -> str:
    return f"{run_id}:{event}"


def write_gate_opened_record(
    ledger: LedgerStore | None,
    *,
    run_id: str,
    namespace: str,
    created_at: str,
) -> None:
    if ledger is None:
        return
    ledger.upsert(
        APPROVALS,
        record_id(run_id, "gate:opened"),
        {
            "run_id": run_id,
            "namespace": namespace,
            "phase": "gate",
            "event": "opened",
            "status": "collecting_evidence",
            "created_at": created_at,
            "mutation_allowed": False,
        },
    )


def write_gate_pending_record(ledger: LedgerStore | None, *, pack: EvidencePack) -> None:
    if ledger is None:
        return
    ledger.upsert(
        APPROVALS,
        record_id(pack.run_id, "gate:pending"),
        _base(pack, phase="gate", event="pending_approval")
        | {
            "required_hash": pack.evidence_hash,
            "mutation_allowed": False,
        },
    )


def write_diagnosis_records(
    ledger: LedgerStore | None,
    *,
    pack: EvidencePack,
    query_filter: dict[str, Any],
    query_sort: list[tuple[str, int]],
    limit: int,
    current_index: str,
    source: str = "deterministic_esr",
) -> None:
    if ledger is None:
        return
    query = {"filter": query_filter, "sort": query_sort, "limit": limit}
    ledger.upsert(
        SLOW_QUERIES,
        record_id(pack.run_id, "diagnose:slow_query"),
        _base(pack, phase="diagnose", event="slow_query")
        | {"query": query, "evidence": _evidence(pack.before), "source": source},
    )
    ledger.upsert(
        CANDIDATES,
        record_id(pack.run_id, "diagnose:candidate"),
        _base(pack, phase="diagnose", event="candidate")
        | {
            "index_spec": _index_spec(pack.recommendation.index_spec),
            "rationale": pack.recommendation.rationale,
            "source": source,
            "selected": True,
        },
    )
    ledger.upsert(
        EXPERIMENTS,
        record_id(pack.run_id, "diagnose:before"),
        _base(pack, phase="diagnose", event="before_explain")
        | {
            "hint": current_index,
            "outcome": _metrics(pack.before),
            "blocking_sort_detected": pack.before.metrics.has_blocking_sort,
            "source": source,
        },
    )
    write_gate_pending_record(ledger, pack=pack)
    write_pack_record(ledger, pack)


def write_rejection_records(
    ledger: LedgerStore | None,
    *,
    pack: EvidencePack,
    approver: str,
    note: str,
) -> None:
    if ledger is None:
        return
    _write_decision_record(ledger, pack)
    _write_approval_record(ledger, pack, approver=approver, note=note)
    write_pack_record(ledger, pack)


def write_application_records(
    ledger: LedgerStore | None,
    *,
    pack: EvidencePack,
    approver: str,
    note: str,
    index_name: str,
) -> None:
    if ledger is None:
        return
    _write_decision_record(ledger, pack)
    _write_approval_record(ledger, pack, approver=approver, note=note)
    ledger.upsert(
        APPLICATIONS,
        record_id(pack.run_id, "approve:application"),
        _base(pack, phase="approve", event="application")
        | {
            "index_name": index_name,
            "index_spec": _index_spec(pack.recommendation.index_spec),
            "status": "applied",
        },
    )
    ledger.upsert(
        VERIFICATIONS,
        record_id(pack.run_id, "verify:verification"),
        _base(pack, phase="verify", event="verification")
        | {
            "outcome": "passed" if pack.status is PackStatus.VERIFIED else "failed",
            "before": _metrics(pack.before),
            "after": _metrics(pack.after) if pack.after is not None else None,
        },
    )
    write_pack_record(ledger, pack)


def write_pack_record(ledger: LedgerStore, pack: EvidencePack) -> None:
    ledger.upsert(EVIDENCE_PACKS, pack.run_id, pack.model_dump(mode="json"))


def _write_decision_record(ledger: LedgerStore, pack: EvidencePack) -> None:
    if pack.decision is None:
        raise ValueError("decision record requires a decided pack")
    ledger.upsert(
        DECISIONS,
        record_id(pack.run_id, "approve:decision"),
        _base(pack, phase="approve", event="decision")
        | {
            "action": pack.decision.action.value,
            "decision_phase": pack.decision.phase.value,
            "decision_evidence_hash": pack.decision.evidence_hash,
        },
    )


def _write_approval_record(
    ledger: LedgerStore, pack: EvidencePack, *, approver: str, note: str
) -> None:
    if pack.decision is None:
        raise ValueError("approval record requires a decided pack")
    event = "approval" if pack.decision.action is DecisionAction.APPROVE else "rejection"
    ledger.upsert(
        APPROVALS,
        record_id(pack.run_id, f"approve:{event}"),
        _base(pack, phase="approve", event=event)
        | {
            "approver": approver,
            "note": note,
            "action": pack.decision.action.value,
            "decision_evidence_hash": pack.decision.evidence_hash,
        },
    )


def _base(pack: EvidencePack, *, phase: str, event: str) -> dict[str, Any]:
    return {
        "run_id": pack.run_id,
        "namespace": pack.namespace,
        "phase": phase,
        "event": event,
        "status": pack.status.value,
        "evidence_hash": pack.evidence_hash,
        "created_at": pack.created_at,
    }


def _evidence(evidence: Evidence) -> dict[str, Any]:
    return evidence.model_dump(mode="json")


def _metrics(evidence: Evidence) -> dict[str, Any]:
    metrics = evidence.metrics
    return {
        "docs_examined": metrics.docs_examined,
        "docs_returned": metrics.docs_returned,
        "millis": metrics.millis,
        "total_keys_examined": metrics.total_keys_examined,
        "stages": list(metrics.stages),
        "has_blocking_sort": metrics.has_blocking_sort,
    }


def _index_spec(index_spec: tuple[tuple[str, int], ...]) -> list[list[Any]]:
    return [[field, direction] for field, direction in index_spec]

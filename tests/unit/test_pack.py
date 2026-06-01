import json
import pathlib

import pytest
from pydantic import ValidationError

from controller.diagnosis import diagnose
from controller.pack import build_pack, pack_evidence_hash
from controller.phases import Phase
from controller.schemas import (
    Decision,
    DecisionAction,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    PackStatus,
)

SCHEMA = pathlib.Path("contracts/evidence_pack.schema.json")
EXAMPLE = pathlib.Path("contracts/examples/evidence_pack.example.json")

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]


def _before() -> Evidence:
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": 20},
        explain_plan={"stage": "FETCH", "inputStage": {"stage": "SORT"}},
        metrics=EvidenceMetrics(
            docs_examined=20, docs_returned=20, millis=41, total_keys_examined=17209,
            stages=("FETCH", "SORT", "IXSCAN"),
        ),
    )


def _diagnosed_pack() -> EvidencePack:
    diagnosis = diagnose(QUERY_FILTER, QUERY_SORT, has_blocking_sort=True, current_index="esr_wrong_B")
    return build_pack(
        run_id="r1",
        namespace="sample_supplies.sales_agent_demo",
        created_at="2026-06-01T00:00:00Z",
        before=_before(),
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
    )


def test_build_pack_is_diagnosed_and_hash_binds_evidence_and_recommendation():
    pack = _diagnosed_pack()

    assert pack.status is PackStatus.DIAGNOSED
    assert pack.decision is None
    assert pack.version == "v1"
    assert pack.evidence_hash == pack_evidence_hash(pack.before, pack.recommendation)


def test_hash_changes_when_the_recommendation_changes():
    pack = _diagnosed_pack()
    other = diagnose({"x": "y"}, [("ts", -1)], has_blocking_sort=True)

    assert pack_evidence_hash(pack.before, other.recommendation) != pack.evidence_hash


def test_decision_must_bind_the_pack_hash():
    pack = _diagnosed_pack()
    mismatched = Decision(action=DecisionAction.APPROVE, evidence_hash="0" * 64, phase=Phase.APPROVE)

    with pytest.raises(ValidationError):
        EvidencePack(
            run_id=pack.run_id, namespace=pack.namespace, created_at=pack.created_at,
            status=PackStatus.APPROVED, before=pack.before, finding=pack.finding,
            recommendation=pack.recommendation, decision=mismatched,
            evidence_hash=pack.evidence_hash,
        )


def test_matching_decision_is_accepted():
    pack = _diagnosed_pack()
    good = Decision(
        action=DecisionAction.APPROVE, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE
    )

    approved = EvidencePack(
        run_id=pack.run_id, namespace=pack.namespace, created_at=pack.created_at,
        status=PackStatus.APPROVED, before=pack.before, finding=pack.finding,
        recommendation=pack.recommendation, decision=good, evidence_hash=pack.evidence_hash,
    )

    assert approved.decision.evidence_hash == approved.evidence_hash


def test_committed_example_validates_against_the_contract():
    pack = EvidencePack.model_validate_json(EXAMPLE.read_text())

    assert pack.version == "v1"
    assert pack.status is PackStatus.DIAGNOSED
    assert pack.recommendation.index_spec[0] == ("storeLocation", 1)
    assert pack.narrative is None  # example keeps narrative unset


def test_committed_schema_is_in_sync_with_the_model():
    assert json.loads(SCHEMA.read_text()) == EvidencePack.model_json_schema()
    assert "narrative" in EvidencePack.model_json_schema()["properties"]

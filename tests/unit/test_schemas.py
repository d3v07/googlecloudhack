import pytest
from pydantic import ValidationError

from controller.phases import Phase
from controller.schemas import (
    Decision,
    DecisionAction,
    Diagnosis,
    Evidence,
    EvidenceMetrics,
    Finding,
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


def test_diagnosis_composes_finding_and_recommendation():
    diagnosis = Diagnosis(
        finding=Finding(problem="blocking sort", severity=Severity.HIGH, evidence_refs=("x",)),
        recommendation=Recommendation(index_spec=(("a", 1),), rationale="esr"),
    )

    assert diagnosis.finding.severity is Severity.HIGH
    assert diagnosis.recommendation.index_spec == (("a", 1),)

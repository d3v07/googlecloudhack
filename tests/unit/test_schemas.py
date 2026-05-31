import pytest
from pydantic import ValidationError

from controller.phases import Phase
from controller.schemas import (
    Decision,
    DecisionAction,
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
        metrics={"docs_examined": 3, "docs_returned": 1, "millis": 0.7},
    )

    assert evidence.metrics == EvidenceMetrics(docs_examined=3, docs_returned=1, millis=0.7)


def test_evidence_model_rejects_negative_metrics():
    with pytest.raises(ValidationError):
        Evidence(
            query="db.orders.find({tenant: 42})",
            explain_plan={"stage": "IXSCAN"},
            metrics={"docs_examined": -1, "docs_returned": 1, "millis": 0.7},
        )


def test_models_are_frozen():
    evidence = Evidence(
        query={"tenant": 42, "nested": {"status": "open"}, "stages": [{"name": "ixscan"}]},
        explain_plan={"stage": "IXSCAN", "inputStage": {"indexName": "tenant_1"}},
        metrics=EvidenceMetrics(docs_examined=3, docs_returned=1, millis=0.7),
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
        index_spec={"tenant": 1, "status": 1}, rationale="covers filter"
    )
    decision = Decision(
        action=DecisionAction.APPROVE,
        evidence_hash="a" * 64,
        phase=Phase.APPROVE,
    )

    assert finding.evidence_refs == ("abc",)
    assert recommendation.index_spec == {"tenant": 1, "status": 1}
    assert decision.phase is Phase.APPROVE


def test_recommendation_index_spec_is_deeply_frozen():
    recommendation = Recommendation(
        index_spec={"keys": {"tenant": 1}, "options": [{"name": "tenant_1"}], "tags": {"stable"}},
        rationale="covers filter",
    )

    with pytest.raises(TypeError):
        recommendation.index_spec["keys"]["tenant"] = -1
    with pytest.raises(TypeError):
        recommendation.index_spec["options"][0]["name"] = "other"
    assert recommendation.model_dump()["index_spec"] == {
        "keys": {"tenant": 1},
        "options": [{"name": "tenant_1"}],
        "tags": ["stable"],
    }


def test_decision_rejects_invalid_hash():
    with pytest.raises(ValidationError):
        Decision(action=DecisionAction.APPROVE, evidence_hash="not-a-hash", phase=Phase.APPROVE)

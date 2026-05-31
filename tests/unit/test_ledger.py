from controller.ledger import evidence_hash
from controller.schemas import Evidence, EvidenceMetrics


def test_evidence_hash_is_stable_for_same_model():
    evidence = Evidence(
        query={"status": "open", "tenant": 42},
        explain_plan={"stage": "COLLSCAN"},
        metrics=EvidenceMetrics(docs_examined=100, docs_returned=4, millis=9.5),
    )

    assert evidence_hash(evidence) == evidence_hash(evidence)


def test_evidence_hash_sorts_nested_keys_and_excludes_volatile_fields():
    left = {
        "query": {"tenant": 42, "status": "open"},
        "timestamp": "2026-05-31T00:00:00Z",
        "explain_plan": {"inputStage": {"stage": "COLLSCAN", "direction": "forward"}},
    }
    right = {
        "explain_plan": {"inputStage": {"direction": "forward", "stage": "COLLSCAN"}},
        "generated_at": "2028-01-01T00:00:00Z",
        "query": {"status": "open", "tenant": 42},
    }

    assert evidence_hash(left) == evidence_hash(right)


def test_evidence_hash_is_order_independent_for_collections():
    first = Evidence(
        query={"status": "open"},
        explain_plan={"stage": "IXSCAN"},
        metrics=EvidenceMetrics(docs_examined=10, docs_returned=2, millis=1.5),
    )
    second = Evidence(
        query={"status": "closed"},
        explain_plan={"stage": "COLLSCAN"},
        metrics=EvidenceMetrics(docs_examined=300, docs_returned=3, millis=12),
    )

    assert evidence_hash([first, second]) == evidence_hash([second, first])


def test_evidence_hash_preserves_nested_list_order():
    left = {"explain_plan": {"stages": ["IXSCAN", "FETCH"]}}
    right = {"explain_plan": {"stages": ["FETCH", "IXSCAN"]}}

    assert evidence_hash(left) != evidence_hash(right)


def test_evidence_hash_is_order_independent_for_sets():
    assert evidence_hash({"values": {"b", "a"}}) == evidence_hash({"values": {"a", "b"}})


def test_evidence_hash_handles_byte_values():
    assert evidence_hash({"explain": b"abc"}) == evidence_hash({"explain": b"abc"})

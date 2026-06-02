"""Python-native Mongo tools for Agent Engine.

These tools are read-only. They mirror the deterministic controller's demo fixture
query and never create or drop indexes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from controller.demo_fixture import COLL, DB, LIMIT, QUERY_FILTER, QUERY_SORT
from controller.diagnosis import diagnose
from controller.explain import capture_evidence, get_connection_string
from controller.schemas import Evidence

INDEX_B_NAME = "esr_wrong_B"
INDEX_C_NAME = "esr_right_C"
INDEX_B_KEYS = (("storeLocation", 1), ("customer.age", 1), ("saleDate", -1))
INDEX_C_KEYS = (("storeLocation", 1), ("saleDate", -1), ("customer.age", 1))
NAMESPACE = f"{DB}.{COLL}"


def _require_connection_string() -> str:
    conn = get_connection_string()
    if conn:
        return conn
    raise RuntimeError(
        "MongoDB connection unavailable: set MONGO_SECRET_NAME for Agent Engine "
        "or MDB_MCP_CONNECTION_STRING locally."
    )


def _capture_with_hint(hint: str | list[tuple[str, int]]) -> Evidence:
    from pymongo import MongoClient

    client = MongoClient(_require_connection_string())
    try:
        return capture_evidence(client[DB][COLL], QUERY_FILTER, QUERY_SORT, LIMIT, hint=hint)
    finally:
        client.close()


def _evidence_payload(evidence: Evidence, *, hint: str | list[tuple[str, int]]) -> dict[str, Any]:
    return {
        "namespace": NAMESPACE,
        "hint": hint,
        "evidence": evidence.model_dump(mode="json"),
        "metrics": evidence.metrics.model_dump(mode="json"),
    }


def _candidate_payload(
    name: str, index_spec: tuple[tuple[str, int], ...], evidence: Evidence
) -> dict[str, Any]:
    return {
        "name": name,
        "index_spec": [[field, direction] for field, direction in index_spec],
        "has_blocking_sort": evidence.metrics.has_blocking_sort,
        "total_keys_examined": evidence.metrics.total_keys_examined,
        "docs_examined": evidence.metrics.docs_examined,
        "docs_returned": evidence.metrics.docs_returned,
        "stages": list(evidence.metrics.stages),
    }


def explain_slow_query() -> dict[str, Any]:
    """Capture the canonical slow-query evidence by hinting the known wrong ESR index."""
    evidence = _capture_with_hint(INDEX_B_NAME)
    return _evidence_payload(evidence, hint=INDEX_B_NAME)


def compare_candidate_indexes() -> dict[str, Any]:
    """Compare wrong-vs-correct ESR candidates using read-only hinted explains."""
    wrong = _capture_with_hint(INDEX_B_NAME)
    correct = _capture_with_hint(list(INDEX_C_KEYS))
    return {
        "namespace": NAMESPACE,
        "query": {"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        "candidates": [
            _candidate_payload(INDEX_B_NAME, INDEX_B_KEYS, wrong),
            _candidate_payload(INDEX_C_NAME, INDEX_C_KEYS, correct),
        ],
        "winner": INDEX_C_NAME
        if correct.metrics.total_keys_examined < wrong.metrics.total_keys_examined
        else INDEX_B_NAME,
    }


def diagnose_candidate() -> dict[str, Any]:
    """Run the deterministic ESR diagnosis from live slow-query evidence."""
    evidence = _capture_with_hint(INDEX_B_NAME)
    diagnosis = diagnose(
        QUERY_FILTER,
        QUERY_SORT,
        has_blocking_sort=evidence.metrics.has_blocking_sort,
        current_index=INDEX_B_NAME,
    )
    return {
        "namespace": NAMESPACE,
        "source": "deterministic_esr",
        "before": evidence.model_dump(mode="json"),
        "diagnosis": diagnosis.model_dump(mode="json"),
    }


def rationalize_recommendation() -> dict[str, Any]:
    """Return a concise evidence-grounded rationale for the ESR recommendation."""
    slow = _capture_with_hint(INDEX_B_NAME)
    fast = _capture_with_hint(list(INDEX_C_KEYS))
    diagnosis = diagnose(
        QUERY_FILTER,
        QUERY_SORT,
        has_blocking_sort=slow.metrics.has_blocking_sort,
        current_index=INDEX_B_NAME,
    )
    before_keys = slow.metrics.total_keys_examined
    after_keys = fast.metrics.total_keys_examined
    return {
        "namespace": NAMESPACE,
        "recommended_index": diagnosis.recommendation.model_dump(mode="json")["index_spec"],
        "rationale": (
            "Index B puts the range field before the sort field, causing a blocking SORT "
            f"and {before_keys} keys examined. ESR index C moves saleDate before "
            f"customer.age, removes the SORT stage, and examines {after_keys} keys."
        ),
        "evidence": {
            "before_keys_examined": before_keys,
            "after_keys_examined": after_keys,
            "before_has_blocking_sort": slow.metrics.has_blocking_sort,
            "after_has_blocking_sort": fast.metrics.has_blocking_sort,
        },
    }


def tool_manifest() -> tuple[Mapping[str, str], ...]:
    return (
        {"name": "explain_slow_query", "mutation": "none", "phase": "diagnose"},
        {"name": "compare_candidate_indexes", "mutation": "none", "phase": "diagnose"},
        {"name": "diagnose_candidate", "mutation": "none", "phase": "diagnose"},
        {"name": "rationalize_recommendation", "mutation": "none", "phase": "diagnose"},
    )

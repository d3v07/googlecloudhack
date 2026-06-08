"""Python-native Mongo tools for Agent Engine.

These tools are read-only and query-parameterised: each one takes the captured slow query as a
JSON string (`query_json`) and explains/diagnoses THAT query against the live collection. They
never create or drop an index — the ESR-correct index is derived deterministically and is built
only after a human approves the evidence hash.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from controller.demo_fixture import COLL, DB
from controller.diagnosis import diagnose
from controller.explain import capture_evidence, get_connection_string
from controller.schemas import Evidence

NAMESPACE = f"{DB}.{COLL}"


def _require_connection_string() -> str:
    conn = get_connection_string()
    if conn:
        return conn
    raise RuntimeError(
        "MongoDB connection unavailable: set MONGO_SECRET_NAME for Agent Engine "
        "or MDB_MCP_CONNECTION_STRING locally."
    )


def _parse_query(
    query_json: str | Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, int]], int]:
    """Parse the query the orchestrator passes to every tool.

    Accepts {"filter": ..., "sort": [["f", -1]], "limit": N} or a {"query": {...}} wrapper.
    """
    data = json.loads(query_json) if isinstance(query_json, str) else dict(query_json)
    spec = data.get("query", data) if isinstance(data, dict) else {}
    query_filter = dict(spec.get("filter", {}))
    query_sort = [(str(field), int(direction)) for field, direction in spec.get("sort", [])]
    limit = int(spec.get("limit", 20))
    return query_filter, query_sort, limit


def _capture(
    query_filter: Mapping[str, Any], query_sort: Sequence[tuple[str, int]], limit: int
) -> Evidence:
    """Capture the query's NATURAL explain plan (no index hint), read-only."""
    from pymongo import MongoClient

    client = MongoClient(_require_connection_string())
    try:
        return capture_evidence(client[DB][COLL], query_filter, query_sort, limit)
    finally:
        client.close()


def _query_echo(
    query_filter: Mapping[str, Any], query_sort: Sequence[tuple[str, int]], limit: int
) -> dict[str, Any]:
    return {
        "filter": dict(query_filter),
        "sort": [[field, direction] for field, direction in query_sort],
        "limit": limit,
    }


def _recommended_spec(diagnosis: Any) -> list[list[Any]]:
    return [[field, direction] for field, direction in diagnosis.recommendation.index_spec]


def explain_slow_query(query_json: str) -> dict[str, Any]:
    """Explain the given slow query's natural plan and return its before-evidence.

    Args:
        query_json: JSON string of the query, e.g.
            {"filter": {"purchaseMethod": "Phone", "customer.age": {"$gte": 55, "$lte": 75}},
             "sort": [["saleDate", -1]], "limit": 15}
    """
    query_filter, query_sort, limit = _parse_query(query_json)
    evidence = _capture(query_filter, query_sort, limit)
    return {
        "namespace": NAMESPACE,
        "query": _query_echo(query_filter, query_sort, limit),
        "evidence": evidence.model_dump(mode="json"),
        "metrics": evidence.metrics.model_dump(mode="json"),
    }


def compare_candidate_indexes(query_json: str) -> dict[str, Any]:
    """Compare the query's current plan against the ESR-recommended index (read-only).

    The current plan is measured; the recommended index is derived deterministically and is NOT
    created here — diagnosis never mutates. The recommendation is the winner.

    Args:
        query_json: JSON string {"filter": ..., "sort": ..., "limit": ...}.
    """
    query_filter, query_sort, limit = _parse_query(query_json)
    current = _capture(query_filter, query_sort, limit)
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=current.metrics.has_blocking_sort,
        current_index=None,
    )
    return {
        "namespace": NAMESPACE,
        "query": _query_echo(query_filter, query_sort, limit),
        "candidates": [
            {
                "name": "current_plan",
                "index_spec": None,
                "has_blocking_sort": current.metrics.has_blocking_sort,
                "total_keys_examined": current.metrics.total_keys_examined,
                "docs_examined": current.metrics.docs_examined,
                "docs_returned": current.metrics.docs_returned,
                "stages": list(current.metrics.stages),
            },
            {
                "name": "esr_recommended",
                "index_spec": _recommended_spec(diagnosis),
            },
        ],
        "winner": "esr_recommended",
    }


def diagnose_candidate(query_json: str) -> dict[str, Any]:
    """Capture natural evidence for the query and run the deterministic ESR diagnosis.

    Args:
        query_json: JSON string {"filter": ..., "sort": ..., "limit": ...}.
    """
    query_filter, query_sort, limit = _parse_query(query_json)
    evidence = _capture(query_filter, query_sort, limit)
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=evidence.metrics.has_blocking_sort,
        current_index=None,
    )
    return {
        "namespace": NAMESPACE,
        "source": "deterministic_esr",
        "before": evidence.model_dump(mode="json"),
        "diagnosis": diagnosis.model_dump(mode="json"),
        "recommended_index": _recommended_spec(diagnosis),
    }


def rationalize_recommendation(query_json: str) -> dict[str, Any]:
    """Return an evidence-grounded rationale for the ESR recommendation (read-only).

    Args:
        query_json: JSON string {"filter": ..., "sort": ..., "limit": ...}.
    """
    query_filter, query_sort, limit = _parse_query(query_json)
    current = _capture(query_filter, query_sort, limit)
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=current.metrics.has_blocking_sort,
        current_index=None,
    )
    spec = _recommended_spec(diagnosis)
    keys = current.metrics.total_keys_examined
    docs = current.metrics.docs_examined
    returned = current.metrics.docs_returned
    order = ", ".join(f"{field}:{direction}" for field, direction in spec)
    problem = (
        "performs a blocking in-memory SORT"
        if current.metrics.has_blocking_sort
        else "over-scans the collection"
    )
    return {
        "namespace": NAMESPACE,
        "recommended_index": spec,
        "rationale": (
            f"The query examines {keys} keys and {docs} documents to return {returned}, and "
            f"{problem}. The ESR-ordered index ({order}) places equality fields first, the sort "
            "field next, and range fields last, so the index supplies the requested order and "
            "removes the blocking SORT."
        ),
        "evidence": {
            "keys_examined": keys,
            "docs_examined": docs,
            "docs_returned": returned,
            "has_blocking_sort": current.metrics.has_blocking_sort,
        },
    }


def tool_manifest() -> tuple[Mapping[str, str], ...]:
    return (
        {"name": "explain_slow_query", "mutation": "none", "phase": "diagnose"},
        {"name": "compare_candidate_indexes", "mutation": "none", "phase": "diagnose"},
        {"name": "diagnose_candidate", "mutation": "none", "phase": "diagnose"},
        {"name": "rationalize_recommendation", "mutation": "none", "phase": "diagnose"},
    )

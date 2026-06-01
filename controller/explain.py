"""Explain capture adapter: run a query's executionStats explain and extract the
structural ESR signals into an Evidence. The `collection` is any object exposing
pymongo's `find().sort().limit().hint().explain()` chain, so this stays driver-thin
and unit-testable with a fake collection.
"""

import os
from collections.abc import Mapping, Sequence
from typing import Any

from controller.schemas import Evidence, EvidenceMetrics

_CONN_VARS = ("MDB_MCP_CONNECTION_STRING", "MONGODB_TARGET_URI")


def get_connection_string() -> str | None:
    for var in _CONN_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return None


def _walk_stages(plan: Mapping[str, Any]) -> list[str]:
    stages: list[str] = []
    node: Any = plan
    while isinstance(node, Mapping):
        stage = node.get("stage")
        if stage:
            stages.append(stage)
        if "inputStage" in node:
            node = node["inputStage"]
        elif "inputStages" in node:
            for child in node["inputStages"]:
                stages.extend(_walk_stages(child))
            break
        else:
            break
    return stages


def capture_evidence(
    collection: Any,
    query_filter: Mapping[str, Any],
    query_sort: Sequence[tuple[str, int]],
    limit: int,
    hint: Any | None = None,
) -> Evidence:
    cursor = collection.find(dict(query_filter), sort=list(query_sort), limit=limit)
    if hint is not None:
        cursor = cursor.hint(hint)
    explained = cursor.explain()

    winning = explained["queryPlanner"]["winningPlan"]
    stats = explained["executionStats"]
    metrics = EvidenceMetrics(
        docs_examined=stats["totalDocsExamined"],
        docs_returned=stats["nReturned"],
        millis=float(stats.get("executionTimeMillis", 0)),
        total_keys_examined=stats["totalKeysExamined"],
        stages=tuple(_walk_stages(winning)),
    )
    return Evidence(
        query={"filter": dict(query_filter), "sort": list(query_sort), "limit": limit},
        explain_plan=winning,
        metrics=metrics,
    )

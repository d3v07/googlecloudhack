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


def _secret_project() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCRAH_AGENT_PROJECT")
    if project:
        return project
    raise RuntimeError(
        "MongoDB secret project unavailable: set GOOGLE_CLOUD_PROJECT or GCRAH_AGENT_PROJECT"
    )


def _connection_string_from_secret() -> str | None:
    secret_name = os.environ.get("MONGO_SECRET_NAME")
    if not secret_name:
        return None

    from google.cloud import secretmanager  # noqa: PLC0415

    version = os.environ.get("MONGO_SECRET_VERSION", "latest")
    client = secretmanager.SecretManagerServiceClient()
    path = f"projects/{_secret_project()}/secrets/{secret_name}/versions/{version}"
    response = client.access_secret_version(name=path)
    return response.payload.data.decode("utf-8")


def get_connection_string() -> str | None:
    for var in _CONN_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return _connection_string_from_secret()


def walk_stages(plan: Mapping[str, Any]) -> list[str]:
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
                stages.extend(walk_stages(child))
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
    max_time_ms: int | None = None,
) -> Evidence:
    cursor = collection.find(dict(query_filter), sort=list(query_sort), limit=limit)
    if hint is not None:
        cursor = cursor.hint(hint)
    if max_time_ms is not None:
        cursor = cursor.max_time_ms(max_time_ms)
    explained = cursor.explain()

    winning = explained["queryPlanner"]["winningPlan"]
    stats = explained["executionStats"]
    metrics = EvidenceMetrics(
        docs_examined=stats["totalDocsExamined"],
        docs_returned=stats["nReturned"],
        millis=float(stats.get("executionTimeMillis", 0)),
        total_keys_examined=stats["totalKeysExamined"],
        stages=tuple(walk_stages(winning)),
    )
    return Evidence(
        query={"filter": dict(query_filter), "sort": list(query_sort), "limit": limit},
        explain_plan=winning,
        metrics=metrics,
    )

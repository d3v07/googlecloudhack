"""Agent-facing tools and the pure explain->diagnosis bridge.

`diagnose_index` is the FunctionTool the agent calls. `diagnosis_from_explain` is the
pure adapter the scripted driver uses: it pulls the ESR signal out of a raw MCP/driver
explain document and runs the deterministic diagnosis — no I/O, fully testable offline.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from controller.diagnosis import diagnose
from controller.explain import walk_stages


def diagnose_index(
    query_filter: dict,
    query_sort: list,
    has_blocking_sort: bool,
    current_index: str,
) -> dict:
    """Diagnose an ESR index problem and recommend the correct index key order.

    Returns the Finding and the recommended index as ordered (field, direction) pairs.
    """
    sort_pairs = [(field, int(direction)) for field, direction in query_sort]
    diagnosis = diagnose(
        query_filter,
        sort_pairs,
        has_blocking_sort=has_blocking_sort,
        current_index=current_index or None,
    )
    return diagnosis.model_dump(mode="json")


def _index_name(plan: Mapping[str, Any]) -> str | None:
    node: Any = plan
    while isinstance(node, Mapping):
        if node.get("stage") == "IXSCAN":
            return node.get("indexName")
        node = node.get("inputStage")
    return None


def extract_explain_json(text: str) -> dict:
    """Pull the explain document out of the MongoDB MCP `explain` tool's response.

    That tool returns prose + the queryPlanner JSON wrapped in injection-guard tags,
    not raw JSON — so scan for the first balanced object that carries `queryPlanner`.
    """
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "queryPlanner" in obj:
            return obj
    raise ValueError("no queryPlanner JSON found in MCP explain response")


def diagnosis_from_explain(
    explain: Mapping[str, Any],
    query_filter: Mapping[str, Any],
    query_sort: Sequence[tuple[str, int]],
) -> dict:
    winning = explain["queryPlanner"]["winningPlan"]
    stages = walk_stages(winning)
    return diagnose_index(
        dict(query_filter),
        [list(pair) for pair in query_sort],
        has_blocking_sort="SORT" in stages,
        current_index=_index_name(winning) or "",
    )

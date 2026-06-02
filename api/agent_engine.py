"""Agent Engine diagnosis advisor used by the Cloud Run /run path.

The deployed agent is advisory only: it can propose/rationalize from observed evidence,
but the deterministic controller recomputes the winner and evidence hash.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from controller.orchestrator import DiagnosisAdvice
from controller.schemas import Evidence


def _normalize_index_spec(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list | tuple):
        return ()
    normalized: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) != 2:
            return ()
        field, direction = item
        try:
            normalized.append((str(field), int(direction)))
        except (TypeError, ValueError):
            return ()
    return tuple(normalized)


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


def _event_text(event: Any) -> str:
    if isinstance(event, dict):
        content = event.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if isinstance(parts, list):
            return "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        return str(event.get("text", ""))

    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if parts:
        return "".join(str(getattr(part, "text", "")) for part in parts)
    return str(getattr(event, "text", ""))


def _build_prompt(
    *,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    before: Evidence,
) -> str:
    metrics = before.metrics
    payload = {
        "run_id": run_id,
        "namespace": namespace,
        "query": {"filter": query_filter, "sort": query_sort, "limit": limit},
        "observed": {
            "stages": list(metrics.stages),
            "docs_examined": metrics.docs_examined,
            "docs_returned": metrics.docs_returned,
            "total_keys_examined": metrics.total_keys_examined,
            "has_blocking_sort": metrics.has_blocking_sort,
        },
    }
    return (
        "You are the DBRE Diagnose Agent. Review this MongoDB explain evidence and "
        "recommend the ESR-correct index. Return compact JSON with keys "
        "`recommended_index` as [[field, direction], ...] and `rationale` as one "
        "short paragraph. Do not request or perform any database mutation.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )


def _advice_from_text(resource_name: str, text: str) -> DiagnosisAdvice:
    parsed = _first_json_object(text)
    nested_recommendation = parsed.get("recommendation")
    nested_index = (
        nested_recommendation.get("index_spec") if isinstance(nested_recommendation, dict) else None
    )
    proposed = _normalize_index_spec(
        parsed.get("recommended_index") or parsed.get("index_spec") or nested_index
    )
    rationale = str(parsed.get("rationale") or "").strip() if parsed else ""
    narrative = rationale or text.strip()
    return DiagnosisAdvice(source=resource_name, narrative=narrative, proposed_index=proposed)


@dataclass(frozen=True)
class AgentEngineDiagnosisClient:
    resource_name: str
    project: str | None = None
    location: str | None = None

    @classmethod
    def from_env(cls) -> "AgentEngineDiagnosisClient | None":
        resource_name = os.environ.get("AGENT_ENGINE_RESOURCE")
        if not resource_name:
            return None
        return cls(
            resource_name=resource_name,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )

    async def advise(  # pragma: no cover - live Vertex AI I/O
        self,
        *,
        run_id: str,
        namespace: str,
        query_filter: dict,
        query_sort: list[tuple[str, int]],
        limit: int,
        before: Evidence,
    ) -> DiagnosisAdvice:
        import vertexai

        prompt = _build_prompt(
            run_id=run_id,
            namespace=namespace,
            query_filter=query_filter,
            query_sort=query_sort,
            limit=limit,
            before=before,
        )
        client = vertexai.Client(project=self.project, location=self.location)
        remote = client.agent_engines.get(name=self.resource_name)
        chunks: list[str] = []
        async for event in remote.async_stream_query(user_id=run_id, message=prompt):
            chunks.append(_event_text(event))
        return _advice_from_text(self.resource_name, "".join(chunks))

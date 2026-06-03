"""Agent Engine diagnosis client used by the Cloud Run /run path.

The deployed agent performs read-only Mongo diagnosis with native tools. The Cloud Run
controller still recomputes the ESR winner and evidence hash before emitting a pack.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from controller.orchestrator import AgentDiagnosisResult
from controller.schemas import (
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    Evidence,
)


class AgentDiagnosisParseError(ValueError):
    """Raised when Agent Engine returns a response that cannot be parsed as diagnosis."""


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


def _event_parts(event: Any) -> list[Any]:
    if isinstance(event, dict):
        content = event.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        return parts if isinstance(parts, list) else []

    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content else None
    return list(parts) if parts else []


def _part_text(part: Any) -> str:
    if isinstance(part, dict):
        return str(part.get("text", ""))
    return str(getattr(part, "text", ""))


def _part_function_response(part: Any) -> tuple[str, dict[str, Any]] | None:
    response = part.get("function_response") if isinstance(part, dict) else None
    if response is None and not isinstance(part, dict):
        response = getattr(part, "function_response", None)
    if response is None:
        return None

    name = response.get("name") if isinstance(response, dict) else getattr(response, "name", "")
    payload = (
        response.get("response")
        if isinstance(response, dict)
        else getattr(response, "response", None)
    )
    return (str(name), dict(payload)) if isinstance(payload, dict) else None


def _event_text(event: Any) -> str:
    if isinstance(event, dict) and not _event_parts(event):
        return str(event.get("text", ""))
    if not _event_parts(event):
        return str(getattr(event, "text", ""))
    return "".join(_part_text(part) for part in _event_parts(event))


def _event_function_responses(event: Any) -> list[tuple[str, dict[str, Any]]]:
    responses: list[tuple[str, dict[str, Any]]] = []
    for part in _event_parts(event):
        response = _part_function_response(part)
        if response is not None:
            responses.append(response)
    return responses


def _build_prompt(
    *,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
) -> str:
    payload = {
        "run_id": run_id,
        "namespace": namespace,
        "query": {"filter": query_filter, "sort": query_sort, "limit": limit},
    }
    return (
        "You are the DBRE Diagnose Agent. Run the native Mongo diagnosis tools in this "
        "order: explain_slow_query, compare_candidate_indexes, diagnose_candidate, "
        "rationalize_recommendation. Return compact JSON with keys `before`, "
        "`recommended_index`, `rationale`, and `tool_trace`. Do not perform any "
        "database mutation.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )


def _trace_for_tool(name: str, payload: dict[str, Any]) -> AgentTraceEvent:
    stage = {
        "explain_slow_query": AgentTraceStage.DETECT,
        "compare_candidate_indexes": AgentTraceStage.CANDIDATE,
        "diagnose_candidate": AgentTraceStage.DIAGNOSE,
        "rationalize_recommendation": AgentTraceStage.RATIONALE,
    }.get(name, AgentTraceStage.DIAGNOSE)
    summary = {
        "explain_slow_query": "Agent Engine captured slow-query explain evidence.",
        "compare_candidate_indexes": "Agent Engine compared candidate ESR indexes.",
        "diagnose_candidate": "Agent Engine ran deterministic ESR diagnosis.",
        "rationalize_recommendation": "Agent Engine produced an evidence-grounded rationale.",
    }.get(name, f"Agent Engine ran {name}.")
    if name == "compare_candidate_indexes" and payload.get("winner"):
        summary = f"Agent Engine compared candidates and selected {payload['winner']}."
    return AgentTraceEvent(
        stage=stage,
        actor=AgentTraceActor.AGENT_ENGINE,
        status=AgentTraceStatus.OK,
        tool=name,
        summary=summary,
    )


def _response_by_name(
    responses: list[tuple[str, dict[str, Any]]], name: str
) -> dict[str, Any] | None:
    for response_name, payload in reversed(responses):
        if response_name == name:
            return payload
    return None


def _before_from_payload(
    parsed: dict[str, Any], responses: list[tuple[str, dict[str, Any]]]
) -> Evidence:
    explain = _response_by_name(responses, "explain_slow_query")
    if explain and isinstance(explain.get("evidence"), dict):
        return Evidence.model_validate(explain["evidence"])

    diagnose_payload = _response_by_name(responses, "diagnose_candidate")
    if diagnose_payload and isinstance(diagnose_payload.get("before"), dict):
        return Evidence.model_validate(diagnose_payload["before"])

    before = parsed.get("before") or parsed.get("evidence")
    if isinstance(before, dict):
        if isinstance(before.get("evidence"), dict):
            before = before["evidence"]
        return Evidence.model_validate(before)
    raise ValueError("Agent Engine diagnosis did not return before evidence")


def _proposed_index_from_payload(
    parsed: dict[str, Any], responses: list[tuple[str, dict[str, Any]]]
) -> tuple[tuple[str, int], ...]:
    proposed = _normalize_index_spec(parsed.get("recommended_index") or parsed.get("index_spec"))
    if proposed:
        return proposed

    rationale_payload = _response_by_name(responses, "rationalize_recommendation") or {}
    proposed = _normalize_index_spec(rationale_payload.get("recommended_index"))
    if proposed:
        return proposed

    diagnosis_payload = _response_by_name(responses, "diagnose_candidate") or {}
    diagnosis = diagnosis_payload.get("diagnosis")
    recommendation = diagnosis.get("recommendation") if isinstance(diagnosis, dict) else None
    index_spec = recommendation.get("index_spec") if isinstance(recommendation, dict) else None
    return _normalize_index_spec(index_spec)


def _rationale_from_payload(
    parsed: dict[str, Any], responses: list[tuple[str, dict[str, Any]]], text: str
) -> str:
    if parsed.get("rationale"):
        return str(parsed["rationale"]).strip()
    rationale_payload = _response_by_name(responses, "rationalize_recommendation") or {}
    if rationale_payload.get("rationale"):
        return str(rationale_payload["rationale"]).strip()
    return text.strip()


def _diagnosis_from_events(
    resource_name: str, text: str, responses: list[tuple[str, dict[str, Any]]]
) -> AgentDiagnosisResult:
    parsed = _first_json_object(text)
    before = _before_from_payload(parsed, responses)
    proposed_index = _proposed_index_from_payload(parsed, responses)
    rationale = _rationale_from_payload(parsed, responses, text)
    trace = tuple(_trace_for_tool(name, payload) for name, payload in responses)
    return AgentDiagnosisResult(
        source=resource_name,
        before=before,
        narrative=rationale,
        proposed_index=proposed_index,
        trace=trace,
    )


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

    async def diagnose(  # pragma: no cover - live Vertex AI I/O
        self,
        *,
        run_id: str,
        namespace: str,
        query_filter: dict,
        query_sort: list[tuple[str, int]],
        limit: int,
    ) -> AgentDiagnosisResult:
        import vertexai

        prompt = _build_prompt(
            run_id=run_id,
            namespace=namespace,
            query_filter=query_filter,
            query_sort=query_sort,
            limit=limit,
        )
        client = vertexai.Client(project=self.project, location=self.location)
        remote = client.agent_engines.get(name=self.resource_name)
        chunks: list[str] = []
        responses: list[tuple[str, dict[str, Any]]] = []
        async for event in remote.async_stream_query(user_id=run_id, message=prompt):
            chunks.append(_event_text(event))
            responses.extend(_event_function_responses(event))
        try:
            return _diagnosis_from_events(self.resource_name, "".join(chunks), responses)
        except ValueError as exc:
            raise AgentDiagnosisParseError(str(exc)) from exc

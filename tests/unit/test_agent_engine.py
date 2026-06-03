import json

import pytest

from api.agent_engine import (
    AgentDiagnosisParseError,
    AgentEngineDiagnosisClient,
    AgentEngineDiagnosisPipeline,
    AgentEngineRoleClient,
    AgentEngineConfigError,
    _build_prompt,
    _diagnosis_from_events,
    _event_function_responses,
    _event_text,
    _first_json_object,
    _normalize_index_spec,
    diagnosis_agent_from_env,
)
from controller.schemas import AgentTraceActor, AgentTraceStage, Evidence, EvidenceMetrics


def _evidence_payload() -> dict:
    evidence = Evidence(
        query={"filter": {"x": 1}},
        explain_plan={"stage": "SORT"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=4,
            total_keys_examined=17209,
            stages=("FETCH", "SORT", "IXSCAN"),
        ),
    )
    return evidence.model_dump(mode="json")


def test_normalize_index_spec_accepts_json_pairs():
    assert _normalize_index_spec([["storeLocation", 1], ["saleDate", -1]]) == (
        ("storeLocation", 1),
        ("saleDate", -1),
    )


def test_normalize_index_spec_rejects_malformed_specs():
    assert _normalize_index_spec({"storeLocation": 1}) == ()
    assert _normalize_index_spec([["storeLocation"]]) == ()
    assert _normalize_index_spec([["storeLocation", "bad"]]) == ()


def test_first_json_object_extracts_embedded_object():
    assert _first_json_object('text before {"rationale":"ok"} text after') == {"rationale": "ok"}


def test_first_json_object_skips_malformed_candidates():
    assert _first_json_object('bad { json then good {"rationale":"ok"}') == {"rationale": "ok"}


def test_event_text_handles_dict_and_object_events():
    assert _event_text({"content": {"parts": [{"text": "a"}, {"text": "b"}]}}) == "ab"
    assert _event_text({"text": "plain"}) == "plain"

    class _Part:
        text = "c"

    class _Content:
        parts = [_Part()]

    class _Event:
        content = _Content()

    assert _event_text(_Event()) == "c"

    class _PlainEvent:
        text = "object-plain"

    assert _event_text(_PlainEvent()) == "object-plain"


def test_event_function_responses_handles_dict_events():
    event = {
        "content": {
            "parts": [
                {
                    "function_response": {
                        "name": "explain_slow_query",
                        "response": {"evidence": _evidence_payload()},
                    }
                }
            ]
        }
    }

    assert _event_function_responses(event) == [
        ("explain_slow_query", {"evidence": _evidence_payload()})
    ]


def test_event_function_responses_handles_object_events_and_ignores_missing():
    class _Response:
        name = "diagnose_candidate"
        response = {"before": _evidence_payload()}

    class _Part:
        function_response = _Response()

    class _EmptyPart:
        text = "no function"

    class _Content:
        parts = [_EmptyPart(), _Part()]

    class _Event:
        content = _Content()

    assert _event_function_responses(_Event()) == [
        ("diagnose_candidate", {"before": _evidence_payload()})
    ]


def test_diagnosis_from_tool_events_prefers_function_responses():
    responses = [
        ("explain_slow_query", {"evidence": _evidence_payload()}),
        (
            "diagnose_candidate",
            {
                "diagnosis": {
                    "recommendation": {
                        "index_spec": [
                            ["storeLocation", 1],
                            ["saleDate", -1],
                            ["customer.age", 1],
                        ]
                    }
                }
            },
        ),
        (
            "rationalize_recommendation",
            {
                "recommended_index": [
                    ["storeLocation", 1],
                    ["saleDate", -1],
                    ["customer.age", 1],
                ],
                "rationale": "ESR removes the blocking sort.",
            },
        ),
    ]

    result = _diagnosis_from_events("engine", "not-json", responses)

    assert result.before.metrics.total_keys_examined == 17209
    assert result.proposed_index == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert result.narrative == "ESR removes the blocking sort."
    assert result.trace[0].stage is AgentTraceStage.DETECT
    assert result.trace[0].actor is AgentTraceActor.AGENT_ENGINE


def test_diagnosis_trace_records_candidate_winner():
    responses = [
        ("explain_slow_query", {"evidence": _evidence_payload()}),
        ("compare_candidate_indexes", {"winner": "esr_right_C"}),
    ]

    result = _diagnosis_from_events("engine", "fallback rationale", responses)

    assert "selected esr_right_C" in result.trace[1].summary
    assert result.narrative == "fallback rationale"


def test_diagnosis_from_diagnose_payload_before_and_proposal():
    responses = [
        (
            "diagnose_candidate",
            {
                "before": _evidence_payload(),
                "diagnosis": {
                    "recommendation": {
                        "index_spec": [
                            ["storeLocation", 1],
                            ["saleDate", -1],
                            ["customer.age", 1],
                        ]
                    }
                },
            },
        )
    ]

    result = _diagnosis_from_events("engine", "plain rationale", responses)

    assert result.before.metrics.total_keys_examined == 17209
    assert result.proposed_index == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert result.narrative == "plain rationale"


def test_diagnosis_from_text_json_fallback():
    text = (
        '{"before":'
        + json.dumps(_evidence_payload())
        + ',"recommended_index":[["storeLocation",1],["saleDate",-1]],"rationale":"ok"}'
    )

    result = _diagnosis_from_events("engine", text, [])

    assert result.before.metrics.total_keys_examined == 17209
    assert result.proposed_index == (("storeLocation", 1), ("saleDate", -1))
    assert result.narrative == "ok"


def test_diagnosis_from_text_nested_evidence_fallback():
    text = (
        '{"evidence":{"evidence":'
        + json.dumps(_evidence_payload())
        + '},"rationale":"nested evidence"}'
    )

    result = _diagnosis_from_events("engine", text, [])

    assert result.before.metrics.total_keys_examined == 17209
    assert result.proposed_index == ()
    assert result.narrative == "nested evidence"


def test_diagnosis_from_events_requires_before_evidence():
    with pytest.raises(ValueError, match="before evidence"):
        _diagnosis_from_events("engine", '{"rationale":"missing"}', [])


def test_build_prompt_requests_native_tool_order():
    prompt = _build_prompt(
        run_id="run-1",
        namespace="db.coll",
        query_filter={"x": 1},
        query_sort=[("y", -1)],
        limit=20,
    )
    assert "explain_slow_query" in prompt
    assert "compare_candidate_indexes" in prompt
    assert "diagnose_candidate" in prompt
    assert '"run_id": "run-1"' in prompt


def test_client_from_env(monkeypatch):
    monkeypatch.delenv("AGENT_ENGINE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_CANDIDATE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_RATIONALE_RESOURCE", raising=False)
    assert AgentEngineDiagnosisClient.from_env() is None

    monkeypatch.setenv("AGENT_ENGINE_RESOURCE", "engine")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    client = AgentEngineDiagnosisClient.from_env()
    assert client is not None
    assert client.resource_name == "engine"
    assert client.project == "project"
    assert client.location == "global"


def test_diagnosis_agent_from_env_prefers_split_resources(monkeypatch):
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE", "legacy-engine")
    monkeypatch.setenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", "diagnose-engine")
    monkeypatch.setenv("AGENT_ENGINE_CANDIDATE_RESOURCE", "candidate-engine")
    monkeypatch.setenv("AGENT_ENGINE_RATIONALE_RESOURCE", "rationale-engine")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

    client = diagnosis_agent_from_env()

    assert isinstance(client, AgentEngineDiagnosisPipeline)
    assert client.diagnose_agent.resource_name == "diagnose-engine"
    assert client.candidate_agent.resource_name == "candidate-engine"
    assert client.rationale_agent.resource_name == "rationale-engine"
    assert client.diagnose_agent.location == "global"


def test_diagnosis_agent_from_env_rejects_partial_split_resources(monkeypatch):
    monkeypatch.delenv("AGENT_ENGINE_RESOURCE", raising=False)
    monkeypatch.setenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", "diagnose-engine")
    monkeypatch.delenv("AGENT_ENGINE_CANDIDATE_RESOURCE", raising=False)
    monkeypatch.setenv("AGENT_ENGINE_RATIONALE_RESOURCE", "rationale-engine")

    with pytest.raises(AgentEngineConfigError, match="partially configured"):
        diagnosis_agent_from_env()


def test_diagnosis_agent_from_env_rejects_duplicate_split_resources(monkeypatch):
    monkeypatch.delenv("AGENT_ENGINE_RESOURCE", raising=False)
    monkeypatch.setenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", "same-engine")
    monkeypatch.setenv("AGENT_ENGINE_CANDIDATE_RESOURCE", "same-engine")
    monkeypatch.setenv("AGENT_ENGINE_RATIONALE_RESOURCE", "rationale-engine")

    with pytest.raises(AgentEngineConfigError, match="distinct"):
        diagnosis_agent_from_env()


def test_diagnosis_agent_from_env_requires_split_in_production(monkeypatch):
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE", "legacy-engine")
    monkeypatch.delenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_CANDIDATE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_RATIONALE_RESOURCE", raising=False)

    with pytest.raises(AgentEngineConfigError, match="legacy-only"):
        diagnosis_agent_from_env(require_split=True, allow_legacy=False)


def test_diagnosis_agent_from_env_uses_legacy_when_split_absent(monkeypatch):
    monkeypatch.setenv("AGENT_ENGINE_RESOURCE", "legacy-engine")
    monkeypatch.delenv("AGENT_ENGINE_DIAGNOSE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_CANDIDATE_RESOURCE", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_RATIONALE_RESOURCE", raising=False)

    client = diagnosis_agent_from_env()

    assert isinstance(client, AgentEngineDiagnosisClient)
    assert client.resource_name == "legacy-engine"


class _FakeRoleClient:
    def __init__(self, resource_name: str, payloads: dict[str, dict]) -> None:
        self.resource_name = resource_name
        self.payloads = payloads
        self.calls: list[str] = []

    async def run_tool(self, *, user_id: str, tool_name: str, prompt: str):
        del user_id, prompt
        self.calls.append(tool_name)
        return f"text from {tool_name}", self.payloads[tool_name]


def test_split_pipeline_combines_three_agent_outputs():
    payloads = {
        "explain_slow_query": {"evidence": _evidence_payload()},
        "compare_candidate_indexes": {"winner": "esr_right_C"},
        "diagnose_candidate": {
            "before": _evidence_payload(),
            "diagnosis": {
                "recommendation": {
                    "index_spec": [
                        ["storeLocation", 1],
                        ["saleDate", -1],
                        ["customer.age", 1],
                    ]
                }
            },
        },
        "rationalize_recommendation": {
            "recommended_index": [
                ["storeLocation", 1],
                ["saleDate", -1],
                ["customer.age", 1],
            ],
            "rationale": "Rationale Agent grounded the ESR recommendation.",
        },
    }
    diagnose_client = _FakeRoleClient("diagnose-resource", payloads)
    candidate_client = _FakeRoleClient("candidate-resource", payloads)
    rationale_client = _FakeRoleClient("rationale-resource", payloads)
    pipeline = AgentEngineDiagnosisPipeline(
        diagnose_agent=diagnose_client,
        candidate_agent=candidate_client,
        rationale_agent=rationale_client,
    )

    import asyncio

    result = asyncio.run(
        pipeline.diagnose(
            run_id="split-run",
            namespace="db.coll",
            query_filter={"x": 1},
            query_sort=[("y", -1)],
            limit=20,
        )
    )

    assert diagnose_client.calls == ["explain_slow_query", "diagnose_candidate"]
    assert candidate_client.calls == ["compare_candidate_indexes"]
    assert rationale_client.calls == ["rationalize_recommendation"]
    assert result.source == "split_agent_engine"
    assert result.before.metrics.total_keys_examined == 17209
    assert result.proposed_index == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert [event.tool for event in result.trace] == [
        "explain_slow_query",
        "compare_candidate_indexes",
        "diagnose_candidate",
        "rationalize_recommendation",
    ]
    assert {event.component for event in result.trace} == {
        "diagnose_agent",
        "candidate_agent",
        "rationale_agent",
    }
    assert {event.resource for event in result.trace} == {
        "diagnose-resource",
        "candidate-resource",
        "rationale-resource",
    }


def test_role_client_rejects_extra_tool_responses(monkeypatch):
    class _Remote:
        async def async_stream_query(self, *, user_id: str, message: str):
            del user_id, message
            yield {
                "content": {
                    "parts": [
                        {
                            "function_response": {
                                "name": "explain_slow_query",
                                "response": {"evidence": _evidence_payload()},
                            }
                        },
                        {
                            "function_response": {
                                "name": "diagnose_candidate",
                                "response": {"before": _evidence_payload()},
                            }
                        },
                    ]
                }
            }

    class _AgentEngines:
        def get(self, *, name: str):
            assert name == "diagnose-resource"
            return _Remote()

    class _Client:
        agent_engines = _AgentEngines()

    class _Vertex:
        def Client(self, project, location):
            return _Client()

    import sys

    monkeypatch.setitem(sys.modules, "vertexai", _Vertex())
    client = AgentEngineRoleClient("diagnose-resource", "project", "us-central1")

    import asyncio

    with pytest.raises(AgentDiagnosisParseError, match="exactly one explain_slow_query"):
        asyncio.run(client.run_tool(user_id="u", tool_name="explain_slow_query", prompt="p"))

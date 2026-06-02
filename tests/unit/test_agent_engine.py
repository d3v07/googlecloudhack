import json

import pytest

from api.agent_engine import (
    AgentEngineDiagnosisClient,
    _build_prompt,
    _diagnosis_from_events,
    _event_function_responses,
    _event_text,
    _first_json_object,
    _normalize_index_spec,
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
    assert AgentEngineDiagnosisClient.from_env() is None

    monkeypatch.setenv("AGENT_ENGINE_RESOURCE", "engine")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    client = AgentEngineDiagnosisClient.from_env()
    assert client is not None
    assert client.resource_name == "engine"
    assert client.project == "project"
    assert client.location == "global"

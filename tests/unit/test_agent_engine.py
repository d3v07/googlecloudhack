from api.agent_engine import (
    AgentEngineDiagnosisClient,
    _advice_from_text,
    _build_prompt,
    _event_text,
    _first_json_object,
    _normalize_index_spec,
)
from controller.schemas import Evidence, EvidenceMetrics


def _evidence() -> Evidence:
    return Evidence(
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


def test_advice_from_text_parses_json_index_and_rationale():
    advice = _advice_from_text(
        "projects/p/locations/us-central1/reasoningEngines/1",
        '{"recommended_index":[["storeLocation",1],["saleDate",-1]],"rationale":"ESR"}',
    )
    assert advice.source.endswith("/1")
    assert advice.proposed_index == (("storeLocation", 1), ("saleDate", -1))
    assert advice.narrative == "ESR"


def test_advice_from_text_parses_nested_recommendation_index():
    advice = _advice_from_text(
        "engine",
        '{"recommendation":{"index_spec":[["storeLocation",1],["saleDate",-1]]}}',
    )
    assert advice.proposed_index == (("storeLocation", 1), ("saleDate", -1))


def test_advice_from_text_falls_back_to_raw_text():
    advice = _advice_from_text("engine", "plain rationale")
    assert advice.proposed_index == ()
    assert advice.narrative == "plain rationale"


def test_build_prompt_contains_observed_evidence():
    prompt = _build_prompt(
        run_id="run-1",
        namespace="db.coll",
        query_filter={"x": 1},
        query_sort=[("y", -1)],
        limit=20,
        before=_evidence(),
    )
    assert "DBRE Diagnose Agent" in prompt
    assert '"total_keys_examined": 17209' in prompt
    assert '"has_blocking_sort": true' in prompt


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

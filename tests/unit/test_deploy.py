from agents.deploy import _REQUIREMENTS, _resource_name, _staging_bucket


def test_staging_bucket_default_and_override(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_STAGING_BUCKET", raising=False)
    assert _staging_bucket("performer-497915") == "gs://performer-497915-agent-engine-staging"

    monkeypatch.setenv("GOOGLE_CLOUD_STAGING_BUCKET", "gs://custom-bucket")
    assert _staging_bucket("performer-497915") == "gs://custom-bucket"


def test_resource_name_prefers_api_resource():
    class _ApiResource:
        name = "projects/x/locations/us-central1/reasoningEngines/123"

    class _RemoteAgent:
        api_resource = _ApiResource()

    assert _resource_name(_RemoteAgent()) == "projects/x/locations/us-central1/reasoningEngines/123"


def test_resource_name_falls_back_to_name():
    class _RemoteAgent:
        api_resource = None
        name = "fallback-resource"

    assert _resource_name(_RemoteAgent()) == "fallback-resource"


def test_agent_engine_requirements_do_not_request_conflicting_adk_extra():
    assert "google-cloud-aiplatform[agent_engines]>=1.112" in _REQUIREMENTS
    assert all("[agent_engines,adk]" not in requirement for requirement in _REQUIREMENTS)
    assert "google-adk>=2.1.0" in _REQUIREMENTS

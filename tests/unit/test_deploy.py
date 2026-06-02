from agents.deploy import _REQUIREMENTS, _agent_env_vars, _resource_name, _staging_bucket


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
    assert "pymongo>=4.6" in _REQUIREMENTS
    assert "mcp" not in _REQUIREMENTS


def test_agent_env_vars_use_secret_manager_reference(monkeypatch):
    monkeypatch.setenv("MONGO_SECRET_NAME", "mongo-uri")
    monkeypatch.setenv("MONGO_SECRET_VERSION", "3")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash")

    env_vars = _agent_env_vars()

    assert env_vars["MONGODB_TARGET_URI"] == {"secret": "mongo-uri", "version": "3"}
    assert env_vars["GEMINI_MODEL"] == "gemini-3-flash"


def test_deploy_uses_packaging_create_api():
    import inspect

    from agents import deploy

    source = inspect.getsource(deploy.deploy)
    assert "agent_engines.create(" in source
    assert "client.agent_engines.create" not in source

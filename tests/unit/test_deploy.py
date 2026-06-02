from agents.deploy import (
    _ENTRYPOINT_MODULE,
    _ENTRYPOINT_OBJECT,
    _MAX_INSTANCES,
    _MIN_INSTANCES,
    _REQUIREMENTS,
    _REQUIREMENTS_FILE,
    _SOURCE_PACKAGES,
    _agent_env_vars,
    _class_methods_for_source_deploy,
    _resource_name,
    _staging_bucket,
)


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


def test_resource_name_prefers_legacy_resource_name_before_short_name():
    class _RemoteAgent:
        api_resource = None
        resource_name = "projects/p/locations/us-central1/reasoningEngines/123"
        name = "123"

    assert _resource_name(_RemoteAgent()) == (
        "projects/p/locations/us-central1/reasoningEngines/123"
    )


def test_agent_engine_requirements_do_not_request_conflicting_adk_extra():
    assert "google-cloud-aiplatform[agent_engines]>=1.112" in _REQUIREMENTS
    assert all("[agent_engines,adk]" not in requirement for requirement in _REQUIREMENTS)
    assert "google-adk>=2.1.0" in _REQUIREMENTS
    assert "pymongo>=4.6" in _REQUIREMENTS
    assert "mcp" not in _REQUIREMENTS


def test_agent_engine_source_requirements_match_runtime_list():
    with open(_REQUIREMENTS_FILE, encoding="utf-8") as requirements_file:
        source_requirements = [
            line.strip() for line in requirements_file if line.strip() and not line.startswith("#")
        ]

    assert source_requirements == _REQUIREMENTS


def test_agent_env_vars_use_secret_manager_reference(monkeypatch):
    monkeypatch.setenv("MONGO_SECRET_NAME", "mongo-uri")
    monkeypatch.setenv("MONGO_SECRET_VERSION", "3")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash")

    env_vars = _agent_env_vars("performer-497915", "us-central1")

    assert env_vars["GOOGLE_CLOUD_PROJECT"] == "performer-497915"
    assert env_vars["GOOGLE_CLOUD_LOCATION"] == "us-central1"
    assert env_vars["MONGODB_TARGET_URI"] == {"secret": "mongo-uri", "version": "3"}
    assert env_vars["GEMINI_MODEL"] == "gemini-3-flash"


def test_deploy_uses_source_code_api():
    import inspect

    from agents import deploy

    source = inspect.getsource(deploy.deploy)
    assert "client.agent_engines.create(" in source
    assert "source_packages" in source
    assert "entrypoint_module" in source
    assert "agent_engine=" not in source


def test_agent_engine_runtime_keeps_demo_instance_warm():
    assert _MIN_INSTANCES == 1
    assert _MAX_INSTANCES == 1


def test_agent_engine_source_entrypoint_points_to_adk_app():
    assert _SOURCE_PACKAGES == ("agents", "controller")
    assert _ENTRYPOINT_MODULE == "agents.agent_engine_app"
    assert _ENTRYPOINT_OBJECT == "adk_app"


def test_agent_engine_source_class_methods_include_stream_query():
    methods = _class_methods_for_source_deploy()
    by_name = {method["name"]: method for method in methods}

    assert by_name["async_stream_query"]["api_mode"] == "async_stream"
    assert by_name["stream_query"]["api_mode"] == "stream"


def test_agent_engine_source_entrypoint_imports_adk_app():
    from vertexai.agent_engines.templates.adk import AdkApp

    from agents.agent_engine_app import adk_app

    assert isinstance(adk_app, AdkApp)
    assert hasattr(adk_app, "async_stream_query")
    assert hasattr(adk_app, "stream_query")

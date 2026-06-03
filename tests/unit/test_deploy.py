from agents.deploy import (
    _EXTRA_PACKAGES,
    _MAX_INSTANCES,
    _MIN_INSTANCES,
    _REQUIREMENTS,
    _agent_env_vars,
    _resource_name,
    _staging_bucket,
    ROLE_ENV_VARS,
)
from agents.agent import AgentRole


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
    assert "google-cloud-secret-manager>=2.20" in _REQUIREMENTS
    assert "pymongo>=4.6" in _REQUIREMENTS
    assert "mcp" not in _REQUIREMENTS


def test_agent_env_vars_use_secret_manager_reference(monkeypatch):
    monkeypatch.setenv("MONGO_SECRET_NAME", "mongo-uri")
    monkeypatch.setenv("MONGO_SECRET_VERSION", "3")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash")

    env_vars = _agent_env_vars("performer-497915", "us-central1")

    assert env_vars["GCRAH_AGENT_PROJECT"] == "performer-497915"
    assert env_vars["GCRAH_AGENT_LOCATION"] == "us-central1"
    assert env_vars["GCRAH_AGENT_ROLE"] == "full"
    assert env_vars["MONGO_SECRET_NAME"] == "mongo-uri"
    assert env_vars["MONGO_SECRET_VERSION"] == "3"
    assert env_vars["GEMINI_MODEL"] == "gemini-3-flash"


def test_agent_env_vars_include_role(monkeypatch):
    monkeypatch.setenv("MONGO_SECRET_NAME", "mongo-uri")

    env_vars = _agent_env_vars("performer-497915", "us-central1", AgentRole.CANDIDATE)

    assert env_vars["GCRAH_AGENT_ROLE"] == "candidate"


def test_role_env_vars_match_cloud_run_contract():
    assert ROLE_ENV_VARS == {
        AgentRole.DIAGNOSE: "AGENT_ENGINE_DIAGNOSE_RESOURCE",
        AgentRole.CANDIDATE: "AGENT_ENGINE_CANDIDATE_RESOURCE",
        AgentRole.RATIONALE: "AGENT_ENGINE_RATIONALE_RESOURCE",
    }


def test_deploy_uses_object_package_api():
    import inspect

    from agents import deploy

    source = inspect.getsource(deploy.deploy)
    assert "client.agent_engines.create(" in source
    assert "agent=app" in source
    assert "extra_packages" in source
    assert "source_packages" not in source


def test_agent_engine_runtime_keeps_demo_instance_warm():
    assert _MIN_INSTANCES == 1
    assert _MAX_INSTANCES == 1


def test_agent_engine_extra_packages_include_project_code():
    assert _EXTRA_PACKAGES == ("controller", "agents")


def test_agent_engine_factory_builds_adk_app():
    from vertexai.agent_engines.templates.adk import AdkApp

    from agents.agent_engine_factory import build_adk_app

    app = build_adk_app()
    assert isinstance(app, AdkApp)
    assert hasattr(app, "async_stream_query")
    assert hasattr(app, "stream_query")


def test_agent_engine_factory_builds_split_role_apps():
    from vertexai.agent_engines.templates.adk import AdkApp

    from agents.agent_engine_factory import build_adk_app

    for role in (AgentRole.DIAGNOSE, AgentRole.CANDIDATE, AgentRole.RATIONALE):
        app = build_adk_app(role=role)
        assert isinstance(app, AdkApp)
        assert role.value in app._app_name()

import os
import subprocess


def _run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "deploy/deploy_cloudrun.sh"],
        cwd=os.getcwd(),
        env={**os.environ, **env},
        text=True,
        capture_output=True,
        check=False,
    )


def test_cloudrun_deploy_fails_when_run_api_token_missing():
    result = _run_script(
        {
            "RUN_API_TOKEN": "",
            "AGENT_ENGINE_DIAGNOSE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/d",
            "AGENT_ENGINE_CANDIDATE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/c",
            "AGENT_ENGINE_RATIONALE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/r",
            "MONGO_SECRET_NAME": "mongo-uri",
        }
    )

    assert result.returncode == 1
    assert "RUN_API_TOKEN is required" in result.stdout


def test_cloudrun_deploy_fails_when_split_agent_engine_resource_missing():
    result = _run_script(
        {
            "RUN_API_TOKEN": "test-token",
            "AGENT_ENGINE_DIAGNOSE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/d",
            "AGENT_ENGINE_CANDIDATE_RESOURCE": "",
            "AGENT_ENGINE_RATIONALE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/r",
            "MONGO_SECRET_NAME": "mongo-uri",
        }
    )

    assert result.returncode == 1
    assert "all three split Agent Engine resources are required" in result.stdout


def test_cloudrun_deploy_fails_when_mongo_secret_name_missing():
    result = _run_script(
        {
            "RUN_API_TOKEN": "test-token",
            "AGENT_ENGINE_DIAGNOSE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/d",
            "AGENT_ENGINE_CANDIDATE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/c",
            "AGENT_ENGINE_RATIONALE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/r",
            "MONGO_SECRET_NAME": "",
        }
    )

    assert result.returncode == 1
    assert "MONGO_SECRET_NAME is required" in result.stdout


def test_cloudrun_deploy_fails_when_split_agent_resources_are_duplicate():
    same = "projects/p/locations/us-central1/reasoningEngines/same"
    result = _run_script(
        {
            "RUN_API_TOKEN": "test-token",
            "AGENT_ENGINE_DIAGNOSE_RESOURCE": same,
            "AGENT_ENGINE_CANDIDATE_RESOURCE": same,
            "AGENT_ENGINE_RATIONALE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/r",
            "MONGO_SECRET_NAME": "mongo-uri",
        }
    )

    assert result.returncode == 1
    assert "three distinct deployed agents" in result.stdout

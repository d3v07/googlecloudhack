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
            "AGENT_ENGINE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/e",
            "MONGO_SECRET_NAME": "mongo-uri",
        }
    )

    assert result.returncode == 1
    assert "RUN_API_TOKEN is required" in result.stdout


def test_cloudrun_deploy_fails_when_agent_engine_resource_missing():
    result = _run_script(
        {
            "RUN_API_TOKEN": "test-token",
            "AGENT_ENGINE_RESOURCE": "",
            "MONGO_SECRET_NAME": "mongo-uri",
        }
    )

    assert result.returncode == 1
    assert "AGENT_ENGINE_RESOURCE is required" in result.stdout


def test_cloudrun_deploy_fails_when_mongo_secret_name_missing():
    result = _run_script(
        {
            "RUN_API_TOKEN": "test-token",
            "AGENT_ENGINE_RESOURCE": "projects/p/locations/us-central1/reasoningEngines/e",
            "MONGO_SECRET_NAME": "",
        }
    )

    assert result.returncode == 1
    assert "MONGO_SECRET_NAME is required" in result.stdout

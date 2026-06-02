"""Production deploy of the DBRE ADK agent to Vertex AI Agent Engine.

Creates a PERSISTENT (not torn-down) Agent Engine resource — the hackathon hosted URL.

Run:
    uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \\
           --with google-adk \\
           --with python-dotenv \\
           python -m agents.deploy [deploy | teardown --name RESOURCE_NAME]

All heavy imports (vertexai, agent_engines) are lazy so this module stays
importable in CI without the aiplatform package installed.
"""

import argparse
import os

from agents.agent import build_agent

_REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines]>=1.112",
    "google-adk>=2.1.0",
    "mcp",
    "pydantic>=2.0",
    "cloudpickle>=3.0",
]


def _staging_bucket(project: str) -> str:
    return os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET", f"gs://{project}-agent-engine-staging")


def _resource_name(remote_agent) -> str:
    api_resource = getattr(remote_agent, "api_resource", None)
    return getattr(api_resource, "name", "") or getattr(remote_agent, "name", "")


def deploy() -> str:  # pragma: no cover - live deploy
    import vertexai
    from vertexai import agent_engines
    from vertexai import types as vertexai_types

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    staging_bucket = _staging_bucket(project)

    print(f"PROJECT={project}")
    print(f"LOCATION={location}")
    print(f"STAGING_BUCKET={staging_bucket}")

    client = vertexai.Client(project=project, location=location)
    app = agent_engines.AdkApp(agent=build_agent(), app_name="gcrah_dbre_agent")

    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "display_name": "GCRAH DBRE Agent",
            "description": "Evidence-driven MongoDB performance engineer — ESR index diagnosis.",
            "requirements": _REQUIREMENTS,
            # the pickled agent's tools import these local packages — ship them into
            # the runtime (pip requirements alone don't include first-party code)
            "extra_packages": ["controller", "agents"],
            "staging_bucket": staging_bucket,
            "identity_type": vertexai_types.IdentityType.AGENT_IDENTITY,
            "min_instances": 0,
            "max_instances": 1,
        },
    )

    resource_name = _resource_name(remote_agent)
    print(f"ENGINE_RESOURCE={resource_name}")
    return resource_name


def teardown(resource_name: str) -> None:  # pragma: no cover - live deploy
    import vertexai

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    client = vertexai.Client(project=project, location=location)
    client.agent_engines.delete(name=resource_name, force=True)
    print(f"TEARDOWN=engine_deleted resource={resource_name}")


if __name__ == "__main__":  # pragma: no cover - live deploy
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Deploy or tear down the DBRE Agent Engine.")
    subparsers = parser.add_subparsers(dest="command", help="deploy | teardown")

    subparsers.add_parser("deploy", help="Create a persistent Agent Engine (default).")

    teardown_parser = subparsers.add_parser("teardown", help="Delete a deployed Agent Engine.")
    teardown_parser.add_argument("--name", required=True, help="Resource name to delete.")

    args = parser.parse_args()

    if args.command == "teardown":
        teardown(args.name)
    else:
        deploy()

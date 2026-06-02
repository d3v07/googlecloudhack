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
    "pydantic>=2.0",
    "pymongo>=4.6",
    "cloudpickle>=3.0",
]


def _staging_bucket(project: str) -> str:
    return os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET", f"gs://{project}-agent-engine-staging")


def _resource_name(remote_agent) -> str:
    api_resource = getattr(remote_agent, "api_resource", None)
    return getattr(api_resource, "name", "") or getattr(remote_agent, "name", "")


def _agent_env_vars() -> dict[str, str | dict[str, str]]:
    secret_name = os.environ.get("MONGO_SECRET_NAME", "mongodb-connection-string")
    secret_version = os.environ.get("MONGO_SECRET_VERSION", "latest")
    return {
        "MONGODB_TARGET_URI": {"secret": secret_name, "version": secret_version},
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    }


def deploy() -> str:  # pragma: no cover - live deploy
    import vertexai
    from vertexai import agent_engines

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    staging_bucket = _staging_bucket(project)
    env_vars = _agent_env_vars()

    print(f"PROJECT={project}")
    print(f"LOCATION={location}")
    print(f"STAGING_BUCKET={staging_bucket}")
    print(f"MONGO_SECRET_NAME={env_vars['MONGODB_TARGET_URI']['secret']}")

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)
    app = agent_engines.AdkApp(agent=build_agent(), app_name="gcrah_dbre_agent")

    remote_agent = agent_engines.create(
        agent_engine=app,
        display_name="GCRAH DBRE Agent",
        description="Evidence-driven MongoDB performance engineer — ESR index diagnosis.",
        requirements=_REQUIREMENTS,
        # the pickled agent's tools import these local packages — ship them into
        # the runtime (pip requirements alone don't include first-party code)
        extra_packages=["controller", "agents"],
        env_vars=env_vars,
        min_instances=0,
        max_instances=1,
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


async def smoke(resource_name: str, run_id: str = "agent-engine-smoke") -> None:  # pragma: no cover
    import vertexai

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    client = vertexai.Client(project=project, location=location)
    remote = client.agent_engines.get(name=resource_name)
    prompt = (
        "Run the native Mongo diagnosis tools in this order: explain_slow_query, "
        "compare_candidate_indexes, diagnose_candidate, rationalize_recommendation. "
        "Return compact JSON with tool names, candidate metrics, recommended_index, "
        "and rationale. Do not mutate the database."
    )
    async for event in remote.async_stream_query(user_id=run_id, message=prompt):
        print(event)


if __name__ == "__main__":  # pragma: no cover - live deploy
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Deploy or tear down the DBRE Agent Engine.")
    subparsers = parser.add_subparsers(dest="command", help="deploy | teardown")

    subparsers.add_parser("deploy", help="Create a persistent Agent Engine (default).")

    teardown_parser = subparsers.add_parser("teardown", help="Delete a deployed Agent Engine.")
    teardown_parser.add_argument("--name", required=True, help="Resource name to delete.")
    smoke_parser = subparsers.add_parser("smoke", help="Query a deployed Agent Engine.")
    smoke_parser.add_argument("--name", required=True, help="Resource name to query.")
    smoke_parser.add_argument("--run-id", default="agent-engine-smoke", help="Remote user id.")

    args = parser.parse_args()

    if args.command == "teardown":
        teardown(args.name)
    elif args.command == "smoke":
        import asyncio

        asyncio.run(smoke(args.name, args.run_id))
    else:
        deploy()

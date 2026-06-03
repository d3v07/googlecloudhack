"""Production deploy of the DBRE ADK agent to Vertex AI Agent Engine.

Creates a PERSISTENT (not torn-down) Agent Engine resource — the hackathon hosted URL.

Run:
    uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \\
           --with google-adk \\
           --with python-dotenv \\
           python -m agents.deploy [deploy-all | deploy --role ROLE | teardown --name RESOURCE_NAME]

All heavy imports (vertexai, agent_engines) are lazy so this module stays
importable in CI without the aiplatform package installed.
"""

import argparse
import os

from agents.agent import AgentRole
from agents.agent_engine_factory import build_adk_app

_REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines]>=1.112",
    "google-adk>=2.1.0",
    "google-cloud-secret-manager>=2.20",
    "pydantic>=2.0",
    "pymongo>=4.6",
    "cloudpickle>=3.0",
]
_MIN_INSTANCES = 1
_MAX_INSTANCES = 1
_EXTRA_PACKAGES = ("controller", "agents")


def _staging_bucket(project: str) -> str:
    return os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET", f"gs://{project}-agent-engine-staging")


def _resource_name(remote_agent) -> str:
    api_resource = getattr(remote_agent, "api_resource", None)
    return (
        getattr(api_resource, "name", "")
        or getattr(remote_agent, "resource_name", "")
        or getattr(remote_agent, "name", "")
    )


ROLE_ENV_VARS = {
    AgentRole.DIAGNOSE: "AGENT_ENGINE_DIAGNOSE_RESOURCE",
    AgentRole.CANDIDATE: "AGENT_ENGINE_CANDIDATE_RESOURCE",
    AgentRole.RATIONALE: "AGENT_ENGINE_RATIONALE_RESOURCE",
}


def _agent_env_vars(
    project: str | None = None,
    location: str | None = None,
    role: AgentRole | str = AgentRole.FULL,
) -> dict[str, str | dict[str, str]]:
    role = AgentRole(role)
    secret_name = os.environ.get("MONGO_SECRET_NAME", "mongodb-connection-string")
    secret_version = os.environ.get("MONGO_SECRET_VERSION", "latest")
    return {
        "GCRAH_AGENT_PROJECT": project or os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        "GCRAH_AGENT_LOCATION": location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        "GCRAH_AGENT_ROLE": role.value,
        "MONGO_SECRET_NAME": secret_name,
        "MONGO_SECRET_VERSION": secret_version,
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    }


def deploy(role: AgentRole | str = AgentRole.FULL) -> str:  # pragma: no cover - live deploy
    import vertexai
    from vertexai import types as vertexai_types

    role = AgentRole(role)
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    staging_bucket = _staging_bucket(project)
    env_vars = _agent_env_vars(project, location, role)

    print(f"PROJECT={project}")
    print(f"LOCATION={location}")
    print(f"ROLE={role.value}")
    print(f"STAGING_BUCKET={staging_bucket}")
    print(f"MONGO_SECRET_NAME={env_vars['MONGO_SECRET_NAME']}")

    app = build_adk_app(project, location, role)
    client = vertexai.Client(project=project, location=location)
    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "display_name": f"GCRAH DBRE {role.value.title()} Agent",
            "description": (f"Evidence-driven MongoDB performance engineer — {role.value} role."),
            "requirements": _REQUIREMENTS,
            "extra_packages": list(_EXTRA_PACKAGES),
            "agent_framework": "google-adk",
            "staging_bucket": staging_bucket,
            "env_vars": env_vars,
            "identity_type": vertexai_types.IdentityType.AGENT_IDENTITY,
            "min_instances": _MIN_INSTANCES,
            "max_instances": _MAX_INSTANCES,
        },
    )

    resource_name = _resource_name(remote_agent)
    env_var = ROLE_ENV_VARS.get(role, "AGENT_ENGINE_RESOURCE")
    print(f"{env_var}={resource_name}")
    return resource_name


def deploy_all() -> dict[AgentRole, str]:  # pragma: no cover - live deploy
    resources: dict[AgentRole, str] = {}
    for role in (AgentRole.DIAGNOSE, AgentRole.CANDIDATE, AgentRole.RATIONALE):
        resources[role] = deploy(role)
    print(
        "CLOUD_RUN_ENV="
        + ",".join(f"{ROLE_ENV_VARS[role]}={name}" for role, name in resources.items())
    )
    return resources


def teardown(resource_name: str) -> None:  # pragma: no cover - live deploy
    import vertexai

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    client = vertexai.Client(project=project, location=location)
    client.agent_engines.delete(name=resource_name, force=True)
    print(f"TEARDOWN=engine_deleted resource={resource_name}")


def _smoke_prompt(role: AgentRole) -> str:
    prompts = {
        AgentRole.DIAGNOSE: (
            "Run explain_slow_query and diagnose_candidate. Return compact JSON with "
            "tool names, before evidence, diagnosis, and recommended_index. Do not mutate."
        ),
        AgentRole.CANDIDATE: (
            "Run compare_candidate_indexes. Return compact JSON with tool names, candidate "
            "metrics, and winner. Do not mutate."
        ),
        AgentRole.RATIONALE: (
            "Run rationalize_recommendation. Return compact JSON with tool names, "
            "recommended_index, and rationale. Do not mutate."
        ),
        AgentRole.FULL: (
            "Run the native Mongo diagnosis tools in this order: explain_slow_query, "
            "compare_candidate_indexes, diagnose_candidate, rationalize_recommendation. "
            "Return compact JSON with tool names, candidate metrics, recommended_index, "
            "and rationale. Do not mutate the database."
        ),
    }
    return prompts[role]


async def smoke(
    resource_name: str,
    run_id: str = "agent-engine-smoke",
    role: AgentRole | str = AgentRole.FULL,
) -> None:  # pragma: no cover
    import vertexai

    role = AgentRole(role)
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    client = vertexai.Client(project=project, location=location)
    remote = client.agent_engines.get(name=resource_name)
    prompt = _smoke_prompt(role)
    async for event in remote.async_stream_query(user_id=run_id, message=prompt):
        print(event)


if __name__ == "__main__":  # pragma: no cover - live deploy
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Deploy or tear down the DBRE Agent Engine.")
    subparsers = parser.add_subparsers(dest="command", help="deploy-all | deploy | teardown")

    deploy_parser = subparsers.add_parser("deploy", help="Create a persistent Agent Engine.")
    deploy_parser.add_argument(
        "--role",
        choices=[role.value for role in AgentRole],
        default=AgentRole.FULL.value,
        help="Agent role to deploy.",
    )
    subparsers.add_parser("deploy-all", help="Create diagnose, candidate, and rationale engines.")

    teardown_parser = subparsers.add_parser("teardown", help="Delete a deployed Agent Engine.")
    teardown_parser.add_argument("--name", required=True, help="Resource name to delete.")
    smoke_parser = subparsers.add_parser("smoke", help="Query a deployed Agent Engine.")
    smoke_parser.add_argument("--name", required=True, help="Resource name to query.")
    smoke_parser.add_argument("--run-id", default="agent-engine-smoke", help="Remote user id.")
    smoke_parser.add_argument(
        "--role",
        choices=[role.value for role in AgentRole],
        default=AgentRole.FULL.value,
        help="Agent role prompt to use.",
    )

    args = parser.parse_args()

    if args.command == "teardown":
        teardown(args.name)
    elif args.command == "smoke":
        import asyncio

        asyncio.run(smoke(args.name, args.run_id, args.role))
    elif args.command == "deploy-all":
        deploy_all()
    else:
        deploy(args.role) if args.command == "deploy" else deploy_all()

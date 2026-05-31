"""Deploy a throwaway ADK agent to Agent Runtime and delete it.

Run:
uv run --with "google-cloud-aiplatform[agent_engines,adk]>=1.112" --with google-adk --with python-dotenv python spikes/day1_deploy/deploy.py
"""

import asyncio
import os
from collections.abc import AsyncIterator
from collections.abc import Mapping

from dotenv import load_dotenv

load_dotenv()

import vertexai
from vertexai import agent_engines
from vertexai import types as vertexai_types

from agent import root_agent


def _staging_bucket(project: str) -> str:
    return os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET", f"gs://{project}-agent-engine-staging")


def _event_text(event) -> str:
    if isinstance(event, Mapping):
        content = event.get("content", {})
        parts = content.get("parts", []) if isinstance(content, Mapping) else []
        return "\n".join(str(part.get("text")) for part in parts if part.get("text"))
    text = getattr(event, "text", None)
    if text:
        return str(text)
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return ""
    return "\n".join(str(part.text) for part in parts if getattr(part, "text", None))


async def _query(remote_agent) -> list[str]:
    chunks = []
    raw_events = []
    events: AsyncIterator = remote_agent.async_stream_query(
        user_id="deploy-spike",
        message="Confirm the hosted deployment is callable.",
    )
    async for event in events:
        raw_events.append(repr(event)[:500])
        text = _event_text(event)
        if text:
            chunks.append(text)
    if not chunks:
        print(f"REMOTE_EVENTS={raw_events}")
        raise RuntimeError("remote query returned no text")
    return chunks


def _resource_name(remote_agent) -> str:
    api_resource = getattr(remote_agent, "api_resource", None)
    return getattr(api_resource, "name", "") or getattr(remote_agent, "name", "")


def _delete_remote(client, remote_agent, resource_name: str) -> None:
    try:
        remote_agent.delete(force=True)
    except AttributeError:
        client.agent_engines.delete(name=resource_name, force=True)


async def main() -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    staging_bucket = _staging_bucket(project)
    client = vertexai.Client(project=project, location=location)
    app = agent_engines.AdkApp(agent=root_agent, app_name="gcrah_deploy_probe")
    remote_agent = None
    resource_name = ""

    print(f"PROJECT={project}")
    print(f"LOCATION={location}")
    print(f"MODEL={root_agent.model}")
    print(f"STAGING_BUCKET={staging_bucket}")
    print("DEPLOY_REQUEST=Confirm the hosted deployment is callable.")

    try:
        remote_agent = client.agent_engines.create(
            agent=app,
            config={
                "display_name": "GCRAH Day 1 deploy probe",
                "description": "Throwaway ADK Agent Runtime deploy spike.",
                "requirements": [
                    "google-cloud-aiplatform[agent_engines,adk]>=1.112",
                    "cloudpickle>=3.0",
                    "pydantic>=2.0",
                ],
                "staging_bucket": staging_bucket,
                "identity_type": vertexai_types.IdentityType.AGENT_IDENTITY,
                "min_instances": 0,
                "max_instances": 1,
            },
        )
        resource_name = _resource_name(remote_agent)
        print(f"ENGINE_RESOURCE={resource_name}")
        chunks = await _query(remote_agent)
        print(f"REMOTE_RESPONSE={' '.join(chunks).strip()}")
    finally:
        if remote_agent is None:
            print("TEARDOWN=skipped_no_engine_created")
        else:
            _delete_remote(client, remote_agent, resource_name)
            print(f"TEARDOWN=engine_deleted resource={resource_name}")


if __name__ == "__main__":
    asyncio.run(main())

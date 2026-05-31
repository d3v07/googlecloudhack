# Day 1 Agent Runtime Deploy Spike

## Scope

This spike deploys a throwaway ADK `Agent` to Vertex AI Agent Runtime, sends one remote request,
and deletes the deployed engine in a `finally` block.

## Current API

The current SDK path is:

```python
import vertexai
from vertexai import agent_engines

client = vertexai.Client(project=PROJECT_ID, location=LOCATION)
app = agent_engines.AdkApp(agent=root_agent)
remote_agent = client.agent_engines.create(agent=app, config={...})
```

Remote calls use `remote_agent.async_stream_query(...)`. Cleanup uses
`remote_agent.delete(force=True)`.

## Project Setup

Project:

```text
performer-497915
```

Runtime location:

```text
us-central1
```

Staging bucket:

```text
gs://performer-497915-agent-engine-staging
```

Required APIs:

- `aiplatform.googleapis.com`
- `storage.googleapis.com`
- `logging.googleapis.com`
- `monitoring.googleapis.com`
- `cloudtrace.googleapis.com`
- `cloudresourcemanager.googleapis.com`
- `telemetry.googleapis.com`

Required deploy identity roles:

- `roles/aiplatform.user` on the project for
  `dbre-agent@performer-497915.iam.gserviceaccount.com`
- `roles/aiplatform.admin` on the project for the same service account. `roles/aiplatform.user`
  was not enough to list/delete Agent Runtime resources during cleanup audit.
- `roles/storage.admin` on `gs://performer-497915-agent-engine-staging` for the same service account

The deployed agent uses Agent Identity:

```python
"identity_type": vertexai.types.IdentityType.AGENT_IDENTITY
```

## Run

```bash
uv run --with "google-cloud-aiplatform[agent_engines,adk]>=1.112" --with google-adk --with python-dotenv python spikes/day1_deploy/deploy.py
```

## Cost Notes

Agent Runtime billing is based on vCPU-seconds and GiB-seconds. Google lists a monthly free tier
for the runtime, then usage-based runtime charges. LLM token usage is billed separately. This spike
keeps `min_instances=0`, `max_instances=1`, sends one request, and deletes the engine immediately.

## Result

Successful live run:

```text
PROJECT=performer-497915
LOCATION=us-central1
MODEL=gemini-2.5-flash
STAGING_BUCKET=gs://performer-497915-agent-engine-staging
DEPLOY_REQUEST=Confirm the hosted deployment is callable.
ENGINE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/7667337133912227840
REMOTE_RESPONSE=deploy-ok: The hosted deployment is callable.
TEARDOWN=engine_deleted resource=projects/782567466199/locations/us-central1/reasoningEngines/7667337133912227840
```

Post-run cleanup audit:

```text
agent_engine_count=0
```

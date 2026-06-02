# DBRE Agent — Production Deploy Runbook

Deploys the DBRE ADK agent as a persistent Vertex AI Agent Engine resource.
The resource is NOT torn down after deploy — it remains callable at a stable hosted URL
for the duration of the hackathon.

## Prerequisites

### GCP Project

```text
GOOGLE_CLOUD_PROJECT=performer-497915
GOOGLE_CLOUD_LOCATION=us-central1
```

### Required APIs

All were enabled in the Day-1 spike. Confirm with:

```bash
gcloud services list --project performer-497915 --filter "NAME:aiplatform OR NAME:storage OR NAME:logging OR NAME:monitoring OR NAME:cloudtrace OR NAME:cloudresourcemanager OR NAME:telemetry"
```

Required:

- `aiplatform.googleapis.com`
- `storage.googleapis.com`
- `logging.googleapis.com`
- `monitoring.googleapis.com`
- `cloudtrace.googleapis.com`
- `cloudresourcemanager.googleapis.com`
- `telemetry.googleapis.com`

### Service Account IAM

SA: `dbre-agent@performer-497915.iam.gserviceaccount.com`

Required roles (already granted per spike):

- `roles/aiplatform.admin` on the project
- `roles/storage.admin` on `gs://performer-497915-agent-engine-staging`

### Staging Bucket

```text
gs://performer-497915-agent-engine-staging
```

Already created. The deploy script defaults to `gs://{project}-agent-engine-staging` when
`GOOGLE_CLOUD_STAGING_BUCKET` is unset.

### .env (local)

```bash
GOOGLE_CLOUD_PROJECT=performer-497915
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_STAGING_BUCKET=gs://performer-497915-agent-engine-staging
# MONGO_URI only needed if smoke-testing MCP path locally
```

## Deploy

From the repo root (takes 3-5 minutes while Agent Engine builds the container):

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy
```

Or explicitly pass the `deploy` subcommand:

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy deploy
```

Note: `-m agents.deploy` is required (not `python agents/deploy.py`). Script mode puts
`agents/` on `sys.path`, not the repo root, which breaks the `from agents.agent import build_agent`
and the downstream `controller.*` imports. `-m` mode puts the repo root on `sys.path`, matching
pytest's `pythonpath = ["."]` config.

Expected output:

```text
PROJECT=performer-497915
LOCATION=us-central1
STAGING_BUCKET=gs://performer-497915-agent-engine-staging
ENGINE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<id>
```

Save the `ENGINE_RESOURCE` value — it is the stable resource name for all subsequent calls and teardown.

## Smoke Test

After deploy completes, send one remote query to confirm the engine is callable:

```python
import vertexai
from vertexai import agent_engines

client = vertexai.Client(project="performer-497915", location="us-central1")
remote = client.agent_engines.get(name="<ENGINE_RESOURCE>")

import asyncio

async def ping():
    events = remote.async_stream_query(
        user_id="smoke-test",
        message="You have no tools to call. Reply: deploy-ok",
    )
    async for event in events:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            for p in parts:
                print(getattr(p, "text", ""))

asyncio.run(ping())
```

Expect: a text reply confirming the engine responds.

## MCP Toolset — Deferred

`build_agent()` deploys with only the `diagnose_index` FunctionTool. The MongoDB MCP toolset
(`build_mcp_toolset()`) is **not attached** for this deploy.

**Why:** the MCP toolset spawns `npx -y mongodb-mcp-server` over stdio at tool-call time.
Agent Engine's managed runtime is a Python-only container — there is no Node/npx in the image.
Attaching the MCP toolset would not fail at deploy time but would crash at every tool call,
which is worse.

**Follow-up options (post-hackathon):**

1. Expose a remote HTTP/SSE MCP endpoint and use `StreamableHTTPConnectionParams` instead of
   `StdioConnectionParams` — no Node required in the Agent Engine container.
2. Replace the MCP path with a native `pymongo`-backed FunctionTool for the explain/find/aggregate
   operations — keeps everything Python.
3. Build a custom Agent Engine container image that bundles Node, enabling npx at runtime.

For the hackathon demo the `diagnose_index` FunctionTool covers the core ESR diagnosis path.

## Cost Notes

Agent Engine billing is per vCPU-second and GiB-second of runtime (compute), plus standard
Gemini token charges. With `min_instances=0` the engine scales to zero when idle — no continuous
compute cost. Expect cold-start latency (~10-30 s) on the first call after idle. LLM calls are
billed at the Gemini model rate regardless of warm/cold state.

Rough estimate for hackathon use (light traffic, mostly idle): < $2 total.

## Teardown

After the hackathon, delete the persistent engine:

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy teardown --name "projects/782567466199/locations/us-central1/reasoningEngines/<id>"
```

Or use the Python API directly:

```python
client.agent_engines.delete(name="<ENGINE_RESOURCE>", force=True)
```

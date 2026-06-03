# DBRE Agent — Production Deploy Runbook

Deploys the DBRE ADK agent as three persistent Vertex AI Agent Engine resources:
Diagnose, Candidate, and Rationale. The resources are NOT torn down after deploy;
each remains callable at a stable hosted URL for the duration of the hackathon.

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
- `roles/secretmanager.secretAccessor` on the Mongo connection secret for the deployed
  Agent Engine identity

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
MONGO_SECRET_NAME=mongodb-connection-string
# Agent Engine reads this secret at tool-call time with its Agent Identity.
```

## Deploy

From the repo root (each role takes 3-5 minutes while Agent Engine builds the container):

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy deploy-all
```

To redeploy one role, explicitly pass the role:

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy deploy --role diagnose
```

Note: `-m agents.deploy` is required (not `python agents/deploy.py`). Script mode puts
`agents/` on `sys.path`, not the repo root, which breaks downstream `agents.*` and
`controller.*` imports. `-m` mode puts the repo root on `sys.path`, matching pytest's
`pythonpath = ["."]` config.

Each deploy uses the official ADK object deploy path:

- deployed object: role-specific `vertexai.agent_engines.AdkApp`
- extra packages: `controller/`, `agents/`
- requirements: runtime package list in `agents/deploy.py`
- runtime identity: Agent Identity, with MongoDB read from Secret Manager by name
- runtime env: non-reserved `GCRAH_AGENT_PROJECT` / `GCRAH_AGENT_LOCATION` seed
  the ADK app initialization, `GCRAH_AGENT_ROLE` selects the role, and
  `MONGO_SECRET_NAME` / `MONGO_SECRET_VERSION` identify the MongoDB URI secret.
  Google-reserved `GOOGLE_CLOUD_PROJECT` is not set by the deploy script.

Expected output:

```text
PROJECT=performer-497915
LOCATION=us-central1
ROLE=diagnose
STAGING_BUCKET=gs://performer-497915-agent-engine-staging
MONGO_SECRET_NAME=mongodb-connection-string
AGENT_ENGINE_DIAGNOSE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<diagnose-id>
...
AGENT_ENGINE_CANDIDATE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<candidate-id>
...
AGENT_ENGINE_RATIONALE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<rationale-id>
CLOUD_RUN_ENV=AGENT_ENGINE_DIAGNOSE_RESOURCE=projects/.../<diagnose-id>,AGENT_ENGINE_CANDIDATE_RESOURCE=projects/.../<candidate-id>,AGENT_ENGINE_RATIONALE_RESOURCE=projects/.../<rationale-id>
```

Save all three `AGENT_ENGINE_*_RESOURCE` values. Cloud Run requires the Diagnose,
Candidate, and Rationale resources and calls them in that order.

## Smoke Test

After deploy completes, send one remote query per role to confirm each engine is callable:

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy smoke \
         --name "projects/782567466199/locations/us-central1/reasoningEngines/<diagnose-id>" \
         --role diagnose
```

Repeat with the Candidate and Rationale resource names and matching `--role` values.
Expect streamed output for each role.

## MCP Toolset — Local Only

`build_agent()` deploys with Python-native Mongo FunctionTools plus the deterministic
`diagnose_index` FunctionTool. The MongoDB MCP toolset (`build_mcp_toolset()`) is **not
attached** for this deploy.

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

For the shipped demo, Agent Engine performs the read-only diagnosis, candidate
comparison, and rationale steps with Python-native Mongo tools. The deterministic
controller validates the ESR winner, hash, phase gate, apply, verification, and
ledger writes.

## Cost Notes

Agent Engine billing is per vCPU-second and GiB-second of runtime (compute), plus standard
Gemini token charges. The demo deployment keeps `min_instances=1` and `max_instances=1` so the
hosted runtime has a live instance for direct smoke tests and Cloud Run `/run` calls. Google
documents `min_instances=1` as the default; while this runtime-control feature is in Preview,
Google says higher minimum instances are not billed while the agent is idle. Recheck that note
before leaving the engine running after the hackathon. LLM calls are billed at the Gemini model
rate regardless of warm/cold state.

Rough estimate for hackathon use (light traffic, mostly idle): < $2 total, assuming the Preview
idle-billing behavior still applies.

## Teardown

After the hackathon, delete each persistent engine:

```bash
uv run --with "google-cloud-aiplatform[agent_engines]>=1.112" \
       --with google-adk \
       --with python-dotenv \
       python -m agents.deploy teardown --name "projects/782567466199/locations/us-central1/reasoningEngines/<diagnose-id>"
```

Or use the Python API directly:

```python
client.agent_engines.delete(name="<RESOURCE_NAME>", force=True)
```

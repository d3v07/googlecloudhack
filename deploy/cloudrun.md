# Cloud Run Deploy Runbook — gcrah-read-api

Service: **gcrah-read-api**
Project: **performer-497915**
Region: **us-central1**
Entrypoint: `api.server:app` (FastAPI, `create_app()` factory)

---

## Prerequisites

### 1. Secret Manager — Mongo connection string

The API reads the MongoDB Atlas URI from Secret Manager at startup. Create it once:

```bash
# Create the secret
gcloud secrets create mongodb-connection-string \
  --replication-policy=automatic \
  --project=performer-497915

# Add the connection string as version 1
echo -n "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/dbre_state?retryWrites=true" \
  | gcloud secrets versions add mongodb-connection-string \
      --data-file=- \
      --project=performer-497915
```

The secret name (`mongodb-connection-string`) is what you pass as `MONGO_SECRET_NAME`. The API
resolves the actual value using the Secret Manager SDK at runtime — the plaintext URI
never appears in Cloud Run env vars or logs.

### 2. Service account

Use the existing SA from the agent-runtime spike:

```
dbre-agent@performer-497915.iam.gserviceaccount.com
```

Grant it access to the secret:

```bash
gcloud secrets add-iam-policy-binding mongodb-connection-string \
  --project=performer-497915 \
  --role=roles/secretmanager.secretAccessor \
  --member="serviceAccount:dbre-agent@performer-497915.iam.gserviceaccount.com"
```

---

## Deploy

Run from the **repo root**:

```bash
export GCP_PROJECT=performer-497915
export MONGO_SECRET_NAME=mongodb-connection-string
export AGENT_ENGINE_DIAGNOSE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/DIAGNOSE_ENGINE_ID
export AGENT_ENGINE_CANDIDATE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/CANDIDATE_ENGINE_ID
export AGENT_ENGINE_RATIONALE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/RATIONALE_ENGINE_ID
export RUN_API_TOKEN=$(openssl rand -hex 16)   # gates the write endpoints; reads stay public
export SESSION_SECRET=$(openssl rand -hex 32)  # verifies dashboard session tokens — use the SAME value on the dashboard
bash deploy/deploy_cloudrun.sh
```

The script uses `--source .` which triggers Cloud Build to build from the `Dockerfile`
in the repo root and push the image to Artifact Registry automatically.

> **Write auth:** `POST /run` and `POST /packs/{id}/decision` require the
> `X-API-Token` header to match `RUN_API_TOKEN`. The deploy script fails if
> `RUN_API_TOKEN` is empty. Reads (`/health`, `/packs`) are always public. The
> dashboard must send the token from its server-side proxy; never expose it in
> the client bundle.
>
> **Agent Engine:** all three split resources are required for deploy:
> `AGENT_ENGINE_DIAGNOSE_RESOURCE`, `AGENT_ENGINE_CANDIDATE_RESOURCE`, and
> `AGENT_ENGINE_RATIONALE_RESOURCE`. `/run` opens the approval gate first, then
> calls the Diagnose, Candidate, and Rationale Agent Engine resources in order.
> The deterministic controller validates the winner/hash and emits the DIAGNOSED
> EvidencePack. `MONGO_SECRET_NAME` is also required; production must read MongoDB
> credentials from Secret Manager.

### What the script does

1. Grants `roles/secretmanager.secretAccessor` on the secret to the SA (idempotent).
2. Calls `gcloud run deploy` with:
   - `GOOGLE_CLOUD_PROJECT=performer-497915` — used by the Secret Manager client
   - `MONGO_SECRET_NAME=mongodb-connection-string` — the secret name (not the value)
   - `RUN_API_TOKEN` — shared secret gating the write endpoints
   - `AGENT_ENGINE_DIAGNOSE_RESOURCE` — deployed Diagnose Agent Engine resource
   - `AGENT_ENGINE_CANDIDATE_RESOURCE` — deployed Candidate Agent Engine resource
   - `AGENT_ENGINE_RATIONALE_RESOURCE` — deployed Rationale Agent Engine resource
   - SA: `dbre-agent@performer-497915.iam.gserviceaccount.com`
   - 0–3 instances, 512 MiB, 1 vCPU
3. Prints the live service URL.

---

## Smoke Tests

After deploy, get the URL:

```bash
SERVICE_URL=$(gcloud run services describe gcrah-read-api \
  --region us-central1 --project performer-497915 \
  --format "value(status.url)")
```

**Liveness:**
```bash
curl -sf "${SERVICE_URL}/health"
# Expected: {"status":"ok"}
```

**Pack list (empty is fine on first deploy):**
```bash
curl -sf "${SERVICE_URL}/packs"
# Expected: [] or a JSON array of evidence packs
```

**Single pack (replace RUN_ID with a real run_id from /packs):**
```bash
curl -sf "${SERVICE_URL}/packs/RUN_ID"
# Expected: JSON object with run_id, status, evidence, etc.
# 404 if pack doesn't exist
```

**Authenticate as the DBRE — the write endpoints now also require a session bearer:**
```bash
TOKEN=$(curl -sf -X POST "${SERVICE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"dbre","password":"<dbre-password>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
```

**Diagnose a captured query (a user must first run a workload so the queue is non-empty):**
```bash
# CAPTURED_ID comes from GET /workload/slow-queries (DBRE bearer required)
curl -sf -X POST "${SERVICE_URL}/run" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: ${RUN_API_TOKEN}" -H "Authorization: Bearer ${TOKEN}" \
  -d "{\"captured_query_id\": \"CAPTURED_ID\"}"
# Expected: 200 + a DIAGNOSED EvidencePack for that captured query (blocking sort,
# severity high, ESR recommendation). No index is applied yet.
# 401 without a valid bearer; 403 if the session is not the DBRE role.
```

**Approve → apply + verify (the human-gated mutation):**
```bash
curl -sf -X POST "${SERVICE_URL}/packs/RUN_ID/decision" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: ${RUN_API_TOKEN}" -H "Authorization: Bearer ${TOKEN}" \
  -d '{"decision": "approve", "evidence_hash": "<hash-from-pack>"}'
# Issues a hash-bound approval ticket, applies the recommended index, and verifies
# → 200 + a VERIFIED pack (no blocking sort, far fewer docs examined). The approver is
# taken from the verified DBRE session, not the request body.
# 401/403 without a valid DBRE bearer; 409 stale_evidence_hash / already_decided.
```

**Ledger records:** a completed approve flow creates or updates deterministic
records for the run in each internal collection: `slow_queries`, `candidates`,
`experiments`, `decisions`, `evidence_packs`, `approvals`, `applications`, and
`verifications`. The `approvals` collection includes `gate:opened` and
`gate:pending` records from `/run` before any mutation.

---

## Estimated Cost

Cloud Run charges only for active request time on this config (min-instances=0).

| Resource | Rate (approx) |
|---|---|
| vCPU-second | $0.000024/vCPU-s |
| Memory-second | $0.0000025/GiB-s |
| Requests | $0.40/million |
| Idle (min=0) | $0 — scales to zero |

For a hackathon with light traffic: well under $1/day.

---

## Teardown

```bash
gcloud run services delete gcrah-read-api \
  --region us-central1 \
  --project performer-497915 \
  --quiet
```

To also delete the secret:
```bash
gcloud secrets delete mongodb-connection-string --project performer-497915 --quiet
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `uvicorn: not found` at start | PATH not set in image | `ENV PATH="/app/.venv/bin:$PATH"` is in Dockerfile — rebuild |
| `ModuleNotFoundError: api` | Wrong import root | `--app-dir .` in CMD ensures `/app` is the import root |
| 500 on `/packs` | Mongo conn failed | Check SA has Secret Manager accessor role; verify secret version exists |
| 403 on Secret Manager | Missing IAM | Re-run the `gcloud secrets add-iam-policy-binding` command above |
| Port mismatch | Cloud Run injects `PORT` | CMD uses `${PORT:-8080}` via `sh -c` — already handled |

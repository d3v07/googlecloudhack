# Dashboard deploy → Cloud Run

Ship the Next.js DBRE Console to a public URL pointed at the live read API.
Mirrors the read-API runbook (`../deploy/cloudrun.md`).

> **Who runs this:** @d3v07 runs the `gcloud` deploy. The standalone build, Dockerfile,
> and the env contract below are ready in this branch.

## Service

- Service: **gcrah-dashboard**
- Project: **performer-497915**  ·  Region: **us-central1**
- Build: `Dockerfile` (multi-stage, Next standalone output) — runs `node server.js`, honors `PORT`.

## Required server env (set on the Cloud Run service)

| Var | Value | Why |
|-----|-------|-----|
| `API_URL` | the read API base URL | server proxies + server components fetch here |
| `SESSION_SECRET` | **byte-identical to the read API's `SESSION_SECRET`** | middleware verifies the HS256 session cookie with it. If absent or mismatched, `verifyToken` returns null and **every request bounces to `/login` even after a successful sign-in** — login silently fails |
| `RUN_API_TOKEN` | the read API's write token | injected by the `/api/diagnose` + `/api/decision` proxies as `X-API-Token`; **server-only, never in the client bundle** |

`SESSION_SECRET` and `RUN_API_TOKEN` must match the read API exactly and must **not** use the
`NEXT_PUBLIC_` prefix (that ships them to the browser). Do **not** set `NEXT_PUBLIC_API_URL`:
server components read the API via `API_URL` at runtime, and the public prefix would inline the
internal URL into the client bundle.

## Deploy

From `dashboard/` — use the SAME `SESSION_SECRET` + `RUN_API_TOKEN` set on the read API:

```bash
gcloud run deploy gcrah-dashboard \
  --source . \
  --project performer-497915 \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "API_URL=https://<read-api-host>" \
  --set-secrets "SESSION_SECRET=gcrah-session-secret:latest,RUN_API_TOKEN=gcrah-run-token:latest"
```

`--source .` triggers Cloud Build on the `Dockerfile`. Prefer Secret Manager (as shown) over
`--set-env-vars` for the two secrets.

## Smoke tests

```bash
URL=$(gcloud run services describe gcrah-dashboard \
  --region us-central1 --project performer-497915 --format "value(status.url)")

# unauthenticated request redirects to login (middleware)
curl -s -o /dev/null -w "%{http_code}\n" "$URL/"          # expect 307
curl -sf "$URL/login" | grep -q "DBRE Console" && echo "login ok"
```

Then in a browser (seed accounts first: `uv run python seed/seed_users.py`):

1. Sign in as a user (Dev Trivedi / Aakash Singh) → run a guided workload from the console.
2. Sign in as the DBRE → the Slow-Query Queue shows the captured query, ranked by evidence.
3. Diagnose → review the DIAGNOSED pack → Approve → the pack moves to `verified`.

## Build locally

```bash
npm ci
npm run build          # emits .next/standalone (output: "standalone")
```

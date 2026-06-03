# Dashboard deploy → Cloud Run (#32)

Ship the Next.js DBRE Console to a public URL pointed at the live read API.
Mirrors the read-API runbook (`../deploy/cloudrun.md`).

> **Who runs this:** @d3v07 runs the `gcloud` deploy (the dashboard author has no
> `gcloud` auth). Everything else — the standalone build, Dockerfile, and the
> env contract below — is ready in this branch.

## Service

- Service: **gcrah-dashboard**
- Project: **performer-497915**  ·  Region: **us-central1**
- Build: `Dockerfile` (multi-stage, Next standalone output) — runs `node server.js`, honors Cloud Run's `PORT`.

## Required server env (set on the Cloud Run service)

| Var | Value | Why |
|-----|-------|-----|
| `API_URL` | `https://gcrah-read-api-2vbnam7yma-uc.a.run.app` | the proxy routes forward here |
| `RUN_API_TOKEN` | *(the read API's write token)* | injected by the `/api/run` + `/api/decision` proxies as `X-API-Token`; **server-only, never in the client bundle** |
| `NEXT_PUBLIC_API_URL` | `https://gcrah-read-api-2vbnam7yma-uc.a.run.app` | browser-side reads (`/packs`, `/packs/{id}`) — unauthenticated, safe to expose |

`RUN_API_TOKEN` is the same secret already set on the read API. It must **not**
use the `NEXT_PUBLIC_` prefix (that would ship it to the browser). Reads need no
token; only the write proxies use it.

## Deploy

From `dashboard/`:

```bash
gcloud run deploy gcrah-dashboard \
  --source . \
  --project performer-497915 \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "API_URL=https://gcrah-read-api-2vbnam7yma-uc.a.run.app,NEXT_PUBLIC_API_URL=https://gcrah-read-api-2vbnam7yma-uc.a.run.app" \
  --set-env-vars "RUN_API_TOKEN=<the-write-token>"
```

`--source .` triggers Cloud Build to build the `Dockerfile`. (For a real secret,
prefer Secret Manager + `--set-secrets RUN_API_TOKEN=gcrah-run-token:latest`
instead of `--set-env-vars`, matching how the read API handles its Mongo URI.)

## Smoke tests

```bash
URL=$(gcloud run services describe gcrah-dashboard \
  --region us-central1 --project performer-497915 --format "value(status.url)")

curl -sf "$URL/" | grep -q "DBRE Console" && echo "homepage ok"

# the write proxy injects the token server-side; client sends none:
curl -sf -X POST "$URL/api/run" -H 'content-type: application/json' -d '{}' \
  | python3 -c "import json,sys; print('run ->', json.load(sys.stdin)['status'])"
```

Expected: `homepage ok`, then `run -> diagnosed`.

In the rendered page, the first viewport should show the **Approval Gate**. A live
run should move the gate from collecting evidence to `pending approval`, show the
`evidence hash`, and keep the live/ledger persisted footer. Approving the run should
return a `verified` pack and close the gate as verified.

## Local verification (already done)

The standalone server was run exactly as the container does it
(`node .next/standalone/server.js`, `PORT=8080`, env from `.env.local`):
homepage `200`, the ask-the-agent button renders, and `/api/run` returned a live
`diagnosed` pack with the ESR index C — proving the image + proxy work before the
cloud deploy.

## Build locally

```bash
npm ci
npm run build          # emits .next/standalone (output: "standalone")
# container entrypoint is: node server.js  (with static + public copied alongside)
```

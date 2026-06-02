#!/usr/bin/env bash
# deploy_cloudrun.sh — Cloud Run deploy for gcrah-read-api (issue #31)
#
# PURPOSE: Run this script manually from the repo root to deploy or re-deploy
#          the read API to Cloud Run. It does NOT run automatically.
#
# PREREQUISITES (complete these once before the first deploy):
#   1. Secret created in Secret Manager:
#        gcloud secrets create "$MONGO_SECRET_NAME" \
#          --replication-policy=automatic \
#          --project="$GCP_PROJECT"
#      Then add the connection string as the first version:
#        echo -n "mongodb+srv://..." | gcloud secrets versions add "$MONGO_SECRET_NAME" \
#          --data-file=- --project="$GCP_PROJECT"
#   2. Service account exists:
#        gcloud iam service-accounts create dbre-agent \
#          --display-name="GCRAH dbre agent" --project="$GCP_PROJECT"
#   3. SA has permission to READ the secret (run the grant block below, or
#      follow the manual grant in cloudrun.md).
#
# USAGE:
#   export GCP_PROJECT=performer-497915
#   export MONGO_SECRET_NAME=mongodb-connection-string
#   export AGENT_ENGINE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<id>
#   bash deploy/deploy_cloudrun.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT="${GCP_PROJECT:-performer-497915}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-gcrah-read-api}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-dbre-agent@${GCP_PROJECT}.iam.gserviceaccount.com}"
MONGO_SECRET_NAME="${MONGO_SECRET_NAME:-mongodb-connection-string}"
# Shared secret gating the write endpoints (POST /run, /decision). Reads stay public.
# If empty, writes are UNAUTHENTICATED — set it: export RUN_API_TOKEN=$(openssl rand -hex 16)
RUN_API_TOKEN="${RUN_API_TOKEN:-}"
AGENT_ENGINE_RESOURCE="${AGENT_ENGINE_RESOURCE:-}"
# ───────────────────────────────────────────────────────────────────────────────

if [ -z "${RUN_API_TOKEN}" ]; then
  echo "WARNING: RUN_API_TOKEN is empty — POST /run and /decision will be UNAUTHENTICATED."
fi
if [ -z "${AGENT_ENGINE_RESOURCE}" ]; then
  echo "ERROR: AGENT_ENGINE_RESOURCE is required so POST /run uses Agent Engine diagnosis."
  echo "Set it to projects/<project-number>/locations/<region>/reasoningEngines/<id>."
  exit 1
fi

echo "==> Granting Secret Manager accessor role to ${SERVICE_ACCOUNT}"
gcloud secrets add-iam-policy-binding "${MONGO_SECRET_NAME}" \
  --project="${GCP_PROJECT}" \
  --role="roles/secretmanager.secretAccessor" \
  --member="serviceAccount:${SERVICE_ACCOUNT}"

echo "==> Deploying ${SERVICE_NAME} to Cloud Run (${REGION})"
# --source . uses the Dockerfile at the repo root via Cloud Build.
# MONGO_SECRET_NAME is the secret's *name*, not its value — the app
# reads the actual connection string from Secret Manager at runtime.
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --project "${GCP_PROJECT}" \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT},MONGO_SECRET_NAME=${MONGO_SECRET_NAME},RUN_API_TOKEN=${RUN_API_TOKEN},AGENT_ENGINE_RESOURCE=${AGENT_ENGINE_RESOURCE}" \
  --port 8080 \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1

echo "==> Deploy complete. Service URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project "${GCP_PROJECT}" \
  --format "value(status.url)"

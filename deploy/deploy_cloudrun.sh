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
#   export AGENT_ENGINE_DIAGNOSE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<id>
#   export AGENT_ENGINE_CANDIDATE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<id>
#   export AGENT_ENGINE_RATIONALE_RESOURCE=projects/782567466199/locations/us-central1/reasoningEngines/<id>
#   export RUN_API_TOKEN=$(openssl rand -hex 16)
#   bash deploy/deploy_cloudrun.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT="${GCP_PROJECT:-performer-497915}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-gcrah-read-api}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-dbre-agent@${GCP_PROJECT}.iam.gserviceaccount.com}"
MONGO_SECRET_NAME="${MONGO_SECRET_NAME:-}"
# Shared secret gating the write endpoints (POST /run, /decision). Reads stay public.
# Required for production deploy: export RUN_API_TOKEN=$(openssl rand -hex 16)
RUN_API_TOKEN="${RUN_API_TOKEN:-}"
# Signs/verifies the session token shared with the dashboard (must match the dashboard's value).
# Required for the two-persona login: export SESSION_SECRET=$(openssl rand -hex 32)
SESSION_SECRET="${SESSION_SECRET:-}"
AGENT_ENGINE_DIAGNOSE_RESOURCE="${AGENT_ENGINE_DIAGNOSE_RESOURCE:-}"
AGENT_ENGINE_CANDIDATE_RESOURCE="${AGENT_ENGINE_CANDIDATE_RESOURCE:-}"
AGENT_ENGINE_RATIONALE_RESOURCE="${AGENT_ENGINE_RATIONALE_RESOURCE:-}"
# ───────────────────────────────────────────────────────────────────────────────

if [ -z "${RUN_API_TOKEN}" ]; then
  echo "ERROR: RUN_API_TOKEN is required so POST /run and /decision are authenticated."
  echo "Set it with: export RUN_API_TOKEN=\$(openssl rand -hex 16)"
  exit 1
fi
if [ -z "${AGENT_ENGINE_DIAGNOSE_RESOURCE}" ] || [ -z "${AGENT_ENGINE_CANDIDATE_RESOURCE}" ] || [ -z "${AGENT_ENGINE_RATIONALE_RESOURCE}" ]; then
  echo "ERROR: all three split Agent Engine resources are required for production /run."
  echo "Set AGENT_ENGINE_DIAGNOSE_RESOURCE, AGENT_ENGINE_CANDIDATE_RESOURCE, and AGENT_ENGINE_RATIONALE_RESOURCE."
  exit 1
fi
if [ "${AGENT_ENGINE_DIAGNOSE_RESOURCE}" = "${AGENT_ENGINE_CANDIDATE_RESOURCE}" ] || [ "${AGENT_ENGINE_DIAGNOSE_RESOURCE}" = "${AGENT_ENGINE_RATIONALE_RESOURCE}" ] || [ "${AGENT_ENGINE_CANDIDATE_RESOURCE}" = "${AGENT_ENGINE_RATIONALE_RESOURCE}" ]; then
  echo "ERROR: split Agent Engine resources must be three distinct deployed agents."
  exit 1
fi
if [ -z "${MONGO_SECRET_NAME}" ]; then
  echo "ERROR: MONGO_SECRET_NAME is required so production reads MongoDB credentials from Secret Manager."
  echo "Set it with: export MONGO_SECRET_NAME=mongodb-connection-string"
  exit 1
fi
if [ -z "${SESSION_SECRET}" ]; then
  echo "ERROR: SESSION_SECRET is required so the read API can verify dashboard session tokens."
  echo "Set it with: export SESSION_SECRET=\$(openssl rand -hex 32)  (same value as the dashboard)"
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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT},MONGO_SECRET_NAME=${MONGO_SECRET_NAME},RUN_API_TOKEN=${RUN_API_TOKEN},SESSION_SECRET=${SESSION_SECRET},AGENT_ENGINE_DIAGNOSE_RESOURCE=${AGENT_ENGINE_DIAGNOSE_RESOURCE},AGENT_ENGINE_CANDIDATE_RESOURCE=${AGENT_ENGINE_CANDIDATE_RESOURCE},AGENT_ENGINE_RATIONALE_RESOURCE=${AGENT_ENGINE_RATIONALE_RESOURCE}" \
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

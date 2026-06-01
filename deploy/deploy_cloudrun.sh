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
#   export MONGO_SECRET_NAME=gcrah-mongo-uri
#   bash deploy/deploy_cloudrun.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
GCP_PROJECT="${GCP_PROJECT:-performer-497915}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-gcrah-read-api}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-dbre-agent@${GCP_PROJECT}.iam.gserviceaccount.com}"
MONGO_SECRET_NAME="${MONGO_SECRET_NAME:-gcrah-mongo-uri}"
# ───────────────────────────────────────────────────────────────────────────────

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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${GCP_PROJECT},MONGO_SECRET_NAME=${MONGO_SECRET_NAME}" \
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

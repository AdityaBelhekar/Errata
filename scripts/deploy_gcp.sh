#!/usr/bin/env bash
#
# Errata -- deploy the reviewer console to Cloud Run.
#
#   bash scripts/deploy_gcp.sh <PROJECT_ID>
#
# Builds from source in Cloud Build, so no local Docker is needed -- only the gcloud CLI.
#
# WHY CLOUD RUN AND NOT RENDER
#
# Render's free and starter instances cap at 512Mi and the console was OOM-killed on boot.
# `load_etim` holds every ETIM feature and value description in memory and loads all 5,640
# classes on purpose: a retriever that can only see the classes it was told about "would report
# perfect accuracy by construction". Trimming the model to fit would have deleted the property
# that makes its accuracy number mean anything. 2Gi is the honest fix.
#
# --min-instances 1 is the other half. It keeps one instance warm, which
#   (a) removes the ~50s cold start entirely, and
#   (b) makes the whole keepalive-ping arrangement unnecessary -- no UptimeRobot, no cron.
# It also means the service bills continuously rather than scaling to zero. That is what the
# credits are for; drop it to 0 when the demo is over.

set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${1:-}"
if [[ -z "$PROJECT" ]]; then
    echo "usage: bash scripts/deploy_gcp.sh <PROJECT_ID>" >&2
    echo "  find yours with: gcloud projects list" >&2
    exit 1
fi

SERVICE="token-wasters-errata"
# Mumbai. The judges and the operator are in India; us-central1 adds ~200ms to every click in a
# console whose whole interaction model is clicking through a review queue.
REGION="${REGION:-asia-south1}"

echo "==> project $PROJECT / region $REGION / service $SERVICE"
gcloud config set project "$PROJECT" --quiet

echo "==> enabling the APIs this needs (idempotent)"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    --quiet

echo "==> building and deploying from source"
# --allow-unauthenticated: the console is the public demo. Note this is GCP-level access control;
# the application itself still has none, which is why --allow-remote had to be passed to it.
gcloud run deploy "$SERVICE" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 1 \
    --min-instances 1 \
    --max-instances 3 \
    --concurrency 20 \
    --timeout 300 \
    --port 8080 \
    --set-env-vars PYTHONUNBUFFERED=1 \
    --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"

echo
echo "=============================================================================="
echo "  live: $URL"
echo "=============================================================================="
echo
echo "Point the Vercel rewrite at it -- web/static-vercel.json, both /web/console rules --"
echo "then rebuild and redeploy the static site:"
echo
echo "    python scripts/build_static.py"
echo "    cd public && npx vercel deploy --prod --yes"

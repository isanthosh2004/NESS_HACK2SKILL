#!/usr/bin/env bash
# =============================================================================
# AgentControl — Task 0: Google Cloud foundation
#
# Run this YOURSELF in Google Cloud Shell (https://shell.cloud.google.com),
# which already has gcloud and is logged in as you. Read each section first:
# it grants IAM roles, which is an account-security action.
#
#   PROJECT_ID=my-agentcontrol-123 bash infra/setup_gcp.sh
#
# Prerequisites (manual, see infra/MANUAL_STEPS.md):
#   - the project exists and has a billing account linked (free trial is fine);
#   - a budget alert is set on that billing account.
#
# Safe to re-run: "already exists" errors are skipped.
# It does NOT create or read any secret values.
# =============================================================================
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID=<your project id>}"
REGION="${REGION:-asia-south1}"                 # Cloud Run + Firestore
BUCKET_LOCATION="${BUCKET_LOCATION:-us-central1}" # Cloud Storage always-free tier is US regions only
BUCKET="${BUCKET:-${PROJECT_ID}-agentcontrol-runs}"
LLM_PROVIDER="${LLM_PROVIDER:-ai_studio}"       # set to "vertex" to also enable Vertex AI

API_SA="agentcontrol-api"
SANDBOX_SA="agentcontrol-sandbox"
API_SA_EMAIL="${API_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
SANDBOX_SA_EMAIL="${SANDBOX_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRETS=("github-token" "gemini-api-key")

step() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok_if_exists() { "$@" 2>&1 | grep -v -i "already exists" || true; }

step "0. Select project ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"
if ! gcloud billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' | grep -qi true; then
  echo "Billing is NOT enabled on ${PROJECT_ID}. Link a billing account in the console first (see MANUAL_STEPS.md)."
  exit 1
fi

step "1. Enable APIs"
APIS=(run.googleapis.com firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com
      artifactregistry.googleapis.com cloudbuild.googleapis.com logging.googleapis.com iam.googleapis.com)
# The Gemini API key itself is created in Google AI Studio, in a SEPARATE project WITHOUT billing,
# so Gemini usage stays on the free tier (see MANUAL_STEPS.md).
if [[ "${LLM_PROVIDER}" == "vertex" ]]; then APIS+=(aiplatform.googleapis.com); fi
gcloud services enable "${APIS[@]}"

step "2. Firestore (Native mode, '(default)' database = the one with free quota) in ${REGION}"
if gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  echo "Firestore (default) already exists: $(gcloud firestore databases describe --database='(default)' --format='value(locationId,type)')"
else
  gcloud firestore databases create --database='(default)' --location="${REGION}" --type=firestore-native
fi

step "3. Cloud Storage bucket gs://${BUCKET} (private, uniform access, 30-day auto-delete)"
ok_if_exists gcloud storage buckets create "gs://${BUCKET}" --location="${BUCKET_LOCATION}" \
  --uniform-bucket-level-access --public-access-prevention
LIFECYCLE_FILE="$(mktemp)"
echo '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}' > "${LIFECYCLE_FILE}"
gcloud storage buckets update "gs://${BUCKET}" --lifecycle-file="${LIFECYCLE_FILE}"
rm -f "${LIFECYCLE_FILE}"

step "4. Secret Manager: create EMPTY secret containers (you add the values yourself)"
for s in "${SECRETS[@]}"; do
  ok_if_exists gcloud secrets create "${s}" --replication-policy=automatic
done

step "5. Service accounts"
ok_if_exists gcloud iam service-accounts create "${API_SA}" --display-name="AgentControl API (Cloud Run)"
ok_if_exists gcloud iam service-accounts create "${SANDBOX_SA}" --display-name="AgentControl sandbox (no secrets, no GitHub)"
sleep 5  # IAM propagation

step "6. Least-privilege role grants — API service account"
for role in roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${API_SA_EMAIL}" \
    --role="${role}" --condition=None --quiet >/dev/null && echo "  ${API_SA}: ${role} (project)"
done
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${API_SA_EMAIL}" \
  --role=roles/storage.objectAdmin >/dev/null && echo "  ${API_SA}: storage.objectAdmin (bucket only)"
for s in "${SECRETS[@]}"; do
  gcloud secrets add-iam-policy-binding "${s}" --member="serviceAccount:${API_SA_EMAIL}" \
    --role=roles/secretmanager.secretAccessor >/dev/null && echo "  ${API_SA}: secretAccessor on ${s} only"
done
if [[ "${LLM_PROVIDER}" == "vertex" ]]; then
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${API_SA_EMAIL}" \
    --role=roles/aiplatform.user --condition=None --quiet >/dev/null && echo "  ${API_SA}: aiplatform.user"
fi

step "7. Least-privilege role grants — sandbox service account (NO secrets, NO GitHub)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${SANDBOX_SA_EMAIL}" \
  --role=roles/logging.logWriter --condition=None --quiet >/dev/null && echo "  ${SANDBOX_SA}: logging.logWriter"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SANDBOX_SA_EMAIL}" \
  --role=roles/storage.objectCreator \
  --condition="expression=resource.name.startsWith(\"projects/_/buckets/${BUCKET}/objects/sandbox/\"),title=sandbox-prefix-only" \
  >/dev/null && echo "  ${SANDBOX_SA}: objectCreator on gs://${BUCKET}/sandbox/* only"
if [[ "${LLM_PROVIDER}" == "vertex" ]]; then
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${SANDBOX_SA_EMAIL}" \
    --role=roles/aiplatform.user --condition=None --quiet >/dev/null && echo "  ${SANDBOX_SA}: aiplatform.user"
fi

step "Done. Next (manual):"
cat <<EOF
  1. Add secret values (paste when prompted; nothing is echoed or saved to history):
       read -rs -p "GitHub token: " T && printf '%s' "\$T" | gcloud secrets versions add github-token --data-file=- && unset T
       read -rs -p "Gemini API key: " K && printf '%s' "\$K" | gcloud secrets versions add gemini-api-key --data-file=- && unset K
  2. Put these in config.yaml:
       project.gcp_project_id:   ${PROJECT_ID}
       project.region:           ${REGION}
       project.artifacts_bucket: ${BUCKET}
  3. Org-policy check for later (Task 8): can Cloud Run services be public?
       gcloud resource-manager org-policies describe iam.allowedPolicyMemberDomains --project=${PROJECT_ID} || true
EOF

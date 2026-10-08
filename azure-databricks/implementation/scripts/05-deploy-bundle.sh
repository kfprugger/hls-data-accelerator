#!/usr/bin/env bash
# 05-deploy-bundle.sh
# Deploys Databricks workload resources as one versioned release.
# This replaces the per-item Fabric REST calls in deploy-fabric-rti.ps1,
# deploy-data-agents.ps1, deploy-ontology.ps1, and deploy-payer-rti.ps1.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(dirname "$SCRIPT_DIR")/bundle"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

: "${ENVIRONMENT:?}" "${EVENTHUB_NAMESPACE:?}"
WORKLOAD_PRINCIPAL="${WORKLOAD_PRINCIPAL:-}"
WAREHOUSE_ID="${WAREHOUSE_ID:-}"
if [[ -z "$WAREHOUSE_ID" && -f "$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json" ]]; then
  WAREHOUSE_ID="$(jq -r '.warehouse_id // empty' "$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json")"
fi
[[ -n "$WAREHOUSE_ID" ]] || { echo "FAIL: run 04-unity-catalog-bootstrap.sh first; no serverless warehouse id found" >&2; exit 1; }
if [[ "$ENVIRONMENT" != "dev" && -z "$WORKLOAD_PRINCIPAL" ]]; then
  echo "FAIL: WORKLOAD_PRINCIPAL is required for $ENVIRONMENT run_as" >&2
  exit 1
fi

cd "$BUNDLE_DIR"

common_vars=(
  --var "catalog=hls_${ENVIRONMENT}"
  --var "eventhub_namespace=${EVENTHUB_NAMESPACE}"
  --var "telemetry_hub=${TELEMETRY_HUB:-telemetry-stream}"
  --var "claims_hub=${CLAIMS_HUB:-claim-stream}"
  --var "telemetry_consumer_group=${TELEMETRY_CONSUMER_GROUP:-hls-dbx-telemetry}"
  --var "claims_consumer_group=${CLAIMS_CONSUMER_GROUP:-hls-dbx-claims}"
  --var "eventhub_secret_scope=${EVENTHUB_SECRET_SCOPE:-hls-eventhubs}"
  --var "eventhub_secret_key=${EVENTHUB_SECRET_KEY:-listen-key}"
  --var "fhir_export_volume=/Volumes/hls_${ENVIRONMENT}/bronze/fhir_export"
  --var "dicom_volume=/Volumes/hls_${ENVIRONMENT}/bronze/dicom_source"
  --var "workload_principal=${WORKLOAD_PRINCIPAL}"
  --var "alert_email=${ALERT_EMAIL:-}"
  --var "warehouse_id=${WAREHOUSE_ID}"
)

echo "Step 1 of 3: validate configuration against the pinned CLI schema."
databricks bundle validate -t "$ENVIRONMENT" "${common_vars[@]}"

echo
echo "Step 2 of 3: show the planned resource actions before mutating the workspace."
databricks bundle plan -t "$ENVIRONMENT" "${common_vars[@]}" || \
  echo "  (bundle plan unavailable in this CLI version; proceeding to deploy review)"

echo
if [[ "${HLS_NONINTERACTIVE:-0}" != "1" ]]; then
  read -r -p "Deploy these resources to target '$ENVIRONMENT'? [y/N] " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted. Nothing deployed."; exit 1; }
fi

echo
echo "Step 3 of 3: deploy."
deploy_log="$(mktemp)"
trap 'rm -f "$deploy_log"' EXIT
deploy_flags=(--fail-on-active-runs)
[[ "${HLS_NONINTERACTIVE:-0}" != "1" ]] || deploy_flags+=(--auto-approve)
if ! databricks bundle deploy -t "$ENVIRONMENT" "${common_vars[@]}" "${deploy_flags[@]}" 2>&1 | tee "$deploy_log"; then
  # On a fresh workspace the Genie spaces cannot be created yet: the Gold and Silver tables
  # they query only exist after 06-run-and-gate.sh runs the pipelines. Accept exactly that
  # case: every error is a Genie space creation error and nothing else is left undeployed.
  errors="$(grep '^Error:' "$deploy_log" || true)"
  undeployed="$(databricks bundle summary -t "$ENVIRONMENT" "${common_vars[@]}" -o json |
    jq -r '.resources | to_entries[] | .key as $type | .value | to_entries[] | select(.value.id == null) | $type')"
  if [[ -n "$errors" ]] && ! grep -qv '^Error: cannot create resources\.genie_spaces\.' <<<"$errors" &&
     [[ -n "$undeployed" ]] && ! grep -qv '^genie_spaces$' <<<"$undeployed"; then
    echo
    echo "Every resource except the Genie spaces is deployed. They need the Gold and Silver"
    echo "tables, so 06-run-and-gate.sh creates them after the gates pass."
  else
    echo "FAIL: bundle deploy failed (see the errors above)." >&2
    exit 1
  fi
fi

echo
echo "Deployed resource summary:"
databricks bundle summary -t "$ENVIRONMENT" "${common_vars[@]}"

if [[ -z "${ALERT_EMAIL:-}" ]]; then
  echo
  echo "NOTE: ALERT_EMAIL was empty, so the clinical alert stays PAUSED with no recipient."
  echo "      This is intentional. No default address is ever invented."
fi

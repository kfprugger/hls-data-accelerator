#!/usr/bin/env bash
# 06-run-and-gate.sh
# Runs Bronze files -> Silver files -> Silver gate, then the scheduled serverless
# Bronze streams -> Silver streams -> freshness gate -> Gold -> Gold gate job.
#
# Every compute step is serverless and finishes. The stream ingestion job can be
# scheduled without holding continuous compute open between updates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(dirname "$SCRIPT_DIR")/bundle"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
: "${ENVIRONMENT:?}" "${EVENTHUB_NAMESPACE:?}"
WAREHOUSE_ID="${WAREHOUSE_ID:-}"
if [[ -z "$WAREHOUSE_ID" && -f "$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json" ]]; then
  WAREHOUSE_ID="$(jq -r '.warehouse_id // empty' "$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json")"
fi
[[ -n "$WAREHOUSE_ID" ]] || { echo "FAIL: no serverless warehouse id found" >&2; exit 1; }

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
  --var "state_volume=/Volumes/hls_${ENVIRONMENT}/meta/ingestion_state"
  --var "workload_principal=${WORKLOAD_PRINCIPAL:-}"
  --var "alert_email=${ALERT_EMAIL:-}"
  --var "warehouse_id=${WAREHOUSE_ID}"
)

cd "$BUNDLE_DIR"

echo "== Batch medallion =="
databricks bundle run -t "$ENVIRONMENT" "${common_vars[@]}" hls_batch_medallion

echo
echo "== Scheduled stream-to-Gold workflow =="
databricks bundle run -t "$ENVIRONMENT" "${common_vars[@]}" hls_stream_freshness_gate


echo
echo "All pipelines ran and every gate passed."
echo "A green pipeline alone is not completion. Run scripts/07-validate-deployment.py next."

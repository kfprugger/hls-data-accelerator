#!/usr/bin/env bash
# 99-teardown.sh — ordered, ownership-aware teardown.
# Never deletes the shared metastore, the source containers, or FHIR data by name prefix.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BUNDLE_DIR="$ROOT_DIR/bundle"
: "${ENVIRONMENT:?}" "${AZ_RESOURCE_GROUP:?}"

STATE_FILE="$ROOT_DIR/.state/foundation-${ENVIRONMENT}.json"
WAREHOUSE_STATE="$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json"
DELETE_FOUNDATION="${DELETE_FOUNDATION:-false}"
DELETE_CATALOG="${DELETE_CATALOG:-false}"
DELETE_WAREHOUSE="${DELETE_WAREHOUSE:-false}"

WAREHOUSE_ID="${WAREHOUSE_ID:-}"
if [[ -z "$WAREHOUSE_ID" && -f "$WAREHOUSE_STATE" ]]; then
  WAREHOUSE_ID="$(jq -r '.warehouse_id // empty' "$WAREHOUSE_STATE")"
fi

common_vars=(
  --var "catalog=hls_${ENVIRONMENT}"
  --var "eventhub_namespace=${EVENTHUB_NAMESPACE:?}"
  --var "warehouse_id=${WAREHOUSE_ID}"
)
echo "Scope of this teardown:"
echo "  bundle target      : $ENVIRONMENT"
echo "  catalog            : hls_${ENVIRONMENT} (deleted: $DELETE_CATALOG)"
echo "  bootstrap warehouse: ${WAREHOUSE_ID:-none} (deleted: $DELETE_WAREHOUSE)"
echo "  Databricks workspace/connector deleted: $DELETE_FOUNDATION"
echo "  Azure source estate: PRESERVED (FHIR, ADLS source containers, Event Hubs, ACR, Key Vault)"
read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted."; exit 1; }

echo "1. Bundle destroy removes the active schedule and triggered workload resources."

echo "2. Exporting final validation evidence before destruction..."
mkdir -p "$ROOT_DIR/.state"
python3 "$SCRIPT_DIR/07-validate-deployment.py" --environment "$ENVIRONMENT" --json \
  > "$ROOT_DIR/.state/final-validation-${ENVIRONMENT}.json" || \
  echo "   validation reported failures; evidence retained anyway"

echo "3. Destroying bundle-managed resources for target $ENVIRONMENT..."
databricks bundle destroy -t "$ENVIRONMENT" "${common_vars[@]}" --auto-approve

if [[ "$DELETE_CATALOG" == "true" ]]; then
  [[ -n "$WAREHOUSE_ID" ]] || { echo "FAIL: no warehouse id available for catalog deletion" >&2; exit 1; }
  echo "4. Dropping the environment catalog and API-managed governance objects..."
  statement="DROP CATALOG IF EXISTS hls_${ENVIRONMENT} CASCADE"
  databricks api post /api/2.0/sql/statements --json "$(jq -n \
    --arg s "$statement" --arg w "$WAREHOUSE_ID" \
    '{statement: $s, warehouse_id: $w, wait_timeout: "50s", on_wait_timeout: "CANCEL"}')" >/dev/null
  for location in "hls_${ENVIRONMENT}_managed" "hls_${ENVIRONMENT}_fhir_export" "hls_${ENVIRONMENT}_dicom_output"; do
    databricks external-locations delete "$location" --force 2>/dev/null || true
  done
  databricks storage-credentials delete "hls_${ENVIRONMENT}_connector" --force 2>/dev/null || true
else
  echo "4. Catalog and Unity Catalog governance objects retained (DELETE_CATALOG=false)."
fi

if [[ "$DELETE_WAREHOUSE" == "true" ]]; then
  [[ -f "$WAREHOUSE_STATE" ]] || { echo "FAIL: $WAREHOUSE_STATE missing; warehouse ownership is unproven" >&2; exit 1; }
  jq -e '.created_by_bootstrap == true' "$WAREHOUSE_STATE" >/dev/null \
    || { echo "FAIL: warehouse state does not prove bootstrap ownership" >&2; exit 1; }
  [[ -n "$WAREHOUSE_ID" ]] || { echo "FAIL: warehouse state has no id" >&2; exit 1; }
  databricks warehouses delete "$WAREHOUSE_ID"
else
  echo "5. Bootstrap SQL warehouse retained (DELETE_WAREHOUSE=false)."
fi

if [[ "$DELETE_FOUNDATION" == "true" ]]; then
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "FAIL: $STATE_FILE missing, so this run cannot prove it owns the workspace." >&2
    exit 1
  fi
  workspace_id="$(jq -r '.workspaceId.value' "$STATE_FILE")"
  connector_id="$(jq -r '.accessConnectorId.value' "$STATE_FILE")"
  echo "6. Deleting resources this deployment created:"
  echo "   $workspace_id"
  echo "   $connector_id"
  az resource delete --ids "$workspace_id" --verbose
  az resource delete --ids "$connector_id" --verbose
else
  echo "6. Databricks workspace and Access Connector retained (DELETE_FOUNDATION=false)."
fi

echo
echo "Teardown finished. The managed Delta container still exists; delete it explicitly"
echo "only after you no longer need the derived data:"
echo "  az storage container delete --account-name \"\$STORAGE_ACCOUNT_NAME\" --name databricks-managed --auth-mode login"

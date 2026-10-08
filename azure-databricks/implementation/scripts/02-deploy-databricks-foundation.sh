#!/usr/bin/env bash
# 02-deploy-databricks-foundation.sh — first mutating step.
# Creates: Databricks Premium workspace, Access Connector, managed container, scoped RBAC.
# Does not touch FHIR, ADLS source containers, Event Hubs entities, ACR, ACI, or Key Vault.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_NAME="hls-databricks-foundation-$(date -u +%Y%m%d%H%M%S)"
OUTPUT_FILE="$ROOT_DIR/.state/foundation-${ENVIRONMENT}.json"

: "${AZ_RESOURCE_GROUP:?}" "${AZ_LOCATION:?}" "${STORAGE_ACCOUNT_NAME:?}" "${EVENTHUB_NAMESPACE:?}" "${ENVIRONMENT:?}"
mkdir -p "$ROOT_DIR/.state"

echo "Validating template against the live resource group (no changes yet)..."
az deployment group validate \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --template-file "$ROOT_DIR/bicep/databricks-foundation.bicep" \
  --parameters location="$AZ_LOCATION" \
               storageAccountName="$STORAGE_ACCOUNT_NAME" \
               eventHubNamespaceName="$EVENTHUB_NAMESPACE" \
               adminGroupObjectId="${ADMIN_GROUP_OBJECT_ID:-}" \
  --output none

echo "Showing the exact change set before mutation..."
az deployment group what-if \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --template-file "$ROOT_DIR/bicep/databricks-foundation.bicep" \
  --parameters location="$AZ_LOCATION" \
               storageAccountName="$STORAGE_ACCOUNT_NAME" \
               eventHubNamespaceName="$EVENTHUB_NAMESPACE" \
               adminGroupObjectId="${ADMIN_GROUP_OBJECT_ID:-}"

if [[ "${HLS_NONINTERACTIVE:-0}" != "1" ]]; then
  read -r -p "Apply this change set? [y/N] " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted. Nothing changed."; exit 1; }
fi

az deployment group create \
  --resource-group "$AZ_RESOURCE_GROUP" \
  --name "$DEPLOYMENT_NAME" \
  --template-file "$ROOT_DIR/bicep/databricks-foundation.bicep" \
  --parameters location="$AZ_LOCATION" \
               storageAccountName="$STORAGE_ACCOUNT_NAME" \
               eventHubNamespaceName="$EVENTHUB_NAMESPACE" \
               adminGroupObjectId="${ADMIN_GROUP_OBJECT_ID:-}" \
  --query properties.outputs -o json > "$OUTPUT_FILE"

echo "Foundation outputs written to $OUTPUT_FILE"
jq -r 'to_entries[] | "  \(.key) = \(.value.value)"' "$OUTPUT_FILE"

cat <<EOF

Next, export these into your shell (or re-source env.sh after updating it):

  export DATABRICKS_HOST="$(jq -r '.workspaceUrl.value' "$OUTPUT_FILE")"
  export ACCESS_CONNECTOR_ID="$(jq -r '.accessConnectorId.value' "$OUTPUT_FILE")"
  export MANAGED_LOCATION_URL="$(jq -r '.managedLocationUrl.value' "$OUTPUT_FILE")"
  export FHIR_EXPORT_URL="${FHIR_EXPORT_URL:-$(jq -r '.fhirExportUrl.value' "$OUTPUT_FILE")}"
  export DICOM_OUTPUT_URL="$(jq -r '.dicomOutputUrl.value' "$OUTPUT_FILE")"

Then authenticate the CLI:

  databricks auth login --host "\$DATABRICKS_HOST"

Unity Catalog prerequisite:
  The hosted orchestrator attempts regional metastore assignment and pauses if
  account-admin permission is required. Manual runs must assign it in the account
  console (Catalog -> Metastores -> Assign to workspace) before step 03.
EOF

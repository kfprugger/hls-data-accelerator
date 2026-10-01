#!/usr/bin/env bash
# 04-unity-catalog-bootstrap.sh
# Substitutes environment values into sql/unity_catalog_bootstrap.sql and runs it
# on a SQL warehouse as a metastore admin.
#
# This is the step that replaces OneLake shortcuts: a storage credential over the
# Access Connector identity, read-only external locations over the source containers,
# and a managed location for derived Delta data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

: "${ENVIRONMENT:?}" "${ACCESS_CONNECTOR_ID:?}" "${MANAGED_LOCATION_URL:?}" \
  "${FHIR_EXPORT_URL:?}" "${DICOM_OUTPUT_URL:?}" "${DATABRICKS_ADMIN_GROUP:?}" "${WORKLOAD_PRINCIPAL:?}"

WAREHOUSE_NAME="hls-${ENVIRONMENT}-serving"
WAREHOUSE_STATE="$ROOT_DIR/.state/warehouse-${ENVIRONMENT}.json"
mkdir -p "$ROOT_DIR/.state"

WAREHOUSE_ID="${WAREHOUSE_ID:-}"
warehouse_created=false
if [[ -z "$WAREHOUSE_ID" && -f "$WAREHOUSE_STATE" ]]; then
  WAREHOUSE_ID="$(jq -r '.warehouse_id // empty' "$WAREHOUSE_STATE")"
fi
if [[ -z "$WAREHOUSE_ID" ]]; then
  WAREHOUSE_ID="$(databricks warehouses list -o json | jq -r --arg name "$WAREHOUSE_NAME" '.[] | select(.name == $name) | .id' | sed -n '1p')"
fi
if [[ -z "$WAREHOUSE_ID" ]]; then
  echo "Creating bootstrap serverless SQL warehouse $WAREHOUSE_NAME..."
  warehouse_response="$(databricks api post /api/2.0/sql/warehouses --json "$(jq -n \
    --arg name "$WAREHOUSE_NAME" \
    '{name: $name, cluster_size: "Small", min_num_clusters: 1, max_num_clusters: 2, auto_stop_mins: 10, warehouse_type: "PRO", enable_serverless_compute: true}')")"
  WAREHOUSE_ID="$(jq -r '.id // empty' <<<"$warehouse_response")"
  [[ -n "$WAREHOUSE_ID" ]] || { echo "FAIL: warehouse create returned no id" >&2; exit 1; }
  warehouse_created=true
fi
jq -n --arg id "$WAREHOUSE_ID" --arg name "$WAREHOUSE_NAME" --argjson created "$warehouse_created" \
  '{warehouse_id: $id, name: $name, created_by_bootstrap: $created}' > "$WAREHOUSE_STATE"
export WAREHOUSE_ID
echo "Using serverless SQL warehouse $WAREHOUSE_ID ($WAREHOUSE_NAME)"

CREDENTIAL_NAME="hls_${ENVIRONMENT}_connector"
if ! databricks storage-credentials get "$CREDENTIAL_NAME" -o json >/dev/null 2>&1; then
  echo "Creating Unity Catalog storage credential $CREDENTIAL_NAME..."
  databricks storage-credentials create --json "$(jq -n \
    --arg name "$CREDENTIAL_NAME" \
    --arg id "$ACCESS_CONNECTOR_ID" \
    --arg comment "HLS ${ENVIRONMENT} Unity Catalog identity for ADLS Gen2" \
    '{name: $name, azure_managed_identity: {access_connector_id: $id}, comment: $comment}')" \
    -o json >/dev/null
fi
echo "Using Unity Catalog storage credential $CREDENTIAL_NAME"

ensure_external_location() {
  local name="$1" url="$2" comment="$3" mode="$4"
  if databricks external-locations get "$name" -o json >/dev/null 2>&1; then
    return
  fi
  echo "Creating Unity Catalog external location $name..."
  if [[ "$mode" == "read-only" ]]; then
    databricks external-locations create "$name" "$url" "$CREDENTIAL_NAME" \
      --read-only --skip-validation --comment "$comment" -o json >/dev/null
  else
    databricks external-locations create "$name" "$url" "$CREDENTIAL_NAME" \
      --comment "$comment" -o json >/dev/null
  fi
}

ensure_external_location "hls_${ENVIRONMENT}_fhir_export" "${FHIR_EXPORT_URL}/" \
  'FHIR export NDJSON source; read-only' read-only
ensure_external_location "hls_${ENVIRONMENT}_dicom_output" "${DICOM_OUTPUT_URL}/" \
  'Re-tagged DICOM source; read-only' read-only
ensure_external_location "hls_${ENVIRONMENT}_managed" "${MANAGED_LOCATION_URL}/${ENVIRONMENT}/" \
  "Managed Delta storage for HLS ${ENVIRONMENT}" writable

for source_location in "hls_${ENVIRONMENT}_fhir_export" "hls_${ENVIRONMENT}_dicom_output"; do
  databricks external-locations get "$source_location" -o json | jq -e '.read_only == true' >/dev/null \
    || { echo "FAIL: $source_location is not read-only" >&2; exit 1; }
done
echo "Unity Catalog external locations are present; source locations are read-only"

rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT
sed \
  -e "s|\${ENVIRONMENT}|$ENVIRONMENT|g" \
  -e "s|\${ACCESS_CONNECTOR_ID}|$ACCESS_CONNECTOR_ID|g" \
  -e "s|\${MANAGED_LOCATION_URL}|$MANAGED_LOCATION_URL|g" \
  -e "s|\${FHIR_EXPORT_URL}|$FHIR_EXPORT_URL|g" \
  -e "s|\${DICOM_OUTPUT_URL}|$DICOM_OUTPUT_URL|g" \
  -e "s|\${ADMIN_GROUP}|$DATABRICKS_ADMIN_GROUP|g" \
  -e "s|\${WORKLOAD_PRINCIPAL}|$WORKLOAD_PRINCIPAL|g" \
  "$ROOT_DIR/sql/unity_catalog_bootstrap.sql" > "$rendered"

echo "Executing statements one at a time so a failure is attributable..."
statement_index=0
while IFS= read -r -d ';' statement; do
  trimmed="$(printf '%s' "$statement" | sed -e 's/--.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -z "$trimmed" ]] && continue
  statement_index=$((statement_index + 1))
  printf '  [%02d] %s...\n' "$statement_index" "$(printf '%s' "$trimmed" | head -c 72 | tr '\n' ' ')"
  databricks api post /api/2.0/sql/statements --json "$(jq -n \
    --arg s "$trimmed" --arg w "$WAREHOUSE_ID" \
    '{statement: $s, warehouse_id: $w, wait_timeout: "50s", on_wait_timeout: "CANCEL"}')" \
    | jq -e '.status.state == "SUCCEEDED"' >/dev/null \
    || { echo "FAIL at statement $statement_index" >&2; exit 1; }
done < "$rendered"

echo "Verifying the governance boundary actually behaves as intended..."
verify() {
  local label="$1" sql="$2"
  local result
  result="$(databricks api post /api/2.0/sql/statements --json "$(jq -n \
    --arg s "$sql" --arg w "$WAREHOUSE_ID" \
    '{statement: $s, warehouse_id: $w, wait_timeout: "50s", on_wait_timeout: "CANCEL"}')" \
    | jq -r '.status.state')"
  printf '  %-34s %s\n' "$label" "$result"
  [[ "$result" == "SUCCEEDED" ]]
}

verify "catalog schemas present" "SHOW SCHEMAS IN hls_${ENVIRONMENT}"
verify "FHIR source readable" "LIST '${FHIR_EXPORT_URL}/'"
verify "DICOM source readable" "LIST '${DICOM_OUTPUT_URL}/'"
verify "managed write works" "CREATE TABLE IF NOT EXISTS hls_${ENVIRONMENT}.meta._bootstrap_probe (checked_at TIMESTAMP)"
verify "managed cleanup works" "DROP TABLE IF EXISTS hls_${ENVIRONMENT}.meta._bootstrap_probe"

echo "Unity Catalog bootstrap complete for hls_${ENVIRONMENT}."

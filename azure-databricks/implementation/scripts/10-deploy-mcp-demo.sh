#!/usr/bin/env bash
# Deploy the bounded HLS UC function and two parallel APIM MCP routes without
# changing the existing Intermountain APIs. Safe to rerun.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

: "${ENVIRONMENT:?Set ENVIRONMENT (for example, test)}"
: "${WAREHOUSE_ID:?Set the target Databricks SQL warehouse id}"
: "${DATABRICKS_HOST:?Set the target Databricks workspace URL}"
: "${APIM_RESOURCE_GROUP:?Set the existing APIM resource group}"
: "${APIM_SERVICE_NAME:?Set the existing APIM service name}"
: "${APIM_BACKEND_CLIENT_ID:?Set the APIM user-assigned managed identity client id}"
: "${APIM_CALLER_CLIENT_ID:?Set the allowed agent runtime managed identity client id}"
: "${GENIE_SPACE_ID:?Set the curated Genie space id}"

CATALOG="hls_${ENVIRONMENT}"
FUNCTION_SCHEMA="ops"
FUNCTION_NAME="get_imaging_modality_counts"
FUNCTION_FULL_NAME="${CATALOG}.${FUNCTION_SCHEMA}.${FUNCTION_NAME}"
SOURCE_TABLE="${CATALOG}.gold.agent_imaging_cohort"
GENIE_SECONDARY_TABLE="${CATALOG}.gold.agent_patient_360"
APIM_API_VERSION="${APIM_API_VERSION:-2024-05-01}"
APIM_UC_API_ID="${APIM_UC_API_ID:-hls-uc-functions-mcp}"
APIM_GENIE_API_ID="${APIM_GENIE_API_ID:-hls-genie-mcp}"
APIM_UC_PATH="${APIM_UC_PATH:-hls-uc}"
APIM_GENIE_PATH="${APIM_GENIE_PATH:-hls-genie}"
AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(az account show --query tenantId -o tsv)}"
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
APIM_BASE="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${APIM_RESOURCE_GROUP}/providers/Microsoft.ApiManagement/service/${APIM_SERVICE_NAME}"
DATABRICKS_BACKEND="${DATABRICKS_HOST%/}"

run_sql() {
  local statement="$1"
  databricks api post /api/2.0/sql/statements --json "$(jq -n \
    --arg statement "$statement" \
    --arg warehouse "$WAREHOUSE_ID" \
    '{statement:$statement,warehouse_id:$warehouse,wait_timeout:"50s",on_wait_timeout:"CANCEL"}')" \
    -o json | jq -e '.status.state == "SUCCEEDED"' >/dev/null
}

rendered_sql="$(mktemp)"
temp_dir="$(mktemp -d)"
trap 'rm -f "$rendered_sql"; rm -rf "$temp_dir"' EXIT
sed "s|\${ENVIRONMENT}|${ENVIRONMENT}|g" "$ROOT_DIR/sql/mcp_demo_functions.sql" > "$rendered_sql"
run_sql "$(cat "$rendered_sql")"

echo "Ensuring APIM managed identity exists in the Databricks workspace..."
sp_json="$(databricks service-principals list --filter "applicationId eq \"${APIM_BACKEND_CLIENT_ID}\"" -o json)"
sp_id="$(jq -r '.[0].id // empty' <<<"$sp_json")"
if [[ -z "$sp_id" ]]; then
  sp_id="$(databricks service-principals create \
    --application-id "$APIM_BACKEND_CLIENT_ID" \
    --display-name "${APIM_BACKEND_DISPLAY_NAME:-umi-imh-uc-agent}" \
    --active -o json | jq -r '.id')"
fi

databricks service-principals patch "$sp_id" --json '{
  "schemas":["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations":[{"op":"add","path":"entitlements","value":[
    {"value":"workspace-access"},{"value":"databricks-sql-access"}
  ]}]
}' -o json >/dev/null

principal="$APIM_BACKEND_CLIENT_ID"
grant() {
  local type="$1" name="$2" privilege="$3"
  databricks grants update "$type" "$name" --json "$(jq -n \
    --arg principal "$principal" --arg privilege "$privilege" \
    '{changes:[{principal:$principal,add:[$privilege]}]}')" -o json >/dev/null
}

grant catalog "$CATALOG" USE_CATALOG
grant schema "${CATALOG}.ops" USE_SCHEMA
grant function "$FUNCTION_FULL_NAME" EXECUTE
grant schema "${CATALOG}.gold" USE_SCHEMA
grant table "$SOURCE_TABLE" SELECT
grant table "$GENIE_SECONDARY_TABLE" SELECT

databricks permissions update genie "$GENIE_SPACE_ID" --json "$(jq -n \
  --arg principal "$principal" \
  '{access_control_list:[{service_principal_name:$principal,permission_level:"CAN_RUN"}]}')" -o json >/dev/null
databricks permissions update warehouses "$WAREHOUSE_ID" --json "$(jq -n \
  --arg principal "$principal" \
  '{access_control_list:[{service_principal_name:$principal,permission_level:"CAN_USE"}]}')" -o json >/dev/null

create_api() {
  local api_id="$1" display_name="$2" path="$3"
  jq -n \
    --arg display "$display_name" \
    --arg path "$path" \
    --arg backend "$DATABRICKS_BACKEND" \
    '{properties:{displayName:$display,path:$path,protocols:["https"],serviceUrl:$backend,subscriptionRequired:false,apiRevision:"1"}}' \
    > "$temp_dir/api.json"
  az rest --method put --url "${APIM_BASE}/apis/${api_id}?api-version=${APIM_API_VERSION}" \
    --body @"$temp_dir/api.json" --output none

  local method operation
  for method in POST GET DELETE; do
    operation="$(tr '[:upper:]' '[:lower:]' <<<"$method")"
    jq -n --arg method "$method" \
      '{properties:{displayName:("MCP " + $method),method:$method,urlTemplate:"/mcp",templateParameters:[],responses:[]}}' \
      > "$temp_dir/operation.json"
    az rest --method put \
      --url "${APIM_BASE}/apis/${api_id}/operations/mcp-${operation}?api-version=${APIM_API_VERSION}" \
      --body @"$temp_dir/operation.json" --output none
  done
}

create_api "$APIM_UC_API_ID" "HLS imaging UC function MCP via managed identity" "$APIM_UC_PATH"
create_api "$APIM_GENIE_API_ID" "HLS imaging Genie MCP via managed identity" "$APIM_GENIE_PATH"

policy_xml() {
  local backend_path="$1"
  cat <<XML
<policies><inbound><base /><validate-azure-ad-token tenant-id="${AZURE_TENANT_ID}" header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="A valid Entra token for the HLS MCP demo is required."><client-application-ids><application-id>${APIM_CALLER_CLIENT_ID}</application-id></client-application-ids><audiences><audience>https://management.azure.com</audience><audience>https://management.azure.com/</audience></audiences></validate-azure-ad-token><rate-limit-by-key calls="30" renewal-period="60" counter-key="@(context.Request.IpAddress)" /><set-variable name="correlationId" value="@(context.RequestId.ToString())" /><set-header name="x-hls-correlation-id" exists-action="override"><value>@((string)context.Variables["correlationId"])</value></set-header><set-header name="Authorization" exists-action="delete" /><set-header name="Ocp-Apim-Subscription-Key" exists-action="delete" /><rewrite-uri template="${backend_path}" copy-unmatched-params="false" /><authentication-managed-identity resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d" client-id="${APIM_BACKEND_CLIENT_ID}" ignore-error="false" /></inbound><backend><forward-request timeout="180" buffer-response="false" /></backend><outbound><set-header name="x-hls-correlation-id" exists-action="override"><value>@((string)context.Variables["correlationId"])</value></set-header><base /></outbound><on-error><base /></on-error></policies>
XML
}

put_policy() {
  local api_id="$1" backend_path="$2"
  jq -n --arg value "$(policy_xml "$backend_path")" \
    '{properties:{format:"rawxml",value:$value}}' > "$temp_dir/policy.json"
  az rest --method put \
    --url "${APIM_BASE}/apis/${api_id}/policies/policy?api-version=${APIM_API_VERSION}" \
    --body @"$temp_dir/policy.json" --output none
}

put_policy "$APIM_UC_API_ID" "/api/2.0/mcp/functions/${CATALOG}/${FUNCTION_SCHEMA}/${FUNCTION_NAME}"
put_policy "$APIM_GENIE_API_ID" "/api/2.0/mcp/genie/${GENIE_SPACE_ID}"

gateway_url="$(az apim show --resource-group "$APIM_RESOURCE_GROUP" --name "$APIM_SERVICE_NAME" --query gatewayUrl -o tsv)"

if [[ -n "${MCP_JOB_ENVIRONMENT_ID:-}" && -n "${APIM_CALLER_IDENTITY_RESOURCE_ID:-}" ]]; then
  client_b64="$(base64 < "$SCRIPT_DIR/09-mcp-demo-client.py" | tr -d '\n')"
  job_location="$(az apim show --resource-group "$APIM_RESOURCE_GROUP" --name "$APIM_SERVICE_NAME" --query location -o tsv)"
  job_command='import base64,os;exec(compile(base64.b64decode(os.environ["CLIENT_B64"]),"09-mcp-demo-client.py","exec"))'

  create_demo_job() {
    local job_name="$1" container_name="$2" mcp_url="$3" mode="$4"
    local extra_env
    if [[ "$mode" == "uc" ]]; then
      extra_env="$(jq -n --arg tool "${CATALOG}__${FUNCTION_SCHEMA}__${FUNCTION_NAME}" \
        '[{name:"MCP_TOOL",value:$tool},{name:"MCP_ARGS",value:"{}"}]')"
    else
      extra_env="$(jq -n \
        '[{name:"MCP_QUERY",value:"Count imaging studies and represented patients by modality. Include the governed data source."}]')"
    fi
    jq -n \
      --arg location "$job_location" \
      --arg identity "$APIM_CALLER_IDENTITY_RESOURCE_ID" \
      --arg environment "$MCP_JOB_ENVIRONMENT_ID" \
      --arg name "$container_name" \
      --arg client "$client_b64" \
      --arg url "$mcp_url" \
      --arg caller "$APIM_CALLER_CLIENT_ID" \
      --arg command "$job_command" \
      --argjson extra "$extra_env" \
      '{location:$location,identity:{type:"UserAssigned",userAssignedIdentities:{($identity):{}}},properties:{environmentId:$environment,configuration:{triggerType:"Manual",replicaTimeout:300,replicaRetryLimit:0,manualTriggerConfig:{parallelism:1,replicaCompletionCount:1}},template:{containers:[{name:$name,image:"mcr.microsoft.com/azurelinux/base/python:3.12",command:["python3","-c",$command],env:([{name:"CLIENT_B64",value:$client},{name:"APIM_MCP_URL",value:$url},{name:"APIM_AUTH",value:"mi"},{name:"APIM_AUDIENCE",value:"https://management.azure.com"},{name:"AZURE_CLIENT_ID",value:$caller},{name:"PYTHONUNBUFFERED",value:"1"}] + $extra),resources:{cpu:0.25,memory:"0.5Gi"}}]}}}' \
      > "$temp_dir/job.json"
    az rest --method put \
      --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${APIM_RESOURCE_GROUP}/providers/Microsoft.App/jobs/${job_name}?api-version=2024-03-01" \
      --body @"$temp_dir/job.json" --output none
  }

  create_demo_job "${MCP_UC_JOB_NAME:-job-hls-uc-mcp-demo}" "hls-uc-demo" \
    "${gateway_url}/${APIM_UC_PATH}/mcp" uc
  create_demo_job "${MCP_GENIE_JOB_NAME:-job-hls-genie-mcp-demo}" "hls-genie-demo" \
    "${gateway_url}/${APIM_GENIE_PATH}/mcp" genie
else
  echo "Demo jobs not changed; set MCP_JOB_ENVIRONMENT_ID and APIM_CALLER_IDENTITY_RESOURCE_ID to deploy them."
fi
echo "UC MCP:    ${gateway_url}/${APIM_UC_PATH}/mcp"
echo "Genie MCP: ${gateway_url}/${APIM_GENIE_PATH}/mcp"
echo "Deployment complete for ${DATABRICKS_HOST} (${CATALOG})."

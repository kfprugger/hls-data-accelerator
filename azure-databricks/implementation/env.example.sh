# Copy to env.sh, fill in, then: source env.sh
# env.sh is intentionally gitignored. Never commit real IDs or keys.

# --- Azure context (must match your existing HLS deployment) ---
export AZ_TENANT_ID=""
export AZ_SUBSCRIPTION_ID=""
export AZ_RESOURCE_GROUP=""            # existing HLS resource group
export AZ_LOCATION="eastus"
export ADMIN_GROUP_OBJECT_ID=""        # Entra security group object ID

# --- Existing source estate (read from the current deployment, do not recreate) ---
export STORAGE_ACCOUNT_NAME=""         # ADLS Gen2 account with fhir-export + dicom-output
export EVENTHUB_NAMESPACE=""           # namespace name only, no .servicebus.windows.net
export TELEMETRY_HUB="telemetry-stream"
export CLAIMS_HUB="claim-stream"
export KEY_VAULT_NAME=""

# --- Databricks target ---
export ENVIRONMENT="dev"               # dev | test | prod
export DATABRICKS_HOST=""              # filled by 02-deploy-databricks-foundation.sh
export DATABRICKS_ACCOUNT_ID=""
export WORKLOAD_PRINCIPAL=""           # service principal application ID
export DATABRICKS_ADMIN_GROUP="hls-platform-admins"
export EVENTHUB_SECRET_SCOPE="hls-eventhubs"
export EVENTHUB_SECRET_KEY="listen-key"
export DATABRICKS_LISTEN_POLICY="hls-databricks-listen"
export TELEMETRY_CONSUMER_GROUP="hls-dbx-telemetry"
export CLAIMS_CONSUMER_GROUP="hls-dbx-claims"

# --- Optional behavior ---
export ALERT_EMAIL=""                  # reviewed recipient; empty leaves the alert paused

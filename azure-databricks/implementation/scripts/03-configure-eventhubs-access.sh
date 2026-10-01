#!/usr/bin/env bash
# 03-configure-eventhubs-access.sh
# Adds Databricks-only consumer groups and a Listen-only policy, then stores the key
# in Key Vault and mirrors it into a Databricks secret scope.
#
# Why: the existing emulator-access rule has Send+Listen at namespace scope. Reusing it
# would give the analytics plane the ability to inject events. It must not be reused.
set -euo pipefail

: "${AZ_RESOURCE_GROUP:?}" "${EVENTHUB_NAMESPACE:?}" "${KEY_VAULT_NAME:?}" \
  "${TELEMETRY_HUB:?}" "${CLAIMS_HUB:?}" "${TELEMETRY_CONSUMER_GROUP:?}" "${CLAIMS_CONSUMER_GROUP:?}" \
  "${DATABRICKS_LISTEN_POLICY:?}" "${EVENTHUB_SECRET_SCOPE:?}" "${EVENTHUB_SECRET_KEY:?}"

echo "Creating dedicated consumer groups so Databricks never shares offsets with Fabric or the emulator..."
az eventhubs eventhub consumer-group create \
  --resource-group "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" \
  --eventhub-name "$TELEMETRY_HUB" --name "$TELEMETRY_CONSUMER_GROUP" --output none
az eventhubs eventhub consumer-group create \
  --resource-group "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" \
  --eventhub-name "$CLAIMS_HUB" --name "$CLAIMS_CONSUMER_GROUP" --output none

echo "Creating a Listen-only namespace policy for Databricks..."
az eventhubs namespace authorization-rule create \
  --resource-group "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" \
  --name "$DATABRICKS_LISTEN_POLICY" --rights Listen --output none

rights="$(az eventhubs namespace authorization-rule show \
  --resource-group "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" \
  --name "$DATABRICKS_LISTEN_POLICY" --query "rights" -o tsv)"
if [[ "$rights" != "Listen" ]]; then
  echo "FAIL: policy rights are '$rights', expected exactly 'Listen'." >&2
  exit 1
fi
echo "Verified: policy grants Listen only."

echo "Fetching the primary key and storing it in Key Vault..."
listen_key="$(az eventhubs namespace authorization-rule keys list \
  --resource-group "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" \
  --name "$DATABRICKS_LISTEN_POLICY" --query primaryKey -o tsv)"

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "databricks-eventhubs-listen-key" \
  --value "$listen_key" \
  --output none
echo "Stored in Key Vault as databricks-eventhubs-listen-key."

echo "Mirroring into the Databricks secret scope used by the pipeline..."
databricks secrets create-scope "$EVENTHUB_SECRET_SCOPE" 2>/dev/null || \
  echo "  scope $EVENTHUB_SECRET_SCOPE already exists"
databricks secrets put-secret "$EVENTHUB_SECRET_SCOPE" "$EVENTHUB_SECRET_KEY" --string-value "$listen_key"
unset listen_key

echo "Verifying the scope is readable without printing the value..."
databricks secrets list-secrets "$EVENTHUB_SECRET_SCOPE" -o json | jq -r '.[].key'
echo "Event Hubs access configured. The key was never written to stdout or the repo."

#!/usr/bin/env bash
# 01-preflight.sh — read-only readiness check. Mutates nothing.
# Replaces the Fabric capacity/workspace portion of Preflight-Check.ps1.
set -euo pipefail

fail=0
note() { printf '  %s %s\n' "$1" "$2"; }
require_var() {
  if [[ -z "${!1:-}" ]]; then note "FAIL" "$1 is not set"; fail=1; else note "ok" "$1"; fi
}

echo "== Required environment =="
for var in AZ_TENANT_ID AZ_SUBSCRIPTION_ID AZ_RESOURCE_GROUP AZ_LOCATION \
           STORAGE_ACCOUNT_NAME EVENTHUB_NAMESPACE ENVIRONMENT; do
  require_var "$var"
done

echo "== Local tooling =="
for tool in az databricks jq; do
  if command -v "$tool" >/dev/null 2>&1; then note "ok" "$tool present"; else note "FAIL" "$tool missing"; fail=1; fi
done

if command -v az >/dev/null 2>&1; then
  echo "== Azure identity =="
  account_json="$(az account show -o json 2>/dev/null || true)"
  if [[ -z "$account_json" ]]; then
    note "FAIL" "az is not logged in"; fail=1
  else
    actual_sub="$(jq -r '.id' <<<"$account_json")"
    actual_tenant="$(jq -r '.tenantId' <<<"$account_json")"
    [[ "$actual_sub" == "${AZ_SUBSCRIPTION_ID:-}" ]] && note "ok" "subscription matches" || { note "FAIL" "subscription is $actual_sub"; fail=1; }
    [[ "$actual_tenant" == "${AZ_TENANT_ID:-}" ]] && note "ok" "tenant matches" || { note "FAIL" "tenant is $actual_tenant"; fail=1; }
  fi

  echo "== Resource providers =="
  for provider in Microsoft.Databricks Microsoft.Storage Microsoft.EventHub Microsoft.KeyVault Microsoft.EventGrid; do
    state="$(az provider show --namespace "$provider" --query registrationState -o tsv 2>/dev/null || echo missing)"
    [[ "$state" == "Registered" ]] && note "ok" "$provider" || { note "FAIL" "$provider is $state"; fail=1; }
  done

  echo "== Existing source estate =="
  hns="$(az storage account show -g "$AZ_RESOURCE_GROUP" -n "$STORAGE_ACCOUNT_NAME" --query isHnsEnabled -o tsv 2>/dev/null || echo missing)"
  [[ "$hns" == "true" ]] && note "ok" "ADLS hierarchical namespace enabled" || { note "FAIL" "hierarchical namespace is $hns"; fail=1; }

  storage_region="$(az storage account show -g "$AZ_RESOURCE_GROUP" -n "$STORAGE_ACCOUNT_NAME" --query location -o tsv 2>/dev/null || echo missing)"
  [[ "$storage_region" == "$AZ_LOCATION" ]] && note "ok" "storage region matches target" || note "WARN" "storage is in $storage_region, target is $AZ_LOCATION (egress risk)"

  for container in "${FHIR_EXPORT_CONTAINER:-fhir-export}" dicom-output; do
    exists="$(az storage container exists --account-name "$STORAGE_ACCOUNT_NAME" --name "$container" --auth-mode login --query exists -o tsv 2>/dev/null || echo false)"
    [[ "$exists" == "true" ]] && note "ok" "container $container" || { note "FAIL" "container $container missing"; fail=1; }
  done

  for hub in "${TELEMETRY_HUB:-telemetry-stream}" "${CLAIMS_HUB:-claim-stream}"; do
    if az eventhubs eventhub show -g "$AZ_RESOURCE_GROUP" --namespace-name "$EVENTHUB_NAMESPACE" -n "$hub" -o none 2>/dev/null; then
      note "ok" "event hub $hub"
    else
      note "FAIL" "event hub $hub missing"; fail=1
    fi
  done
fi

if command -v databricks >/dev/null 2>&1 && [[ -n "${DATABRICKS_HOST:-}" ]]; then
  echo "== Databricks authentication =="
  if databricks current-user me -o json >/dev/null 2>&1; then
    note "ok" "Databricks CLI authenticated to $DATABRICKS_HOST"
  else
    note "WARN" "Databricks CLI not authenticated yet (expected before step 02)"
  fi
fi

echo
if [[ "$fail" -ne 0 ]]; then
  echo "Preflight FAILED. Nothing was changed."
  exit 1
fi
echo "Preflight passed. No cloud resource was modified."

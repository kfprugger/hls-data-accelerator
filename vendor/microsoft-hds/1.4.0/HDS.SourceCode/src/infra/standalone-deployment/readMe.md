# FHIR Export Function App — Standalone Deployment Guide

This directory contains the self-contained deployment script for the HDS FHIR Export Function App.
Use this when the Azure Marketplace pipeline is deprecated and customers need to deploy directly.

## Prerequisites

### Software Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| [Az PowerShell module](https://learn.microsoft.com/en-us/powershell/azure/install-az-ps) | v9.0+ | Az.Accounts, Az.Resources, Az.Storage |
| [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) | v2.50+ | **Required** — used to publish the function key to Key Vault and for the health check |
| .NET 8 SDK | 8.0+ | **Only** if using `-BuildFromSource` |

### Azure Permissions

| Role | Scope | Purpose |
|------|-------|---------|
| **Contributor** | Resource Group | Create all infrastructure resources |
| **User Access Administrator** | Resource Group | Create RBAC role assignments for managed identities |
| **User Access Administrator** (or Owner) | **FHIR service** (may be a *different* RG/subscription) | Required for the one **manual** post-deployment role assignment that targets the FHIR service: granting **FHIR Data Exporter** to the function app MI (see [Post-Deployment → Step 2](#step-2-assign-rbac-roles)). The template does **not** modify the pre-existing FHIR service, so this is done by hand. *(The other Step 2 assignment — **Storage Blob Data Contributor** for the FHIR service MI — is scoped to the HDS export storage account in the deployment resource group, so it is already covered by the **Resource Group** row above.)* |
| **Key Vault Secrets Officer** | Key Vault (self-assigned by the script) | Store the `ExportFunctionKey` secret. The Key Vault is RBAC-authorized and created by this script, so even an Owner has no data-plane access initially. Step 6 self-assigns this role to the deploying identity via `az role assignment create` and waits for propagation. This requires **User Access Administrator** (or Owner). |

> **Tip:** The **Owner** role includes both Contributor and User Access Administrator.

### Subscription Requirements

| Requirement | Details |
|-------------|---------|
| **Function hosting** | The function app runs on a **Y1 Consumption** plan — serverless, with no pre-provisioned App Service Plan quota required in most subscriptions |
| **Storage network access** | Storage is created with **open** network access by default. Only pass `-RestrictStorageNetworkAccess` if your subscription policy *requires* `networkAcls.defaultAction=Deny`. (Note: a Consumption-plan content share is not supported behind a storage firewall, so leave this off unless required — the function host may fail to start.) |
| **Resource provider registrations** | `Microsoft.Web`, `Microsoft.Storage`, `Microsoft.KeyVault`, `Microsoft.Insights` |

> **Note:** The Y1 Consumption plan does not require pre-provisioned quota in most subscriptions. Ensure the resource providers above are registered before deploying.

### FHIR Service Requirements (Post-Deployment)

The FHIR service is a **pre-existing** customer resource. It must:
- Be an Azure Health Data Services FHIR R4 service
- Have **System-Assigned Managed Identity** enabled
- Be accessible from the Azure region where you deploy

> **⚠️ Do not strip the FHIR managed identity.** The FHIR `$export` runs under the FHIR
> service's **system-assigned managed identity**. If you (re)create or update the FHIR service
> with the CLI/ARM and omit `--identity-type SystemAssigned` (or set identity to `None`), the
> MI is **silently removed** and exports then fail with a cryptic **"Unknown Error"** — there is
> no identity left to authenticate to storage. Always pass `--identity-type SystemAssigned` on
> `az healthcareapis workspace fhir-service create/update`, and re-grant the storage role
> (below) afterwards, since the principalId changes when the MI is recreated.

## Directory Structure

```
src/infra/
├── standalone-deployment/         ← You are here
│   ├── Deploy-FhirExportFunctionApp.ps1   ← Thin deployment script
│   └── readMe.md                          ← This guide
├── main.bicep                     ← Bicep orchestrator (source of mainTemplate.json)
├── mainTemplate.json              ← Compiled ARM solution template (what the script deploys)
├── modules/                       ← Bicep modules
│   ├── deploySharedComponents.bicep
│   ├── deployAppServices.bicep
│   ├── addNonFunctionSecretstoKeyVault.bicep
│   └── delayDeployment.bicep
├── config/                        ← Configuration
│   ├── armArtifactsConfig.json
│   └── blobStorageContainersConfig.json
└── functionapps/                  ← Pre-built function app (for Download Center)
    └── exportprocessor.zip
```

The script references `mainTemplate.json` (preferred) — or compiles `main.bicep` if the JSON is
absent — plus `config/` and `functionapps/` from the parent `src/infra/` directory.

## How It Deploys (thin design)

This script is intentionally **thin**: it does **not** re-implement any deployment logic. It reuses
the existing ARM solution template (`mainTemplate.json`) end-to-end, which already knows how to
deploy every resource, RBAC assignment, app setting, **and the function code itself** via its own
native `Microsoft.Web/sites/extensions ZipDeploy` resource.

The script's only job around the template is to **stage the ZIP** so the template can fetch it:

1. **Stage** — upload `exportprocessor.zip` to a short-lived storage account
   (`stghdsdeploy<random>`) at `artifacts/functionapps/exportprocessor.zip`, and mint a narrow,
   read-only, blob-scoped SAS (4 h).
2. **Deploy once** — run `mainTemplate.json` with `skipZipDeploy=$false` and
   `_artifactsLocation`/`_artifactsLocationSasToken` pointing at the staged blob. The template
   provisions all infrastructure **and** delivers the code through its native ZipDeploy.
3. **Clean up** — delete the staging storage account (ZipDeploy completes synchronously inside the
   ARM deployment, so this is race-free).
4. **Publish key** — store `ExportFunctionKey` in Key Vault. This is the one post-deploy action the
   template cannot perform, because the function key only exists after the host registers
   `Run_Export` (after the deployment returns). The downstream Fabric service reads this secret to
   trigger exports.

Both consumer scenarios use the **same** path: Microsoft ships the pre-built ZIP, or the customer
builds it with `-BuildFromSource`. Either way the ZIP is staged and the template deploys it.

> **Deferred: restricted-tenant fallback.** A small number of tenants enforce Azure Policy that
> blocks creating a staging storage account or issuing a SAS. For those, an opt-in
> `-DirectZipDeploy` fallback (push the code directly via the management plane, no staging storage)
> was scoped but **intentionally left out for now** to keep this script thin and reviewable. It will
> be added only if a customer actually hits the policy block. If staging fails in such a tenant, the
> script fails fast with a clear message pointing here. *(Pending review with engineering management
> before deciding whether to implement.)*

## Deployment Options

### Option 1: Full Deployment with Pre-built ZIP (Recommended)

```powershell
.\Deploy-FhirExportFunctionApp.ps1 `
    -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
    -ResourceGroupName "my-rg" `
    -FhirServerUri "https://myfhirserver.fhir.azurehealthcareapis.com" `
    -Location "eastus"
```

### Option 2: Update Existing Deployment (Code-only / in-process → isolated migration)

Redeploys the ZIP via the template's update-only ZipDeploy (no shared-infrastructure changes),
then **migrates the runtime settings to the .NET 8 isolated worker** (Step 5b). This is the path an
existing **.NET 6 in-process** customer uses to move to the isolated model: the template's
update-only path deploys only the ZIP (siteConfig/appSettings are guarded by `if(!deployUpdatesOnly)`),
so the script patches the four isolated-worker settings on the app afterwards — otherwise the .NET 8
package would land on an app still configured for in-process and no user functions would register.
Uses the same thin staging path. Safe to re-run — it also re-publishes `ExportFunctionKey`, so it
doubles as a repair if that secret is missing.

```powershell
.\Deploy-FhirExportFunctionApp.ps1 `
    -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
    -ResourceGroupName "my-rg" `
    -DeployUpdatesOnly
```

### Option 3: Build from Source and Deploy

```powershell
.\Deploy-FhirExportFunctionApp.ps1 `
    -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
    -ResourceGroupName "my-rg" `
    -FhirServerUri "https://myfhirserver.fhir.azurehealthcareapis.com" `
    -BuildFromSource `
    -SourceProjectPath "../../export/ExportProcessor/ExportProcessor.csproj"
```

Run `Get-Help .\Deploy-FhirExportFunctionApp.ps1 -Full` for all parameters.

> **Optional — restricted storage networking:** Add `-RestrictStorageNetworkAccess` only if your
> subscription policy requires storage `networkAcls.defaultAction=Deny`. The flag is passed straight
> through to the template. Leave it **off** (the default) for a standard Consumption-plan
> deployment, since the function content share is not supported behind a storage firewall and the
> host may fail to start. The script prints a warning when the flag is set.

## What the Script Does

| Step | Description | Auto-Handled |
|------|-------------|:---:|
| **1** | Validates prerequisites (Az module, Azure CLI, subscription context, resource group) | ✅ |
| **2** | Resolves the pre-built `exportprocessor.zip` — or builds it from source with `-BuildFromSource` | ✅ |
| **3** | Resolves the deployment template (`mainTemplate.json`, or compiles `main.bicep`) | ✅ |
| **4** | Stages the ZIP to a short-lived storage account and mints a read-only blob SAS | ✅ |
| **5** | Runs the solution template once (`skipZipDeploy=$false`) — provisions all infra, RBAC, settings, **and the code via the template's native ZipDeploy** | ✅ |
| **5b** | *(update-only only)* Migrates runtime settings to .NET 8 isolated (`netFrameworkVersion=v8.0`, `use32BitWorkerProcess=false`, `FUNCTIONS_WORKER_RUNTIME=dotnet-isolated`, `WEBSITE_USE_PLACEHOLDER_DOTNETISOLATED=1`) and restarts the host. The template skips these in update-only mode. | ✅ |
| **6** | Deletes the staging storage account; self-assigns `Key Vault Secrets Officer` if needed, polls for `Run_Export`, and stores `ExportFunctionKey` in Key Vault | ✅ |
| **7** | Verifies function app health, critical app settings, and registered functions | ✅ |
| **finally** | Safety-net cleanup of the staging storage account (in case of mid-run failure) | ✅ |

### Resources Created

| Resource | Naming Pattern | Purpose |
|----------|---------------|---------|
| App Service Plan | `msft-asp-hds-{unique}` | Hosts the function app (Y1 Consumption SKU) |
| Function App | `msft-func-hds-export-{unique}` | FHIR export orchestration |
| Storage Account (HDS) | `msftst{unique}` | Export landing zone for NDJSON files |
| Storage Account (Func) | `msftstexprt{unique}` | Function app runtime storage |
| Key Vault | `msft-kv-{unique}` | Stores connection strings and function keys |
| App Insights | `msft-appi-hds-{unique}` | Monitoring and diagnostics |
| Log Analytics | `msft-log-hds-{unique}` | Log aggregation |

> `{unique}` is a deterministic hash derived from `uniqueString(subscriptionId, resourceGroupId)`.

## Post-Deployment: FHIR Service Configuration (Manual)

After the script completes, configure the FHIR service. The script prints these steps in the summary.

### Step 1: Set FHIR Export Storage Account

```powershell
# Via Azure Portal: FHIR service → Export → Storage account → Select 'msftst{unique}'
# Or via CLI:
az rest --method patch `
    --url "https://management.azure.com{fhir-resource-id}?api-version=2024-03-31" `
    --body '{"properties":{"exportConfiguration":{"storageAccountName":"msftst{unique}"}}}'
```

### Step 2: Assign RBAC Roles

```powershell
# Get the managed identity principal IDs
$fhirMI = "<FHIR-service-managed-identity-principal-id>"
$funcMI = "<Function-app-managed-identity-principal-id>"

# 1. FHIR MI needs Storage Blob Data Contributor on HDS storage
az role assignment create --role "Storage Blob Data Contributor" `
    --assignee-object-id $fhirMI --assignee-principal-type ServicePrincipal `
    --scope "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/msftst{unique}"

# 2. Function App MI needs FHIR Data Exporter on FHIR service
az role assignment create --role "FHIR Data Exporter" `
    --assignee-object-id $funcMI --assignee-principal-type ServicePrincipal `
    --scope "{fhir-resource-id}"
```

> **⚠️ RBAC Propagation:** Role assignments take **2-5 minutes** to propagate. Wait before testing.

### Step 3: Verify Export (Optional)

```powershell
# Get the function key
$funcKey = az functionapp function keys list `
    --name "msft-func-hds-export-{unique}" `
    --resource-group "{rg}" `
    --function-name "Run_Export" --query "default" -o tsv

# Trigger an export (note: GET method, requires {run_id} in URL)
$response = Invoke-RestMethod `
    -Uri "https://msft-func-hds-export-{unique}.azurewebsites.net/api/Run_Export/test-run-001?code=$funcKey" `
    -Method Get

# Check orchestration status
Invoke-RestMethod -Uri $response.StatusQueryGetUri -Method Get
```

## Troubleshooting

### Common Issues

| Error | Cause | Resolution |
|-------|-------|------------|
| `InternalSubscriptionIsOverQuotaForSku` | No App Service Plan quota in target region | Check quota with `az vm list-usage --location <region>`, request increase, or try a different region |
| `Storage accounts should restrict network access` (Azure Policy) | Subscription policy enforces a storage firewall | Pass `-RestrictStorageNetworkAccess` (forwarded to the template). Note the Consumption content share is not supported behind a firewall, so the app may not start. |
| `Staged artifact not reachable via SAS` / staging storage account creation denied | Azure Policy blocks creating the staging storage account or issuing a SAS | This is the restricted-tenant case. See **How It Deploys → Deferred: restricted-tenant fallback** above. The `-DirectZipDeploy` fallback is not yet implemented. |
| `Forbidden` / `No such host` on Key Vault secret write | Deployer has no Key Vault data-plane role yet (RBAC vault, just created) | ✅ Handled automatically — Step 6 self-assigns `Key Vault Secrets Officer` to the deploying identity and polls for propagation. Requires **User Access Administrator**/Owner. If self-assignment fails, the script prints clear guidance. |
| `Run_Export` returns 404 | Wrong HTTP method or missing route parameter | Use **GET** (not POST), include a run ID: `GET /api/Run_Export/{any-run-id}?code=<key>` |
| Function app shows 0 functions | Functions not yet registered after cold start | Wait 1-2 min, then restart: `az functionapp restart --name <name> --resource-group <rg>` |
| FHIR 403 Authorization Failed | RBAC propagation delay | Wait 2-5 minutes after role assignment, then retry |
| Export fails immediately with **"Unknown Error"** | FHIR service has **no managed identity** (it was stripped — e.g. a `fhir-service create/update` without `--identity-type SystemAssigned`) | Re-enable the system-assigned MI on the FHIR service, then re-grant **Storage Blob Data Contributor** to the *new* FHIR MI principalId on the HDS storage account (the principalId changes when the MI is recreated). See **FHIR Service Requirements** above. |

### ExportFunctionKey Not Stored

If Step 6 fails (function didn't register within ~10 minutes, or the deployer never gained Key
Vault data-plane access), store it manually — or simply re-run with `-DeployUpdatesOnly`, which
re-publishes the key:

```powershell
# 1. Restart the function app to trigger function discovery
az functionapp restart --name 'msft-func-hds-export-<unique>' --resource-group '<rg>'

# 2. Wait 2-3 minutes, then verify functions are registered
az functionapp function list --name 'msft-func-hds-export-<unique>' --resource-group '<rg>'

# 3. Get the function key
az functionapp function keys list --name 'msft-func-hds-export-<unique>' --resource-group '<rg>' --function-name 'Run_Export'

# 4. Store in Key Vault
az keyvault secret set --vault-name 'msft-kv-<unique>' --name 'ExportFunctionKey' --value '<default-key>'
```

### App Settings Not Applied

The solution template owns all app settings (including the Key Vault references for storage). If a
required setting is missing, the deployment itself failed — re-run the script (or re-run with
`-DeployUpdatesOnly`) rather than patching settings by hand. The Step 7 health check reports any
missing critical settings (`FUNCTIONS_WORKER_RUNTIME`, `WEBSITE_RUN_FROM_PACKAGE`, `fhirServerUri`,
`jobOutputStorageAccountName`).

## Cleanup

To remove all deployed resources:

```powershell
# Delete the entire resource group (removes all HDS export resources)
az group delete --name "<rg>" --yes --no-wait
```

<#
.SYNOPSIS
    Deploys the HDS FHIR Export Function App (.NET 8 isolated worker).

.DESCRIPTION
    Thin, self-contained deployment for the Healthcare Data Solutions FHIR Export
    Function App. It reuses the existing ARM solution template end-to-end instead of
    re-implementing any deployment logic:

        1. Stage the function ZIP to a short-lived storage container and mint a read SAS.
        2. Run the solution template (mainTemplate.json) once, passing the staged location
           and skipZipDeploy=$false.
        3. The template deploys EVERYTHING - storage, Key Vault, App Insights, Log Analytics,
           App Service Plan, Function App, all RBAC and app settings, AND the function code via
           its own native 'Microsoft.Web/sites/extensions ZipDeploy' resource.
        4. Stage storage is deleted; the ExportFunctionKey is published to Key Vault for the
           downstream Fabric service to consume.

    The ZIP can be a pre-built package (default) or produced locally from source
    (-BuildFromSource), so both consumer scenarios are covered identically: Microsoft
    ships the ZIP, or the customer builds it.

    This replaces the deprecated Azure Marketplace "Create" deployment path.

    NOTE (deferred): a -DirectZipDeploy fallback (push code via management-plane config-zip,
    no staging storage) was intentionally NOT included to keep this script thin. It is only
    needed for tenants whose Azure Policy forbids creating a staging storage account or SAS.
    See readMe.md "Deferred: restricted-tenant fallback" - to be revisited after review.

.PARAMETER SubscriptionId
    Azure subscription ID where resources will be deployed.

.PARAMETER ResourceGroupName
    Resource group to deploy into. Created if it does not already exist.

.PARAMETER Location
    Azure region for all resources. Default: eastus.

.PARAMETER FhirServerUri
    FHIR Server URI for export (https://<name>.fhir.azurehealthcareapis.com).
    Use 'NA' to defer FHIR configuration.

.PARAMETER ExportStartTime
    Export start date in yyyy-MM-dd format. Default: 30 days ago.

.PARAMETER LanguageServiceId
    Optional. Full resource ID of an Azure Language Service for NLP enrichment.

.PARAMETER DeployUpdatesOnly
    If set, refreshes an existing deployment's code/runtime only (no shared infra changes).
    Uses the same thin staging path - the template's update-only ZipDeploy delivers the code,
    then the four .NET 8 isolated-worker settings are patched on the app (Step 5b) so an existing
    .NET 6 in-process deployment is fully migrated to the isolated model.

.PARAMETER BuildFromSource
    If set, builds exportprocessor.zip from source via 'dotnet publish' instead of using a
    pre-built ZIP. Requires -SourceProjectPath.

.PARAMETER SourceProjectPath
    Path to ExportProcessor.csproj. Required when -BuildFromSource is used.

.PARAMETER PreBuiltZipPath
    Path to the pre-built exportprocessor.zip. Default: ../functionapps/exportprocessor.zip
    relative to this script.

.PARAMETER TagsByResources
    Optional hashtable of tags keyed by resource type.

.PARAMETER RestrictStorageNetworkAccess
    If set, storage accounts are created with networkAcls.defaultAction=Deny. Only enable when
    Azure Policy requires it - the Consumption-plan function content share is not supported
    behind a storage firewall and the host may fail to start.

.PARAMETER KeepStagingAccount
    Diagnostic. If set, the short-lived staging storage account is not deleted after deployment.

.EXAMPLE
    # Deploy with the pre-built ZIP (most common)
    .\Deploy-FhirExportFunctionApp.ps1 `
        -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
        -ResourceGroupName "my-rg" `
        -FhirServerUri "https://myfhirserver.fhir.azurehealthcareapis.com" `
        -Location "eastus"

.EXAMPLE
    # Refresh code only on an existing deployment
    .\Deploy-FhirExportFunctionApp.ps1 `
        -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
        -ResourceGroupName "my-rg" -DeployUpdatesOnly

.EXAMPLE
    # Build from source and deploy
    .\Deploy-FhirExportFunctionApp.ps1 `
        -SubscriptionId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
        -ResourceGroupName "my-rg" `
        -FhirServerUri "https://myfhirserver.fhir.azurehealthcareapis.com" `
        -BuildFromSource -SourceProjectPath "..\..\export\ExportProcessor\ExportProcessor.csproj"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$SubscriptionId,
    [Parameter(Mandatory = $true)] [string]$ResourceGroupName,
    [string]$Location = 'eastus',
    [string]$FhirServerUri = 'NA',
    [string]$ExportStartTime = (Get-Date).AddDays(-30).ToString('yyyy-MM-dd'),
    [string]$LanguageServiceId = '',
    [switch]$DeployUpdatesOnly,
    [switch]$BuildFromSource,
    [string]$SourceProjectPath,
    [string]$PreBuiltZipPath,
    [hashtable]$TagsByResources = @{},
    [switch]$RestrictStorageNetworkAccess,
    [switch]$KeepStagingAccount
)

$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

# Script lives in standalone-deployment/; infra root is one level up.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InfraDir  = Split-Path -Parent $ScriptDir

function Write-Step    { param([string]$m) Write-Host ""; Write-Host "── $m" -ForegroundColor Cyan }
function Write-Ok      { param([string]$m) Write-Host "   OK  $m" -ForegroundColor Green }
function Write-Info    { param([string]$m) Write-Host "       $m" -ForegroundColor Gray }
function Write-Warn    { param([string]$m) Write-Host "   !   $m" -ForegroundColor Yellow }

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Prerequisites + Azure context
# ─────────────────────────────────────────────────────────────────────────────
function Initialize-Deployment {
    Write-Step "Step 1: Validating prerequisites"

    if (-not (Get-Module -Name Az.Resources -ListAvailable)) {
        throw "Az PowerShell module not found. Install with: Install-Module Az -Scope CurrentUser -Force"
    }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) not found. Install from https://aka.ms/installazurecli"
    }

    Set-AzContext -Subscription $SubscriptionId | Out-Null
    az account set --subscription $SubscriptionId 2>$null
    Write-Ok "Subscription context set: $SubscriptionId"

    if ($RestrictStorageNetworkAccess) {
        Write-Warn "-RestrictStorageNetworkAccess applies storage firewall (networkAcls=Deny)."
        Write-Info "The Consumption-plan content share is NOT supported behind a storage firewall;"
        Write-Info "the function host may fail to start. Only use this if Azure Policy forces it."
    }

    if (-not (Get-AzResourceGroup -Name $ResourceGroupName -ErrorAction SilentlyContinue)) {
        Write-Info "Creating resource group '$ResourceGroupName' in $Location..."
        New-AzResourceGroup -Name $ResourceGroupName -Location $Location | Out-Null
    }
    Write-Ok "Resource group ready: $ResourceGroupName"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Resolve (or build) the function ZIP
# ─────────────────────────────────────────────────────────────────────────────
function Resolve-FunctionZip {
    Write-Step "Step 2: Resolving function package"

    if ($BuildFromSource) {
        if (-not $SourceProjectPath -or -not (Test-Path $SourceProjectPath)) {
            throw "-BuildFromSource requires a valid -SourceProjectPath (ExportProcessor.csproj)."
        }
        $publishDir = Join-Path $env:TEMP "hds-export-publish-$(Get-Random)"
        $zipPath    = Join-Path $env:TEMP "exportprocessor-$(Get-Random).zip"
        Write-Info "Building from source: $SourceProjectPath"
        # Pipe build output to the host so it never contaminates the function's return value.
        dotnet publish $SourceProjectPath -c Release -o $publishDir --nologo | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed (exit $LASTEXITCODE)." }
        Compress-Archive -Path (Join-Path $publishDir '*') -DestinationPath $zipPath -Force
        Remove-Item $publishDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Ok "Built package: $zipPath ($([math]::Round((Get-Item $zipPath).Length/1MB,1)) MB)"
        return [pscustomobject]@{ Path = $zipPath; Temp = $true }
    }

    $zipPath = if ($PreBuiltZipPath) { $PreBuiltZipPath } else { Join-Path $InfraDir 'functionapps\exportprocessor.zip' }
    if (-not (Test-Path $zipPath)) {
        throw "Pre-built ZIP not found at '$zipPath'. Provide -PreBuiltZipPath or use -BuildFromSource."
    }
    Write-Ok "Using pre-built package: $zipPath ($([math]::Round((Get-Item $zipPath).Length/1MB,1)) MB)"
    return [pscustomobject]@{ Path = $zipPath; Temp = $false }
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Resolve the deployment template (shipped JSON preferred; bicep fallback)
# ─────────────────────────────────────────────────────────────────────────────
function Resolve-Template {
    $json  = Join-Path $InfraDir 'mainTemplate.json'
    if (Test-Path $json) { return $json }

    $bicep = Join-Path $InfraDir 'main.bicep'
    if (Test-Path $bicep) {
        # The Az module cannot always find bicep on PATH; compile with the az-bundled bicep.
        $compiled = Join-Path $env:TEMP "hds-main-$(Get-Random).json"
        Write-Info "mainTemplate.json not found; compiling main.bicep -> $compiled"
        az bicep build --file $bicep --outfile $compiled 2>&1 | Out-Host
        if (-not (Test-Path $compiled)) { throw "Bicep compile failed - no JSON produced." }
        return $compiled
    }
    throw "No deployment template found (expected mainTemplate.json or main.bicep in $InfraDir)."
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Stage the ZIP for the template's native ZipDeploy
# ─────────────────────────────────────────────────────────────────────────────
# The template fetches the package from _artifactsLocation + 'functionapps/exportprocessor.zip'
# + a read SAS. We stage into a short-lived storage account scoped to exactly that blob.
function New-StagingArtifacts {
    param([string]$ZipPath)
    Write-Step "Step 4: Staging deployment artifacts"

    $stamp     = -join ((97..122) | Get-Random -Count 8 | ForEach-Object { [char]$_ })
    $account   = "stghdsdeploy$stamp"             # 12 + 8 = 20 chars (< 24 limit)
    $container = 'artifacts'
    $blob      = 'functionapps/exportprocessor.zip'

    Write-Info "Creating short-lived staging account '$account'..."
    New-AzStorageAccount -ResourceGroupName $ResourceGroupName -Name $account `
        -Location $Location -SkuName Standard_LRS -Kind StorageV2 `
        -AllowBlobPublicAccess $false -MinimumTlsVersion TLS1_2 `
        -Tag @{ purpose = 'hds-export-deploy-staging'; safeToDelete = 'true' } -ErrorAction Stop | Out-Null
    $script:StagingAccountName = $account

    $key = (Get-AzStorageAccountKey -ResourceGroupName $ResourceGroupName -Name $account)[0].Value
    $ctx = New-AzStorageContext -StorageAccountName $account -StorageAccountKey $key
    New-AzStorageContainer -Name $container -Context $ctx -Permission Off -ErrorAction Stop | Out-Null

    Write-Info "Uploading package to '$container/$blob'..."
    Set-AzStorageBlobContent -File $ZipPath -Container $container -Blob $blob -Context $ctx -Force -ErrorAction Stop | Out-Null

    # Narrow, read-only, blob-scoped SAS (4h). ZipDeploy only needs to GET this one blob.
    $sas = (New-AzStorageBlobSASToken -Container $container -Blob $blob -Permission r `
                -ExpiryTime (Get-Date).AddHours(4) -Context $ctx -ErrorAction Stop).TrimStart('?')
    $artifactsLocation = "https://$account.blob.core.windows.net/$container/"

    # Confirm the platform can fetch the staged blob via SAS before deploying.
    try {
        Invoke-WebRequest -Uri "$artifactsLocation$blob`?$sas" -Method Head -UseBasicParsing -TimeoutSec 30 | Out-Null
        Write-Ok "Staged artifact reachable via SAS"
    } catch {
        throw "Staged artifact not reachable via SAS: $($_.Exception.Message). If Azure Policy blocks staging storage/SAS in this tenant, see readMe.md 'Deferred: restricted-tenant fallback'."
    }
    return [pscustomobject]@{ ArtifactsLocation = $artifactsLocation; SasToken = $sas }
}

function Remove-StagingArtifacts {
    if (-not $script:StagingAccountName) { return }
    if ($KeepStagingAccount) {
        Write-Info "Keeping staging account '$script:StagingAccountName' (-KeepStagingAccount)."
        return
    }
    try {
        Remove-AzStorageAccount -ResourceGroupName $ResourceGroupName -Name $script:StagingAccountName -Force -ErrorAction Stop
        Write-Info "Removed staging account '$script:StagingAccountName'."
        $script:StagingAccountName = $null
    } catch {
        Write-Warn "Could not remove staging account '$script:StagingAccountName': $($_.Exception.Message). Delete it manually."
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Deploy the solution template (infra + settings + native code ZipDeploy)
# ─────────────────────────────────────────────────────────────────────────────
function Invoke-TemplateDeployment {
    param([string]$TemplatePath, [string]$ArtifactsLocation, [string]$SasToken)
    Write-Step "Step 5: Deploying solution template"

    $deployParams = @{
        ResourceGroupName            = $ResourceGroupName
        TemplateFile                 = $TemplatePath
        fhirServerUri                = $FhirServerUri
        exportStartTime              = $ExportStartTime
        location                     = $Location
        deployUpdatesOnly            = [bool]$DeployUpdatesOnly
        skipZipDeploy                = $false
        restrictStorageNetworkAccess = [bool]$RestrictStorageNetworkAccess
        '_artifactsLocation'         = $ArtifactsLocation
        '_artifactsLocationSasToken' = (ConvertTo-SecureString -String $SasToken -AsPlainText -Force)
    }
    if ($LanguageServiceId)        { $deployParams['languageServiceId'] = $LanguageServiceId }
    if ($TagsByResources.Count -gt 0) { $deployParams['tagsByResources'] = $TagsByResources }

    $name = "hds-export-deploy-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Write-Info "Mode: $(if ($DeployUpdatesOnly) { 'Update-only (code)' } else { 'Full (infra + code)' })"
    Write-Info "Deployment name: $name"

    $result = New-AzResourceGroupDeployment -Name $name @deployParams -Verbose
    if ($result.ProvisioningState -ne 'Succeeded') {
        throw "Template deployment state: $($result.ProvisioningState). Inspect with: Get-AzResourceGroupDeploymentOperation -ResourceGroupName '$ResourceGroupName' -Name '$name'"
    }
    Write-Ok "Template deployment succeeded (code delivered by native ZipDeploy)"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Publish ExportFunctionKey to Key Vault (consumed by the Fabric service)
# ─────────────────────────────────────────────────────────────────────────────
# The function key only exists after the host registers Run_Export, which happens after the
# ARM deployment returns. This is the single post-deploy action the template cannot perform.
function Publish-ExportFunctionKey {
    Write-Step "Step 6: Publishing ExportFunctionKey to Key Vault"

    $funcApp = Get-SingleDeployedName -Kind 'export function app' -Prefix 'msft-func-hds-export-' -Service functionapp
    $kv      = Get-SingleDeployedName -Kind 'Key Vault'          -Prefix 'msft-kv-'              -Service keyvault
    if (-not $funcApp -or -not $kv) {
        Write-Warn "Function app or Key Vault not found; skipping ExportFunctionKey. (app='$funcApp', kv='$kv')"
        return
    }
    Write-Info "Function app: $funcApp"
    Write-Info "Key Vault:    $kv"

    # Poll for Run_Export to register, then read its function key (cold start can take 1-2 min).
    # Read the key from the ARM listkeys endpoint via 'az rest', NOT 'az functionapp function keys
    # list': az >= 2.87 deserializes that command into an empty envelope (all fields null) even on a
    # 200 response. 'az rest' returns the raw key dictionary and is version-independent. A relative
    # URL lets 'az rest' prepend the active cloud's ARM endpoint, so this stays correct in sovereign
    # clouds. The single api-version URL (no JMESPath brackets, no '&') is safe through the az.cmd shim.
    $keyUrl = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.Web/sites/$funcApp/functions/Run_Export/listkeys?api-version=2022-03-01"
    $key = $null
    foreach ($attempt in 1..20) {
        $key = az rest --method post --url $keyUrl --query default -o tsv 2>$null
        if ($key) { Write-Ok "Retrieved Run_Export function key after ~$(($attempt-1)*30)s"; break }
        Write-Info "Waiting for Run_Export to register... ($attempt/20)"
        Start-Sleep -Seconds 30
    }
    if (-not $key) { throw "Run_Export did not register in time; ExportFunctionKey not published. Re-run after the app warms up." }

    # Write the secret. A freshly RBAC-created vault grants no data-plane role to the deployer,
    # so on the first 'forbidden' we self-assign Key Vault Secrets Officer and poll for the role
    # to propagate (RBAC can take a few minutes) before giving up.
    if (Set-FunctionKeySecret -KeyVault $kv -Value $key) { Write-Ok "ExportFunctionKey published to '$kv'"; return }

    $oid = az ad signed-in-user show --query id -o tsv 2>$null
    if (-not $oid) { throw "Cannot write ExportFunctionKey and could not resolve the signed-in identity to self-assign 'Key Vault Secrets Officer'. Assign that role on '$kv' and re-run with -DeployUpdatesOnly." }
    $scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.KeyVault/vaults/$kv"
    Write-Info "Assigning 'Key Vault Secrets Officer' to the deployer; waiting for RBAC to propagate..."
    az role assignment create --role "Key Vault Secrets Officer" --assignee-object-id $oid --assignee-principal-type User --scope $scope 2>$null | Out-Null
    foreach ($attempt in 1..6) {
        Start-Sleep -Seconds 30
        if (Set-FunctionKeySecret -KeyVault $kv -Value $key) { Write-Ok "ExportFunctionKey published to '$kv'"; return }
        Write-Info "RBAC not yet effective; retrying... ($attempt/6)"
    }
    throw "Failed to write ExportFunctionKey to '$kv' after self-assigning Key Vault Secrets Officer (waited ~3 min for RBAC). Verify your data-plane access and re-run with -DeployUpdatesOnly."
}

function Set-FunctionKeySecret {
    param([string]$KeyVault, [string]$Value)
    az keyvault secret set --vault-name $KeyVault --name ExportFunctionKey --value $Value 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# Returns the single deployed resource name whose name starts with $Prefix, or throws if a shared
# resource group contains more than one match (publishing the wrong key would be a silent hazard).
# We list as JSON and filter the prefix in PowerShell rather than using an az '--query' JMESPath
# filter: on Windows, az is a .cmd shim and PowerShell forwards a no-space '[?...]' query UNQUOTED
# to cmd.exe, which fails with '].name was unexpected at this time'. JSON + Where-Object is portable
# across shells and CLI versions.
function Get-SingleDeployedName {
    param([string]$Kind, [string]$Prefix, [ValidateSet('functionapp','keyvault')] [string]$Service)
    $json  = az $Service list -g $ResourceGroupName -o json 2>$null
    $names = @(($json | ConvertFrom-Json -ErrorAction SilentlyContinue) |
               Where-Object { $_.name -like "$Prefix*" } | Select-Object -ExpandProperty name)
    if ($names.Count -gt 1) {
        throw "Ambiguous $Kind in resource group '$ResourceGroupName': $($names -join ', '). This deployment expects a dedicated resource group with a single HDS export deployment."
    }
    return ($names | Select-Object -First 1)
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Health summary
# ─────────────────────────────────────────────────────────────────────────────
function Show-HealthSummary {
    Write-Step "Step 7: Deployment health"

    $funcApp = Get-SingleDeployedName -Kind 'export function app' -Prefix 'msft-func-hds-export-' -Service functionapp
    if (-not $funcApp) { Write-Warn "Function app not found for health check."; return }

    $state = az functionapp show -n $funcApp -g $ResourceGroupName --query state -o tsv 2>$null
    if ($state -eq 'Running') { Write-Ok "Function app running: $funcApp" } else { Write-Warn "Function app state: $state" }

    $expected = @{ FUNCTIONS_WORKER_RUNTIME = 'dotnet-isolated'; WEBSITE_RUN_FROM_PACKAGE = '1'; FUNCTIONS_EXTENSION_VERSION = '~4' }
    $present = @{}
    az functionapp config appsettings list -n $funcApp -g $ResourceGroupName -o json 2>$null |
        ConvertFrom-Json | ForEach-Object { $present[$_.name] = $_.value }
    $issues = @()
    foreach ($k in $expected.Keys) { if ($present[$k] -ne $expected[$k]) { $issues += "$k (got '$($present[$k])')" } }
    if ([string]::IsNullOrEmpty($present['fhirServerUri']))               { $issues += 'fhirServerUri (missing)' }
    if ([string]::IsNullOrEmpty($present['jobOutputStorageAccountName'])) { $issues += 'jobOutputStorageAccountName (missing)' }
    if ($issues.Count -eq 0) { Write-Ok "Critical app settings verified" } else { Write-Warn "App setting issues: $($issues -join '; ')" }

    $funcNames = @((az functionapp function list -n $funcApp -g $ResourceGroupName -o json 2>$null |
        ConvertFrom-Json -ErrorAction SilentlyContinue) | Select-Object -ExpandProperty name -ErrorAction SilentlyContinue)
    if ($funcNames.Count) { Write-Ok "Functions registered: $($funcNames.Count)" }
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5b: Migrate runtime settings to .NET 8 isolated (update-only path only)
# ─────────────────────────────────────────────────────────────────────────────
# In update-only mode the template deploys ONLY the ZIP - siteConfig and appSettings are guarded
# by if(!deployUpdatesOnly) in deployAppServices.bicep. An existing .NET 6 in-process app would
# therefore receive .NET 8 isolated bits while still configured for in-process, so the host loads
# only the built-in WarmUp and no user functions register. Patch the four isolated settings here so
# -DeployUpdatesOnly performs a true in-process -> isolated migration. Idempotent: re-applying the
# same values to an already-isolated app is a no-op.
function Update-RuntimeSettingsForIsolated {
    Write-Step "Step 5b: Migrating runtime settings to .NET 8 isolated worker"

    $funcApp = Get-SingleDeployedName -Kind 'export function app' -Prefix 'msft-func-hds-export-' -Service functionapp
    if (-not $funcApp) { throw "Update-only: no 'msft-func-hds-export-*' function app found in '$ResourceGroupName' to migrate." }
    Write-Info "Function app: $funcApp"

    # siteConfig: .NET 8 runtime + 64-bit worker (both required by the isolated model).
    az functionapp config set -n $funcApp -g $ResourceGroupName `
        --net-framework-version v8.0 --use-32bit-worker-process false 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to patch siteConfig (netFrameworkVersion/use32BitWorkerProcess) on '$funcApp'." }
    Write-Ok "siteConfig set: netFrameworkVersion=v8.0, use32BitWorkerProcess=false"

    # appSettings: out-of-process runtime + isolated placeholder warmup.
    az functionapp config appsettings set -n $funcApp -g $ResourceGroupName `
        --settings FUNCTIONS_WORKER_RUNTIME=dotnet-isolated WEBSITE_USE_PLACEHOLDER_DOTNETISOLATED=1 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to patch app settings (FUNCTIONS_WORKER_RUNTIME/WEBSITE_USE_PLACEHOLDER_DOTNETISOLATED) on '$funcApp'." }
    Write-Ok "appSettings set: FUNCTIONS_WORKER_RUNTIME=dotnet-isolated, WEBSITE_USE_PLACEHOLDER_DOTNETISOLATED=1"

    # Setting changes recycle the host; an explicit restart guarantees the isolated worker
    # re-registers the user functions against the freshly deployed ZIP.
    Write-Info "Restarting function app to apply the runtime migration..."
    az functionapp restart -n $funcApp -g $ResourceGroupName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restart function app '$funcApp' after the runtime migration." }
    Write-Ok "Function app restarted; isolated worker will re-register Run_Export"
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
$script:StagingAccountName = $null
$zip = $null

try {
    Write-Host ""
    Write-Host "HDS FHIR Export Function App - Deployment (.NET 8 isolated worker)" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan

    Initialize-Deployment
    $zip      = Resolve-FunctionZip
    $template = Resolve-Template
    $staging  = New-StagingArtifacts -ZipPath $zip.Path
    Invoke-TemplateDeployment -TemplatePath $template -ArtifactsLocation $staging.ArtifactsLocation -SasToken $staging.SasToken
    # Update-only deploys ONLY the ZIP; migrate the runtime settings so an existing in-process
    # app is fully converted to the isolated model (no-op if it is already isolated).
    if ($DeployUpdatesOnly) { Update-RuntimeSettingsForIsolated }
    # Native ZipDeploy completes inside the ARM deployment, so staging is no longer needed.
    Remove-StagingArtifacts
    # Always (re)publish the key: it is idempotent, and lets -DeployUpdatesOnly repair a vault
    # whose ExportFunctionKey is missing from an earlier partial run.
    Publish-ExportFunctionKey
    Show-HealthSummary

    Write-Host ""
    Write-Host "Deployment completed successfully." -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Host "Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    exit 1
}
finally {
    Remove-StagingArtifacts   # safety net if we failed before the explicit cleanup
    if ($zip -and $zip.Temp -and (Test-Path $zip.Path)) {
        Remove-Item $zip.Path -Force -ErrorAction SilentlyContinue
    }
}

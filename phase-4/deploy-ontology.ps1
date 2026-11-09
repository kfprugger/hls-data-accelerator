#!/usr/bin/env pwsh
# ============================================================================
# deploy-ontology.ps1
# Creates (or updates) Fabric IQ ontologies via REST API.
#
# By default this deploys the clinical device ontology only. Pass -IncludeGold
# and a payer-oriented -OntologyName (for example DevicePayerOntology) to add
# claims, payer, care-gap, risk, and high-cost entities from the Gold Lakehouse.
#
# ClinicalDeviceOntology entity types:
#   - Static (Lakehouse): Patient, Device, Encounter, Condition,
#                          MedicationRequest, Observation, ImagingStudy,
#                          DeviceAssociation
#   - TimeSeries (Eventhouse): DeviceTelemetry
#
# DevicePayerOntology adds Gold Lakehouse entities:
#   - Claim, Payer, Diagnosis, PatientDiagnosis, MedAdherence,
#     CareGap, PatientRisk, HighCostClaimant
#
# Clinical relationships stay focused on patient/device care. Payer relationships
# live in the payer ontology so clinical agents are not grounded in payer-first semantics.
#
# Prerequisites:
#   - az login completed
#   - Phase 1 + Phase 2 deployed (Eventhouse, KQL DB, Silver Lakehouse)
#   - Ontology projection tables created (DeviceAssociation plus *Ontology tables from Step 8b)
#   - Ontology item (preview) enabled on Fabric tenant
#
# Usage:
#   .\deploy-ontology.ps1
#   .\deploy-ontology.ps1 -FabricWorkspaceName "my-workspace"
# ============================================================================

[CmdletBinding()]
param (
    [string]$FabricWorkspaceName = "med-device-rti-hds",
    [string]$OntologyName        = "ClinicalDeviceOntology",
    [string]$FabricApiBase       = "https://api.fabric.microsoft.com/v1",
    [switch]$IncludeFhir,
    [switch]$IncludeDicom,
    [switch]$IncludeTelemetry,
    [switch]$IncludeGold,
    [switch]$ReplaceExisting
)

# Default to the clinical device ontology if no component switches are specified.
# Gold claims/payer entities are opt-in so ClinicalDeviceOntology stays clinical.
$allSwitchesFalse = -not $IncludeFhir -and -not $IncludeDicom -and -not $IncludeTelemetry -and -not $IncludeGold
if ($allSwitchesFalse) {
    $IncludeFhir = $true
    $IncludeDicom = $true
    $IncludeTelemetry = $true
}

$ErrorActionPreference = "Stop"

# ============================================================================
# AUTH HELPERS (same pattern as deploy-fabric-rti.ps1)
# ============================================================================

$script:AccessTokenCache = @{}
function Get-AccessTokenForResource {
    param ([string]$ResourceUrl)
    $key = $ResourceUrl.ToLowerInvariant()
    $cached = $script:AccessTokenCache[$key]
    if ($cached -and $cached.ExpiresOn -gt (Get-Date).AddMinutes(5)) { return $cached.Token }
    try {
        $tokenObj = Get-AzAccessToken -ResourceUrl $ResourceUrl -ErrorAction Stop
        $rawToken = $tokenObj.Token
        if ($rawToken -is [System.Security.SecureString]) {
            $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($rawToken)
            try { $rawToken = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
            finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        } elseif ($rawToken -isnot [string]) {
            $rawToken = $rawToken | ConvertFrom-SecureString -AsPlainText
        }
        $script:AccessTokenCache[$key] = @{ Token = $rawToken; ExpiresOn = $tokenObj.ExpiresOn }
        return $rawToken
    } catch {
        $cliJson = az account get-access-token --resource $ResourceUrl -o json 2>$null | ConvertFrom-Json
        if (-not $cliJson -or -not $cliJson.accessToken) { throw }
        $rawToken = [string]$cliJson.accessToken
        $script:AccessTokenCache[$key] = @{ Token = $rawToken; ExpiresOn = (Get-Date).AddMinutes(50) }
        return $rawToken
    }
}

function Get-FabricAccessToken { return Get-AccessTokenForResource -ResourceUrl "https://api.fabric.microsoft.com" }

function Invoke-FabricApi {
    param (
        [string]$Method   = "GET",
        [string]$Endpoint,
        [object]$Body     = $null,
        [int]$MaxRetries   = 10
    )
    $uri     = "$FabricApiBase$Endpoint"
    $bodyJson = if ($Body) { $Body | ConvertTo-Json -Depth 30 -Compress } else { $null }

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        $token   = Get-FabricAccessToken
        $headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }
        try {
            $params = @{ Method = $Method; Uri = $uri; Headers = $headers }
            if ($bodyJson -and $Method -ne "GET") { $params["Body"] = $bodyJson }
            $response = Invoke-WebRequest @params -ErrorAction Stop
            $statusCode = [int]$response.StatusCode

            if ($statusCode -eq 202) {
                $location = $null
                try { $location = $response.Headers["Location"] } catch {}
                if ($location -is [array]) { $location = $location[0] }
                $opId = $null
                try { $opId = $response.Headers["x-ms-operation-id"] } catch {}
                if ($opId -is [array]) { $opId = $opId[0] }

                if ($location) {
                    Write-Host "  Long-running operation ($opId), polling..." -ForegroundColor Gray
                    $retryOperation = $false
                    for ($poll = 0; $poll -lt 60; $poll++) {
                        Start-Sleep -Seconds 5
                        $pollHeaders = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }
                        try {
                            $opResponse = Invoke-RestMethod -Uri $location -Headers $pollHeaders -Method GET -ErrorAction Stop
                        } catch {
                            $pollStatusCode = $null
                            try { $pollStatusCode = [int]$_.Exception.Response.StatusCode } catch {}
                            $pollBody = $_.ErrorDetails.Message
                            $pollTransient = ($pollStatusCode -in @(429, 500, 502, 503, 504)) -or ($pollStatusCode -eq 403 -and $pollBody -match "RequestDeniedByInboundPolicy")
                            if ($pollTransient) {
                                Write-Host "    LRO poll transient HTTP $pollStatusCode — retrying..." -ForegroundColor Yellow
                                continue
                            }
                            throw $_
                        }
                        if ($opResponse.status -eq "Succeeded") {
                            return $opResponse
                        }
                        if ($opResponse.status -eq "Failed") {
                            $errDetail = $opResponse | ConvertTo-Json -Depth 10
                            if ($errDetail -match "RequestDeniedByInboundPolicy" -and $attempt -lt $MaxRetries) {
                                $retryOperation = $true
                                break
                            }
                            throw "LRO failed: $errDetail"
                        }
                        Write-Host "    Status: $($opResponse.status)... ($($poll * 5)s)" -ForegroundColor DarkGray
                    }
                    if ($retryOperation) {
                        $delay = [Math]::Min(20 * $attempt, 120)
                        Write-Host "  Fabric inbound policy denied the LRO backend call. Retrying operation in ${delay}s... (attempt $attempt/$MaxRetries)" -ForegroundColor Yellow
                        Start-Sleep -Seconds $delay
                        continue
                    }
                    throw "LRO timed out after 300s"
                }
                if ($response.Content) { return ($response.Content | ConvertFrom-Json) }
                return $null
            }

            if ($response.Content) { return ($response.Content | ConvertFrom-Json) }
            return $null
        }
        catch {
            $errStatusCode = $null
            try { $errStatusCode = [int]$_.Exception.Response.StatusCode } catch {}
            $errBody = $_.ErrorDetails.Message
            $isTransient = ($errStatusCode -in @(429, 500, 502, 503, 504)) -or ($errStatusCode -eq 403 -and $errBody -match "RequestDeniedByInboundPolicy") -or ($errStatusCode -eq 409 -and $errBody -match "ItemDisplayNameNotAvailableYet")
            if ($isTransient -and $attempt -lt $MaxRetries) {
                $retryAfter = [Math]::Min(20 * $attempt, 120)
                try {
                    $headerRetry = [int]$_.Exception.Response.Headers["Retry-After"]
                    if ($headerRetry -gt 0) { $retryAfter = $headerRetry }
                } catch {}
                Write-Host "  Fabric API transient HTTP $errStatusCode — retrying in ${retryAfter}s... (attempt $attempt/$MaxRetries)" -ForegroundColor Yellow
                if ($errBody) { Write-Host $errBody -ForegroundColor DarkGray }
                Start-Sleep -Seconds $retryAfter
                continue
            }
            throw $_
        }
    }
}

function ConvertTo-Base64 {
    param ([string]$Text)
    [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text))
}

# ============================================================================
# ID GENERATION — Ontology uses positive 64-bit integers as IDs
# ============================================================================

$script:idCounter = [long](Get-Date).Ticks

function New-OntologyId {
    $script:idCounter++
    return [string]$script:idCounter
}

# ============================================================================
# DISCOVER WORKSPACE, LAKEHOUSE, EVENTHOUSE
# ============================================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     FABRIC IQ — Deploy Ontology                            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# --- Workspace ---
Write-Host "  Discovering workspace..." -ForegroundColor White
$workspaces = Invoke-FabricApi -Endpoint "/workspaces"
$ws = $workspaces.value | Where-Object { $_.displayName -eq $FabricWorkspaceName }
if (-not $ws) {
    Write-Host "ERROR: Workspace '$FabricWorkspaceName' not found." -ForegroundColor Red
    exit 1
}
$workspaceId = $ws.id
Write-Host "  ✓ Workspace: $FabricWorkspaceName ($workspaceId)" -ForegroundColor Green

# --- Silver Lakehouse ---
$silverLhId = $null
$silverLhName = $null
if ($IncludeFhir -or $IncludeDicom -or $IncludeTelemetry) {
    $lakehouses = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/lakehouses"
    $silverLh = $lakehouses.value | Where-Object { $_.displayName -match "[Ss]ilver" }
    if (-not $silverLh) {
        Write-Host "ERROR: Silver Lakehouse not found in workspace." -ForegroundColor Red
        exit 1
    }
    if ($silverLh -is [array]) { $silverLh = $silverLh[0] }
    $silverLhId   = $silverLh.id
    $silverLhName = $silverLh.displayName
    Write-Host "  ✓ Silver Lakehouse: $silverLhName ($silverLhId)" -ForegroundColor Green
}

# --- Eventhouse & KQL Database ---
$eventhouseId = $null
$eventhouseName = $null
$kqlDbId = $null
$kqlDbName = $null
$kustoUri = $null

if ($IncludeTelemetry) {
    Write-Host "  Discovering Eventhouse..." -ForegroundColor White
    $eventhouses = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/eventhouses"
    $eventhouse = $eventhouses.value | Where-Object { $_.displayName -match "Masimo" }
    if (-not $eventhouse) {
        $eventhouse = $eventhouses.value | Select-Object -First 1
    }
    if (-not $eventhouse) {
        Write-Host "ERROR: Eventhouse not found in workspace." -ForegroundColor Red
        exit 1
    }
    if ($eventhouse -is [array]) { $eventhouse = $eventhouse[0] }
    $eventhouseId   = $eventhouse.id
    $eventhouseName = $eventhouse.displayName
    Write-Host "  ✓ Eventhouse: $eventhouseName ($eventhouseId)" -ForegroundColor Green

    # --- KQL Database ---
    $kqlDbs = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/kqlDatabases"
    $kqlDb = $kqlDbs.value | Where-Object { $_.displayName -eq "MasimoKQLDB" -or $_.displayName -eq $eventhouseName }
    if (-not $kqlDb) { $kqlDb = $kqlDbs.value | Select-Object -First 1 }
    if (-not $kqlDb) {
        Write-Host "ERROR: KQL Database not found." -ForegroundColor Red
        exit 1
    }
    if ($kqlDb -is [array]) { $kqlDb = $kqlDb[0] }
    $kqlDbId   = $kqlDb.id
    $kqlDbName = $kqlDb.displayName

    $kqlDbDetail = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/kqlDatabases/$kqlDbId"
    $kustoUri = $kqlDbDetail.queryServiceUri
    if (-not $kustoUri) { $kustoUri = $kqlDbDetail.queryUri }
    if (-not $kustoUri) { try { $kustoUri = $kqlDbDetail.properties.queryUri } catch {} }
    if (-not $kustoUri) { try { $kustoUri = $kqlDbDetail.properties.queryServiceUri } catch {} }
    if (-not $kustoUri) {
        Write-Host "ERROR: Cannot discover Kusto query URI. Required for Eventhouse data bindings." -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ KQL Database: $kqlDbName ($kqlDbId)" -ForegroundColor Green
    Write-Host "  ✓ Kusto URI: $kustoUri" -ForegroundColor Green
}

# --- Gold (Reporting) Lakehouse ---
$goldLhId = $null
$goldLhName = $null
if ($IncludeGold) {
    $lakehouses = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/lakehouses"
    $goldLh = $lakehouses.value | Where-Object { $_.displayName -match "[Rr]eporting.*[Gg]old" }
    if (-not $goldLh) {
        $goldLh = $lakehouses.value | Where-Object { $_.displayName -match "[Gg]old" }
    }
    if ($goldLh) {
        if ($goldLh -is [array]) { $goldLh = $goldLh[0] }
        $goldLhId   = $goldLh.id
        $goldLhName = $goldLh.displayName
        Write-Host "  ✓ Gold Lakehouse: $goldLhName ($goldLhId)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Gold Lakehouse not found — claims/quality entities are required because IncludeGold is set" -ForegroundColor Red
        exit 1
    }
}

# --- Check for existing ontology ---
Write-Host ""
Write-Host "  Checking for existing ontology..." -ForegroundColor White
$existingOntology = $null
try {
    $ontologies = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/ontologies"
    $existingOntology = $ontologies.value | Where-Object { $_.displayName -eq $OntologyName }
} catch {}
if ($existingOntology) {
    if ($existingOntology -is [array]) { $existingOntology = $existingOntology[0] }
    $existingIsV2 = $false
    $chkHeaders = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json"; "x-ms-fabric-skill" = "fabriciq-ontology-cli" }
    $chkResp = $null
    try {
        $chkResp = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/ontologies/$($existingOntology.id)/getDefinition" -Headers $chkHeaders -Method POST -ErrorAction Stop
    } catch {
        throw "Failed to probe definition of existing ontology '$OntologyName' ($($existingOntology.id)): $_"
    }
    $chkDef = $null
    if ($chkResp.Content) {
        $chkDef = $chkResp.Content | ConvertFrom-Json
    } else {
        $chkOpId = $chkResp.Headers["x-ms-operation-id"]; if ($chkOpId -is [array]) { $chkOpId = $chkOpId[0] }
        $chkLoc = $chkResp.Headers["Location"]; if ($chkLoc -is [array]) { $chkLoc = $chkLoc[0] }
        if ($chkLoc -and $chkLoc -notmatch '^https?://') { $chkLoc = "https://api.fabric.microsoft.com/v1/$($chkLoc.TrimStart('/'))" }
        if (-not $chkLoc -and $chkOpId) { $chkLoc = "https://api.fabric.microsoft.com/v1/operations/$chkOpId" }
        if (-not $chkLoc) {
            throw "getDefinition for ontology '$OntologyName' returned neither content nor operation location/ID."
        }
        # Poll the getDefinition LRO for >= 5 min (300 seconds)
        $pollDeadline = (Get-Date).AddMinutes(5)
        $lroSucceeded = $false
        while ((Get-Date) -lt $pollDeadline) {
            Start-Sleep -Seconds 5
            try {
                $chkOp = Invoke-RestMethod -Uri $chkLoc -Headers $chkHeaders -ErrorAction Stop
            } catch {
                continue
            }
            if ($chkOp.status -eq "Succeeded") {
                $resUri = if ($chkLoc -match '/result$') { $chkLoc } else { "$chkLoc/result" }
                try {
                    $chkDef = Invoke-RestMethod -Uri $resUri -Headers $chkHeaders -ErrorAction Stop
                } catch {
                    throw "getDefinition LRO succeeded for ontology '$OntologyName', but failed to retrieve result from $($resUri): $_"
                }
                $lroSucceeded = $true
                break
            }
            if ($chkOp.status -in @("Failed", "Cancelled")) {
                $opError = try { $chkOp.error | ConvertTo-Json -Depth 5 -Compress } catch { [string]$chkOp.status }
                throw "getDefinition LRO for ontology '$OntologyName' ended with status $($chkOp.status): $opError"
            }
        }
        if (-not $lroSucceeded -or -not $chkDef) {
            throw "getDefinition LRO for ontology '$OntologyName' did not complete within 5 minutes ($chkLoc)"
        }
    }
    if (-not $chkDef -or -not $chkDef.definition -or -not $chkDef.definition.parts) {
        throw "getDefinition for ontology '$OntologyName' succeeded but returned no definition parts"
    }
    $existingIsV2 = @($chkDef.definition.parts | Where-Object { $_.path -eq "database.tmdl" -or $_.path -like "entities/*.tmdl" -or $_.path -like "*.tmdl" }).Count -gt 0

    if (-not $existingIsV2) {
        Write-Host "  Existing ontology '$OntologyName' ($($existingOntology.id)) uses legacy v1 JSON definition; replacing with Ontology v2 (TMDL)..." -ForegroundColor Yellow
        $ReplaceExisting = $true
    } elseif (-not $ReplaceExisting) {
        Write-Host "  ✓ Ontology '$OntologyName' already exists in v2 TMDL format ($($existingOntology.id)); preserving existing item." -ForegroundColor Green
    } else {
        Write-Host "  Existing v2 ontology '$OntologyName' ($($existingOntology.id)) will be updated in place..." -ForegroundColor Yellow
    }
}

$existingIsV1 = $existingOntology -and (-not $existingIsV2)
$totalEntities = 0
$totalRels = 0
$claimEntities = @()

if (-not $existingOntology -or $ReplaceExisting) {
# ============================================================================
# BUILD ONTOLOGY v2 (TMDL) DEFINITION
# ============================================================================

Write-Host ""
Write-Host "  Building Ontology v2 (TMDL) definition..." -ForegroundColor White

$targetLhId = if ($OntologyName -eq "DevicePayerOntology") { $goldLhId } else { $silverLhId }
$targetLhDetail = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/lakehouses/$targetLhId"
$sqlEndpoint = $null
$sqlEndpointId = $null
try {
    $sqlEndpoint = [string]$targetLhDetail.properties.sqlEndpointProperties.connectionString
    $sqlEndpointId = [string]$targetLhDetail.properties.sqlEndpointProperties.id
} catch {}
if ([string]::IsNullOrWhiteSpace($sqlEndpoint) -or [string]::IsNullOrWhiteSpace($sqlEndpointId)) {
    throw "Could not resolve SQL analytics endpoint connectionString/id for lakehouse $targetLhId"
}
Write-Host "  ✓ Backing SQL Endpoint: $sqlEndpoint ($sqlEndpointId)" -ForegroundColor Green

$v2Builder = Join-Path $PSScriptRoot 'build_ontology_v2.py'
if (-not (Test-Path $v2Builder)) { throw "Required Ontology v2 builder is missing: $v2Builder" }
$lockedPython = if ($IsWindows) { Join-Path $PSScriptRoot '../orchestrator/.venv/Scripts/python.exe' } else { Join-Path $PSScriptRoot '../orchestrator/.venv/bin/python' }
$pythonPath = if (Test-Path $lockedPython) { $lockedPython } else { $null }
if (-not $pythonPath) {
    $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
    if (-not $pythonCommand) { throw 'Python is required to build the Ontology v2 (TMDL) definition' }
    $pythonPath = $pythonCommand.Source
}

$builderArgs = @(
    $v2Builder,
    "--ontology-name", $OntologyName,
    "--sql-endpoint", $sqlEndpoint,
    "--sql-endpoint-id", $sqlEndpointId
)
if ($IncludeFhir) { $builderArgs += "--include-fhir" }
if ($IncludeDicom) { $builderArgs += "--include-dicom" }
if ($IncludeTelemetry) { $builderArgs += "--include-telemetry" }
if ($IncludeGold -and $goldLhId) { $builderArgs += "--include-gold" }

$builtJsonRaw = & $pythonPath @builderArgs
if ($LASTEXITCODE -ne 0) { throw "build_ontology_v2.py failed (exit $LASTEXITCODE)" }
$builtObj = $builtJsonRaw | ConvertFrom-Json -Depth 30
$parts = @($builtObj.parts)
$totalEntities = [int]$builtObj.entityCount
$totalRels = [int]$builtObj.relationshipCount
$claimEntities = if ([int]$builtObj.goldEntityCount -gt 0) { @(1..([int]$builtObj.goldEntityCount)) } else { @() }

Write-Host "  ✓ Ontology v2 (TMDL) definition assembled: $($parts.Count) parts" -ForegroundColor Green
Write-Host "    Entity types: $totalEntities ($($builtObj.tableCount) DirectLake backing tables)" -ForegroundColor DarkGray
Write-Host "    Relationships: $totalRels in entityRelationships.tmdl" -ForegroundColor DarkGray

if ($existingIsV1) {
    Write-Host "  Removing legacy v1 ontology '$OntologyName' ($($existingOntology.id)) before creating v2 TMDL item..." -ForegroundColor Yellow
    $delHeaders = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)"; "x-ms-fabric-skill" = "fabriciq-ontology-cli" }
    try {
        Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/ontologies/$($existingOntology.id)" -Headers $delHeaders -Method DELETE -ErrorAction Stop | Out-Null
    } catch {
        throw "Failed to delete legacy v1 ontology '$OntologyName' ($($existingOntology.id)): $_"
    }
    try {
        $oldGms = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/items?type=GraphModel"
        foreach ($gm in @($oldGms.value | Where-Object { $_.displayName -like "$OntologyName`_graph_*" })) {
            Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/items/$($gm.id)" -Headers $delHeaders -Method DELETE -ErrorAction SilentlyContinue | Out-Null
        }
    } catch {
        Write-Warning "Could not clean up legacy graph models for '$OntologyName': $_"
    }
    $existingOntology = $null
    Start-Sleep -Seconds 5
}

# ============================================================================
# DEPLOY ONTOLOGY v2 (TMDL)
# ============================================================================

Write-Host ""
Write-Host "  Deploying Ontology v2 '$OntologyName'..." -ForegroundColor White

$ontologyDescription = if ($IncludeGold) { "Payer-oriented healthcare ontology (v2 TMDL) linking devices, patients, diagnoses, claims, payer categories, care gaps, RAF risk, high-cost cohorts, and telemetry." } else { "Clinical device ontology (v2 TMDL) for patient-device relationships, encounters, conditions, observations, medications, imaging studies, and real-time device telemetry." }
$bodyJson = (@{
    displayName = $OntologyName
    description = $ontologyDescription
    definition  = @{ parts = $parts }
} | ConvertTo-Json -Depth 30 -Compress)
$updateBody = (@{
    definition = @{ parts = $parts }
} | ConvertTo-Json -Depth 30 -Compress)
$createCompleted = $false
for ($attempt = 1; $attempt -le 10 -and -not $createCompleted; $attempt++) {
    try {
        $cToken = Get-FabricAccessToken
        $cHeaders = @{ "Authorization" = "Bearer $cToken"; "Content-Type" = "application/json"; "x-ms-fabric-skill" = "fabriciq-ontology-cli" }
        if ($existingOntology -and $ReplaceExisting) {
            $cResp = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/ontologies/$($existingOntology.id)/updateDefinition?updateMetadata=true" -Headers $cHeaders -Method POST -Body $updateBody -ErrorAction Stop
        } else {
            $cResp = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/ontologies" -Headers $cHeaders -Method POST -Body $bodyJson -ErrorAction Stop
        }

        if ([int]$cResp.StatusCode -eq 202) {
            $cOpId = $cResp.Headers["x-ms-operation-id"]; if ($cOpId -is [array]) { $cOpId = $cOpId[0] }
            Write-Host "  Long-running operation ($cOpId), polling..." -ForegroundColor Gray
            $retryCreate = $false
            for ($poll = 0; $poll -lt 60; $poll++) {
                Start-Sleep -Seconds 5
                $pH = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }
                try {
                    $oR = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/operations/$cOpId" -Headers $pH -ErrorAction Stop
                } catch {
                    $pollStatusCode = $null
                    try { $pollStatusCode = [int]$_.Exception.Response.StatusCode } catch {}
                    $pollBody = $_.ErrorDetails.Message
                    if ($pollStatusCode -in @(429, 500, 502, 503, 504) -or ($pollStatusCode -eq 403 -and $pollBody -match "RequestDeniedByInboundPolicy")) {
                        Write-Host "    Ontology create poll transient HTTP $pollStatusCode — retrying..." -ForegroundColor Yellow
                        continue
                    }
                    throw $_
                }
                Write-Host "    Status: $($oR.status)... ($($poll * 5)s)" -ForegroundColor DarkGray
                if ($oR.status -eq "Succeeded") { $createCompleted = $true; break }
                if ($oR.status -eq "Failed") {
                    $errJson = $oR | ConvertTo-Json -Depth 10
                    if ($errJson -match "RequestDeniedByInboundPolicy" -and $attempt -lt 10) {
                        $retryCreate = $true
                        break
                    }
                    $ed = if ($oR.error) { $oR.error.message } else { "Unknown" }
                    throw "Create failed: $ed"
                }
            }
            if ($retryCreate) {
                $delay = [Math]::Min(30 * $attempt, 180)
                Write-Host "  Ontology create LRO hit Fabric inbound policy. Retrying in ${delay}s... (attempt $attempt/10)" -ForegroundColor Yellow
                Start-Sleep $delay
                continue
            }
            if (-not $createCompleted) { throw "Ontology create operation did not complete within 5 minutes" }
        } else {
            $createCompleted = $true
        }
        Write-Host "  ✓ Ontology created" -ForegroundColor Green
    } catch {
        $createStatusCode = $null
        try { $createStatusCode = [int]$_.Exception.Response.StatusCode } catch {}
        $createBody = $_.ErrorDetails.Message
        $nameLockTransient = $createBody -match "ItemDisplayNameNotAvailableYet"
        if ((($createStatusCode -in @(429, 500, 502, 503, 504) -or ($createStatusCode -eq 403 -and $createBody -match "RequestDeniedByInboundPolicy") -or $nameLockTransient)) -and $attempt -lt 10) {
            $delay = if ($nameLockTransient) { [Math]::Min(60 * $attempt, 300) } else { [Math]::Min(30 * $attempt, 180) }
            Write-Host "  Ontology create transient HTTP $createStatusCode — retrying in ${delay}s... (attempt $attempt/10)" -ForegroundColor Yellow
            if ($createBody) { Write-Host $createBody -ForegroundColor DarkGray }
            Start-Sleep $delay
            continue
        }
        Write-Host "  ✗ Failed to create ontology: $_" -ForegroundColor Red
        exit 1
    }
}
}

if ($existingOntology -and -not $ReplaceExisting) {
    $ontologyId = $existingOntology.id
} else {
    # Fetch ontology ID
    Start-Sleep -Seconds 3
    $ontologies = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/ontologies"
    $ontology = $ontologies.value | Where-Object { $_.displayName -eq $OntologyName }
    if ($ontology -is [array]) { $ontology = $ontology[0] }
    $ontologyId = if ($ontology) { $ontology.id } else { "unknown" }
    if ($ontologyId -eq "unknown") {
        Write-Host "  ✗ Ontology '$OntologyName' was not discoverable after create/update." -ForegroundColor Red
        exit 1
    }
}


# ============================================================================
# VERIFY
if ($ontologyId -eq "unknown") {
    Write-Host "  ✗ Ontology '$OntologyName' was not discoverable after create/update." -ForegroundColor Red
    exit 1
}

# In the new Ontology v2 (TMDL) experience, ontology definitions are virtual over bound DirectLake
# tables and do not require companion GraphModel materialization or RefreshGraph jobs by default.
$graphModels = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/items?type=GraphModel"
$graphModel = $graphModels.value | Where-Object { $_.displayName -like "$OntologyName`_graph_*" } | Select-Object -First 1
if ($graphModel) {
    Write-Host "  ℹ Companion GraphModel present: $($graphModel.displayName) ($($graphModel.id))" -ForegroundColor DarkGray
} else {
    Write-Host "  ✓ Ontology v2 (TMDL) operates virtually over DirectLake tables (no GraphModel RefreshGraph required)" -ForegroundColor Green
}

Write-Host ""
Write-Host "  Verifying Ontology v2 (TMDL) definition..." -ForegroundColor White
Start-Sleep -Seconds 3

try {
    $vH = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json"; "x-ms-fabric-skill" = "fabriciq-ontology-cli" }
    $vR = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/ontologies/$ontologyId/getDefinition" -Headers $vH -Method POST
    if ($vR.Content) {
        $vDef = $vR.Content | ConvertFrom-Json
    } else {
        $vOpId = $vR.Headers["x-ms-operation-id"]; if ($vOpId -is [array]) { $vOpId = $vOpId[0] }
        $vLoc = $vR.Headers["Location"]; if ($vLoc -is [array]) { $vLoc = $vLoc[0] }
        if ($vLoc -and $vLoc -notmatch '^https?://') { $vLoc = "https://api.fabric.microsoft.com/v1/$($vLoc.TrimStart('/'))" }
        if (-not $vLoc -and $vOpId) { $vLoc = "https://api.fabric.microsoft.com/v1/operations/$vOpId" }
        if (-not $vLoc) { throw "getDefinition did not return content, Location, or x-ms-operation-id" }

        $vComplete = $false
        for ($poll = 0; $poll -lt 60; $poll++) {
            Start-Sleep 5
            $op = Invoke-RestMethod -Uri $vLoc -Headers $vH
            if ($op.status -eq "Succeeded") { $vComplete = $true; break }
            if ($op.status -eq "Failed") { throw "getDefinition failed: $($op.error.message)" }
        }
        if (-not $vComplete) { throw "getDefinition did not complete within 5 minutes" }

        $resultUri = if ($vLoc -match '/result$') { $vLoc } else { "$vLoc/result" }
        $vDef = Invoke-RestMethod -Uri $resultUri -Headers $vH
    }
    $vEt = @($vDef.definition.parts | Where-Object { $_.path -like "entities/*.tmdl" }).Count
    $vDb = @($vDef.definition.parts | Where-Object { $_.path -like "tables/*.tmdl" }).Count
    $vRl = @($vDef.definition.parts | Where-Object { $_.path -eq "entityRelationships.tmdl" -or $_.path -eq "relationships.tmdl" }).Count
    $hasDbTmdl = @($vDef.definition.parts | Where-Object { $_.path -eq "database.tmdl" }).Count -gt 0
    Write-Host "  ✓ Verified Ontology v2 (TMDL): $vEt entity .tmdl files, $vDb table .tmdl files, $vRl relationship .tmdl files" -ForegroundColor Green
    if (-not $hasDbTmdl -or $vEt -eq 0 -or $vDb -eq 0) {
        throw "Ontology v2 TMDL verification failed: database.tmdl=$hasDbTmdl Entities=$vEt Tables=$vDb Relationships=$vRl"
    }
} catch {
    Write-Host "  ✗ Could not verify ontology definition: $_" -ForegroundColor Red
    exit 1
}

# ============================================================================
# DONE
# ============================================================================

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║  ✓ Ontology deployed successfully!                   ║" -ForegroundColor Green
Write-Host "  ╚═══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Ontology: $OntologyName" -ForegroundColor White
Write-Host "  ID:       $ontologyId" -ForegroundColor White
Write-Host ""
if ($totalEntities -gt 0) {
    Write-Host "  Deployed:" -ForegroundColor Cyan
    Write-Host ("    {0} entity types total ({1} Gold payer/claims entities)" -f $totalEntities, $claimEntities.Count) -ForegroundColor White
    Write-Host "    $totalRels relationship types with contextualizations" -ForegroundColor White
} else {
    Write-Host "  Verified:" -ForegroundColor Cyan
    Write-Host "    $vEt entity types, $vDb data bindings, $vRl relationship parts" -ForegroundColor White
}
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1. Connect the ontology as a datasource on your Data Agents" -ForegroundColor White

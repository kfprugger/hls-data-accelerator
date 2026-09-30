#Requires -Version 7.2
<#
.SYNOPSIS
Reselect published Lakehouse and KQL objects using Fabric's hydrated draft metadata.
.DESCRIPTION
Read-only by default. Use -Apply and -BackupDirectory to update, publish, and verify.
Missing objects, unhydrated metadata, and unpublished edits fail before any agent is changed.
This does not create missing tables, refresh lakehouse data, or modify permissions.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][guid]$TenantId,
    [Parameter(Mandatory)][guid]$WorkspaceId,
    [string[]]$AgentName = @(),
    [switch]$Apply,
    [string]$BackupDirectory,
    [ValidateRange(30, 1800)][int]$OperationTimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'data-agent-refresh.ps1')

function Get-DataAgentRefreshHeaders {
    if (-not (Get-Variable -Name RefreshTokenExpiry -Scope Script -ErrorAction SilentlyContinue) -or
        (Get-Date) -ge $script:RefreshTokenExpiry) {
        $tokenJson = & az account get-access-token --tenant $TenantId --resource https://api.fabric.microsoft.com --output json
        if ($LASTEXITCODE -ne 0) { throw 'Azure CLI could not authenticate to Fabric. Run az login in the intended tenant.' }
        $token = ($tokenJson -join "`n") | ConvertFrom-Json
        if ([string]$token.tenant -ne [string]$TenantId) { throw 'Azure CLI returned a token for a different tenant' }
        if ([string]::IsNullOrWhiteSpace($token.accessToken)) { throw 'Azure CLI returned an empty Fabric token' }
        $script:RefreshToken = $token.accessToken
        $script:RefreshTokenExpiry = (Get-Date).AddMinutes(5)
    }
    return @{ Authorization = "Bearer $script:RefreshToken"; 'Content-Type' = 'application/json'; 'x-ms-fabric-skill' = 'hls-data-accelerator-fresh-deploy-audit' }
}

function Invoke-DataAgentRefreshHttp {
    param([Parameter(Mandatory)][string]$Uri, [string]$Method = 'GET', [object]$Body)
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        try {
            $arguments = @{
                Uri = $Uri; Method = $Method; Headers = Get-DataAgentRefreshHeaders
                TimeoutSec = 60; ErrorAction = 'Stop'
            }
            if ($null -ne $Body) {
                $arguments.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 100 -Compress))
            }
            return Invoke-WebRequest @arguments
        } catch {
            $response = $_.Exception.PSObject.Properties['Response']
            $status = if ($response -and $response.Value) { [int]$response.Value.StatusCode } else { 0 }
            $readOnly = $Method -eq 'GET' -or $Uri.EndsWith('/getDefinition')
            if ($attempt -lt 4 -and ($status -eq 429 -or ($readOnly -and $status -in @(408, 500, 502, 503, 504)))) {
                Write-Warning "Fabric HTTP $status for $Method $Uri; retry $attempt/4 in 5 seconds."
                Start-Sleep -Seconds 5
                continue
            }
            throw
        }
    }
}

function Invoke-DataAgentRefreshOperation {
    param([Parameter(Mandatory)][string]$Uri, [object]$Body = @{}, [switch]$ReturnResult)
    $response = Invoke-DataAgentRefreshHttp -Uri $Uri -Method 'POST' -Body $Body
    if ($response.StatusCode -in @(200, 201, 204)) {
        if ($ReturnResult) {
            if (-not $response.Content) { throw "Fabric returned no definition for $Uri" }
            return $response.Content | ConvertFrom-Json -Depth 100
        }
        return
    }
    if ($response.StatusCode -ne 202) { throw "Unexpected Fabric HTTP $($response.StatusCode) for $Uri" }
    $locations = @($response.Headers['Location'])
    if (-not $locations.Count -or -not $locations[0]) { throw "Fabric returned 202 without an operation location for $Uri" }
    $location = [string]$locations[0]
    $operationUri = [uri]$location
    if ($operationUri.Scheme -ne 'https' -or
        ($operationUri.Host -ne 'api.fabric.microsoft.com' -and -not $operationUri.Host.EndsWith('.analysis.windows.net'))) {
        throw "Unexpected Fabric operation host: $($operationUri.Host)"
    }
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt $OperationTimeoutSeconds) {
        Start-Sleep -Seconds 2
        $poll = Invoke-DataAgentRefreshHttp -Uri $location
        $operation = $poll.Content | ConvertFrom-Json -Depth 100
        if ($operation.status -eq 'Succeeded') {
            if ($ReturnResult) {
                $result = Invoke-DataAgentRefreshHttp -Uri "$location/result"
                return $result.Content | ConvertFrom-Json -Depth 100
            }
            return
        }
        if ($operation.status -in @('Failed', 'Cancelled', 'Canceled')) {
            throw "Fabric operation $($operation.status): $($operation | ConvertTo-Json -Depth 10 -Compress)"
        }
    }
    throw "Fabric operation timed out after $OperationTimeoutSeconds seconds: $location. Check its status before retrying a write."
}

function Get-RefreshDataAgentDefinition {
    param([Parameter(Mandatory)][string]$AgentId)
    return Invoke-DataAgentRefreshOperation -Uri "$baseUri/items/$AgentId/getDefinition" -ReturnResult
}

if ($Apply -and [string]::IsNullOrWhiteSpace($BackupDirectory)) { throw '-Apply requires -BackupDirectory' }
$baseUri = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId"
$agents = @()
$uri = "$baseUri/items?type=DataAgent"
do {
    $response = Invoke-DataAgentRefreshHttp -Uri $uri
    $page = $response.Content | ConvertFrom-Json -Depth 100
    $agents += @($page.value)
    $uri = if ($page.PSObject.Properties['continuationUri']) { [string]$page.continuationUri } else { $null }
    if ($uri -and -not $uri.StartsWith("$baseUri/")) { throw "Unexpected Fabric pagination URI: $uri" }
} while ($uri)
foreach ($name in $AgentName) {
    if ($name -notin $agents.displayName) { throw "Data agent not found: $name" }
}
if ($AgentName.Count) { $agents = @($agents | Where-Object { $_.displayName -in $AgentName }) }
if (-not $agents.Count) { throw 'No data agents found in this workspace' }

$plans = @()
foreach ($agent in $agents) {
    Write-Host "Reading $($agent.displayName)..."
    $definition = Get-RefreshDataAgentDefinition -AgentId $agent.id
    try {
        $plan = New-DataAgentRefreshPlan -Definition $definition
    } catch {
        throw "Preflight failed for '$($agent.displayName)': $($_.Exception.Message)"
    }
    $plans += [pscustomobject]@{ Agent = $agent; Before = $definition; Plan = $plan }
    foreach ($contract in $plan.Contracts) {
        Write-Host "  $($contract.Kind): tables=$(@($contract.Tables | ForEach-Object { $_.Name }) -join ', '); functions=$($contract.Functions -join ', ')"
    }
}
Write-Host "Preflight passed for $($plans.Count) agent(s)."
if (-not $Apply) {
    Write-Host 'Read-only: no definitions updated or published. Use -Apply with -BackupDirectory to make changes.'
    return
}

$runId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$([guid]::NewGuid().ToString('N'))"
foreach ($entry in $plans) {
    $agent = $entry.Agent
    if (-not $PSCmdlet.ShouldProcess($agent.displayName, 'Back up, refresh schema selections, and publish')) { continue }
    $current = Get-RefreshDataAgentDefinition -AgentId $agent.id
    if ((Get-DataAgentDefinitionFingerprint -Definition $current) -ne $entry.Plan.Fingerprint) {
        throw "Definition changed after preflight for '$($agent.displayName)'. Rerun preflight; no write was made to this agent."
    }
    $null = New-Item -ItemType Directory -Path $BackupDirectory -Force
    $beforePath = Join-Path $BackupDirectory "$runId-$($agent.id)-before.json"
    $entry.Before | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $beforePath -Encoding utf8NoBOM
    Write-Host "Backup: $beforePath"
    Invoke-DataAgentRefreshOperation -Uri "$baseUri/dataAgents/$($agent.id)/updateDefinition" -Body @{ definition = $entry.Plan.Definition }
    Invoke-DataAgentRefreshOperation -Uri "$baseUri/dataAgents/$($agent.id)/staging/publish" -Body @{
        publishedDescription = "$($agent.displayName) - refreshed schema selections"
    }
    $after = Get-RefreshDataAgentDefinition -AgentId $agent.id
    Assert-DataAgentRefreshDefinition -Definition $after -Plan $entry.Plan
    $after | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $BackupDirectory "$runId-$($agent.id)-after.json") -Encoding utf8NoBOM
    Write-Host "Verified draft and published selections: $($agent.displayName)"
}

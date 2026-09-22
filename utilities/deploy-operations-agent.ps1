#!/usr/bin/env pwsh
# ============================================================================
# deploy-operations-agent.ps1
# Creates a Clinical Deterioration Monitor Operations Agent via Fabric REST API.
#
# This agent monitors real-time Masimo telemetry for sustained vital sign
# deterioration trends (not just single-threshold crossings) and recommends
# clinical escalation actions with patient context.
#
# The script:
#   1. Discovers the workspace and KQL database
#   2. Creates the Operations Agent item via REST API
#   3. Outputs portal configuration steps for goals/instructions/actions
#
# Prerequisites:
#   - az login completed
#   - Eventhouse with TelemetryRaw + AlertHistory tables
#   - Operations Agent preview enabled on Fabric tenant
#   - Copilot and Azure OpenAI Service enabled on tenant
#   - NOT on a trial capacity (Operations Agents require paid capacity)
#
# Usage:
#   .\deploy-operations-agent.ps1
#   .\deploy-operations-agent.ps1 -FabricWorkspaceName "my-workspace"
# ============================================================================

[CmdletBinding()]
param (
    [string]$FabricWorkspaceName = "med-device-rti-hds",
    [string]$AgentName           = "ClinicalDeteriorationMonitor",
    [string]$MessageRecipient    = "",
    [string]$FabricApiBase       = "https://api.fabric.microsoft.com/v1"
)

$ErrorActionPreference = "Stop"

# ============================================================================
# AUTH HELPERS
# ============================================================================

function Get-FabricAccessToken {
    $tokenObj = Get-AzAccessToken -ResourceUrl "https://api.fabric.microsoft.com"
    $rawToken = $tokenObj.Token
    if ($rawToken -is [System.Security.SecureString]) {
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($rawToken)
        try { return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    elseif ($rawToken -is [string]) { return $rawToken }
    else { return $rawToken | ConvertFrom-SecureString -AsPlainText }
}

function ConvertTo-Base64 {
    param ([string]$Text)
    [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text))
}

# ============================================================================
# DISCOVER WORKSPACE + EVENTHOUSE
# ============================================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Operations Agent — Clinical Deterioration Monitor          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# --- Workspace ---
Write-Host "  Discovering workspace..." -ForegroundColor White
$token = Get-FabricAccessToken
$headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }
$workspaces = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces" -Headers $headers).value
$ws = $workspaces | Where-Object { $_.displayName -eq $FabricWorkspaceName }
if (-not $ws) {
    Write-Host "ERROR: Workspace '$FabricWorkspaceName' not found." -ForegroundColor Red
    exit 1
}
$workspaceId = $ws.id
Write-Host "  ✓ Workspace: $FabricWorkspaceName ($workspaceId)" -ForegroundColor Green

# --- Eventhouse ---
$eventhouses = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/eventhouses" -Headers $headers).value
$eventhouse = $eventhouses | Where-Object { $_.displayName -match "Masimo" }
if (-not $eventhouse) { $eventhouse = $eventhouses | Select-Object -First 1 }
if (-not $eventhouse) {
    Write-Host "ERROR: Eventhouse not found. Operations Agent requires an Eventhouse." -ForegroundColor Red
    exit 1
}
if ($eventhouse -is [array]) { $eventhouse = $eventhouse[0] }
Write-Host "  ✓ Eventhouse: $($eventhouse.displayName) ($($eventhouse.id))" -ForegroundColor Green

# --- KQL Database ---
# The data source must be the KQLDatabase item. Binding the Eventhouse item id
# stores a definition the service cannot read back (getDefinition returns 500).
$kqlDbs = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/kqlDatabases" -Headers $headers).value
$kqlDb = $kqlDbs | Where-Object { $_.displayName -eq "MasimoKQLDB" -or $_.displayName -eq $eventhouse.displayName }
if (-not $kqlDb) { $kqlDb = $kqlDbs | Select-Object -First 1 }
if ($kqlDb -is [array]) { $kqlDb = $kqlDb[0] }
if (-not $kqlDb -or [string]::IsNullOrWhiteSpace($kqlDb.id)) {
    throw "No KQL database found in workspace '$FabricWorkspaceName'. Create the Eventhouse KQL database before deploying the operations agent."
}
if ($kqlDb.id -eq $eventhouse.id) {
    throw "Resolved KQL database id matches the Eventhouse item id. The operations agent data source must reference the KQLDatabase item."
}
Write-Host "  ✓ KQL Database: $($kqlDb.displayName) ($($kqlDb.id))" -ForegroundColor Green

# --- Check existing ---
Write-Host ""
Write-Host "  Checking for existing operations agent..." -ForegroundColor White
$existingAgents = $null
try {
    $existingAgents = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/OperationsAgents" -Headers $headers).value
} catch {}
$existing = $existingAgents | Where-Object { $_.displayName -eq $AgentName }
if ($existing) {
    Write-Host "  ✓ Operations Agent '$AgentName' already exists ($($existing.id))." -ForegroundColor Yellow
    $agentId = $existing.id
} else {
    # ============================================================================
    # CREATE OPERATIONS AGENT
    # ============================================================================

    Write-Host ""
    Write-Host "  Creating Operations Agent '$AgentName'..." -ForegroundColor White

    $createBody = '{"displayName":"'+$AgentName+'","description":"Monitors Masimo telemetry for sustained SpO2/PR deterioration trends and recommends clinical escalation."}'

    try {
        $createResp = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/OperationsAgents" `
            -Headers $headers -Method POST -Body $createBody -ErrorAction Stop
        $createStatus = [int]$createResp.StatusCode

        if ($createStatus -eq 201) {
            $result = $createResp.Content | ConvertFrom-Json
            $agentId = $result.id
            Write-Host "  ✓ Created: $($result.displayName) ($agentId)" -ForegroundColor Green
        }
        elseif ($createStatus -eq 202) {
            $opId = $createResp.Headers["x-ms-operation-id"]
            if ($opId -is [array]) { $opId = $opId[0] }
            Write-Host "  Long-running operation ($opId), polling..." -ForegroundColor Gray
            for ($poll = 0; $poll -lt 60; $poll++) {
                Start-Sleep -Seconds 5
                $pH = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }
                $op = Invoke-RestMethod -Uri "$FabricApiBase/operations/$opId" -Headers $pH
                Write-Host "    Status: $($op.status)... ($($poll * 5)s)" -ForegroundColor DarkGray
                if ($op.status -eq "Succeeded") { break }
                if ($op.status -eq "Failed") {
                    $ed = if ($op.error) { $op.error.message } else { "Unknown" }
                    throw "Create failed: $ed"
                }
            }
            # Fetch agent ID
            Start-Sleep 3
            $agents = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/OperationsAgents" `
                -Headers @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }).value
            $created = $agents | Where-Object { $_.displayName -eq $AgentName }
            if ($created -is [array]) { $created = $created[0] }
            $agentId = $created.id
            Write-Host "  ✓ Created: $AgentName ($agentId)" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ✗ Failed to create Operations Agent: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Troubleshooting:" -ForegroundColor Yellow
        Write-Host "    - Operations Agent requires PAID capacity (not trial)" -ForegroundColor White
        Write-Host "    - Ensure 'Operations agent (preview)' is enabled in tenant admin" -ForegroundColor White
        Write-Host "    - Ensure 'Copilot and Azure OpenAI Service' is enabled" -ForegroundColor White
        exit 1
    }
}

# ============================================================================
# CREATE REFLEX (DATA ACTIVATOR) FOR AGENT ACTIONS
# ============================================================================

Write-Host ""
Write-Host "  Creating Data Activator (Reflex) for agent actions..." -ForegroundColor White

$reflexName = "DeteriorationEscalation"
$existingReflex = $null
try {
    $items = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/items" `
        -Headers @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }).value
    $existingReflex = $items | Where-Object { $_.displayName -eq $reflexName -and $_.type -eq "Reflex" }
} catch {}

if ($existingReflex) {
    if ($existingReflex -is [array]) { $existingReflex = $existingReflex[0] }
    $reflexId = $existingReflex.id
    Write-Host "  ✓ Reflex '$reflexName' already exists ($reflexId)" -ForegroundColor Yellow
} else {
    # Create empty Reflex (definition must be configured in portal due to Activator ALM requirements)
    $reflexBody = '{"displayName":"'+$reflexName+'","description":"Data Activator for Clinical Deterioration Monitor - connect to Operations Agent actions.","type":"Reflex"}'

    try {
        $rToken = Get-FabricAccessToken
        $rHeaders = @{ "Authorization" = "Bearer $rToken"; "Content-Type" = "application/json" }
        $rResp = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/items" `
            -Headers $rHeaders -Method POST -Body $reflexBody -ErrorAction Stop
        $rStatus = [int]$rResp.StatusCode

        if ($rStatus -eq 201) {
            $rResult = $rResp.Content | ConvertFrom-Json
            $reflexId = $rResult.id
        } elseif ($rStatus -eq 202) {
            $rOpId = $rResp.Headers["x-ms-operation-id"]
            if ($rOpId -is [array]) { $rOpId = $rOpId[0] }
            Write-Host "  Provisioning..." -ForegroundColor Gray
            for ($poll = 0; $poll -lt 30; $poll++) {
                Start-Sleep -Seconds 5
                $pH = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }
                $op = Invoke-RestMethod -Uri "$FabricApiBase/operations/$rOpId" -Headers $pH
                if ($op.status -ne "Running") { break }
            }
            Start-Sleep 3
            $items2 = (Invoke-RestMethod -Uri "$FabricApiBase/workspaces/$workspaceId/items" `
                -Headers @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }).value
            $reflex = $items2 | Where-Object { $_.displayName -eq $reflexName -and $_.type -eq "Reflex" }
            if ($reflex -is [array]) { $reflex = $reflex[0] }
            $reflexId = $reflex.id
        }
        Write-Host "  ✓ Reflex created: $reflexName ($reflexId)" -ForegroundColor Green
    } catch {
        $errMsg = $_.Exception.Message
        try { $errMsg = ($_.ErrorDetails.Message | ConvertFrom-Json).message } catch {}
        if ($errMsg -match "NotAvailableYet") {
            Write-Host "  ⚠ Name not available yet (recent delete). Waiting..." -ForegroundColor Yellow
            Start-Sleep 45
            try {
                $rResp2 = Invoke-WebRequest -Uri "$FabricApiBase/workspaces/$workspaceId/items" `
                    -Headers @{ "Authorization" = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json" } `
                    -Method POST -Body $reflexBody -ErrorAction Stop
                $rResult2 = $rResp2.Content | ConvertFrom-Json
                $reflexId = $rResult2.id
                Write-Host "  ✓ Reflex created on retry: $reflexName ($reflexId)" -ForegroundColor Green
            } catch {
                Write-Host "  ⚠ Could not create Reflex: $_" -ForegroundColor Yellow
                $reflexId = $null
            }
        } else {
            Write-Host "  ⚠ Could not create Reflex: $errMsg" -ForegroundColor Yellow
            $reflexId = $null
        }
    }
}

# ============================================================================
# PUSH DEFINITION (goals, instructions, data source, actions)
# ============================================================================

Write-Host ""
Write-Host "  Pushing configuration (instructions, knowledge source, message destination)..." -ForegroundColor White

$instructionsText = @'
Monitor Masimo Radius-7 pulse oximeter telemetry in the MasimoEventhouse KQL database and detect sustained clinical deterioration before a patient crosses a critical alert threshold.

Monitored property source: the materialized table agent_deterioration_findings. It is refreshed from agent_DeteriorationTrend(15) and holds exactly one current row per monitored device. Use this table directly; do not recompute trends from raw telemetry, and do not re-filter on signal quality because the source function already discards unreliable readings.

Columns and meaning:
- device_id: Masimo device identifier, pattern MASIMO-RADIUS7-NNNN
- severity: STABLE, WATCH, CONCERN, or ESCALATE
- current_spo2: mean SpO2 over the recent 15-minute window
- baseline_spo2: mean SpO2 over the preceding 60-minute baseline
- spo2_drop: baseline_spo2 minus current_spo2, in percentage points
- current_pr, baseline_pr, pr_rise: recent, baseline, and delta pulse rate in bpm
- pr_stddev: pulse-rate standard deviation over the recent window, in bpm
- multi_metric: 1 when SpO2 is falling and pulse rate is rising together, otherwise 0
- readings: qualifying readings behind the row
- last_reading_utc: UTC timestamp of the newest qualifying reading
- refreshed_at: UTC time the row was materialized

Rules, evaluated per device_id:
- Raise a WATCH finding when spo2_drop is above 1 or pr_stddev is above 10.
- Raise a CONCERN finding when spo2_drop is above 2 or pr_stddev is above 15.
- Raise an ESCALATE finding when spo2_drop is above 4, or pr_stddev is above 25, or multi_metric is 1.
- Do not raise a finding while severity is STABLE.

Reporting:
- Report only rows present in agent_deterioration_findings; never invent a device, patient, or value.
- Always state device_id, severity, current_spo2, baseline_spo2, spo2_drop, pr_stddev, and last_reading_utc as UTC.
- Recommend clinical review for CONCERN and immediate bedside assessment for ESCALATE.
- Never run an action without explicit human approval.
'@

# GA Operations Agent schema contract, verified against the live service:
#   * `goals` was removed in June 2026 — goals belong in `instructions`.
#   * An empty `playbook` object is rejected with
#     "No rule definitions available in the playbook."; omit the key entirely.
#   * Exactly one knowledge source is accepted.
#   * Only `Configurations.json` is required; a `.platform` part carrying an
#     all-zero logicalId is not needed and is not written here.
$configuration = [ordered]@{
    instructions = $instructionsText
    dataSources  = @{ masimoKqlDb = @{ id = $kqlDb.id; type = "KustoDatabase"; workspaceId = $workspaceId } }
    actions      = @{}
}
if (-not [string]::IsNullOrWhiteSpace($MessageRecipient)) {
    $configuration['messageDestination'] = @{ kind = "Recipient"; recipient = $MessageRecipient }
}
$opsConfig = [ordered]@{
    "`$schema"    = "https://developer.microsoft.com/json-schemas/fabric/item/operationsAgents/definition/1.0.0/schema.json"
    configuration = $configuration
    shouldRun     = $false
}
$configJson = $opsConfig | ConvertTo-Json -Depth 30

# Build the update definition body
$updateBody = '{"definition":{"format":"OperationsAgentV1","parts":[{"path":"Configurations.json","payload":"'+(ConvertTo-Base64 $configJson)+'","payloadType":"InlineBase64"}]}}'

$updateToken = Get-FabricAccessToken
$updateHeaders = @{ "Authorization" = "Bearer $updateToken"; "Content-Type" = "application/json" }
$updateUri = "$FabricApiBase/workspaces/$workspaceId/OperationsAgents/$agentId/updateDefinition?updateMetadata=True"

try {
    $updateResp = Invoke-WebRequest -Uri $updateUri -Headers $updateHeaders -Method POST -Body $updateBody -ErrorAction Stop
    $updateStatus = [int]$updateResp.StatusCode

    if ($updateStatus -eq 202) {
        $updateOpId = $updateResp.Headers["x-ms-operation-id"]
        if ($updateOpId -is [array]) { $updateOpId = $updateOpId[0] }
        Write-Host "  Long-running operation ($updateOpId), polling..." -ForegroundColor Gray
        for ($poll = 0; $poll -lt 30; $poll++) {
            Start-Sleep -Seconds 5
            $pH = @{ "Authorization" = "Bearer $(Get-FabricAccessToken)" }
            $op = Invoke-RestMethod -Uri "$FabricApiBase/operations/$updateOpId" -Headers $pH
            Write-Host "    Status: $($op.status)... ($($poll * 5)s)" -ForegroundColor DarkGray
            if ($op.status -eq "Succeeded") { break }
            if ($op.status -eq "Failed") {
                $ed = if ($op.error) { $op.error.message } else { "Unknown" }
                throw "Definition update failed: $ed"
            }
        }
    }
    Write-Host "  ✓ Configuration pushed successfully" -ForegroundColor Green
} catch {
    throw "Failed to push the operations agent configuration: $_"
}

# ============================================================================
# DONE
# ============================================================================

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║  ✓ Operations Agent deployed!                        ║" -ForegroundColor Green
Write-Host "  ╚═══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Agent: $AgentName" -ForegroundColor White
Write-Host "  ID:    $agentId" -ForegroundColor White
Write-Host ""
Write-Host "  Configuration:" -ForegroundColor Cyan
Write-Host "    Instructions: Deterioration monitoring over agent_deterioration_findings" -ForegroundColor White
Write-Host "    Data source:  $($kqlDb.displayName) (KQL Database $($kqlDb.id))" -ForegroundColor White
Write-Host "    Destination:  $(if ([string]::IsNullOrWhiteSpace($MessageRecipient)) { 'Teams default (no recipient supplied)' } else { $MessageRecipient })" -ForegroundColor White
Write-Host "    Status:       Inactive (start manually when ready)" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    1. Open the agent in the Fabric portal" -ForegroundColor White
Write-Host "    2. Select Generate Playbook and review the properties and rules" -ForegroundColor White
Write-Host "    3. Click START to activate the agent" -ForegroundColor White
Write-Host "    4. Install 'Fabric Operations Agent' Teams app to receive messages" -ForegroundColor White
Write-Host "    Optional: attach the '$reflexName' Reflex only if you add a custom action" -ForegroundColor Gray

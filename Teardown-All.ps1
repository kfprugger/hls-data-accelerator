<#
.SYNOPSIS
    Tear down one deployment and its owned front ends through the shared teardown CLI.
.DESCRIPTION
    Always discovers and prints a read-only plan first. Deletion includes the Fabric workspace,
    Rayfin apps, deployment-bound connections and Unity Catalog objects, the main Azure resource
    group, and owned cardiology and DICOM viewer front ends. Shared or
    unrelated front ends are skipped with reasons. Azure deletion waits for completion.
    Tokens are pinned to the deployment subscription, never the Azure CLI default.
.PARAMETER FabricWorkspaceName
    Fabric workspace name; defaults from the deployment state file.
.PARAMETER ResourceGroupName
    Main Azure resource group; defaults from the deployment state file, with no hardcoded fallback.
.PARAMETER SubscriptionId
    Deployment subscription. Required unless HLS_SUBSCRIPTION_ID or deployment state supplies it.
.PARAMETER ExpectedTenantId
    Refuse before deleting anything if the subscription belongs to a different tenant.
.PARAMETER FrontEndResourceGroup
    Explicit front-end resource groups. Each must still be tied to this deployment.
.PARAMETER DicomViewerResourceGroup
    Optional DICOM viewer resource group, passed as an explicit front-end resource group.
.PARAMETER NoFrontEndDiscovery
    Disable automatic front-end resource group discovery; explicit groups are still checked.
.PARAMETER SkipAzure
    Omit main Azure resource group deletion. Review front-end actions in the plan.
.PARAMETER SkipFabric
    Omit Fabric workspace deletion. Review connection and front-end actions in the plan.
.PARAMETER Force
    Skip the confirmation prompt, but not the read-only plan or ownership checks.
.PARAMETER Plan
    Print the read-only plan and exit without prompting, deleting resources or removing state.
.EXAMPLE
    .\Teardown-All.ps1 -FabricWorkspaceName "my-workspace" -ResourceGroupName "my-rg" `
        -SubscriptionId "<subscription-id>" -ExpectedTenantId "<tenant-id>" -Plan
.EXAMPLE
    .\Teardown-All.ps1 -FabricWorkspaceName "my-workspace" -ResourceGroupName "my-rg" `
        -SubscriptionId "<subscription-id>" -FrontEndResourceGroup "my-cardio-rg" -Force
#>
param(
    [string]$FabricWorkspaceName,
    [string]$ResourceGroupName,
    [string]$SubscriptionId,
    [string]$ExpectedTenantId,
    [string[]]$FrontEndResourceGroup = @(),
    [string]$DicomViewerResourceGroup,
    [switch]$NoFrontEndDiscovery,
    [switch]$SkipAzure,
    [switch]$SkipFabric,
    [switch]$Force,
    [switch]$Plan
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$ScriptDir = $PSScriptRoot
$orchestratorDir = Join-Path $ScriptDir "orchestrator"
$stateDir = if ($env:HLS_STATE_DIR) { $env:HLS_STATE_DIR } elseif ($env:HLS_DATA_DIR) { Join-Path $env:HLS_DATA_DIR "state-tracking" } else { Join-Path $ScriptDir "state-tracking" }
$stateFile = $null
$stateCandidates = @()
if ($FabricWorkspaceName) {
    $stateCandidates += Join-Path $stateDir ".deployment-state-$FabricWorkspaceName.json"
    $stateCandidates += Join-Path $ScriptDir ".deployment-state-$FabricWorkspaceName.json"
}
$stateCandidates += Join-Path $ScriptDir ".deployment-state.json"
$stateFile = $stateCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $SubscriptionId) { $SubscriptionId = $env:HLS_SUBSCRIPTION_ID }
if ($stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $lastPhase = $state.phases | Select-Object -Last 1
    $stateWorkspace = [string]$lastPhase.resources.FabricWorkspaceName
    if ($FabricWorkspaceName -and $stateWorkspace -and $stateWorkspace -ne $FabricWorkspaceName) {
        # Never mix another deployment's resource group or subscription into this teardown.
        Write-Host "Ignoring $stateFile (it records workspace '$stateWorkspace', not '$FabricWorkspaceName')." -ForegroundColor Yellow
        $stateFile = $null
        $lastPhase = $null
        $state = $null
    }
}
if ($stateFile) {
    if (-not $FabricWorkspaceName) { $FabricWorkspaceName = $lastPhase.resources.FabricWorkspaceName }
    if (-not $ResourceGroupName) { $ResourceGroupName = $lastPhase.resources.ResourceGroupName }
    if (-not $SubscriptionId) {
        $SubscriptionId = @(
            $lastPhase.resources.SubscriptionId
            $lastPhase.resources.ExpectedSubscriptionId
            $state.SubscriptionId
            $state.ExpectedSubscriptionId
            $state.subscription_id
        ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
    }
}

foreach ($required in @("FabricWorkspaceName", "ResourceGroupName", "SubscriptionId")) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $required -ValueOnly))) {
        Write-Host "Refused: -$required is required (no deployment state or explicit default supplies it)." -ForegroundColor Red
        exit 2
    }
}

$python = $null
$pythonPrefix = @()
foreach ($relative in @(".venv/bin/python", ".venv/Scripts/python.exe")) {
    $candidate = Join-Path $orchestratorDir $relative
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $python = $candidate; break }
}
if (-not $python) {
    foreach ($name in @("python3", "py", "python")) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            $python = $command.Source
            if ($name -eq "py") { $pythonPrefix = @("-3") }
            break
        }
    }
}
if (-not $python) { throw "Python is required: create orchestrator/.venv or install Python 3." }

$cliArgs = @("-u", "-m", "shared.full_teardown", "--subscription", $SubscriptionId,
    "--workspace", $FabricWorkspaceName, "--resource-group", $ResourceGroupName)
if ($ExpectedTenantId) { $cliArgs += @("--expected-tenant", $ExpectedTenantId) }
foreach ($group in @($FrontEndResourceGroup) + @($DicomViewerResourceGroup)) {
    if (-not [string]::IsNullOrWhiteSpace($group)) { $cliArgs += @("--front-end-resource-group", $group) }
}
if ($NoFrontEndDiscovery) { $cliArgs += "--no-front-end-discovery" }
if (-not $SkipFabric) { $cliArgs += "--delete-workspace" }
if (-not $SkipAzure) { $cliArgs += "--delete-resource-group" }

function Invoke-SharedTeardown {
    param([switch]$PlanOnly)
    $arguments = $pythonPrefix + $cliArgs
    if ($PlanOnly) { $arguments += "--plan" }
    $result = $null
    & $python @arguments | ForEach-Object {
        $line = [string]$_
        Write-Host $line
        if ($line.StartsWith("RESULT: ")) { $result = $line.Substring(8) | ConvertFrom-Json }
    }
    $code = $LASTEXITCODE
    return @{ ExitCode = $code; Result = $result }
}

function Write-TeardownSummary {
    param($Result)
    if (-not $Result) { Write-Host "No RESULT summary was returned."; return }
    if ($Result.planOnly) {
        Write-Host "Plan only: no resources deleted; deployment state retained."
    } else {
        Write-Host "Teardown status: $($Result.status)"
    }
    foreach ($kind in $Result.deleted.PSObject.Properties) {
        Write-Host "Deleted $($kind.Name):"
        foreach ($item in $kind.Value) { Write-Host "  $item" }
    }
    foreach ($frontEnd in $Result.plan.front_ends) {
        if (-not $frontEnd.delete) { Write-Host "Skipped front end '$($frontEnd.name)': $($frontEnd.skip_reason)" }
    }
    foreach ($failure in $Result.failures) { Write-Host "Failure: $failure" -ForegroundColor Red }
    if ($Result.reason) { Write-Host "Refused: $($Result.reason)" -ForegroundColor Red }
}

Push-Location $orchestratorDir
try {
    $preview = Invoke-SharedTeardown -PlanOnly
    if ($preview.ExitCode -ne 0 -or $Plan) {
        Write-TeardownSummary $preview.Result
        exit $preview.ExitCode
    }
    if (-not $Force -and (Read-Host "Delete the resources in this plan? Type yes to continue") -cne "yes") {
        Write-Host "Cancelled: nothing deleted; deployment state retained."
        exit 0
    }
    $execution = Invoke-SharedTeardown
    Write-TeardownSummary $execution.Result
    if ($execution.ExitCode -eq 0) {
        $cleanupPaths = @(
            (Join-Path $stateDir ".deployment-state-$FabricWorkspaceName.json")
            (Join-Path $ScriptDir ".deployment-state-$FabricWorkspaceName.json")
        )
        if ($stateFile) { $cleanupPaths += $stateFile }
        foreach ($path in $cleanupPaths | Select-Object -Unique) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
                Write-Host "Removed deployment state: $path"
            }
        }
    }
    exit $execution.ExitCode
} finally {
    Pop-Location
}

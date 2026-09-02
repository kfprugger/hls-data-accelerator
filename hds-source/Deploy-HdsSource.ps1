[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$FabricWorkspaceName,

    [string]$WorkspaceId = "",

    [switch]$ValidateOnly,

    [switch]$ContractOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$orchestratorRoot = Join-Path $repoRoot "orchestrator"
$pythonCandidates = @(
    (Join-Path $orchestratorRoot ".venv/bin/python"),
    (Join-Path $orchestratorRoot ".venv/Scripts/python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1

if (-not $python) {
    throw "HDS source deployment requires orchestrator/.venv. Run: pwsh -NoProfile -File ./setup-prereqs.ps1"
}

& $python -c "import requests; import azure.identity" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "orchestrator/.venv is incomplete. Run: pwsh -NoProfile -File ./setup-prereqs.ps1"
}

$arguments = @("-m", "activities.deploy_hds_source", "--workspace", $FabricWorkspaceName)
if ($WorkspaceId) {
    $arguments += @("--workspace-id", $WorkspaceId)
}
if ($ValidateOnly) {
    $arguments += "--validate-only"
}
if ($ContractOnly) {
    $arguments += "--contract-only"
}

Push-Location $orchestratorRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

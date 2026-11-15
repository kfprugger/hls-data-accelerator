$ErrorActionPreference = "Stop"

$deployScript = Join-Path $PSScriptRoot "Deploy-All.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($deployScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "Deploy-All.ps1 has parse errors: $($parseErrors[0].Message)"
}


foreach ($functionName in @("Start-HdsSourceDeployment", "Wait-HdsSourceDeployment", "Start-PayerScaffoldDeployment", "Wait-PayerScaffoldDeployment")) {
    $functionAst = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName
    }, $true)
    if (-not $functionAst) { throw "Function '$functionName' was not found in Deploy-All.ps1" }
    Invoke-Expression $functionAst.Extent.Text
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "parallel-hds-$([guid]::NewGuid())"
$hdsRoot = Join-Path $tempRoot "hds-source"
New-Item -ItemType Directory -Path $hdsRoot -Force | Out-Null
$script:ScriptDir = $tempRoot
$script:hdsSourceJob = $null
$script:hdsSourceTimer = $null
$script:payerScaffoldJob = $null
$script:payerScaffoldTimer = $null

try {
    $fakeHds = Join-Path $hdsRoot "Deploy-HdsSource.ps1"
    @'
param([string]$FabricWorkspaceName, [string]$WorkspaceId)
$root = Split-Path -Parent $PSScriptRoot
Set-Content -Path (Join-Path $root "started") -Value "$FabricWorkspaceName|$WorkspaceId"
while (-not (Test-Path (Join-Path $root "release"))) { Start-Sleep -Milliseconds 50 }
Write-Output "@@HDS_SOURCE|contract|succeeded|parallel test@@"
exit 0
'@ | Set-Content -Path $fakeHds

    Start-HdsSourceDeployment -WorkspaceName "workspace" -WorkspaceId "workspace-id"
    if (-not $script:hdsSourceJob) { throw "Parallel HDS start did not retain a job handle." }

    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path (Join-Path $tempRoot "started")) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 50
    }
    if (-not (Test-Path (Join-Path $tempRoot "started")) ) {
        throw "Parallel HDS job did not begin independently."
    }

    Set-Content -Path (Join-Path $tempRoot "release") -Value "continue"
    $null = Wait-HdsSourceDeployment
    if ($script:hdsSourceJob) { throw "Parallel HDS wait did not clear the completed job handle." }

    Remove-Item (Join-Path $tempRoot "started"), (Join-Path $tempRoot "release") -Force
    @'
param([string]$FabricWorkspaceName, [string]$WorkspaceId)
throw "synthetic HDS failure"
'@ | Set-Content -Path $fakeHds

    Start-HdsSourceDeployment -WorkspaceName "workspace" -WorkspaceId "workspace-id"
    try {
        $null = Wait-HdsSourceDeployment
        throw "Parallel HDS failure was not propagated."
    } catch {
        if ($_.Exception.Message -notlike "*synthetic HDS failure*") {
            throw "Parallel HDS propagated the wrong failure: $($_.Exception.Message)"
        }
    }

    $payerRoot = Join-Path $tempRoot "phase-7"
    New-Item -ItemType Directory -Path $payerRoot -Force | Out-Null
    $fakePayer = Join-Path $payerRoot "deploy-payer-rti.ps1"
    @'
param(
    [string]$FabricWorkspaceName,
    [string]$ResourceGroupName,
    [string]$Location,
    [string]$PayerOpsEmail,
    [int]$ClaimEventRatePerMinute,
    [hashtable]$Tags,
    [string]$ExpectedTenantId,
    [string]$ExpectedSubscriptionId,
    [switch]$SkipPayerRti,
    [switch]$SkipPayerActivator,
    [switch]$SkipOpsAgent,
    [switch]$SkipGraphAgent,
    [switch]$SkipClaimEmulator,
    [switch]$SkipSnapshotMaterialization
)
$root = Split-Path -Parent $PSScriptRoot
Set-Content -Path (Join-Path $root "payer-started") -Value "started"
while (-not (Test-Path (Join-Path $root "payer-release"))) { Start-Sleep -Milliseconds 50 }
exit 0
'@ | Set-Content -Path $fakePayer

    $payerArgs = @{
        FabricWorkspaceName = "workspace"
        ResourceGroupName = "resource-group"
        Location = "westus3"
        PayerOpsEmail = "payer@example.test"
        ClaimEventRatePerMinute = 120
        Tags = @{}
        ExpectedTenantId = "tenant"
        ExpectedSubscriptionId = "subscription"
        SkipClaimEmulator = $true
        SkipSnapshotMaterialization = $true
    }
    Start-PayerScaffoldDeployment -Arguments $payerArgs
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path (Join-Path $tempRoot "payer-started")) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 50
    }
    if (-not (Test-Path (Join-Path $tempRoot "payer-started"))) {
        throw "Parallel payer job did not begin independently."
    }
    Set-Content -Path (Join-Path $tempRoot "payer-release") -Value "continue"
    $null = Wait-PayerScaffoldDeployment
    if ($script:payerScaffoldJob) { throw "Scaffolding payer wait did not clear the completed job handle." }

    Remove-Item (Join-Path $tempRoot "payer-started"), (Join-Path $tempRoot "payer-release") -Force
    @'
param([Parameter(ValueFromRemainingArguments=$true)]$Remaining)
throw "synthetic payer failure"
'@ | Set-Content -Path $fakePayer
    Start-PayerScaffoldDeployment -Arguments $payerArgs
    try {
        $null = Wait-PayerScaffoldDeployment
        throw "Parallel scaffolding payer failure was not propagated."
    } catch {
        if ($_.Exception.Message -notlike "*synthetic payer failure*") {
            throw "Parallel scaffolding payer propagated the wrong failure: $($_.Exception.Message)"
        }
    }

    Write-Host "Parallel HDS deployment tests passed."
} finally {
    if ($script:hdsSourceJob) {
        Stop-Job -Job $script:hdsSourceJob -ErrorAction SilentlyContinue
        Remove-Job -Job $script:hdsSourceJob -Force -ErrorAction SilentlyContinue
    }
    if ($script:payerScaffoldJob) {
        Stop-Job -Job $script:payerScaffoldJob -ErrorAction SilentlyContinue
        Remove-Job -Job $script:payerScaffoldJob -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

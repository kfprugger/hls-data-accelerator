$ErrorActionPreference = "Stop"

$deployScript = Join-Path $PSScriptRoot "Deploy-All.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($deployScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "Deploy-All.ps1 has parse errors: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Get-P5FabricHttpError", "Test-P5FabricTransientError")) {
    $functionAst = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName
    }, $true)
    if (-not $functionAst) { throw "Function '$functionName' was not found in Deploy-All.ps1" }
    Invoke-Expression $functionAst.Extent.Text
}

function Assert-Equal {
    param(
        [Parameter(Mandatory)]$Expected,
        [Parameter(Mandatory)]$Actual,
        [Parameter(Mandatory)][string]$Message
    )
    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

$bareForbidden = [pscustomobject]@{
    ErrorDetails = [pscustomobject]@{ Message = "" }
    Exception = [pscustomobject]@{
        Message = "Response status code does not indicate success: 403 (Forbidden)."
        Response = $null
    }
}
$bareForbiddenInfo = Get-P5FabricHttpError -ErrorRecord $bareForbidden
Assert-Equal 403 ([int]$bareForbiddenInfo.StatusCode) "Message-only Fabric 403 should parse status code."
if (-not (Test-P5FabricTransientError -StatusCode $bareForbiddenInfo.StatusCode -ErrorText $bareForbiddenInfo.Text)) {
    throw "Message-only Fabric 403 should be retried because Fabric often omits the inbound-policy response body."
}

$policyForbidden = [pscustomobject]@{
    ErrorDetails = [pscustomobject]@{ Message = '{"errorCode":"RequestDeniedByInboundPolicy","message":"Request is denied due to inbound communication policy."}' }
    Exception = [pscustomobject]@{
        Message = "Forbidden"
        Response = [pscustomobject]@{ StatusCode = 403 }
    }
}
$policyForbiddenInfo = Get-P5FabricHttpError -ErrorRecord $policyForbidden
Assert-Equal 403 ([int]$policyForbiddenInfo.StatusCode) "Response-backed Fabric 403 should parse status code."
if (-not (Test-P5FabricTransientError -StatusCode $policyForbiddenInfo.StatusCode -ErrorText $policyForbiddenInfo.Text)) {
    throw "Fabric RequestDeniedByInboundPolicy 403 should be retried."
}

if (-not (Test-P5FabricTransientError -StatusCode 429 -ErrorText "")) {
    throw "Fabric 429 throttling should be retried."
}

if (Test-P5FabricTransientError -StatusCode 403 -ErrorText "AuthorizationFailed: principal lacks required workspace permission.") {
    throw "Non-policy authorization 403 should not be classified as transient."
}


$deployText = Get-Content $deployScript -Raw
if ($deployText -notmatch 'Invoke-P5PowerBiRest\s+-Uri\s+\$dsUrl') {
    throw "Quality report datasource lookup should use the Power BI retry wrapper."
}
if ($deployText -notmatch 'Invoke-P5PowerBiWeb\s+-Method\s+PATCH\s+-Uri\s+\$patchUrl') {
    throw "Quality report datasource credential patch should use the Power BI retry wrapper."
}
if ($deployText -match 'datasets/429bede8-09bc-4806-b5db-40a1a79341d2') {
    throw "Quality report operations must not use a hard-coded dataset id."
}
if ($deployText -notmatch 'datasets/\$qualityDatasetId') {
    throw "Quality report operations should use the dynamically resolved dataset id."
}
Write-Host "Phase 6 Fabric retry tests passed."

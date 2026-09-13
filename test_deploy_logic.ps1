$scriptPath = Join-Path $PSScriptRoot "phase-1/deploy-fhir.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$tokens,
    [ref]$parseErrors
)

if ($parseErrors.Count -gt 0) {
    throw "deploy-fhir.ps1 has parse errors: $($parseErrors.Message -join '; ')"
}

$parameterNames = @($ast.ParamBlock.Parameters | ForEach-Object {
    $_.Name.VariablePath.UserPath
})
$requiredParameters = @(
    "ResourceGroupName",
    "Location",
    "ReusePatients",
    "ReseedData",
    "SourceResourceGroup",
    "ExpectedSubscriptionId"
)
$missingParameters = @($requiredParameters | Where-Object { $_ -notin $parameterNames })
if ($missingParameters.Count -gt 0) {
    throw "deploy-fhir.ps1 CLI contract is missing parameters: $($missingParameters -join ', ')"
}

Write-Output "deploy-fhir.ps1 CLI contract tests passed."

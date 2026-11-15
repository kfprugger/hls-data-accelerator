$ErrorActionPreference = 'Stop'

$scripts = @(
    "phase-1/deploy-fhir.ps1",
    "Deploy-All.ps1",
    "Preflight-Check.ps1"
)

$failedScripts = @()

foreach ($relPath in $scripts) {
    $scriptPath = Join-Path $PSScriptRoot $relPath
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        Write-Error "[$relPath] Script file not found: $scriptPath" -ErrorAction Continue
        $failedScripts += $relPath
        continue
    }

    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $scriptPath,
        [ref]$tokens,
        [ref]$parseErrors
    )

    if ($parseErrors -and $parseErrors.Count -gt 0) {
        $failedScripts += $relPath
        Write-Error "PowerShell syntax check FAILED: $relPath ($($parseErrors.Count) error(s)):" -ErrorAction Continue
        foreach ($err in $parseErrors) {
            Write-Error "  Line $($err.Extent.StartLineNumber), Col $($err.Extent.StartColumnNumber): $($err.Message)" -ErrorAction Continue
        }
    } else {
        Write-Output "PowerShell syntax check passed: $relPath"
    }
}

if ($failedScripts.Count -gt 0) {
    throw "PowerShell syntax check failed for: $($failedScripts -join ', ')"
}

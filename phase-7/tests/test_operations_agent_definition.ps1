$ErrorActionPreference = 'Stop'

# Guards the GA Operations Agent definition contract that regressed silently in
# med-0906: an empty `playbook` object is rejected by the live service with
# "No rule definitions available in the playbook.", a second knowledge source is
# rejected with "The agent setup only supports a single knowledge source.", and
# the removed `goals` property leaves the stored definition unreadable.

$scriptPath = Join-Path $PSScriptRoot '../deploy-payer-rti.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "deploy-payer-rti.ps1 has parse errors: $($parseErrors[0].Message)"
}

$functionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'New-OperationsAgentDefinition'
}, $true)
if (-not $functionAst) { throw "Function 'New-OperationsAgentDefinition' was not found in deploy-payer-rti.ps1" }
Invoke-Expression $functionAst.Extent.Text

function Assert-True {
    param([bool]$Value, [string]$Message)
    if (-not $Value) { throw $Message }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -ne $Actual) { throw "$Message Expected '$Expected', got '$Actual'." }
}

$kqlDbId = '11111111-2222-4333-8444-555555555555'
$workspaceId = '66666666-7777-4888-9999-aaaaaaaaaaaa'
$instructions = 'Monitor agent_ops_stream_health and raise a finding when age_minutes exceeds its threshold.'

$withRecipient = New-OperationsAgentDefinition -Instructions $instructions -KqlDatabaseId $kqlDbId -WorkspaceId $workspaceId -Recipient 'ops@contoso.com'
$roundTripped = $withRecipient | ConvertTo-Json -Depth 30 | ConvertFrom-Json

Assert-True (-not $roundTripped.PSObject.Properties.Name.Contains('playbook')) 'Definition must omit playbook; an empty playbook object is rejected by the service.'
Assert-True (-not $roundTripped.configuration.PSObject.Properties.Name.Contains('goals')) 'Definition must omit the deprecated goals property.'

$sources = @($roundTripped.configuration.dataSources.PSObject.Properties)
Assert-Equal 1 $sources.Count 'Definition must bind exactly one knowledge source.'
Assert-Equal 'KustoDatabase' $sources[0].Value.type 'Knowledge source must be a KustoDatabase.'
Assert-Equal $kqlDbId $sources[0].Value.id 'Knowledge source must carry the supplied KQL database id.'
Assert-Equal $workspaceId $sources[0].Value.workspaceId 'Knowledge source must carry the supplied workspace id.'

Assert-Equal 'Recipient' $roundTripped.configuration.messageDestination.kind 'Supplied recipient must produce a Recipient message destination.'
Assert-Equal 'ops@contoso.com' $roundTripped.configuration.messageDestination.recipient 'Recipient UPN must round-trip.'
Assert-Equal $instructions $roundTripped.configuration.instructions 'Instructions must round-trip unchanged.'
Assert-Equal $false $roundTripped.shouldRun 'Agent must be deployed stopped so the playbook is reviewed before it runs.'

$withoutRecipient = New-OperationsAgentDefinition -Instructions $instructions -KqlDatabaseId $kqlDbId -WorkspaceId $workspaceId |
    ConvertTo-Json -Depth 30 | ConvertFrom-Json
Assert-True (-not $withoutRecipient.configuration.PSObject.Properties.Name.Contains('messageDestination')) 'Omitting the recipient must omit messageDestination rather than emit an empty destination.'

Write-Host 'Operations Agent definition contract tests passed.' -ForegroundColor Green

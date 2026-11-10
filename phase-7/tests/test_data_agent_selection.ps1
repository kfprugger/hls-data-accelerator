$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '../../utilities/data-agent-selection.ps1')

function Assert-True {
    param([bool]$Value, [string]$Message)
    if (-not $Value) { throw $Message }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -ne $Actual) { throw "$Message Expected '$Expected', got '$Actual'." }
}

$targetTables = @('fact_claim', 'dim_payer', 'care_gaps', 'agg_high_cost_claimants', 'readmission_risk_scores')
function New-Column([string]$Name) {
    return [pscustomobject]@{ id = [guid]::NewGuid().ToString(); display_name = $Name; type = 'lakehouse_tables.column'; is_selected = $true; children = @() }
}
function New-Table([string]$Name) {
    return [pscustomobject]@{
        id = [guid]::NewGuid().ToString()
        display_name = $Name
        type = 'lakehouse_tables.table'
        is_selected = $false
        children = @((New-Column 'patient_id'), (New-Column 'value'))
    }
}

$tablesNode = [pscustomobject]@{
    id = [guid]::NewGuid().ToString()
    display_name = 'Tables'
    type = 'table_grouping'
    is_selected = $false
    children = @($targetTables | ForEach-Object { New-Table $_ }) + @((New-Table 'agg_utilization_summary'))
}
$dboNode = [pscustomobject]@{
    id = [guid]::NewGuid().ToString()
    display_name = 'dbo'
    type = 'lakehouse_tables.schema'
    is_selected = $false
    children = @($tablesNode)
}
$root = [pscustomobject]@{
    id = [guid]::NewGuid().ToString()
    display_name = 'Schemas'
    type = 'schema_grouping'
    is_selected = $false
    children = @($dboNode)
}

$null = Update-DataAgentLakehouseElementSelection -Node $root -TargetTables $targetTables
$selected = @(Get-SelectedDataAgentTables -Elements @($root) -SelectionKind 'lakehouse')
Assert-True $root.is_selected 'Schemas grouping should be selected when it contains selected tables.'
Assert-True $dboNode.is_selected 'dbo schema should be selected when it contains selected tables.'
Assert-True $tablesNode.is_selected 'Tables grouping should be selected when it contains selected tables.'
Assert-Equal -Expected (($targetTables | Sort-Object) -join ',') -Actual ($selected -join ',') -Message 'Hydrated tree should select exactly the requested Gold tables.'
foreach ($table in @($tablesNode.children)) {
    $expected = $targetTables -contains $table.display_name
    Assert-Equal -Expected $expected -Actual $table.is_selected -Message "Table '$($table.display_name)' selection mismatch."
    foreach ($column in @($table.children)) {
        Assert-Equal -Expected $expected -Actual $column.is_selected -Message "Column '$($column.display_name)' should follow its table selection."
    }
}

$kustoTargets = @('TelemetryRaw', 'AlertHistory', 'claims_events', 'fraud_scores', 'highcost_alerts', 'care_gap_alerts')
$kustoRoot = [pscustomobject]@{
    id = [guid]::NewGuid().ToString()
    display_name = 'Tables'
    type = 'table_grouping'
    is_selected = $false
    children = @($kustoTargets + 'unused_table' | ForEach-Object {
        [pscustomobject]@{
            id = [guid]::NewGuid().ToString()
            display_name = $_
            type = 'kusto.table'
            is_selected = $false
            children = @([pscustomobject]@{ id = 'value'; display_name = 'value'; type = 'kusto.column'; is_selected = $true; children = @() })
        }
    })
}
$kustoFunctions = @('fn_FraudRisk', 'agent_PayerOpsWorklist')
$functionRoot = [pscustomobject]@{
    id = [guid]::NewGuid().ToString()
    display_name = 'Functions'
    type = 'function_grouping'
    is_selected = $false
    children = @($kustoFunctions + 'unused_function' | ForEach-Object {
        [pscustomobject]@{ id = [guid]::NewGuid().ToString(); display_name = $_; type = 'kusto.function'; is_selected = $false; children = @() }
    })
}
$null = Update-DataAgentKustoElementSelection -Node $kustoRoot -TargetTables $kustoTargets -TargetFunctions $kustoFunctions
$selectedKusto = @(Get-SelectedDataAgentTables -Elements @($kustoRoot) -SelectionKind 'kusto')
Assert-True $kustoRoot.is_selected 'Kusto Tables grouping should be selected when it contains selected tables.'
Assert-Equal -Expected (($kustoTargets | Sort-Object) -join ',') -Actual ($selectedKusto -join ',') -Message 'Hydrated Kusto tree should select exactly the requested Eventhouse tables.'
foreach ($table in @($kustoRoot.children)) {
    $expected = $kustoTargets -contains $table.display_name
    Assert-Equal -Expected $expected -Actual $table.is_selected -Message "Kusto table '$($table.display_name)' selection mismatch."
    Assert-Equal -Expected $expected -Actual $table.children[0].is_selected -Message "Kusto column should follow table '$($table.display_name)' selection."
}
$null = Update-DataAgentKustoElementSelection -Node $functionRoot -TargetTables $kustoTargets -TargetFunctions $kustoFunctions
$selectedFunctions = @(Get-SelectedDataAgentFunctions -Elements @($functionRoot))
Assert-True $functionRoot.is_selected 'Kusto Functions grouping should be selected when it contains selected functions.'
Assert-Equal -Expected (($kustoFunctions | Sort-Object) -join ',') -Actual ($selectedFunctions -join ',') -Message 'Hydrated Kusto tree should select exactly the requested functions.'
foreach ($function in @($functionRoot.children)) {
    Assert-Equal -Expected ($kustoFunctions -contains $function.display_name) -Actual $function.is_selected -Message "Kusto function '$($function.display_name)' selection mismatch."
}

# A datasource whose cached schema lacks a target table is detached and re-imported exactly once.
$deployScript = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '../deploy-payer-rti.ps1'), [ref]$null, [ref]$null)
foreach ($functionName in @('ConvertTo-Base64', 'Get-ErrorMessage', 'Deploy-DataAgent')) {
    $definition = $deployScript.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName }, $true)
    Assert-True ($null -ne $definition) "deploy-payer-rti.ps1 must define $functionName."
    . ([scriptblock]::Create($definition.Extent.Text))
}
$staleId = '1ab47b0f-2e91-4e78-8148-c7541799f596'
$script:apiCalls = [System.Collections.ArrayList]@()
$script:definitionUpdates = 0
$script:staleFailuresLeft = 1
function Invoke-FabricApi {
    param([string]$Method = 'GET', [string]$Endpoint, [object]$Body = $null)
    $null = $script:apiCalls.Add("$Method $Endpoint")
    if ($Method -eq 'GET') { return [pscustomobject]@{ value = @([pscustomobject]@{ displayName = 'Payer Ops Triage'; id = 'agent-1' }) } }
}
function Update-DataAgentDefinition { param([string]$WorkspaceId, [string]$DataAgentId, [object]$Definition) $script:definitionUpdates++ }
function Publish-DataAgentDefinition { param([string]$WorkspaceId, [string]$DataAgentId, [string]$Description) }
function Set-DataAgentNativeSchemaSelection {
    param([string]$WorkspaceId, [string]$DataAgentId, [string]$DatasourceId, [string[]]$Tables, [string[]]$Functions, [scriptblock]$InvokeApi, [switch]$VerifyOnly, [switch]$Published)
    if (-not $VerifyOnly -and $script:staleFailuresLeft -gt 0) {
        $script:staleFailuresLeft--
        throw "Missing, ambiguous, or unavailable native Table 'fact_claim' in datasource '$DatasourceId'. No selection updates were made."
    }
}
$goldSource = @{ FolderName = 'lakehouse-tables-gold'; DatasourceJson = '{}'; FewShotsJson = '{}'; DatasourceId = $staleId; SelectedTables = @('fact_claim'); SelectedFunctions = @() }
$null = Deploy-DataAgent -Name 'Payer Ops Triage' -AiInstructions 'x' -DataSources @($goldSource) -WorkspaceId 'ws-1'
Assert-Equal -Expected 1 -Actual @($script:apiCalls | Where-Object { $_ -eq "DELETE /workspaces/ws-1/dataAgents/agent-1/staging/datasources/$staleId" }).Count -Message 'Stale datasource should be detached once.'
Assert-Equal -Expected 2 -Actual $script:definitionUpdates -Message 'Definition should be applied, then re-applied to re-import the datasource.'

$script:apiCalls.Clear(); $script:definitionUpdates = 0; $script:staleFailuresLeft = 2
$repeatError = ''
try { $null = Deploy-DataAgent -Name 'Payer Ops Triage' -AiInstructions 'x' -DataSources @($goldSource) -WorkspaceId 'ws-1' } catch { $repeatError = $_.Exception.Message }
Assert-True ($repeatError -like 'DataAgent native table selection failed for Payer Ops Triage:*fact_claim*') 'A table still missing after one re-attach must fail the deployment.'
Assert-Equal -Expected 1 -Actual @($script:apiCalls | Where-Object { $_ -like 'DELETE *' }).Count -Message 'Re-attach must not repeat.'

Write-Host 'Data Agent table selection tests passed.'

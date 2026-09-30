$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '../../utilities/data-agent-selection.ps1')
$scriptPath = Join-Path $PSScriptRoot '../deploy-payer-rti.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "deploy-payer-rti.ps1 has parse errors: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    'Assert-DataAgentTableSelection',
    'New-LakehouseDatasource'
)) {
    $functionAst = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName
    }, $true)
    if (-not $functionAst) { throw "Function '$functionName' was not found in deploy-payer-rti.ps1" }
    Invoke-Expression $functionAst.Extent.Text
}

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



$goldFewShots = @(
    @{ id = 'gold-shot'; question = 'Summarize historical claims.'; query = 'SELECT COUNT(*) FROM dbo.fact_claim' }
)
$datasource = New-LakehouseDatasource `
    -DisplayName 'healthcare1_reporting_gold' `
    -LakehouseId 'lakehouse-id' `
    -WorkspaceId 'workspace-id' `
    -Tables $targetTables `
    -Instructions 'Use the selected Gold tables.' `
    -FewShots $goldFewShots

# A hydrated definition uses hyphenated folder prefixes. Verify both stages by
# resolving that native path, rather than pinning the constructor's spelling.
$selectedPayload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((@{ elements = @($root) } | ConvertTo-Json -Depth 100)))
$script:HydratedDefinition = [pscustomobject]@{ definition = [pscustomobject]@{ parts = @(
    [pscustomobject]@{ path = 'Files/Config/draft/lakehouse-tables-healthcare1_reporting_gold/datasource.json'; payload = $selectedPayload },
    [pscustomobject]@{ path = 'Files/Config/published/lakehouse-tables-healthcare1_reporting_gold/datasource.json'; payload = $selectedPayload }
) } }
function Get-DataAgentDefinition {
    param($WorkspaceId, $DataAgentId)
    return $script:HydratedDefinition
}
Assert-DataAgentTableSelection -WorkspaceId 'workspace-id' -DataAgentId 'agent-id' -DatasourceFolderName $datasource.FolderName -Tables $targetTables -Functions $datasource.SelectedFunctions -SelectionKind 'lakehouse'

$publishedDatasource = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($selectedPayload)) | ConvertFrom-Json -Depth 100
$publishedDatasource.elements[0].children[0].children[0].children[0].is_selected = $false
$script:HydratedDefinition.definition.parts[1].payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($publishedDatasource | ConvertTo-Json -Depth 100)))
$rejectedPublishedSelection = $false
try {
    Assert-DataAgentTableSelection -WorkspaceId 'workspace-id' -DataAgentId 'agent-id' -DatasourceFolderName $datasource.FolderName -Tables $targetTables -Functions $datasource.SelectedFunctions -SelectionKind 'lakehouse'
} catch {
    $rejectedPublishedSelection = $_.Exception.Message -like 'published lakehouse selections do not match*'
}
Assert-True $rejectedPublishedSelection 'A missing requested table in the published datasource must fail validation even when draft selections match.'

Write-Host 'Data Agent table selection tests passed.'

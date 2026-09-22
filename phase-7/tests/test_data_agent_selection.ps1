$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot '../deploy-payer-rti.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "deploy-payer-rti.ps1 has parse errors: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    'Set-DataAgentSelectionValue',
    'Update-DataAgentLakehouseElementSelection',
    'Update-DataAgentKustoElementSelection',
    'Get-SelectedDataAgentTables',
    'Get-SelectedDataAgentFunctions',
    'New-KqlDatasource',
    'New-LakehouseDatasource',
    'New-OntologyDatasourceIfAvailable',
    'Deploy-DataAgent'
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


$kustoElements = @($kustoTargets | ForEach-Object { @{ id = [guid]::NewGuid().ToString(); display_name = $_; type = 'kusto.table'; is_selected = $true } })
$kustoDatasource = New-KqlDatasource `
    -DisplayName 'MasimoEventhouse' `
    -KqlDbId 'kql-id' `
    -WorkspaceId 'workspace-id' `
    -Elements $kustoElements `
    -FewShots @() `
    -Instructions 'Use the selected Eventhouse tables.' `
    -Functions $kustoFunctions
Assert-Equal -Expected 'kusto' -Actual $kustoDatasource.SelectionKind -Message 'KQL datasource should request Kusto hydration repair.'
Assert-Equal -Expected ($kustoTargets -join ',') -Actual (@($kustoDatasource.SelectedTables) -join ',') -Message 'KQL datasource metadata should retain the Eventhouse table contract.'
Assert-Equal -Expected ($kustoFunctions -join ',') -Actual (@($kustoDatasource.SelectedFunctions) -join ',') -Message 'KQL datasource metadata should retain the Kusto function contract.'

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
Assert-Equal -Expected 'lakehouse_tables-healthcare1_reporting_gold' -Actual $datasource.FolderName -Message 'Datasource folder convention changed unexpectedly.'
Assert-Equal -Expected ($targetTables -join ',') -Actual (@($datasource.SelectedTables) -join ',') -Message 'Datasource metadata should retain the requested table contract for post-hydration repair.'
Assert-Equal -Expected 'lakehouse' -Actual $datasource.SelectionKind -Message 'Lakehouse datasource should request Lakehouse hydration repair.'
$decodedGoldFewShots = $datasource.FewShotsJson | ConvertFrom-Json -Depth 20
Assert-Equal -Expected 1 -Actual @($decodedGoldFewShots.fewShots).Count -Message 'Gold datasource must retain its source-specific few-shots.'

$script:CallOrder = [System.Collections.Generic.List[string]]::new()
function Invoke-FabricApi {
    param([string]$Method = 'GET', [string]$Endpoint, [object]$Body, [int]$MaxRetries = 3)
    return [pscustomobject]@{ value = @(
        [pscustomobject]@{ displayName = 'Payer Ops Triage'; id = 'agent-id' },
        [pscustomobject]@{ displayName = 'DevicePayerOntology'; id = 'ontology-id' }
    ) }
}
function ConvertTo-Base64 { param([string]$Text) return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text)) }
function Update-DataAgentDefinition { param($WorkspaceId, $DataAgentId, $Definition) $script:CallOrder.Add('update') }
function Get-ErrorMessage { param($Record) return [string]$Record }

$ontologyTypes = @('Patient', 'Device', 'Claim')
$ontologyShots = @(@{ id = 'ontology-shot'; question = 'Trace patient to claim.'; query = 'MATCH (p:Patient)-[:hasClaim]->(c:Claim) RETURN p, c LIMIT 1' })
$ontologyDatasource = New-OntologyDatasourceIfAvailable `
    -OntologyName 'DevicePayerOntology' `
    -WorkspaceId 'workspace-id' `
    -UserDescription 'Graph source' `
    -Instructions 'Use ontology first.' `
    -EntityTypes $ontologyTypes `
    -FewShots $ontologyShots
$decodedOntology = $ontologyDatasource.DatasourceJson | ConvertFrom-Json -Depth 20
$decodedOntologyShots = $ontologyDatasource.FewShotsJson | ConvertFrom-Json -Depth 20
Assert-Equal -Expected 3 -Actual @($decodedOntology.elements).Count -Message 'Ontology datasource must select every requested entity type.'
Assert-True (@($decodedOntology.elements | Where-Object { -not $_.is_selected }).Count -eq 0) 'Every ontology entity must be selected.'
Assert-Equal -Expected 1 -Actual @($decodedOntologyShots.fewShots).Count -Message 'Ontology datasource must retain graph few-shots.'
function Repair-DataAgentTableSelection {
    param($WorkspaceId, $DataAgentId, $DatasourceFolderName, $Tables, $Functions, $SelectionKind)
    $expected = if ($SelectionKind -eq 'kusto') { $kustoTargets } else { $targetTables }
    Assert-Equal -Expected ($expected -join ',') -Actual (@($Tables) -join ',') -Message "Deploy should pass the exact $SelectionKind table contract to hydrated selection repair."
    if ($SelectionKind -eq 'kusto') { Assert-Equal -Expected ($kustoFunctions -join ',') -Actual (@($Functions) -join ',') -Message 'Deploy should pass the exact Kusto function contract to hydrated selection repair.' }
    $script:CallOrder.Add("repair-$SelectionKind")
}
function Publish-DataAgentDefinition { param($WorkspaceId, $DataAgentId, $Description) $script:CallOrder.Add('publish') }
function Assert-DataAgentTableSelection {
    param($WorkspaceId, $DataAgentId, $DatasourceFolderName, $Tables, $Functions, $SelectionKind)
    $expected = if ($SelectionKind -eq 'kusto') { $kustoTargets } else { $targetTables }
    Assert-Equal -Expected ($expected -join ',') -Actual (@($Tables) -join ',') -Message "Deploy should verify the exact $SelectionKind table contract after publish."
    if ($SelectionKind -eq 'kusto') { Assert-Equal -Expected ($kustoFunctions -join ',') -Actual (@($Functions) -join ',') -Message 'Deploy should verify the exact Kusto function contract after publish.' }
    $script:CallOrder.Add("assert-$SelectionKind")
}

$null = Deploy-DataAgent `
    -Name 'Payer Ops Triage' `
    -AiInstructions 'Use selected Gold tables.' `
    -DataSources @($kustoDatasource, $datasource) `
    -WorkspaceId 'workspace-id' `
    -Description 'test agent'
Assert-Equal -Expected 'update,repair-kusto,repair-lakehouse,publish,assert-kusto,assert-lakehouse' -Actual ($script:CallOrder -join ',') -Message 'Deploy must repair all hydrated datasource IDs before publish and verify both definitions afterward.'
Write-Host 'Data Agent table selection tests passed.'

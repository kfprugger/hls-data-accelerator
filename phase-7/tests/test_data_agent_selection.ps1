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

# Deploy-DataAgent recovery runs the real native selection helper against a stateful fake Fabric API.
$deployScript = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '../deploy-payer-rti.ps1'), [ref]$null, [ref]$null)
foreach ($functionName in @('ConvertTo-Base64', 'Get-ErrorMessage', 'Deploy-DataAgent')) {
    $definition = $deployScript.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName }, $true)
    Assert-True ($null -ne $definition) "deploy-payer-rti.ps1 must define $functionName."
    . ([scriptblock]::Create($definition.Extent.Text))
}
$script:fakeWorkspaceId = '00000000-0000-0000-0000-000000000001'
$script:fakeAgentId = '00000000-0000-0000-0000-000000000002'
$script:fakeKqlSourceId = '00000000-0000-0000-0000-000000000003'
$script:fakeGoldSourceId = '00000000-0000-0000-0000-000000000004'
$script:fakeForeignSourceId = '00000000-0000-0000-0000-000000000005'
$script:fakeAgentName = 'Healthcare Graph Agent'

# The helper waits between reads of a just-attached datasource; the fake has no sync delay.
function Start-Sleep { param([int]$Seconds) }

function New-FabricError([string]$Message) {
    $record = [System.Management.Automation.ErrorRecord]::new([System.Exception]::new('Fabric request failed.'), 'FabricApiError', [System.Management.Automation.ErrorCategory]::InvalidOperation, $null)
    $record.ErrorDetails = [System.Management.Automation.ErrorDetails]::new((@{ message = $Message } | ConvertTo-Json -Compress))
    return $record
}

function New-FakeSource {
    param(
        [string]$Id,
        [string[]]$Tables,
        [string[]]$Functions = @(),
        [switch]$Lakehouse,
        # Imports numbered at or below these limits are broken; later re-imports are healthy.
        [int]$UnavailableImports = 0,
        [string]$UnavailableReportedId = '',
        [string]$MissingTable = '',
        [int]$MissingImports = 0
    )
    $reportedId = if ($UnavailableReportedId) { $UnavailableReportedId } else { $Id }
    return @{
        Id = $Id; Tables = $Tables; Functions = $Functions; Lakehouse = [bool]$Lakehouse
        UnavailableImports = $UnavailableImports; ReportedId = $reportedId; MissingTable = $MissingTable; MissingImports = $MissingImports
        Attached = $false; Imports = 0; Staged = @{}; Live = @{}
    }
}

function Reset-FakeFabric {
    param([hashtable[]]$Sources)
    $script:fabric = @{ Published = $false; Sources = @{} }
    foreach ($source in $Sources) { $script:fabric.Sources[$source.Id] = $source }
}

function New-FakeElement([string]$Id, [string]$DisplayName, [string]$Type, [hashtable]$Selection) {
    return [pscustomobject]@{
        id = $Id; displayName = $DisplayName; type = $Type; hasSubElements = $Type -notin @('Table', 'Function')
        isSelected = [bool]$Selection[$Id]; state = 'Available'
    }
}

function Get-FakeElements {
    param([hashtable]$Source, [string]$RootId, [hashtable]$Selection)
    if (-not $RootId) {
        if ($Source.Lakehouse) { return @(New-FakeElement 'schemas' 'Schemas' 'Schemas' $Selection) }
        return @((New-FakeElement 'tables' 'Tables' 'Tables' $Selection), (New-FakeElement 'functions' 'Functions' 'Functions' $Selection))
    }
    if ($RootId -eq 'schemas') { return @(New-FakeElement 'schema-dbo' 'dbo' 'Schema' $Selection) }
    if ($RootId -eq 'schema-dbo') { return @(New-FakeElement 'tables' 'Tables' 'Tables' $Selection) }
    if ($RootId -eq 'tables') {
        $tables = @($Source.Tables | Where-Object { $_ -ne $Source.MissingTable -or $Source.Imports -gt $Source.MissingImports })
        return @($tables | ForEach-Object { New-FakeElement "table-$_" $_ 'Table' $Selection })
    }
    if ($RootId -eq 'functions') { return @($Source.Functions | ForEach-Object { New-FakeElement "function-$_" $_ 'Function' $Selection }) }
    throw "Unexpected native root '$RootId'."
}

function Invoke-FabricApi {
    param([string]$Method = 'GET', [string]$Endpoint, [object]$Body = $null)
    if ($Method -eq 'GET' -and $Endpoint -eq "/workspaces/$script:fakeWorkspaceId/items?type=DataAgent") {
        return [pscustomobject]@{ value = @([pscustomobject]@{ displayName = $script:fakeAgentName; id = $script:fakeAgentId }) }
    }
    if ($Endpoint -notmatch "^/workspaces/$script:fakeWorkspaceId/dataAgents/$script:fakeAgentId/(?<stage>staging/)?datasources/(?<source>[0-9a-f-]{36})(?<elements>/elements)?(?:\?(?<query>.*))?$") {
        throw "Unexpected Fabric call: $Method $Endpoint"
    }
    $sourceId = $Matches.source; $staged = [bool]$Matches.stage; $isElements = [bool]$Matches.elements; $query = [string]$Matches.query
    $source = $script:fabric.Sources[$sourceId]
    if (-not $source) { throw (New-FabricError "Datasource $sourceId is not part of this agent.") }
    if ($Method -eq 'DELETE' -and $staged -and -not $isElements) {
        $source.Attached = $false
        $source.Staged = @{}
        return
    }
    if (-not $isElements) { throw "Unexpected Fabric call: $Method $Endpoint" }
    $parameters = @{}
    foreach ($pair in @($query -split '&' | Where-Object { $_ })) {
        $key, $value = $pair -split '=', 2
        $parameters[$key] = [uri]::UnescapeDataString($value)
    }
    if (-not $staged) {
        if ($Method -ne 'GET' -or -not $script:fabric.Published) { throw "Unexpected published call: $Method $Endpoint" }
        return [pscustomobject]@{ value = @(Get-FakeElements -Source $source -RootId ([string]$parameters['rootId']) -Selection $source.Live) }
    }
    if (-not $source.Attached) { throw (New-FabricError "Datasource $sourceId is not attached.") }
    if ($source.Imports -le $source.UnavailableImports) {
        throw (New-FabricError "The cached path for data source $($source.ReportedId) is unavailable. Retry the request.")
    }
    if ($Method -eq 'GET') {
        return [pscustomobject]@{ value = @(Get-FakeElements -Source $source -RootId ([string]$parameters['rootId']) -Selection $source.Staged) }
    }
    if ($Method -eq 'PATCH') {
        $source.Staged[$parameters['id']] = [bool]$Body.isSelected
        return
    }
    throw "Unexpected Fabric call: $Method $Endpoint"
}

# Applying the definition imports every detached datasource reference-only (nothing selected);
# it leaves already-attached datasources, including broken ones, untouched.
function Update-DataAgentDefinition {
    param([string]$WorkspaceId, [string]$DataAgentId, [object]$Definition)
    foreach ($source in @($script:fabric.Sources.Values | Where-Object { -not $_.Attached })) {
        $source.Attached = $true
        $source.Imports += 1
        $source.Staged = @{}
    }
}
function Publish-DataAgentDefinition {
    param([string]$WorkspaceId, [string]$DataAgentId, [string]$Description)
    foreach ($source in @($script:fabric.Sources.Values)) { $source.Live = $source.Staged.Clone() }
    $script:fabric.Published = $true
}
function Get-PublishedSelection([hashtable]$Source, [string]$Prefix) {
    return (@($Source.Live.Keys | Where-Object { $Source.Live[$_] -and $_ -like "$Prefix-*" } | ForEach-Object { $_.Substring($Prefix.Length + 1) } | Sort-Object) -join ',')
}
function Invoke-FakeDeploy([hashtable]$Contract) {
    $null = Deploy-DataAgent -Name $script:fakeAgentName -AiInstructions 'x' -DataSources @($Contract) -WorkspaceId $script:fakeWorkspaceId
}
function Get-FakeDeployError([hashtable]$Contract) {
    try { Invoke-FakeDeploy $Contract } catch { return $_.Exception.Message }
    return ''
}

$kqlContract = @{ FolderName = 'kusto-masimo'; DatasourceJson = '{}'; FewShotsJson = '{}'; DatasourceId = $script:fakeKqlSourceId; SelectedTables = @('TelemetryRaw', 'AlertHistory'); SelectedFunctions = @('fn_FraudRisk') }
function New-FakeKqlSource([int]$UnavailableImports, [string]$UnavailableReportedId = '') {
    return New-FakeSource -Id $script:fakeKqlSourceId -Tables @('TelemetryRaw', 'AlertHistory', 'unused_table') -Functions @('fn_FraudRisk', 'unused_function') -UnavailableImports $UnavailableImports -UnavailableReportedId $UnavailableReportedId
}

# A KQL datasource whose cached path is unavailable once is re-imported and publishes the exact contract.
Reset-FakeFabric -Sources @((New-FakeKqlSource -UnavailableImports 1))
Invoke-FakeDeploy $kqlContract
$kql = $script:fabric.Sources[$script:fakeKqlSourceId]
Assert-True $script:fabric.Published 'Agent should publish after the unavailable cache is re-imported.'
Assert-Equal -Expected 'AlertHistory,TelemetryRaw' -Actual (Get-PublishedSelection $kql 'table') -Message 'Published KQL tables should match the contract exactly.'
Assert-Equal -Expected 'fn_FraudRisk' -Actual (Get-PublishedSelection $kql 'function') -Message 'Published KQL functions should match the contract exactly.'

# A cache still unavailable after the single re-import stops before publication.
Reset-FakeFabric -Sources @((New-FakeKqlSource -UnavailableImports 99))
$persistentError = Get-FakeDeployError $kqlContract
Assert-True ($persistentError -like "DataAgent native table selection failed for $($script:fakeAgentName): The cached path for data source $($script:fakeKqlSourceId) is unavailable*") "Persistent cache unavailability must fail the deployment; got '$persistentError'."
Assert-True (-not $script:fabric.Published) 'Persistent cache unavailability must leave the agent unpublished.'
Assert-Equal -Expected 2 -Actual $script:fabric.Sources[$script:fakeKqlSourceId].Imports -Message 'Recovery must re-import the datasource at most once.'

# An unavailable cache naming a datasource outside the requested contracts is never detached.
Reset-FakeFabric -Sources @((New-FakeKqlSource -UnavailableImports 1 -UnavailableReportedId $script:fakeForeignSourceId))
$foreignError = Get-FakeDeployError $kqlContract
Assert-True ($foreignError -like "DataAgent native table selection failed for $($script:fakeAgentName): *$($script:fakeForeignSourceId)*") "A foreign datasource error must fail the deployment; got '$foreignError'."
Assert-True (-not $script:fabric.Published) 'A foreign datasource error must leave the agent unpublished.'
$kql = $script:fabric.Sources[$script:fakeKqlSourceId]
Assert-True ($kql.Attached -and $kql.Imports -eq 1) 'A foreign datasource error must not detach or re-import the requested datasource.'

# A lakehouse datasource whose stale schema lacks a target table is re-imported once.
$goldContract = @{ FolderName = 'lakehouse-tables-gold'; DatasourceJson = '{}'; FewShotsJson = '{}'; DatasourceId = $script:fakeGoldSourceId; SelectedTables = @('fact_claim', 'dim_payer'); SelectedFunctions = @() }
function New-FakeGoldSource([int]$MissingImports) {
    return New-FakeSource -Id $script:fakeGoldSourceId -Tables @('fact_claim', 'dim_payer', 'agg_utilization_summary') -Lakehouse -MissingTable 'fact_claim' -MissingImports $MissingImports
}
Reset-FakeFabric -Sources @((New-FakeGoldSource -MissingImports 1))
Invoke-FakeDeploy $goldContract
Assert-True $script:fabric.Published 'Agent should publish after the stale lakehouse datasource is re-imported.'
Assert-Equal -Expected 'dim_payer,fact_claim' -Actual (Get-PublishedSelection $script:fabric.Sources[$script:fakeGoldSourceId] 'table') -Message 'Published lakehouse tables should match the contract exactly.'

Reset-FakeFabric -Sources @((New-FakeGoldSource -MissingImports 99))
$missingError = Get-FakeDeployError $goldContract
Assert-True ($missingError -like "DataAgent native table selection failed for $($script:fakeAgentName):*fact_claim*") "A table still missing after one re-attach must fail the deployment; got '$missingError'."
Assert-True (-not $script:fabric.Published) 'A table still missing after one re-attach must leave the agent unpublished.'

Write-Host 'Data Agent table selection tests passed.'

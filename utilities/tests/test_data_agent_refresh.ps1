#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utilityRoot = Split-Path -Parent $PSScriptRoot
$commandPath = Join-Path $utilityRoot 'Refresh-DataAgentSchemas.ps1'
. (Join-Path $utilityRoot 'data-agent-refresh.ps1')

function Assert-True($Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    try { & $Action } catch {
        if ($_.Exception.Message -notmatch $Pattern) { throw "Unexpected error: $($_.Exception.Message)" }
        return
    }
    throw "Expected error matching '$Pattern'"
}
function Copy-Value($Value) { return $Value | ConvertTo-Json -Depth 100 | ConvertFrom-Json -Depth 100 }
function New-Column([string]$Name, [bool]$Selected = $false) {
    return [pscustomobject]@{ id = "column-$Name"; type = 'lakehouse_tables.column'; display_name = $Name; is_selected = $Selected }
}
function New-TestDefinition {
    $table = [pscustomobject]@{
        id = 'patient-id'; type = 'lakehouse_tables.table'; display_name = 'Patient'; is_selected = $false
        children = @((New-Column 'patient_id'), (New-Column 'name'))
    }
    $unused = [pscustomobject]@{ id = 'unused-id'; type = 'lakehouse_tables.table'; display_name = 'Unused'; is_selected = $false }
    $schema = [pscustomobject]@{
        id = 'schema-id'; type = 'lakehouse_tables.schema'; display_name = 'dbo'; is_selected = $false
        children = @([pscustomobject]@{
            id = 'tables-id'; type = 'table_grouping'; display_name = 'Tables'; is_selected = $false; children = @($table, $unused)
        })
    }
    $draft = [pscustomobject]@{
        artifactId = 'lakehouse-id'; workspaceId = 'workspace-id'; type = 'lakehouse_tables'
        aiInstructions = 'Preserve source instructions'; userDescription = 'Clinical source'
        elements = @([pscustomobject]@{
            id = 'schemas-id'; type = 'schema_grouping'; display_name = 'Schemas'; is_selected = $false; children = @($schema)
        })
    }
    $published = Copy-Value $draft
    $published.elements = @([pscustomobject]@{
        type = 'lakehouse_tables.schema'; display_name = 'dbo'; is_selected = $true
        children = @([pscustomobject]@{ type = 'lakehouse_tables.table'; display_name = 'Patient'; is_selected = $true })
    })
    $parts = @((Write-DataAgentDefinitionPart -Path 'Files/Config/data_agent.json' -Value @{ '$schema' = 'test-schema' }))
    foreach ($stage in @('draft', 'published')) {
        $parts += Write-DataAgentDefinitionPart -Path "Files/Config/$stage/stage_config.json" -Value @{ aiInstructions = 'Preserve agent instructions' }
        $parts += Write-DataAgentDefinitionPart -Path "Files/Config/$stage/lakehouse-tables-clinical/datasource.json" -Value $(if ($stage -eq 'draft') { $draft } else { $published })
        $parts += Write-DataAgentDefinitionPart -Path "Files/Config/$stage/lakehouse-tables-clinical/fewshots.json" -Value @{
            fewShots = @(@{ question = 'Count patients'; query = 'SELECT COUNT(*) FROM dbo.Patient' })
        }
        $parts += Write-DataAgentDefinitionPart -Path "Files/Config/$stage/ontology-clinical/datasource.json" -Value @{
            artifactId = 'ontology-id'; workspaceId = 'workspace-id'; type = 'ontology'; elements = @()
        }
    }
    return [pscustomobject]@{ definition = [pscustomobject]@{ parts = $parts } }
}

function Replace-Source($Definition, [string]$Stage, [scriptblock]$Change) {
    $part = @($Definition.definition.parts | Where-Object path -eq "Files/Config/$Stage/lakehouse-tables-clinical/datasource.json")[0]
    $value = Read-DataAgentDefinitionPart $part
    & $Change $value
    $part.payload = (Write-DataAgentDefinitionPart -Path $part.path -Value $value).payload
}

$definition = New-TestDefinition
$originalFingerprint = Get-DataAgentDefinitionFingerprint $definition
$plan = New-DataAgentRefreshPlan $definition
Assert-True ((Get-DataAgentDefinitionFingerprint $definition) -eq $originalFingerprint) 'Planning mutated the original definition'
Assert-True ($plan.Contracts.Count -eq 1) 'Expected one table source contract'
Assert-True ($plan.Contracts[0].Tables[0].Id -eq 'patient-id') 'Must use current Fabric table ID'
Assert-True ($plan.Contracts[0].Tables[0].Columns.Count -eq 2) 'Name-only published tables should include current columns'
$ds = Read-DataAgentDefinitionPart @($plan.Definition.parts | Where-Object path -like '*/lakehouse-tables-clinical/datasource.json')[0]
Assert-True $ds.elements[0].is_selected 'Schema grouping should be selected'
Assert-True (-not $ds.elements[0].children[0].children[0].children[1].is_selected) 'Unintended tables must not be selected'

$partial = New-TestDefinition
Replace-Source $partial 'published' {
    param($ds)
    $ds.elements[0].children[0] | Add-Member children @((New-Column 'patient_id' $true), (New-Column 'name'))
}
$partialPlan = New-DataAgentRefreshPlan $partial
Assert-True (($partialPlan.Contracts[0].Tables[0].Columns -join ',') -eq 'patient_id') 'Preserve partial column selections'

$missing = New-TestDefinition
Replace-Source $missing 'published' { param($ds) $ds.elements[0].children[0].display_name = 'MissingGroundingTable' }
Assert-Throws { New-DataAgentRefreshPlan $missing } 'Missing/ambiguous current table'
$unhydrated = New-TestDefinition
Replace-Source $unhydrated 'draft' { param($ds) $ds.elements[0].children[0].children[0].children[0].id = '' }
Assert-Throws { New-DataAgentRefreshPlan $unhydrated } 'Unhydrated'
$ambiguous = New-TestDefinition
Replace-Source $ambiguous 'draft' {
    param($ds)
    $tables = $ds.elements[0].children[0].children[0]
    $tables.children += Copy-Value $tables.children[0]
}
Assert-Throws { New-DataAgentRefreshPlan $ambiguous } 'Missing/ambiguous current table'
$wrongSchema = New-TestDefinition
Replace-Source $wrongSchema 'draft' { param($ds) $ds.elements[0].children[0].display_name = 'other' }
Assert-Throws { New-DataAgentRefreshPlan $wrongSchema } 'mismatched schema'
$edits = New-TestDefinition
Replace-Source $edits 'draft' { param($ds) $ds.aiInstructions = 'Unpublished user edit' }
Assert-Throws { New-DataAgentRefreshPlan $edits } 'Unpublished datasource edits'

$kusto = New-TestDefinition
foreach ($stage in @('draft', 'published')) {
    Replace-Source $kusto $stage {
        param($ds)
        $ds.type = 'kusto'
        $ds.elements = @([pscustomobject]@{
            id = 'functions-id'; type = 'function_grouping'; display_name = 'Functions'; is_selected = $false
            children = @([pscustomobject]@{
                id = 'function-id'; type = 'kusto.function'; display_name = 'fn_Test'; is_selected = $true
            })
        })
    }
}
$kustoPlan = New-DataAgentRefreshPlan $kusto
Assert-True ($kustoPlan.Contracts[0].Tables.Count -eq 0) 'Function-only KQL sources should be supported'
Assert-True ($kustoPlan.Contracts[0].FunctionIds['fn_Test'] -eq 'function-id') 'Use the current function ID'
$missingFunction = Copy-Value $kusto
Replace-Source $missingFunction 'draft' { param($ds) $ds.elements[0].children = @() }
Assert-Throws { New-DataAgentRefreshPlan $missingFunction } 'Missing/ambiguous current function'

$aggregateFunctions = Copy-Value $kusto
foreach ($stage in @('draft', 'published')) {
    Replace-Source $aggregateFunctions $stage {
        param($ds)
        $ds.elements = @([pscustomobject]@{
            id = 'functions-id'; type = 'kusto.functions'; display_name = 'Functions'; is_selected = $true; children = @()
        })
    }
}
Assert-Throws { New-DataAgentRefreshPlan $aggregateFunctions } 'Unresolved published function selection'
$aggregateGrouping = Copy-Value $aggregateFunctions
foreach ($stage in @('draft', 'published')) {
    Replace-Source $aggregateGrouping $stage { param($ds) $ds.elements[0].type = 'function_grouping' }
}
Assert-Throws { New-DataAgentRefreshPlan $aggregateGrouping } 'Unresolved published function selection'

$global:DataAgentRefreshTestState = @{
    Cloud = @{ 'agent-one' = (New-TestDefinition); 'agent-two' = (New-TestDefinition) }
    Writes = [Collections.Generic.List[string]]::new()
    AuthCalls = 0
    HttpCalls = 0
    GetCounts = @{}
    ChangeOnSecondRead = $false
    Async = $false
    OperationStatus = 'Succeeded'
    OperationHost = 'api.fabric.microsoft.com'
}
$state = $global:DataAgentRefreshTestState
function az {
    $global:DataAgentRefreshTestState.AuthCalls++
    $global:LASTEXITCODE = 0
    return '{"accessToken":"test-token","tenant":"00000000-0000-0000-0000-000000000002"}'
}
function Invoke-WebRequest {
    param($Uri, $Method, $Headers, $TimeoutSec, $ErrorAction, $Body)
    $global:DataAgentRefreshTestState.HttpCalls++
    if ($Uri -match '/items\?type=DataAgent$') {
        $value = @{ value = @(
            @{ id = 'agent-one'; displayName = 'One' },
            @{ id = 'agent-two'; displayName = 'Two' }
        ) }
    } elseif ($Uri -match '/items/(agent-[^/]+)/getDefinition$') {
        $id = $Matches[1]
        $state = $global:DataAgentRefreshTestState
        if (-not $state.GetCounts.ContainsKey($id)) { $state.GetCounts[$id] = 0 }
        $state.GetCounts[$id]++
        if ($state.ChangeOnSecondRead -and $state.GetCounts[$id] -eq 2) {
            $state.Cloud[$id].definition.parts[0].payload = (Write-DataAgentDefinitionPart 'Files/Config/data_agent.json' @{ '$schema' = 'concurrent-edit' }).payload
        }
        if ($state.Async) {
            return [pscustomobject]@{ StatusCode = 202; Content = ''; Headers = @{ Location = @("https://$($state.OperationHost)/v1/operations/$id") } }
        }
        $value = $state.Cloud[$id]
    } elseif ($Uri -match '/v1/operations/(agent-[^/]+)/result$') {
        $value = $global:DataAgentRefreshTestState.Cloud[$Matches[1]]
    } elseif ($Uri -match '/v1/operations/(agent-[^/]+)$') {
        $value = @{ status = $global:DataAgentRefreshTestState.OperationStatus }
    } elseif ($Uri -match '/dataAgents/(agent-[^/]+)/updateDefinition$') {
        $id = $Matches[1]
        $global:DataAgentRefreshTestState.Writes.Add("update-$id")
        $data = [Text.Encoding]::UTF8.GetString($Body) | ConvertFrom-Json -Depth 100
        $published = @($global:DataAgentRefreshTestState.Cloud[$id].definition.parts | Where-Object { $_.path.Contains('/published/') })
        $global:DataAgentRefreshTestState.Cloud[$id] = [pscustomobject]@{ definition = [pscustomobject]@{ parts = @($data.definition.parts) + $published } }
        $value = @{}
    } elseif ($Uri -match '/dataAgents/(agent-[^/]+)/staging/publish$') {
        $id = $Matches[1]
        $global:DataAgentRefreshTestState.Writes.Add("publish-$id")
        $draft = @($global:DataAgentRefreshTestState.Cloud[$id].definition.parts | Where-Object { -not $_.path.Contains('/published/') })
        $published = @($draft | Where-Object { $_.path.Contains('/draft/') } | ForEach-Object {
            [pscustomobject]@{ path = $_.path.Replace('/draft/', '/published/'); payload = $_.payload; payloadType = $_.payloadType }
        })
        $global:DataAgentRefreshTestState.Cloud[$id].definition.parts = $draft + $published
        $value = @{}
    } else { throw "Unexpected HTTP request: $Method $Uri" }
    return [pscustomobject]@{ StatusCode = 200; Content = ($value | ConvertTo-Json -Depth 100 -Compress); Headers = @{} }
}
function Start-Sleep { param($Seconds) }
$workspace = '00000000-0000-0000-0000-000000000001'
$tenant = '00000000-0000-0000-0000-000000000002'
& $commandPath -TenantId $tenant -WorkspaceId $workspace
Assert-True ($state.Writes.Count -eq 0) 'Default command must not write or publish'
Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'Absent' } 'not found'
Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -Apply } 'requires -BackupDirectory'
$httpCalls = $state.HttpCalls
Assert-Throws {
    & $commandPath -TenantId '00000000-0000-0000-0000-000000000003' -WorkspaceId $workspace
} 'different tenant'
Assert-True ($state.HttpCalls -eq $httpCalls) 'A tenant mismatch must stop before any Fabric request'

$backup = Join-Path ([IO.Path]::GetTempPath()) "data-agent-refresh-test-$([guid]::NewGuid().ToString('N'))"
try {
    & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One' -Apply -BackupDirectory $backup -WhatIf
    Assert-True ($state.Writes.Count -eq 0 -and -not (Test-Path $backup)) '-WhatIf must not create backups or write'
    & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One' -Apply -BackupDirectory $backup -Confirm:$false
    Assert-True (($state.Writes -join ',') -eq 'update-agent-one,publish-agent-one') 'Only the filtered agent should update and publish'
    Assert-True (@(Get-ChildItem -LiteralPath $backup -Filter '*.json').Count -eq 2) 'Expected before and after backups'
    Assert-DataAgentRefreshDefinition -Definition $state.Cloud['agent-one'] -Plan $plan
    $badVerification = Copy-Value $state.Cloud['agent-one']
    Replace-Source $badVerification 'published' { param($ds) $ds.elements[0].children[0].children[0].children[0].id = 'wrong-id' }
    Assert-Throws { Assert-DataAgentRefreshDefinition $badVerification $plan } 'ID mismatch'
    $state.Cloud['agent-two'] = $missing
    $count = $state.Writes.Count
    Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -Apply -BackupDirectory $backup -Confirm:$false } 'Preflight failed'
    Assert-True ($state.Writes.Count -eq $count) 'All-agent preflight must complete before any writes'
    $state.Cloud['agent-one'] = New-TestDefinition
    $state.GetCounts = @{}
    $state.ChangeOnSecondRead = $true
    Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One' -Apply -BackupDirectory $backup -Confirm:$false } 'changed after preflight'
    Assert-True ($state.Writes.Count -eq $count) 'Concurrent edits must stop publication'
    $state.ChangeOnSecondRead = $false
    $state.Async = $true
    & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One'
    Assert-True ($state.Writes.Count -eq $count) 'Async getDefinition must remain read-only'
    $state.OperationStatus = 'Cancelled'
    Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One' } 'operation Cancelled'
    $state.OperationStatus = 'Succeeded'
    $state.OperationHost = 'unexpected.invalid'
    Assert-Throws { & $commandPath -TenantId $tenant -WorkspaceId $workspace -AgentName 'One' } 'Unexpected Fabric operation host'
} finally {
    if (Test-Path -LiteralPath $backup) {
        foreach ($file in @(Get-ChildItem -LiteralPath $backup -File)) { Remove-Item -LiteralPath $file.FullName }
        Remove-Item -LiteralPath $backup
    }
    Remove-Variable -Name DataAgentRefreshTestState -Scope Global
}
Write-Host 'Data Agent schema refresh tests passed (offline; no Fabric changes).'

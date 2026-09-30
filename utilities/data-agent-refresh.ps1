. (Join-Path $PSScriptRoot 'data-agent-selection.ps1')

function Read-DataAgentDefinitionPart {
    param([Parameter(Mandatory)][object]$Part)
    if ($Part.payloadType -ne 'InlineBase64') { throw "Unsupported payload type for '$($Part.path)'" }
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Part.payload)) | ConvertFrom-Json -Depth 100
}

function Write-DataAgentDefinitionPart {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][object]$Value)
    return [pscustomobject]@{
        path = $Path
        payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 100 -Compress)))
        payloadType = 'InlineBase64'
    }
}

function Get-DataAgentDefinitionFingerprint {
    param([Parameter(Mandatory)][object]$Definition)
    $parts = @($Definition.definition.parts | Sort-Object path | Select-Object path, payload, payloadType)
    $bytes = [Text.Encoding]::UTF8.GetBytes(($parts | ConvertTo-Json -Depth 10 -Compress))
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
}

function Get-DataAgentSchemaObjects {
    param([AllowEmptyCollection()][object[]]$Elements, [string]$Schema = '')
    foreach ($element in $Elements) {
        $currentSchema = if ($element.type -eq 'lakehouse_tables.schema') { [string]$element.display_name } else { $Schema }
        if ($element.type -in @('lakehouse_tables.table', 'kusto.table', 'kusto.function', 'function')) {
            [pscustomobject]@{ Node = $element; Schema = $currentSchema }
        } elseif ($element.PSObject.Properties['children'] -and $element.children) {
            Get-DataAgentSchemaObjects -Elements @($element.children) -Schema $currentSchema
        }
    }
}

function Get-DataAgentCanonicalJson {
    param([AllowNull()][object]$Value)
    function ConvertTo-CanonicalValue($Item) {
        if ($null -eq $Item) { return $null }
        if ($Item -is [System.Management.Automation.PSCustomObject] -or $Item -is [System.Collections.IDictionary]) {
            $ordered = [ordered]@{}
            $names = if ($Item -is [System.Collections.IDictionary]) { @($Item.Keys) } else { @($Item.PSObject.Properties.Name) }
            foreach ($name in @($names | Sort-Object)) { $ordered[$name] = ConvertTo-CanonicalValue $Item.$name }
            return $ordered
        }
        if ($Item -is [System.Collections.IEnumerable] -and $Item -isnot [string]) {
            $values = @($Item | ForEach-Object { ConvertTo-CanonicalValue $_ })
            return ,$values
        }
        return $Item
    }
    return ConvertTo-CanonicalValue $Value | ConvertTo-Json -Depth 100 -Compress
}

function Assert-DataAgentRefreshSelection {
    param([Parameter(Mandatory)][object]$Datasource, [Parameter(Mandatory)][object]$Contract)
    if ($Datasource.artifactId -ne $Contract.ArtifactId -or $Datasource.workspaceId -ne $Contract.WorkspaceId) {
        throw "Datasource identity changed: $($Contract.Path)"
    }
    if ((Get-DataAgentCanonicalJson ($Datasource | Select-Object * -ExcludeProperty elements)) -ne $Contract.Settings) {
        throw "Datasource settings changed unexpectedly: $($Contract.Path)"
    }
    $selected = @(Get-SelectedDataAgentTables -Elements @($Datasource.elements) -SelectionKind $Contract.Kind)
    $expected = @($Contract.Tables | ForEach-Object { $_.Name } | Sort-Object -Unique)
    if (($selected -join '|') -ne ($expected -join '|')) { throw "Table selections differ from the contract: $($Contract.Path)" }
    $functions = @(Get-SelectedDataAgentFunctions -Elements @($Datasource.elements))
    if (($functions -join '|') -ne (($Contract.Functions | Sort-Object -Unique) -join '|')) {
        throw "Function selections differ from the contract: $($Contract.Path)"
    }
    $objects = @(Get-DataAgentSchemaObjects -Elements @($Datasource.elements))
    foreach ($function in $Contract.Functions) {
        $match = @($objects | Where-Object { $_.Node.display_name -eq $function -and $_.Node.type -in @('kusto.function', 'function') })
        if ($match.Count -ne 1 -or $match[0].Node.id -ne $Contract.FunctionIds[$function]) {
            throw "Function ID mismatch for '$function'"
        }
    }
    foreach ($table in $Contract.Tables) {
        $match = @($objects | Where-Object { $_.Node.display_name -eq $table.Name -and $_.Node.type -in @('lakehouse_tables.table', 'kusto.table') })
        if ($match.Count -ne 1 -or $match[0].Schema -ne $table.Schema -or $match[0].Node.id -ne $table.Id) {
            throw "Schema/table ID mismatch for '$($table.Schema).$($table.Name)'"
        }
        $columns = @(Get-DataAgentSelectionNodes -Elements @($match[0].Node) |
            Where-Object { $_.type -in @('lakehouse_tables.column', 'kusto.column') -and $_.is_selected } |
            ForEach-Object { [string]$_.display_name } | Sort-Object -Unique)
        if (($columns -join '|') -ne (($table.Columns | Sort-Object -Unique) -join '|')) {
            throw "Column selections differ for '$($table.Name)'"
        }
    }
    foreach ($node in @(Get-DataAgentSelectionNodes -Elements @($Datasource.elements))) {
        if ($node.PSObject.Properties['is_selected'] -and $node.is_selected -and
            (-not $node.PSObject.Properties['id'] -or [string]::IsNullOrWhiteSpace($node.id))) {
            throw "Selected $($node.type) '$($node.display_name)' has no Fabric ID. Open the agent in Fabric and click Refresh."
        }
    }
}

function New-DataAgentRefreshPlan {
    param([Parameter(Mandatory)][object]$Definition)
    # Clone before modifying metadata so backups and fingerprints describe the original definition.
    $copy = $Definition | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json -Depth 100
    $parts = @($copy.definition.parts)
    $duplicates = @($parts | Group-Object path | Where-Object Count -gt 1)
    if ($duplicates.Count) { throw "Duplicate definition paths: $($duplicates.Name -join ', ')" }
    $top = @($parts | Where-Object path -eq 'Files/Config/data_agent.json')
    if ($top.Count -ne 1) { throw 'Missing data_agent.json' }
    $published = @($parts | Where-Object { $_.path.StartsWith('Files/Config/published/') })
    if (-not $published.Count) { throw 'Agent has no published configuration to restore' }
    $writable = @($top)
    $contracts = @()
    foreach ($part in $published) {
        $path = $part.path.Replace('Files/Config/published/', 'Files/Config/draft/')
        $draftParts = @($parts | Where-Object path -eq $path)
        if ($draftParts.Count -ne 1) { throw "Missing draft metadata: $path. Open the agent in Fabric and click Refresh." }
        $value = Read-DataAgentDefinitionPart -Part $part
        $draft = Read-DataAgentDefinitionPart -Part $draftParts[0]
        if (-not $path.EndsWith('/datasource.json')) {
            if (($part.payload -ne $draftParts[0].payload) -and
                ((Get-DataAgentCanonicalJson $value) -ne (Get-DataAgentCanonicalJson $draft))) {
                throw "Unpublished edits in '$path'. Publish or reconcile those edits before refreshing."
            }
        } else {
            if ($value.artifactId -ne $draft.artifactId -or $value.workspaceId -ne $draft.workspaceId -or $value.type -ne $draft.type) {
                throw "Datasource identity differs between draft and published: $path"
            }
            $publishedSettings = $value | Select-Object * -ExcludeProperty elements
            $draftSettings = $draft | Select-Object * -ExcludeProperty elements
            if ((Get-DataAgentCanonicalJson $publishedSettings) -ne (Get-DataAgentCanonicalJson $draftSettings)) {
                throw "Unpublished datasource edits in '$path'. Publish or reconcile those edits before refreshing."
            }
            if ($value.type -in @('lakehouse_tables', 'kusto')) {
                $kind = if ($value.type -eq 'kusto') { 'kusto' } else { 'lakehouse' }
                $tableType = if ($kind -eq 'kusto') { 'kusto.table' } else { 'lakehouse_tables.table' }
                $publishedObjects = @(Get-DataAgentSchemaObjects -Elements @($value.elements))
                $currentObjects = @(Get-DataAgentSchemaObjects -Elements @($draft.elements))
                $targets = @($publishedObjects | Where-Object { $_.Node.type -eq $tableType -and $_.Node.is_selected })
                $functions = @(Get-SelectedDataAgentFunctions -Elements @($value.elements))
                foreach ($group in @(Get-DataAgentSelectionNodes -Elements @($value.elements) |
                    Where-Object { $_.type -in @('kusto.functions', 'function_grouping') -and $_.is_selected })) {
                    $members = @(Get-SelectedDataAgentFunctions -Elements @($group))
                    if (-not $members.Count) {
                        throw "Unresolved published function selection in '$path'. Refresh function metadata in Fabric before applying; aggregate selection must not be silently removed."
                    }
                }
                $functionIds = @{}
                $tableContracts = @()
                foreach ($target in $targets) {
                    $matches = @($currentObjects | Where-Object { $_.Node.type -eq $tableType -and $_.Node.display_name -eq $target.Node.display_name })
                    if ($matches.Count -ne 1) {
                        throw "Missing/ambiguous current table '$($target.Schema).$($target.Node.display_name)' in '$path'. Refresh in Fabric; missing tables must be deployed, not silently removed."
                    }
                    $current = $matches[0]
                    if ($current.Schema -ne $target.Schema -or -not $current.Node.PSObject.Properties['id'] -or -not $current.Node.id) {
                        throw "Unhydrated or mismatched schema for '$($target.Node.display_name)' in '$path'. Open the agent in Fabric and click Refresh."
                    }
                    $oldColumns = @(Get-DataAgentSelectionNodes -Elements @($target.Node) |
                        Where-Object type -in @('lakehouse_tables.column', 'kusto.column'))
                    $newColumns = @(Get-DataAgentSelectionNodes -Elements @($current.Node) |
                        Where-Object type -in @('lakehouse_tables.column', 'kusto.column'))
                    $columnNames = if ($oldColumns.Count) {
                        @($oldColumns | Where-Object is_selected | ForEach-Object { [string]$_.display_name })
                    } else { @($newColumns | ForEach-Object { [string]$_.display_name }) }
                    foreach ($column in $columnNames) {
                        if (@($newColumns | Where-Object display_name -eq $column).Count -ne 1) {
                            throw "Missing/ambiguous selected column '$column' in '$($target.Node.display_name)'"
                        }
                    }
                    $tableContracts += [pscustomobject]@{
                        Name = [string]$current.Node.display_name; Schema = $current.Schema
                        Id = [string]$current.Node.id; Columns = @($columnNames)
                    }
                }
                foreach ($function in $functions) {
                    $matches = @($currentObjects | Where-Object { $_.Node.type -in @('kusto.function', 'function') -and $_.Node.display_name -eq $function })
                    if ($matches.Count -ne 1 -or -not $matches[0].Node.PSObject.Properties['id'] -or -not $matches[0].Node.id) {
                        throw "Missing/ambiguous current function '$function' in '$path'"
                    }
                    $functionIds[$function] = [string]$matches[0].Node.id
                }
                $value.elements = $draft.elements
                $tableNames = @($tableContracts | ForEach-Object { $_.Name })
                foreach ($element in @($value.elements)) {
                    if ($kind -eq 'lakehouse') {
                        $null = Update-DataAgentLakehouseElementSelection -Node $element -TargetTables $tableNames
                    } else {
                        $null = Update-DataAgentKustoElementSelection -Node $element -TargetTables $tableNames -TargetFunctions $functions
                    }
                }
                foreach ($table in $tableContracts) {
                    $node = @($currentObjects | Where-Object { $_.Node.type -eq $tableType -and $_.Node.id -eq $table.Id })[0].Node
                    foreach ($column in @(Get-DataAgentSelectionNodes -Elements @($node) | Where-Object type -in @('lakehouse_tables.column', 'kusto.column'))) {
                        Set-DataAgentSelectionValue -Node $column -Selected ($column.display_name -in $table.Columns)
                    }
                }
                $contract = [pscustomobject]@{
                    Path = $path; Kind = $kind; ArtifactId = $value.artifactId; WorkspaceId = $value.workspaceId
                    Tables = @($tableContracts); Functions = @($functions); FunctionIds = $functionIds
                    Settings = Get-DataAgentCanonicalJson $publishedSettings
                }
                Assert-DataAgentRefreshSelection -Datasource $value -Contract $contract
                $contracts += $contract
            }
        }
        $writable += Write-DataAgentDefinitionPart -Path $path -Value $value
    }
    $draftOnly = @($parts | Where-Object {
        $_.path.StartsWith('Files/Config/draft/') -and $_.path.Replace('/draft/', '/published/') -notin $published.path
    })
    if ($draftOnly.Count) { throw "Unpublished definition parts: $($draftOnly.path -join ', ')" }
    if (-not $contracts.Count) { throw 'No supported published lakehouse/KQL sources found' }
    return [pscustomobject]@{
        Definition = @{ parts = @($writable) }; Contracts = @($contracts)
        Fingerprint = Get-DataAgentDefinitionFingerprint -Definition $Definition
    }
}

function Assert-DataAgentRefreshDefinition {
    param([Parameter(Mandatory)][object]$Definition, [Parameter(Mandatory)][object]$Plan)
    foreach ($contract in $Plan.Contracts) {
        foreach ($stage in @('draft', 'published')) {
            $path = $contract.Path.Replace('/draft/', "/$stage/")
            $part = @($Definition.definition.parts | Where-Object path -eq $path)
            if ($part.Count -ne 1) { throw "Verification missing/ambiguous definition part: $path" }
            Assert-DataAgentRefreshSelection -Datasource (Read-DataAgentDefinitionPart -Part $part[0]) -Contract $contract
        }
    }
    foreach ($expected in $Plan.Definition.parts) {
        if ($expected.path -in $Plan.Contracts.Path) { continue }
        $paths = if ($expected.path.StartsWith('Files/Config/draft/')) {
            @($expected.path, $expected.path.Replace('/draft/', '/published/'))
        } else { @($expected.path) }
        foreach ($path in $paths) {
            $actual = @($Definition.definition.parts | Where-Object path -eq $path)
            if ($actual.Count -ne 1 -or
                (Get-DataAgentCanonicalJson (Read-DataAgentDefinitionPart $actual[0])) -ne
                (Get-DataAgentCanonicalJson (Read-DataAgentDefinitionPart $expected))) {
                throw "Non-table configuration changed unexpectedly: $path"
            }
        }
    }
}

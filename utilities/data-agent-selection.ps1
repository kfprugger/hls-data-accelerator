function Set-DataAgentSelectionValue {
    param([Parameter(Mandatory)][object]$Node, [Parameter(Mandatory)][bool]$Selected)
    if ($Node.PSObject.Properties['is_selected']) {
        $Node.is_selected = $Selected
    } else {
        $Node | Add-Member -NotePropertyName is_selected -NotePropertyValue $Selected
    }
}

function Update-DataAgentLakehouseElementSelection {
    param(
        [Parameter(Mandatory)][object]$Node,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$TargetTables,
        [object]$ParentTableSelected = $null
    )
    $nodeType = [string]$Node.type
    $children = if ($Node.PSObject.Properties['children']) { @($Node.children) } else { @() }
    if ($nodeType -eq 'lakehouse_tables.table') {
        $selected = $TargetTables -contains [string]$Node.display_name
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        foreach ($child in $children) {
            $null = Update-DataAgentLakehouseElementSelection -Node $child -TargetTables $TargetTables -ParentTableSelected $selected
        }
        return $selected
    }
    if ($nodeType -eq 'lakehouse_tables.column') {
        $selected = $null -ne $ParentTableSelected -and [bool]$ParentTableSelected
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        return $selected
    }
    $childSelected = $false
    foreach ($child in $children) {
        if (Update-DataAgentLakehouseElementSelection -Node $child -TargetTables $TargetTables -ParentTableSelected $ParentTableSelected) { $childSelected = $true }
    }
    if ($nodeType -in @('schema_grouping', 'lakehouse_tables.schema', 'table_grouping')) {
        Set-DataAgentSelectionValue -Node $Node -Selected $childSelected
    }
    return $childSelected
}

function Update-DataAgentKustoElementSelection {
    param(
        [Parameter(Mandatory)][object]$Node,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$TargetTables,
        [string[]]$TargetFunctions = @(),
        [object]$ParentTableSelected = $null
    )
    $nodeType = [string]$Node.type
    $children = if ($Node.PSObject.Properties['children']) { @($Node.children) } else { @() }
    if ($nodeType -eq 'kusto.table') {
        $selected = $TargetTables -contains [string]$Node.display_name
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        foreach ($child in $children) {
            $null = Update-DataAgentKustoElementSelection -Node $child -TargetTables $TargetTables -TargetFunctions $TargetFunctions -ParentTableSelected $selected
        }
        return $selected
    }
    if ($nodeType -eq 'kusto.column') {
        $selected = $null -ne $ParentTableSelected -and [bool]$ParentTableSelected
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        return $selected
    }
    if ($nodeType -in @('kusto.function', 'function')) {
        $selected = $TargetFunctions -contains [string]$Node.display_name
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        return $selected
    }
    $childSelected = $false
    foreach ($child in $children) {
        if (Update-DataAgentKustoElementSelection -Node $child -TargetTables $TargetTables -TargetFunctions $TargetFunctions -ParentTableSelected $ParentTableSelected) { $childSelected = $true }
    }
    if ($nodeType -in @('schema_grouping', 'table_grouping', 'function_grouping', 'kusto.functions')) {
        $groupSelected = $childSelected -or ($nodeType -in @('function_grouping', 'kusto.functions') -and $TargetFunctions.Count -gt 0 -and $children.Count -eq 0)
        Set-DataAgentSelectionValue -Node $Node -Selected $groupSelected
        return $groupSelected
    }
    return $childSelected
}

function Get-SelectedDataAgentTables {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Elements,
        [Parameter(Mandatory)][ValidateSet('lakehouse', 'kusto')][string]$SelectionKind
    )
    $tableType = if ($SelectionKind -eq 'lakehouse') { 'lakehouse_tables.table' } else { 'kusto.table' }
    return @(Get-DataAgentSelectionNodes -Elements $Elements |
        Where-Object { $_.type -eq $tableType -and $_.PSObject.Properties['is_selected'] -and $_.is_selected } |
        ForEach-Object { [string]$_.display_name } | Sort-Object -Unique)
}

function Get-SelectedDataAgentFunctions {
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Elements)
    return @(Get-DataAgentSelectionNodes -Elements $Elements |
        Where-Object { $_.type -in @('kusto.function', 'function') -and $_.PSObject.Properties['is_selected'] -and $_.is_selected } |
        ForEach-Object { [string]$_.display_name } | Sort-Object -Unique)
}

function Get-DataAgentSelectionNodes {
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Elements)
    foreach ($element in $Elements) {
        $element
        if ($element.PSObject.Properties['children'] -and $element.children) {
            Get-DataAgentSelectionNodes -Elements @($element.children)
        }
    }
}

function Set-DataAgentNativeSchemaSelection {
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$DataAgentId,
        [Parameter(Mandatory)][string]$DatasourceId,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Tables,
        [string[]]$Functions = @(),
        [string]$Schema = 'dbo',
        [switch]$VerifyOnly,
        [switch]$Published,
        [Parameter(Mandatory)][scriptblock]$InvokeApi
    )
    if ($Published -and -not $VerifyOnly) { throw 'Published selections are read-only; use -VerifyOnly.' }
    $stagePrefix = if ($Published) { '' } else { 'staging/' }
    $endpoint = "/workspaces/$WorkspaceId/dataAgents/$DataAgentId/${stagePrefix}datasources/$DatasourceId/elements"
    function Read-NativeObjects([string]$RootId = '', [string]$CurrentSchema = '') {
        $continuation = ''
        do {
            $query = @()
            if ($RootId) { $query += "rootId=$([uri]::EscapeDataString($RootId))" }
            if ($continuation) { $query += "continuationToken=$([uri]::EscapeDataString($continuation))" }
            $uri = $endpoint + $(if ($query.Count) { '?' + ($query -join '&') } else { '' })
            $page = & $InvokeApi 'GET' $uri $null
            foreach ($element in @($page.value)) {
                $nextSchema = if ($element.type -eq 'Schema') { [string]$element.displayName } else { $CurrentSchema }
                if ($element.type -in @('Table', 'Function')) {
                    [pscustomobject]@{ Element = $element; Schema = $nextSchema }
                } elseif ($element.type -in @('Schemas', 'Schema', 'Tables', 'Functions') -and $element.hasSubElements) {
                    Read-NativeObjects -RootId ([string]$element.id) -CurrentSchema $nextSchema
                }
            }
            $continuation = if ($page.PSObject.Properties['continuationToken']) { [string]$page.continuationToken } else { '' }
        } while ($continuation)
    }
    $objects = @(Read-NativeObjects)
    foreach ($target in @($Tables | ForEach-Object { @{ Name = $_; Type = 'Table' } }) + @($Functions | ForEach-Object { @{ Name = $_; Type = 'Function' } })) {
        $match = @($objects | Where-Object {
            $_.Element.type -eq $target.Type -and $_.Element.displayName -eq $target.Name -and
            ($target.Type -ne 'Table' -or -not $_.Schema -or $_.Schema -eq $Schema)
        })
        if ($match.Count -ne 1 -or -not $match[0].Element.id -or $match[0].Element.state -ne 'Available') {
            throw "Missing, ambiguous, or unavailable native $($target.Type) '$($target.Name)' in datasource '$DatasourceId'. No selection updates were made."
        }
    }
    if (-not $VerifyOnly) {
    foreach ($object in $objects) {
        $element = $object.Element
        $selected = if ($element.type -eq 'Function') { $element.displayName -in $Functions } else {
            $element.displayName -in $Tables -and (-not $object.Schema -or $object.Schema -eq $Schema)
        }
        if ([bool]$element.isSelected -eq $selected) { continue }
        $null = & $InvokeApi 'PATCH' "${endpoint}?id=$([uri]::EscapeDataString([string]$element.id))" @{ isSelected = $selected }
    }
    }
    $actual = if ($VerifyOnly) { $objects } else { @(Read-NativeObjects) }
    $actualTables = @($actual | Where-Object { $_.Element.type -eq 'Table' -and $_.Element.isSelected } | ForEach-Object { $_.Element.displayName } | Sort-Object -Unique)
    $actualFunctions = @($actual | Where-Object { $_.Element.type -eq 'Function' -and $_.Element.isSelected } | ForEach-Object { $_.Element.displayName } | Sort-Object -Unique)
    if (($actualTables -join '|') -ne (($Tables | Sort-Object -Unique) -join '|') -or
        ($actualFunctions -join '|') -ne (($Functions | Sort-Object -Unique) -join '|')) {
        throw "Native datasource selections did not match the requested table/function contract: $DatasourceId"
    }
}

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

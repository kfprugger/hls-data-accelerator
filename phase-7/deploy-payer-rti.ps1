[CmdletBinding()]
param (
    [string]$FabricWorkspaceName,
    [string]$ResourceGroupName,
    [string]$Location = "eastus",
    [string]$EventHubNamespace = "",
    [string]$FabricApiBase = "https://api.fabric.microsoft.com/v1",
    [string]$PayerOpsEmail = "",
    [int]$ClaimEventRatePerMinute = 60,
    [hashtable]$Tags = @{},
    [switch]$SkipPayerRti,
    [switch]$SkipClaimEmulator,
    [switch]$SkipSnapshotMaterialization,
    [switch]$SkipPayerActivator,
    [switch]$SkipOpsAgent,
    [switch]$SkipGraphAgent,
    [string]$ExpectedTenantId = "8d038e6a-9b7d-4cb8-bbcf-e84dff156478",
    [string]$ExpectedSubscriptionId = "9bbee190-dc61-4c58-ab47-1275cb04018f"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$script:AccessTokenCache = @{}

function Get-AccessTokenForResource {
    param ([string]$ResourceUrl)
    $key = $ResourceUrl.ToLowerInvariant()
    $cached = $script:AccessTokenCache[$key]
    if ($cached -and $cached.ExpiresOn -gt (Get-Date).AddMinutes(5)) { return $cached.Token }

    $tokenObj = Get-AzAccessToken -ResourceUrl $ResourceUrl -ErrorAction Stop
    $rawToken = $tokenObj.Token
    if ($rawToken -is [System.Security.SecureString]) {
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($rawToken)
        try { $rawToken = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    } elseif ($rawToken -isnot [string]) {
        $rawToken = $rawToken | ConvertFrom-SecureString -AsPlainText
    }
    $script:AccessTokenCache[$key] = @{ Token = $rawToken; ExpiresOn = $tokenObj.ExpiresOn }
    return $rawToken
}

function Get-FabricAccessToken { return Get-AccessTokenForResource -ResourceUrl "https://api.fabric.microsoft.com" }
function Get-KustoAccessToken { return Get-AccessTokenForResource -ResourceUrl "https://api.kusto.windows.net" }

function Invoke-FabricApi {
    param (
        [string]$Method = "GET",
        [string]$Endpoint,
        [object]$Body = $null,
        [int]$MaxRetries = 3
    )
    $token = Get-FabricAccessToken
    $headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
    $uri = "$FabricApiBase$Endpoint"
    $bodyJson = if ($Body) { $Body | ConvertTo-Json -Depth 30 } else { $null }
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        try {
            $params = @{ Method = $Method; Uri = $uri; Headers = $headers }
            if ($bodyJson -and $Method -ne "GET") { $params["Body"] = $bodyJson }
            return Invoke-RestMethod @params
        } catch {
            $statusCode = $null
            try { $statusCode = [int]$_.Exception.Response.StatusCode } catch {}
            $message = Get-ErrorMessage $_
            $isTransientInbound = $statusCode -eq 403 -and $message -match "RequestDeniedByInboundPolicy|inbound communication policy"
            if (($statusCode -eq 429 -or $isTransientInbound) -and $attempt -lt $MaxRetries) {
                $retryAfter = if ($isTransientInbound) { 15 } else { 30 }
                try { $retryAfter = [int]$_.Exception.Response.Headers["Retry-After"] } catch {}
                $reason = if ($isTransientInbound) { "Fabric inbound policy denied request" } else { "Rate limited" }
                Write-Host "  $reason. Waiting ${retryAfter}s... (attempt $attempt/$MaxRetries)" -ForegroundColor Yellow
                Start-Sleep -Seconds $retryAfter
                continue
            }
            throw $_
        }
    }
}

function Invoke-KustoMgmt {
    param (
        [string]$Command,
        [string]$Label,
        [string]$KustoUri,
        [string]$DatabaseName,
        [hashtable]$KustoHeaders
    )
    $body = @{ db = $DatabaseName; csl = $Command } | ConvertTo-Json -Depth 4 -Compress
    try {
        $null = Invoke-RestMethod -Uri "$KustoUri/v1/rest/mgmt" -Headers $KustoHeaders -Method POST -Body $body
        Write-Host "  ✓ $Label" -ForegroundColor Green
        return $true
    } catch {
        $errBody = $_.ErrorDetails.Message
        try { $parsed = $errBody | ConvertFrom-Json; $msg = $parsed.error.message } catch { $msg = $errBody }
        if ($msg -match "already exists") {
            Write-Host "  ✓ $Label (already exists)" -ForegroundColor Yellow
            return $true
        }
        Write-Host "  ✗ $Label" -ForegroundColor Red
        if ($msg) { Write-Host "    $msg" -ForegroundColor DarkRed } else { Write-Host "    $($_.Exception.Message)" -ForegroundColor DarkRed }
        return $false
    }
}

function Get-AcrImageMetadata {
    param(
        [Parameter(Mandatory)][string]$Registry,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag
    )

    $raw = az acr manifest list-metadata --registry $Registry --name $Repository --query "[?tags[?contains(@, '$Tag')]][0].{digest:digest, createdTime:createdTime, lastUpdateTime:lastUpdateTime}" -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw) -or $raw -eq "null") { return $null }
    return $raw | ConvertFrom-Json
}

function Test-AcrImageUpdated {
    param(
        [object]$Metadata,
        [string]$PreviousDigest,
        [datetime]$StartedUtc
    )

    if (-not $Metadata) { return $false }
    if (-not $PreviousDigest) { return $true }
    if ($Metadata.digest -and $Metadata.digest -ne $PreviousDigest) { return $true }

    $lastUpdate = $null
    if ($Metadata.lastUpdateTime) {
        try { $lastUpdate = [datetime]::Parse($Metadata.lastUpdateTime).ToUniversalTime() } catch { $lastUpdate = $null }
    }
    return ($lastUpdate -and $lastUpdate -ge $StartedUtc.AddMinutes(-1))
}

function Invoke-AcrBuildWithTagVerification {
    param(
        [Parameter(Mandatory)][string]$Registry,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$ContextPath,
        [int]$RemoteCompletionWaitSeconds = 300
    )

    $before = Get-AcrImageMetadata -Registry $Registry -Repository $Repository -Tag $Tag
    $previousDigest = if ($before) { $before.digest } else { $null }
    $startedUtc = (Get-Date).ToUniversalTime()
    az acr build --registry $Registry --image "${Repository}:${Tag}" $ContextPath
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -eq 0) { return }

    Write-Host "  ⚠ ACR build command returned non-zero exit code ($buildExitCode); polling for remote completion..." -ForegroundColor Yellow
    $deadline = (Get-Date).AddSeconds($RemoteCompletionWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 15
        $metadata = Get-AcrImageMetadata -Registry $Registry -Repository $Repository -Tag $Tag
        if (Test-AcrImageUpdated -Metadata $metadata -PreviousDigest $previousDigest -StartedUtc $startedUtc) {
            Write-Host "  ✓ Image ${Repository}:${Tag} is present/updated in ACR after command disconnect — continuing" -ForegroundColor Yellow
            return
        }
    }

    throw "ACR build failed and ${Repository}:${Tag} was not published. Exit code: $buildExitCode"
}
function Wait-FabricItem {
    param (
        [string]$WorkspaceId,
        [string]$ItemType,
        [string]$ItemName,
        [int]$TimeoutSeconds = 120
    )
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $items = Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/items?type=$ItemType"
            $found = $items.value | Where-Object { $_.displayName -eq $ItemName }
            if ($found) { if ($found -is [array]) { return $found[0] }; return $found }
        } catch {}
        Start-Sleep -Seconds 5
        $elapsed += 5
        Write-Host "  Waiting for $ItemType '$ItemName'... (${elapsed}s)" -ForegroundColor Gray
    }
    throw "Timed out waiting for $ItemType '$ItemName' after ${TimeoutSeconds}s"
}

function ConvertTo-Base64 {
    param ([string]$Text)
    [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text))
}

function Get-ErrorMessage {
    param($ErrorRecord)
    $msg = $ErrorRecord.Exception.Message
    try {
        $detail = $ErrorRecord.ErrorDetails.Message | ConvertFrom-Json
        if ($detail.message) { $msg = $detail.message }
        if ($detail.error.message) { $msg = $detail.error.message }
    } catch {}
    return $msg
}

function Invoke-KqlScriptFile {
    param(
        [string]$Path,
        [string]$KustoUri,
        [string]$DatabaseName,
        [hashtable]$KustoHeaders
    )

    function Add-CurrentKqlCommand {
        param(
            [System.Collections.Generic.List[string]]$Current,
            [System.Collections.Generic.List[string]]$Commands
        )
        while ($Current.Count -gt 0) {
            $last = $Current[$Current.Count - 1]
            if ($last -match '^\s*(//.*)?$') { $Current.RemoveAt($Current.Count - 1); continue }
            break
        }
        $command = ($Current -join "`n").Trim()
        if (-not [string]::IsNullOrWhiteSpace($command)) { $Commands.Add($command) }
        $Current.Clear()
    }

    $lines = Get-Content $Path
    $commands = New-Object System.Collections.Generic.List[string]
    $current = New-Object System.Collections.Generic.List[string]
    $inFence = $false
    foreach ($line in $lines) {
        if ($line.Trim() -eq "``````") { $inFence = -not $inFence }
        if (-not $inFence -and $line -match '^\s*\.' -and $current.Count -gt 0) {
            Add-CurrentKqlCommand -Current $current -Commands $commands
        }
        if ($current.Count -gt 0 -or $line -match '^\s*\.') { $current.Add($line) }
    }
    if ($current.Count -gt 0) { Add-CurrentKqlCommand -Current $current -Commands $commands }

    $success = 0; $fail = 0
    foreach ($cmd in $commands) {
        if ([string]::IsNullOrWhiteSpace($cmd)) { continue }
        $firstLine = @($cmd -split "`n" | Where-Object { $_.Trim() })[0].Trim()
        $label = $firstLine
        if ($label.Length -gt 110) { $label = $label.Substring(0, 110) + "..." }
        if (Invoke-KustoMgmt -Command $cmd -Label $label -KustoUri $KustoUri -DatabaseName $DatabaseName -KustoHeaders $KustoHeaders) { $success++ } else { $fail++ }
    }
    Write-Host "  KQL commands: $success succeeded, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
    return @{ Success = $success; Fail = $fail }
}

function Update-DataAgentDefinition {
    param([string]$WorkspaceId, [string]$DataAgentId, [object]$Definition)
    $headers = @{ Authorization = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json" }
    $body = @{ definition = $Definition } | ConvertTo-Json -Depth 30
    $response = Invoke-WebRequest -Method POST `
        -Uri "$FabricApiBase/workspaces/$WorkspaceId/dataAgents/$DataAgentId/updateDefinition" `
        -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
    if ($response.StatusCode -eq 200) { return }
    if ($response.StatusCode -ne 202) { throw "DataAgent definition update returned HTTP $($response.StatusCode)" }

    $location = $response.Headers["Location"]
    if ($location -is [array]) { $location = $location[0] }
    if (-not $location) { throw "DataAgent definition update returned 202 without a Location header" }
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        Start-Sleep 5
        $headers.Authorization = "Bearer $(Get-FabricAccessToken)"
        $operation = Invoke-RestMethod -Uri $location -Headers $headers -Method GET -TimeoutSec 120 -ErrorAction Stop
        if ($operation.status -eq "Succeeded") { return }
        if ($operation.status -eq "Failed") { throw "DataAgent definition update failed: $($operation.error.message)" }
    }
    throw "DataAgent definition update did not complete within 5 minutes"
}

function Publish-DataAgentDefinition {
    param([string]$WorkspaceId, [string]$DataAgentId, [string]$Description)
    $headers = @{ Authorization = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json" }
    $body = @{ publishedDescription = $Description } | ConvertTo-Json -Depth 5
    $response = Invoke-WebRequest -Method POST `
        -Uri "$FabricApiBase/workspaces/$WorkspaceId/dataAgents/$DataAgentId/staging/publish" `
        -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
    if ($response.StatusCode -eq 200) { return }
    if ($response.StatusCode -ne 202) { throw "DataAgent publish returned HTTP $($response.StatusCode)" }

    $location = $response.Headers["Location"]
    if ($location -is [array]) { $location = $location[0] }
    if (-not $location) { throw "DataAgent publish returned 202 without a Location header" }
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        Start-Sleep 5
        $headers.Authorization = "Bearer $(Get-FabricAccessToken)"
        $operation = Invoke-RestMethod -Uri $location -Headers $headers -Method GET -TimeoutSec 120 -ErrorAction Stop
        if ($operation.status -eq "Succeeded") { return }
        if ($operation.status -eq "Failed") { throw "DataAgent publish failed: $($operation.error.message)" }
    }
    throw "DataAgent publish did not complete within 5 minutes"
}

function Get-DataAgentDefinition {
    param([string]$WorkspaceId, [string]$DataAgentId)
    $headers = @{ Authorization = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json" }
    $response = Invoke-WebRequest -Method POST `
        -Uri "$FabricApiBase/workspaces/$WorkspaceId/items/$DataAgentId/getDefinition" `
        -Headers $headers -Body '{}' -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        return $response.Content | ConvertFrom-Json -Depth 100
    }
    if ($response.StatusCode -ne 202) { throw "DataAgent getDefinition returned HTTP $($response.StatusCode)" }

    $location = $response.Headers["Location"]
    if ($location -is [array]) { $location = $location[0] }
    if (-not $location) { throw "DataAgent getDefinition returned 202 without a Location header" }
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        Start-Sleep 2
        $headers.Authorization = "Bearer $(Get-FabricAccessToken)"
        $operation = Invoke-RestMethod -Uri $location -Headers $headers -Method GET -TimeoutSec 120 -ErrorAction Stop
        if ($operation.status -eq "Succeeded") {
            return Invoke-RestMethod -Uri "$location/result" -Headers $headers -Method GET -TimeoutSec 120 -ErrorAction Stop
        }
        if ($operation.status -eq "Failed") { throw "DataAgent getDefinition failed: $($operation.error.message)" }
    }
    throw "DataAgent getDefinition did not complete within 2 minutes"
}

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
        [Parameter(Mandatory)][string[]]$TargetTables,
        [object]$ParentTableSelected = $null
    )
    $nodeType = [string]$Node.type
    if ($nodeType -eq 'lakehouse_tables.table') {
        $selected = $TargetTables -contains [string]$Node.display_name
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        foreach ($child in @($Node.children)) {
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
    foreach ($child in @($Node.children)) {
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
        [Parameter(Mandatory)][string[]]$TargetTables,
        [string[]]$TargetFunctions = @(),
        [object]$ParentTableSelected = $null
    )
    $nodeType = [string]$Node.type
    if ($nodeType -eq 'kusto.table') {
        $selected = $TargetTables -contains [string]$Node.display_name
        Set-DataAgentSelectionValue -Node $Node -Selected $selected
        foreach ($child in @($Node.children)) {
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
    foreach ($child in @($Node.children)) {
        if (Update-DataAgentKustoElementSelection -Node $child -TargetTables $TargetTables -TargetFunctions $TargetFunctions -ParentTableSelected $ParentTableSelected) { $childSelected = $true }
    }
    if ($nodeType -in @('schema_grouping', 'table_grouping', 'function_grouping', 'kusto.functions')) {
        $groupSelected = $childSelected -or ($nodeType -in @('function_grouping', 'kusto.functions') -and $TargetFunctions.Count -gt 0 -and @($Node.children).Count -eq 0)
        Set-DataAgentSelectionValue -Node $Node -Selected $groupSelected
        return $groupSelected
    }
    return $childSelected
}

function Get-SelectedDataAgentTables {
    param(
        [Parameter(Mandatory)][object[]]$Elements,
        [Parameter(Mandatory)][ValidateSet('lakehouse', 'kusto')][string]$SelectionKind
    )
    $tableType = if ($SelectionKind -eq 'lakehouse') { 'lakehouse_tables.table' } else { 'kusto.table' }
    $selected = [System.Collections.Generic.List[string]]::new()
    function Visit-DataAgentElement {
        param([object]$Node)
        if ([string]$Node.type -eq $tableType -and [bool]$Node.is_selected) { $selected.Add([string]$Node.display_name) }
        foreach ($child in @($Node.children)) { Visit-DataAgentElement -Node $child }
    }
    foreach ($element in $Elements) { Visit-DataAgentElement -Node $element }
    return @($selected | Sort-Object -Unique)
}
function Get-SelectedDataAgentFunctions {
    param([Parameter(Mandatory)][object[]]$Elements)
    $selected = [System.Collections.Generic.List[string]]::new()
    function Visit-DataAgentFunction {
        param([object]$Node)
        if ([string]$Node.type -in @('kusto.function', 'function') -and [bool]$Node.is_selected) {
            $selected.Add([string]$Node.display_name)
        }
        foreach ($child in @($Node.children)) { Visit-DataAgentFunction -Node $child }
    }
    foreach ($element in $Elements) { Visit-DataAgentFunction -Node $element }
    return @($selected | Sort-Object -Unique)
}


function Repair-DataAgentTableSelection {
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$DataAgentId,
        [Parameter(Mandatory)][string]$DatasourceFolderName,
        [Parameter(Mandatory)][string[]]$Tables,
        [string[]]$Functions = @(),
        [Parameter(Mandatory)][ValidateSet('lakehouse', 'kusto')][string]$SelectionKind
    )
    $definition = Get-DataAgentDefinition -WorkspaceId $WorkspaceId -DataAgentId $DataAgentId
    $targetPath = "Files/Config/draft/$DatasourceFolderName/datasource.json"
    $parts = @($definition.definition.parts)
    $targetPart = $parts | Where-Object { $_.path -eq $targetPath } | Select-Object -First 1
    if (-not $targetPart) { throw "Hydrated DataAgent datasource '$targetPath' was not found" }
    $datasource = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$targetPart.payload)) | ConvertFrom-Json -Depth 100
    foreach ($element in @($datasource.elements)) {
        if ($SelectionKind -eq 'lakehouse') {
            $null = Update-DataAgentLakehouseElementSelection -Node $element -TargetTables $Tables
        } else {
            $null = Update-DataAgentKustoElementSelection -Node $element -TargetTables $Tables -TargetFunctions $Functions
        }
    }
    $selected = @(Get-SelectedDataAgentTables -Elements @($datasource.elements) -SelectionKind $SelectionKind)
    $selectedFunctions = if ($SelectionKind -eq 'kusto') { @(Get-SelectedDataAgentFunctions -Elements @($datasource.elements)) } else { @() }
    $missing = @($Tables | Where-Object { $_ -notin $selected })
    $unexpected = @($selected | Where-Object { $_ -notin $Tables })
    $missingFunctions = @($Functions | Where-Object { $_ -notin $selectedFunctions })
    $unexpectedFunctions = @($selectedFunctions | Where-Object { $_ -notin $Functions })
    if ($missing.Count -gt 0 -or $unexpected.Count -gt 0 -or $missingFunctions.Count -gt 0 -or $unexpectedFunctions.Count -gt 0) {
        throw "Hydrated $SelectionKind selection mismatch. Missing=$($missing -join ','); Unexpected=$($unexpected -join ','); MissingFunctions=$($missingFunctions -join ','); UnexpectedFunctions=$($unexpectedFunctions -join ',')"
    }
    $targetPart.payload = ConvertTo-Base64 ($datasource | ConvertTo-Json -Depth 100)
    $targetPart.payloadType = 'InlineBase64'
    $writableParts = @($parts | Where-Object { $_.path -eq 'Files/Config/data_agent.json' -or $_.path.StartsWith('Files/Config/draft/') })
    Update-DataAgentDefinition -WorkspaceId $WorkspaceId -DataAgentId $DataAgentId -Definition @{ parts = $writableParts }
    Write-Host "  ✓ Hydrated $SelectionKind selections applied: tables=$($selected -join ', '); functions=$($selectedFunctions -join ', ')" -ForegroundColor Green
}

function Assert-DataAgentTableSelection {
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$DataAgentId,
        [Parameter(Mandatory)][string]$DatasourceFolderName,
        [Parameter(Mandatory)][string[]]$Tables,
        [string[]]$Functions = @(),
        [Parameter(Mandatory)][ValidateSet('lakehouse', 'kusto')][string]$SelectionKind
    )
    $definition = Get-DataAgentDefinition -WorkspaceId $WorkspaceId -DataAgentId $DataAgentId
    foreach ($scope in @('draft', 'published')) {
        $path = "Files/Config/$scope/$DatasourceFolderName/datasource.json"
        $part = @($definition.definition.parts) | Where-Object { $_.path -eq $path } | Select-Object -First 1
        if (-not $part) { throw "DataAgent datasource '$path' was not found" }
        $datasource = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$part.payload)) | ConvertFrom-Json -Depth 100
        $selected = @(Get-SelectedDataAgentTables -Elements @($datasource.elements) -SelectionKind $SelectionKind)
        $selectedFunctions = if ($SelectionKind -eq 'kusto') { @(Get-SelectedDataAgentFunctions -Elements @($datasource.elements)) } else { @() }
        if (@($Tables | Where-Object { $_ -notin $selected }).Count -gt 0 -or @($selected | Where-Object { $_ -notin $Tables }).Count -gt 0 -or @($Functions | Where-Object { $_ -notin $selectedFunctions }).Count -gt 0 -or @($selectedFunctions | Where-Object { $_ -notin $Functions }).Count -gt 0) {
            throw "$scope $SelectionKind selections do not match the requested contract: tables=$($selected -join ', '); functions=$($selectedFunctions -join ', ')"
        }
    }
    Write-Host "  ✓ Draft and published $SelectionKind table/function selections verified" -ForegroundColor Green
}

function Deploy-DataAgent {
    param (
        [string]$Name,
        [string]$AiInstructions,
        [array]$DataSources,
        [string]$WorkspaceId,
        [string]$Description = ""
    )
    Write-Host "  Deploying Data Agent: $Name" -ForegroundColor White
    $agentId = $null
    try {
        $existingItems = Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/items?type=DataAgent"
        $existing = $existingItems.value | Where-Object { $_.displayName -eq $Name }
        if ($existing) { if ($existing -is [array]) { $existing = $existing[0] }; $agentId = $existing.id }
    } catch {
        Write-Host "  ⚠ Could not list DataAgent items. Trying creation..." -ForegroundColor Yellow
    }

    if (-not $agentId) {
        try {
            $createBody = @{ displayName = $Name; type = "DataAgent" }
            if (-not [string]::IsNullOrWhiteSpace($Description)) { $createBody["description"] = $Description }
            $resp = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$WorkspaceId/items" -Body $createBody
            $agentId = $resp.id
            Write-Host "  ✓ Created DataAgent: $Name ($agentId)" -ForegroundColor Green
        } catch {
            throw "Failed to create DataAgent ${Name}: $(Get-ErrorMessage $_)"
        }
    } else {
        Write-Host "  ✓ DataAgent exists: $Name ($agentId)" -ForegroundColor Green
    }

    $dataAgentJson = @{ '$schema' = "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataAgent/2.1.0/schema.json" } | ConvertTo-Json -Depth 5
    $stageConfigJson = @{ '$schema' = "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/stageConfiguration/1.0.0/schema.json"; aiInstructions = $AiInstructions } | ConvertTo-Json -Depth 5
    $parts = [System.Collections.ArrayList]@(
        @{ path = "Files/Config/data_agent.json"; payload = (ConvertTo-Base64 $dataAgentJson); payloadType = "InlineBase64" },
        @{ path = "Files/Config/draft/stage_config.json"; payload = (ConvertTo-Base64 $stageConfigJson); payloadType = "InlineBase64" }
    )
    foreach ($ds in $DataSources) {
        $null = $parts.Add(@{ path = "Files/Config/draft/$($ds.FolderName)/datasource.json"; payload = (ConvertTo-Base64 $ds.DatasourceJson); payloadType = "InlineBase64" })
        $null = $parts.Add(@{ path = "Files/Config/draft/$($ds.FolderName)/fewshots.json"; payload = (ConvertTo-Base64 $ds.FewShotsJson); payloadType = "InlineBase64" })
    }
    $selectableDataSources = @($DataSources | Where-Object {
        $_ -is [hashtable] -and $_.ContainsKey('SelectionKind') -and
        ((@($_.SelectedTables).Count -gt 0) -or (@($_.SelectedFunctions).Count -gt 0))
    })
    try {
        Update-DataAgentDefinition `
            -WorkspaceId $WorkspaceId `
            -DataAgentId $agentId `
            -Definition @{ parts = @($parts) }
        Write-Host "  ✓ DataAgent definition applied: $Name" -ForegroundColor Green
    } catch {
        throw "DataAgent definition update failed for ${Name}: $(Get-ErrorMessage $_)"
    }
    try {
        foreach ($ds in $selectableDataSources) {
            Repair-DataAgentTableSelection `
                -WorkspaceId $WorkspaceId `
                -DataAgentId $agentId `
                -DatasourceFolderName ([string]$ds.FolderName) `
                -Tables @($ds.SelectedTables) `
                -Functions @($ds.SelectedFunctions) `
                -SelectionKind ([string]$ds.SelectionKind)
        }
    } catch {
        throw "DataAgent hydrated table selection repair failed for ${Name}: $(Get-ErrorMessage $_)"
    }
    try {
        $publishDescription = if ([string]::IsNullOrWhiteSpace($Description)) { "$Name production configuration" } else { $Description }
        Publish-DataAgentDefinition -WorkspaceId $WorkspaceId -DataAgentId $agentId -Description $publishDescription
        Write-Host "  ✓ DataAgent published: $Name" -ForegroundColor Green
    } catch {
        throw "DataAgent publish failed for ${Name}: $(Get-ErrorMessage $_)"
    }
    try {
        foreach ($ds in $selectableDataSources) {
            Assert-DataAgentTableSelection `
                -WorkspaceId $WorkspaceId `
                -DataAgentId $agentId `
                -DatasourceFolderName ([string]$ds.FolderName) `
                -Tables @($ds.SelectedTables) `
                -Functions @($ds.SelectedFunctions) `
                -SelectionKind ([string]$ds.SelectionKind)
        }
    } catch {
        throw "DataAgent published table selection verification failed for ${Name}: $(Get-ErrorMessage $_)"
    }
    Write-Host "  ✓ Agent URL: https://app.fabric.microsoft.com/groups/$WorkspaceId/aiskills/$agentId" -ForegroundColor Cyan
    return $agentId
}

function New-KqlDatasource {
    param([string]$DisplayName, [string]$KqlDbId, [string]$WorkspaceId, [array]$Elements, [array]$FewShots, [string]$Instructions, [string[]]$Functions = @())
    $datasourceElements = @($Elements)
    if ($Functions.Count -gt 0) {
        $datasourceElements += @{ id = [guid]::NewGuid().ToString(); display_name = 'Functions'; type = 'kusto.functions'; is_selected = $true; children = @() }
    }
    $datasourceJson = (@{
        '$schema' = "1.0.0"
        artifactId = $KqlDbId
        workspaceId = $WorkspaceId
        displayName = $DisplayName
        type = "kusto"
        userDescription = "KQL database with clinical telemetry, payer RTI claim streams, fraud/high-cost/care-gap scoring tables, and operations worklist functions"
        dataSourceInstructions = $Instructions
        elements = $datasourceElements
    } | ConvertTo-Json -Depth 20)
    $fewShotsJson = (@{ '$schema' = "1.0.0"; fewShots = $FewShots } | ConvertTo-Json -Depth 20)
    $selectedTables = @($Elements | Where-Object { [string]$_.type -eq 'kusto.table' } | ForEach-Object { [string]$_.display_name })
    return @{ FolderName = "kusto-$DisplayName"; DatasourceId = $KqlDbId; DatasourceJson = $datasourceJson; FewShotsJson = $fewShotsJson; SelectionKind = 'kusto'; SelectedTables = $selectedTables; SelectedFunctions = @($Functions) }
}

function New-LakehouseDatasource {
    param([string]$DisplayName, [string]$LakehouseId, [string]$WorkspaceId, [array]$Tables, [string]$Instructions, [array]$FewShots = @())
    $elements = @(
        @{ display_name = 'dbo'; type = 'lakehouse_tables.schema'; is_selected = $true; children = @($Tables | ForEach-Object { @{ display_name = $_; type = 'lakehouse_tables.table'; is_selected = $true } }) }
    )
    $datasourceJson = (@{
        '$schema' = "1.0.0"
        artifactId = $LakehouseId
        workspaceId = $WorkspaceId
        displayName = $DisplayName
        type = "lakehouse_tables"
        userDescription = "Gold Lakehouse tables for claims history, payer dimensions, diagnoses, CMS quality, care gaps, risk adjustment, high-cost cohorts, and readmission risk"
        dataSourceInstructions = $Instructions
        elements = $elements
    } | ConvertTo-Json -Depth 30)
    $fewShotsJson = (@{ '$schema' = "1.0.0"; fewShots = $FewShots } | ConvertTo-Json -Depth 20)
    return @{ FolderName = "lakehouse_tables-$DisplayName"; DatasourceJson = $datasourceJson; FewShotsJson = $fewShotsJson; SelectionKind = 'lakehouse'; SelectedTables = @($Tables) }
}

function New-OntologyDatasourceIfAvailable {
    param(
        [Parameter(Mandatory)][string]$OntologyName,
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$UserDescription,
        [Parameter(Mandatory)][string]$Instructions,
        [Parameter(Mandatory)][string[]]$EntityTypes,
        [array]$FewShots = @()
    )
    try {
        $ontologies = (Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/ontologies").value
        $ontology = $ontologies | Where-Object { $_.displayName -eq $OntologyName } | Select-Object -First 1
        if (-not $ontology) { return $null }
        $elements = @($EntityTypes | ForEach-Object {
            @{ id = $_; is_selected = $true; display_name = $_; type = 'ontology.entity'; description = $null; children = @() }
        })
        $datasourceJson = (@{
            '$schema'              = "1.0.0"
            artifactId             = $ontology.id
            workspaceId            = $WorkspaceId
            displayName            = $OntologyName
            type                   = "ontology"
            userDescription        = $UserDescription
            dataSourceInstructions = $Instructions
            elements               = $elements
        } | ConvertTo-Json -Depth 20)
        $fewShotsJson = (@{ '$schema' = "1.0.0"; fewShots = $FewShots } | ConvertTo-Json -Depth 20)
        return @{ FolderName = "ontology-$OntologyName"; DatasourceJson = $datasourceJson; FewShotsJson = $fewShotsJson }
    } catch {
        Write-Host "  ⚠ Could not attach ontology datasource '$OntologyName': $(Get-ErrorMessage $_)" -ForegroundColor Yellow
        return $null
    }
}


function Ensure-EventHubConnection {
    param([string]$WorkspaceId, [string]$Namespace, [string]$HubName, [string]$ConnectionString)
    $parts = @{}
    $ConnectionString.Split(';') | ForEach-Object {
        if ($_ -match '^([^=]+)=(.+)$') { $parts[$matches[1].Trim()] = $matches[2].Trim() }
    }
    $endpoint = $parts['Endpoint'] -replace '^sb://', '' -replace '/$', ''
    $sasKeyName = $parts['SharedAccessKeyName']
    $sasKey = $parts['SharedAccessKey']
    $connectionName = "masimo-eh-$Namespace-$HubName"
    $connectionId = $null
    try {
        $existingConns = Invoke-FabricApi -Endpoint "/connections"
        $existing = $existingConns.value | Where-Object { $_.displayName -eq $connectionName }
        if ($existing) { if ($existing -is [array]) { $existing = $existing[0] }; $connectionId = $existing.id }
    } catch { Write-Host "  ⚠ Could not list Fabric connections: $(Get-ErrorMessage $_)" -ForegroundColor Yellow }
    if ($connectionId) {
        Write-Host "  ✓ Cloud connection already exists: $connectionName ($connectionId)" -ForegroundColor Green
        return $connectionId
    }
    $connBody = @{
        connectivityType = "ShareableCloud"
        displayName = $connectionName
        connectionDetails = @{ type = "EventHub"; creationMethod = "EventHub.Contents"; parameters = @(@{ dataType = "Text"; name = "endpoint"; value = $endpoint }, @{ dataType = "Text"; name = "entityPath"; value = $HubName }) }
        privacyLevel = "Organizational"
        credentialDetails = @{ singleSignOnType = "None"; connectionEncryption = "NotEncrypted"; skipTestConnection = $false; credentials = @{ credentialType = "Basic"; username = $sasKeyName; password = $sasKey } }
    }
    try {
        $resp = Invoke-FabricApi -Method POST -Endpoint "/connections" -Body $connBody
        Write-Host "  ✓ Cloud connection created: $connectionName ($($resp.id))" -ForegroundColor Green
        return $resp.id
    } catch {
        Write-Host "  ⚠ Failed to create cloud connection ${connectionName}: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
        Write-Host "  Retrying cloud connection using legacy EventHub path payload..." -ForegroundColor Yellow
        $legacyPath = (@{ endpoint = $endpoint; entityPath = $HubName; consumerGroup = "`$Default" } | ConvertTo-Json -Compress)
        $legacyBody = @{
            connectivityType = "ShareableCloud"
            displayName = $connectionName
            connectionDetails = @{ type = "EventHub"; path = $legacyPath }
            privacyLevel = "Organizational"
            credentialDetails = @{ singleSignOnType = "None"; connectionEncryption = "NotEncrypted"; skipTestConnection = $false; credentials = @{ credentialType = "Basic"; username = $sasKeyName; password = $sasKey } }
        }
        try {
            $resp = Invoke-FabricApi -Method POST -Endpoint "/connections" -Body $legacyBody
            Write-Host "  ✓ Cloud connection created: $connectionName ($($resp.id))" -ForegroundColor Green
            return $resp.id
        } catch {
            Write-Host "  ⚠ Failed legacy cloud connection ${connectionName}: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
            return $null
        }
    }
}

function Ensure-Eventstream {
    param([string]$WorkspaceId, [string]$Name, [string]$Description)
    $eventstream = $null
    try { $eventstream = (Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/items?type=Eventstream").value | Where-Object { $_.displayName -eq $Name } } catch {}
    if ($eventstream) { if ($eventstream -is [array]) { $eventstream = $eventstream[0] }; Write-Host "  ✓ Eventstream exists: $Name" -ForegroundColor Green; return $eventstream }
    try {
        $null = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$WorkspaceId/eventstreams" -Body @{ displayName = $Name; description = $Description }
        return Wait-FabricItem -WorkspaceId $WorkspaceId -ItemType "Eventstream" -ItemName $Name -TimeoutSeconds 120
    } catch {
        Write-Host "  ⚠ Eventstream create returned: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
        return Wait-FabricItem -WorkspaceId $WorkspaceId -ItemType "Eventstream" -ItemName $Name -TimeoutSeconds 120
    }
}

function Update-EventstreamDefinition {
    param([string]$WorkspaceId, [string]$EventstreamId, [string]$EventstreamName, [object]$Definition)
    $esJson = $Definition | ConvertTo-Json -Depth 30
    $platformObj = @{ "`$schema" = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"; metadata = @{ type = "Eventstream"; displayName = $EventstreamName }; config = @{ version = "2.0"; logicalId = "00000000-0000-0000-0000-000000000000" } }
    $updateBody = @{ definition = @{ parts = @(
        @{ path = "eventstream.json"; payload = (ConvertTo-Base64 $esJson); payloadType = "InlineBase64" },
        @{ path = ".platform"; payload = (ConvertTo-Base64 ($platformObj | ConvertTo-Json -Depth 10)); payloadType = "InlineBase64" }
    ) } } | ConvertTo-Json -Depth 20
    $headers = @{ Authorization = "Bearer $(Get-FabricAccessToken)"; "Content-Type" = "application/json" }
    $uri = "$FabricApiBase/workspaces/$WorkspaceId/eventstreams/$EventstreamId/updateDefinition?updateMetadata=True"
    try {
        $response = Invoke-WebRequest -Method POST -Uri $uri -Headers $headers -Body $updateBody -UseBasicParsing
        if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 202) {
            Write-Host "  ✓ Eventstream definition updated: $EventstreamName" -ForegroundColor Green
            return $true
        }
        Write-Host "  ⚠ Eventstream update returned status $($response.StatusCode)" -ForegroundColor Yellow
        return $false
    } catch {
        Write-Host "  ⚠ Eventstream update failed for ${EventstreamName}: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
        return $false
    }
}
function Ensure-EventstreamRunning {
    param([string]$WorkspaceId, [string]$EventstreamId, [string]$EventstreamName)
    $deadline = (Get-Date).AddMinutes(5)
    $resumeRequested = $false
    $lastStatus = "Topology unavailable"

    while ((Get-Date) -lt $deadline) {
        try {
            $topology = Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/eventstreams/$EventstreamId/topology"
            $runtimeNodes = @($topology.sources) + @($topology.streams) + @($topology.destinations)
            if ($runtimeNodes.Count -gt 0) {
                $lastStatus = ($runtimeNodes | ForEach-Object { "$($_.name)=$($_.status)" }) -join ", "
                if (@($runtimeNodes | Where-Object { $_.status -eq "Error" }).Count -gt 0) {
                    throw "$EventstreamName contains error nodes: $lastStatus"
                }
                if (@($runtimeNodes | Where-Object { $_.status -ne "Running" }).Count -eq 0) {
                    Write-Host "  ✓ $EventstreamName topology is running: $lastStatus" -ForegroundColor Green
                    return $true
                }
                if (-not $resumeRequested -and @($runtimeNodes | Where-Object { $_.status -eq "Paused" }).Count -gt 0) {
                    Write-Host "  Resuming paused $EventstreamName nodes from their last checkpoint..." -ForegroundColor Yellow
                    Invoke-FabricApi -Method POST -Endpoint "/workspaces/$WorkspaceId/eventstreams/$EventstreamId/resume" -Body @{
                        startType = "WhenLastStopped"
                    } | Out-Null
                    $resumeRequested = $true
                }
                Write-Host "    Waiting for $EventstreamName topology: $lastStatus" -ForegroundColor Gray
            }
        } catch {
            $lastStatus = Get-ErrorMessage $_
            Write-Host "    $EventstreamName topology not ready: $lastStatus" -ForegroundColor Gray
        }
        Start-Sleep -Seconds 10
    }
    Write-Host "  ✗ $EventstreamName did not reach Running within 5 minutes: $lastStatus" -ForegroundColor Red
    return $false
}


function New-ClaimsEventstreamDefinition {
    param([string]$ClaimConnectionId, [string]$WorkspaceId, [string]$KqlDbId, [string]$KqlDbName)
    # Single-source claims topology. Fabric permits exactly one DefaultStream per Eventstream, so claims
    # cannot be merged into the Phase 2 telemetry Eventstream; they route to their own claims_events table.
    $sources = @(@{ name = "ClaimEventHubSource"; type = "AzureEventHub"; properties = @{ dataConnectionId = $ClaimConnectionId; consumerGroupName = "`$Default"; inputSerialization = @{ type = "Json"; properties = @{ encoding = "UTF8" } } } })
    $streams = @(@{ name = "ClaimEventsStream"; type = "DefaultStream"; properties = @{}; inputNodes = @(@{ name = "ClaimEventHubSource" }) })
    $destinations = @(@{ name = "ClaimsEventhouseDestination"; type = "Eventhouse"; properties = @{ dataIngestionMode = "ProcessedIngestion"; workspaceId = $WorkspaceId; itemId = $KqlDbId; databaseName = $KqlDbName; tableName = "claims_events"; inputSerialization = @{ type = "Json"; properties = @{ encoding = "UTF8" } } }; inputNodes = @(@{ name = "ClaimEventsStream" }) })
    return @{ sources = $sources; destinations = $destinations; streams = $streams; operators = @(); compatibilityLevel = "1.1" }
}

function Deploy-PayerReflex {
    param([string]$WorkspaceId, [string]$KqlDbId, [string]$Email)
    $reflexName = "PayerOpsActivator"
    $existing = (Invoke-FabricApi -Endpoint "/workspaces/$WorkspaceId/items?type=Reflex").value | Where-Object { $_.displayName -eq $reflexName }
    if ($existing -is [array]) { $existing = $existing[0] }
    $reflexId = if ($existing) { $existing.id } else { $null }

    $containerId = [guid]::NewGuid().ToString(); $kqlSourceId = [guid]::NewGuid().ToString(); $eventViewId = [guid]::NewGuid().ToString(); $objectViewId = [guid]::NewGuid().ToString()
    $attrDomain = [guid]::NewGuid().ToString(); $attrPriority = [guid]::NewGuid().ToString(); $attrPatient = [guid]::NewGuid().ToString(); $attrProvider = [guid]::NewGuid().ToString(); $attrClaim = [guid]::NewGuid().ToString(); $attrMetricName = [guid]::NewGuid().ToString(); $attrMetricValue = [guid]::NewGuid().ToString(); $attrMessage = [guid]::NewGuid().ToString()
    $kqlQuery = "fn_PayerOpsWorklist(60) | where priority in ('CRITICAL', 'HIGH') | project alert_id, alert_time, alert_domain, priority, patient_id, provider_id, claim_id, metric_name, metric_value, message"
    $srcEvtInst = '{"templateId":"SourceEvent","templateVersion":"1.1","steps":[{"name":"SourceEventStep","id":"' + [guid]::NewGuid().ToString() + '","rows":[{"name":"SourceSelector","kind":"SourceReference","arguments":[{"name":"entityId","type":"string","value":"' + $kqlSourceId + '"}]}]}]}'
    $idPartInst = '{"templateId":"IdentityPartAttribute","templateVersion":"1.1","steps":[{"name":"IdPartStep","id":"' + [guid]::NewGuid().ToString() + '","rows":[{"name":"TypeAssertion","kind":"TypeAssertion","arguments":[{"name":"op","type":"string","value":"Text"},{"name":"format","type":"string","value":""}]}]}]}'
    function New-BasicAttrInstance([string]$evId, [string]$fieldName, [string]$dataType) {
        '{"templateId":"BasicEventAttribute","templateVersion":"1.1","steps":[{"name":"EventSelectStep","id":"' + [guid]::NewGuid().ToString() + '","rows":[{"name":"EventSelector","kind":"Event","arguments":[{"kind":"EventReference","type":"complex","arguments":[{"name":"entityId","type":"string","value":"' + $evId + '"}],"name":"event"}]},{"name":"EventFieldSelector","kind":"EventField","arguments":[{"name":"fieldName","type":"string","value":"' + $fieldName + '"}]}]},{"name":"EventComputeStep","id":"' + [guid]::NewGuid().ToString() + '","rows":[{"name":"TypeAssertion","kind":"TypeAssertion","arguments":[{"name":"op","type":"string","value":"' + $dataType + '"},{"name":"format","type":"string","value":""}]}]}]}'
    }
    $entities = @(
        @{uniqueIdentifier=$containerId; payload=@{name="Payer Operations Alerts";type="kqlQueries"}; type="container-v1"},
        @{uniqueIdentifier=$kqlSourceId; payload=@{name="fn_PayerOpsWorklist"; runSettings=@{executionIntervalInSeconds=60}; query=@{queryString=$kqlQuery}; eventhouseItem=@{itemId=$KqlDbId; workspaceId=$WorkspaceId; itemType="KustoDatabase"}; parentContainer=@{targetUniqueIdentifier=$containerId}}; type="kqlSource-v1"},
        @{uniqueIdentifier=$eventViewId; payload=@{name="PayerOpsAlert events"; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Event"; instance=$srcEvtInst}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$objectViewId; payload=@{name="PayerOpsAlert"; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Object"}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=([guid]::NewGuid().ToString()); payload=@{name="alert_id"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=$idPartInst}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrDomain; payload=@{name="alert_domain"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "alert_domain" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrPriority; payload=@{name="priority"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "priority" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrPatient; payload=@{name="patient_id"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "patient_id" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrProvider; payload=@{name="provider_id"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "provider_id" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrClaim; payload=@{name="claim_id"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "claim_id" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrMetricName; payload=@{name="metric_name"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "metric_name" "Text")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrMetricValue; payload=@{name="metric_value"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "metric_value" "Number")}}; type="timeSeriesView-v1"},
        @{uniqueIdentifier=$attrMessage; payload=@{name="message"; parentObject=@{targetUniqueIdentifier=$objectViewId}; parentContainer=@{targetUniqueIdentifier=$containerId}; definition=@{type="Attribute"; instance=(New-BasicAttrInstance $eventViewId "message" "Text")}}; type="timeSeriesView-v1"}
    )
    $entitiesJson = ConvertTo-Json -InputObject $entities -Depth 30 -Compress
    function FR([string]$f) { '{"arguments":[{"name":"fieldName","type":"string","value":"'+$f+'"}],"kind":"EventFieldReference","type":"complex"}' }
    function NR([string]$f) { '{"arguments":[{"name":"name","type":"string","value":"'+$f+'"},{"arguments":[{"name":"fieldName","type":"string","value":"'+$f+'"}],"kind":"EventFieldReference","name":"reference","type":"complexReference"}],"kind":"NameReferencePair","type":"complex"}' }
    $ruleInst = '{"templateId":"EventTrigger","templateVersion":"1.2.4","steps":[' +
        '{"id":"' + [guid]::NewGuid().ToString() + '","name":"FieldsDefaultsStep","rows":[{"arguments":[{"arguments":[{"name":"entityId","type":"string","value":"' + $eventViewId + '"}],"kind":"EventReference","name":"event","type":"complex"}],"kind":"Event","name":"EventSelector"}]},' +
        '{"id":"' + [guid]::NewGuid().ToString() + '","name":"EventDetectStep","rows":[{"arguments":[],"kind":"OnEveryValue","name":"OnEveryValue"}]},' +
        '{"id":"' + [guid]::NewGuid().ToString() + '","name":"ActStep","rows":[{"arguments":[' +
            '{"name":"messageLocale","type":"string","value":"en-us"},' +
            '{"name":"sentTo","type":"array","values":[{"type":"string","value":"' + $Email + '"}]},' +
            '{"name":"copyTo","type":"array","values":[]},' +
            '{"name":"bCCTo","type":"array","values":[]},' +
            '{"name":"subject","type":"array","values":[{"name":"string","type":"string","value":"PAYER OPS "},' + (FR 'priority') + ',{"name":"string","type":"string","value":" "},' + (FR 'alert_domain') + ',{"name":"string","type":"string","value":" alert"}]},' +
            '{"name":"headline","type":"array","values":[' + (FR 'priority') + ',{"name":"string","type":"string","value":" "},' + (FR 'alert_domain') + ',{"name":"string","type":"string","value":" for patient "},' + (FR 'patient_id') + ']},' +
            '{"name":"optionalMessage","type":"array","values":[' + (FR 'message') + ']},' +
            '{"name":"additionalInformation","type":"array","values":[' + (NR 'alert_domain') + ',' + (NR 'priority') + ',' + (NR 'patient_id') + ',' + (NR 'provider_id') + ',' + (NR 'claim_id') + ',' + (NR 'metric_name') + ',' + (NR 'metric_value') + ',' + (NR 'message') + ']}' +
        '],"kind":"EmailMessage","name":"EmailBinding"}]}' +
    ']}'
    $ruleEntityJson = '{"uniqueIdentifier":"' + [guid]::NewGuid().ToString() + '","payload":{"name":"PayerOpsAlert email alert","parentContainer":{"targetUniqueIdentifier":"' + $containerId + '"},"definition":{"type":"Rule","instance":"' + ($ruleInst -replace '"', '\"') + '","settings":{"shouldRun":true,"shouldApplyRuleOnUpdate":true}}},"type":"timeSeriesView-v1"}'
    $fullEntitiesJson = $entitiesJson.TrimEnd(']') + ',' + $ruleEntityJson + ']'
    if (-not $reflexId) {
        try {
            $createBody = @{ displayName = $reflexName; description = "Payer operations alerting Reflex sourced from fn_PayerOpsWorklist(60) for fraud, high-cost, and care-gap routing."; type = "Reflex"; definition = @{ parts = @(@{path="ReflexEntities.json"; payload=(ConvertTo-Base64 $entitiesJson); payloadType="InlineBase64"}) } }
            $created = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$WorkspaceId/items" -Body $createBody
            $reflexId = $created.id
            Write-Host "  ✓ Reflex created: $reflexName ($reflexId)" -ForegroundColor Green
        } catch { throw "Could not create Reflex: $(Get-ErrorMessage $_)" }
    }
    try {
        $null = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$WorkspaceId/items/$reflexId/updateDefinition" -Body @{ definition = @{ parts = @(@{path="ReflexEntities.json"; payload=(ConvertTo-Base64 $fullEntitiesJson); payloadType="InlineBase64"}) } }
        Write-Host "  ✓ PayerOpsActivator rule applied" -ForegroundColor Green
    } catch { throw "Could not update PayerOpsActivator: $(Get-ErrorMessage $_)" }
}

Write-Host "──────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "Phase 7: Payer RTI & Ops" -ForegroundColor Cyan
Write-Host "──────────────────────────────────────────────────────────────" -ForegroundColor DarkGray

Write-Host "Validating BrakeKat Azure context..." -ForegroundColor White
$accountJson = az account show -o json | ConvertFrom-Json
if ($accountJson.tenantId -ne $ExpectedTenantId) { throw "Wrong Azure tenant '$($accountJson.tenantId)'; expected '$ExpectedTenantId'." }
if ($accountJson.id -ne $ExpectedSubscriptionId) { throw "Wrong Azure subscription '$($accountJson.id)'; expected '$ExpectedSubscriptionId'." }
Write-Host "  ✓ Azure context: tenant=$($accountJson.tenantId), subscription=$($accountJson.id), user=$($accountJson.user.name)" -ForegroundColor Green

Write-Host "Discovering Fabric workspace '$FabricWorkspaceName'..." -ForegroundColor White
$workspaces = Invoke-FabricApi -Endpoint "/workspaces"
$workspace = $workspaces.value | Where-Object { $_.displayName -eq $FabricWorkspaceName }
if ($workspace -is [array]) { $workspace = $workspace[0] }
if (-not $workspace) { throw "Fabric workspace '$FabricWorkspaceName' not found." }
$workspaceId = $workspace.id
Write-Host "  ✓ Workspace: $FabricWorkspaceName ($workspaceId)" -ForegroundColor Green

Write-Host "Discovering KQL database..." -ForegroundColor White
$kqlItems = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/items?type=KQLDatabase"
$kqlDb = $kqlItems.value | Where-Object { $_.displayName -eq "MasimoKQLDB" }
if (-not $kqlDb) { $kqlDb = $kqlItems.value | Where-Object { $_.displayName -eq "MasimoEventhouse" } }
if ($kqlDb -is [array]) { $kqlDb = $kqlDb[0] }
if (-not $kqlDb) { throw "KQL Database 'MasimoKQLDB' or 'MasimoEventhouse' not found." }
$kqlDbId = $kqlDb.id
$kqlDbName = $kqlDb.displayName
# Resolve the Kusto query URI with bounded warm-up retries. When the Fabric
# capacity is paused/reactivating, the RTI compute endpoints (kqlDatabases /
# eventhouses detail) transiently 404 even though the item lists fine, leaving
# queryServiceUri unavailable. Retry both the KQLDatabase detail and the parent
# Eventhouse before treating it as a hard failure.
$kustoUri = $null
for ($uriAttempt = 1; $uriAttempt -le 8 -and -not $kustoUri; $uriAttempt++) {
    $kqlDbDetail = $null
    try { $kqlDbDetail = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/kqlDatabases/$kqlDbId" } catch {}
    if (-not $kqlDbDetail) { try { $kqlDbDetail = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/items/$kqlDbId" } catch {} }
    if ($kqlDbDetail) {
        $prop = $kqlDbDetail.PSObject.Properties['queryServiceUri']; if ($prop) { $kustoUri = $prop.Value }
        if (-not $kustoUri) { $prop = $kqlDbDetail.PSObject.Properties['queryUri']; if ($prop) { $kustoUri = $prop.Value } }
        if (-not $kustoUri) { $prop = $kqlDbDetail.PSObject.Properties['properties']; if ($prop -and $prop.Value) { $p = $prop.Value.PSObject.Properties['queryUri']; if ($p) { $kustoUri = $p.Value } } }
        if (-not $kustoUri) { $prop = $kqlDbDetail.PSObject.Properties['properties']; if ($prop -and $prop.Value) { $p = $prop.Value.PSObject.Properties['queryServiceUri']; if ($p) { $kustoUri = $p.Value } } }
    }
    # Fallback: read the URI off the parent Eventhouse (mirrors deploy-fabric-rti.ps1).
    if (-not $kustoUri) {
        try {
            $ehItems = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/eventhouses"
            foreach ($eh in $ehItems.value) {
                if ($eh.displayName -eq "MasimoEventhouse" -or $eh.displayName -eq $kqlDbName) {
                    $ehDetail = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/eventhouses/$($eh.id)"
                    if ($ehDetail.properties.queryServiceUri) { $kustoUri = $ehDetail.properties.queryServiceUri }
                    elseif ($ehDetail.queryServiceUri) { $kustoUri = $ehDetail.queryServiceUri }
                    if ($kustoUri) { break }
                }
            }
        } catch {}
    }
    if (-not $kustoUri -and $uriAttempt -lt 8) {
        $uriDelay = [Math]::Min(30, 10 * $uriAttempt)
        Write-Host "  Kusto query URI not available yet (capacity may be reactivating); retrying in ${uriDelay}s... ($uriAttempt/8)" -ForegroundColor Yellow
        Start-Sleep -Seconds $uriDelay
    }
}
if (-not $kustoUri) { throw "Could not determine Kusto query URI for $kqlDbName (capacity offline or Eventhouse not ready)." }
Write-Host "  ✓ Kusto URI: $kustoUri" -ForegroundColor Green
Write-Host "  ✓ KQL DB: $kqlDbName ($kqlDbId)" -ForegroundColor Green
$kustoHeaders = @{ Authorization = "Bearer $(Get-KustoAccessToken)"; "Content-Type" = "application/json" }
$kqlParams = @{ KustoUri = $kustoUri; DatabaseName = $kqlDbName; KustoHeaders = $kustoHeaders }

$goldLh = $null
if ($SkipSnapshotMaterialization) {
    Write-Host "  Definition-only mode: Gold Lakehouse bindings are intentionally deferred." -ForegroundColor DarkGray
} else {
    try {
        $lakehouses = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/lakehouses"
        $goldLh = $lakehouses.value | Where-Object { $_.displayName -match "[Rr]eporting.*[Gg]old" }
        if (-not $goldLh) { $goldLh = $lakehouses.value | Where-Object { $_.displayName -match "[Gg]old" } }
        if ($goldLh -is [array]) { $goldLh = $goldLh[0] }
    } catch {}
}

if (-not $SkipPayerRti) {
    Write-Host ""; Write-Host "--- Payer RTI: Event Hub, emulator, KQL, Eventstream ---" -ForegroundColor Cyan
    if ([string]::IsNullOrWhiteSpace($EventHubNamespace)) {
        $EventHubNamespace = az eventhubs namespace list --resource-group $ResourceGroupName --query "[?ends_with(name, '-eh-ns')].name | [0]" -o tsv
    }
    if ([string]::IsNullOrWhiteSpace($EventHubNamespace)) { throw "Event Hub namespace not supplied and auto-detect failed in $ResourceGroupName." }
    Write-Host "  ✓ Event Hub namespace: $EventHubNamespace" -ForegroundColor Green

    $hubExists = az eventhubs eventhub show --resource-group $ResourceGroupName --namespace-name $EventHubNamespace --name claim-stream --query name -o tsv 2>$null
    if ($hubExists -eq "claim-stream") {
        Write-Host "  ✓ claim-stream already exists" -ForegroundColor Green
    } else {
        az eventhubs eventhub create --resource-group $ResourceGroupName --namespace-name $EventHubNamespace --name claim-stream --cleanup-policy Delete --retention-time 24 --partition-count 2 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to create claim-stream Event Hub" }
        Write-Host "  ✓ claim-stream created" -ForegroundColor Green
    }
    if ($SkipClaimEmulator) {
        $existingClaimEmulator = az container show --resource-group $ResourceGroupName --name "claim-emulator-grp" --query name -o tsv 2>$null
        if ($existingClaimEmulator) {
            Write-Host "  Stopping existing claim emulator for zero-data mode..." -ForegroundColor Yellow
            az container stop --resource-group $ResourceGroupName --name $existingClaimEmulator --only-show-errors | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not stop existing claim emulator '$existingClaimEmulator'" }
        }
    }


    if (-not $SkipClaimEmulator) {
    $acrName = $null
    try { $acrName = az deployment group list --resource-group $ResourceGroupName --query "[?properties.outputs.acrName.value != null] | [-1].properties.outputs.acrName.value" -o tsv } catch {}
    if ([string]::IsNullOrWhiteSpace($acrName)) { try { $acrName = az acr list --resource-group $ResourceGroupName --query "[0].name" -o tsv } catch {} }
    if ([string]::IsNullOrWhiteSpace($acrName)) {
        throw "No ACR found; cannot build and deploy claim-emulator"
    } else {
        $acrLoginServer = az acr show --name $acrName --query loginServer -o tsv
        $claimImageTag = "deploy-$(Get-Date -AsUTC -Format 'yyyyMMddHHmmss')"
        Write-Host "  Building claim-emulator:$claimImageTag in ACR $acrName..." -ForegroundColor White
        Invoke-AcrBuildWithTagVerification -Registry $acrName -Repository "claim-emulator" -Tag $claimImageTag -ContextPath "phase-7/claim-emulator"
        $claimImageDigest = az acr manifest show-metadata --registry $acrName --name "claim-emulator:$claimImageTag" --query digest -o tsv 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($claimImageDigest)) { throw "Could not resolve immutable claim-emulator image digest" }
        $resourceTagsJson = if ($Tags.Count -gt 0) { $Tags | ConvertTo-Json -Compress } else { '{}' }
        $deploymentParams = @(
            "acrName=$acrName",
            "imageName=$acrLoginServer/claim-emulator@$claimImageDigest",
            "eventHubName=claim-stream",
            "eventHubNamespace=$EventHubNamespace",
            "eventRatePerMinute=$ClaimEventRatePerMinute",
            "resourceTags=$resourceTagsJson"
        )
        Write-Host "  Deploying claim-emulator-grp..." -ForegroundColor White
        az deployment group create --resource-group $ResourceGroupName --name claim-emulator --template-file "bicep/claim-emulator.bicep" --parameters @deploymentParams | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "claim-emulator deployment failed" }
        if ($Tags.Count -gt 0) {
            $containerGroupId = az container show --resource-group $ResourceGroupName --name claim-emulator-grp --query id -o tsv
            $tagUpdateArgs = @()
            foreach ($kv in $Tags.GetEnumerator()) { $tagUpdateArgs += "$($kv.Key)=$($kv.Value)" }
            az resource tag --ids $containerGroupId --tags @tagUpdateArgs --output none
            if ($LASTEXITCODE -ne 0) { throw "Failed to tag claim-emulator-grp" }
        }
        Write-Host "  ✓ claim-emulator-grp deployed" -ForegroundColor Green
    }
    } else {
        Write-Host "  Claim emulator omitted; claim-stream and payer RTI definitions remain deployed." -ForegroundColor DarkGray
    }

    Write-Host "  Deploying payer KQL contract..." -ForegroundColor White
    $kqlFile = Join-Path $RepoRoot "fabric-rti/kql/07-payer-rti-functions.kql"
    $kqlResult = Invoke-KqlScriptFile -Path $kqlFile @kqlParams
    if ($kqlResult.Fail -gt 0) { throw "Payer KQL contract deployment failed: $($kqlResult.Fail) command(s) failed" }

    $goldCareGapsReady = $false
    if ($goldLh) {
        Write-Host "  Creating GoldCareGaps shortcut/external table from $($goldLh.displayName)..." -ForegroundColor White
        $shortcutBody = @{ name = "GoldCareGaps"; path = "/Tables"; target = @{ oneLake = @{ workspaceId = $workspaceId; itemId = $goldLh.id; path = "Tables/care_gaps" } } }
        try {
            $null = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$workspaceId/items/$kqlDbId/shortcuts?shortcutConflictPolicy=CreateOrOverwrite" -Body $shortcutBody
            $extTableUrl = "https://onelake.dfs.fabric.microsoft.com/$workspaceId/$kqlDbId/Tables/GoldCareGaps;impersonate"
            $goldCareGapsReady = Invoke-KustoMgmt -Command ".create-or-alter external table GoldCareGaps kind=delta (h@'$extTableUrl')" -Label "GoldCareGaps external table" @kqlParams
        } catch {
            Write-Host "  ⚠ GoldCareGaps shortcut/external table failed: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ⚠ Gold Lakehouse not found; deploying care-gap fallback." -ForegroundColor Yellow
    }
    if (-not $goldCareGapsReady) {
        $fallbackCareGap = @'
.create-or-alter function with (
    docstring = "Care gap enrichment fallback — GoldCareGaps external table unavailable",
    folder = "PayerAlerts"
) fn_CareGapOnAlert(windowMinutes: int = 60) {
    datatable(alert_id:string, alert_timestamp:datetime, patient_id:string, facility_id:string, measure_id:string, measure_name:string, gap_days_overdue:int, alert_priority:string, alert_text:string, latitude:real, longitude:real, provider_id:string, claim_id:string, fraud_score:real)[]
}
'@
        if (-not (Invoke-KustoMgmt -Command $fallbackCareGap -Label "fn_CareGapOnAlert fallback" @kqlParams)) { throw "fn_CareGapOnAlert fallback deployment failed" }
    }
    if ($goldCareGapsReady) {
        $goldCareGapFunction = @'
.create-or-alter function with (
    skipvalidation = "true",
    docstring = "Current Gold care gaps exposed to payer operations",
    folder = "PayerAlerts"
) fn_CareGapOnAlert(windowMinutes: int = 60) {
    external_table('GoldCareGaps')
    | where gap_status =~ "open"
    | project
        alert_id = strcat("CAREGAP-", tostring(patient_id), "-", tostring(measure_id)),
        alert_timestamp = now(), patient_id = tostring(patient_id), facility_id = "",
        measure_id = tostring(measure_id), measure_name = tostring(gap_type),
        gap_days_overdue = toint(days_overdue),
        alert_priority = case(toint(days_overdue) >= 90, "HIGH", "MEDIUM"),
        alert_text = tostring(recommended_action), latitude = real(null), longitude = real(null),
        provider_id = "", claim_id = "", fraud_score = real(0)
}
'@
        if (-not (Invoke-KustoMgmt -Command $goldCareGapFunction -Label "fn_CareGapOnAlert Gold" @kqlParams)) { throw "fn_CareGapOnAlert Gold deployment failed" }
    }
    $payerOpsWorklist = @'
.create-or-alter function with (
    skipvalidation = "true",
    docstring = "Unified payer operations worklist across fraud, high-cost, and care-gap RTI alerts",
    folder = "PayerAlerts"
) fn_PayerOpsWorklist(windowMinutes: int = 60) {
    let fraud = fn_FraudRisk(windowMinutes)
        | where risk_tier in ("CRITICAL", "HIGH")
        | project alert_id=score_id, alert_time=score_timestamp, alert_domain="FRAUD", priority=risk_tier,
                  patient_id, provider_id, claim_id, metric_value=fraud_score,
                  metric_name="fraud_score", message=strcat("Fraud risk ", tostring(fraud_score), " for claim ", claim_id, " provider ", provider_id), latitude, longitude;
    let highcost = fn_HighCostTrajectory(90)
        | where risk_tier in ("CRITICAL", "HIGH")
        | project alert_id, alert_time=alert_timestamp, alert_domain="HIGH_COST", priority=risk_tier,
                  patient_id, provider_id="", claim_id="", metric_value=rolling_spend_30d,
                  metric_name="rolling_spend_30d", message=strcat("30d spend $", tostring(rolling_spend_30d), "; ED visits=", tostring(ed_visits_30d), "; trend=", cost_trend), latitude, longitude;
    let gaps = fn_CareGapOnAlert(windowMinutes)
        | where alert_priority in ("CRITICAL", "HIGH")
        | project alert_id, alert_time=alert_timestamp, alert_domain="CARE_GAP", priority=alert_priority,
                  patient_id, provider_id, claim_id, metric_value=todouble(gap_days_overdue),
                  metric_name="gap_days_overdue", message=alert_text, latitude, longitude;
    fraud | union highcost | union gaps | order by priority asc, alert_time desc
}
'@
    if (-not (Invoke-KustoMgmt -Command $payerOpsWorklist -Label "fn_PayerOpsWorklist after care-gap setup" @kqlParams)) { throw "fn_PayerOpsWorklist deployment failed" }
    $operationsFreshness = @'
.create-or-alter function with (
    skipvalidation = "true",
    docstring = "Operations Agent freshness findings for telemetry and claims streams",
    folder = "OperationsAgent"
) fn_OperationsFreshness(staleMinutes: int = 5) {
    let telemetry = TelemetryRaw
        | summarize last_event_time=max(todatetime(timestamp)) by device_id
        | extend age_minutes=datetime_diff("minute", now(), last_event_time)
        | where age_minutes > staleMinutes
        | project condition_name="STALE_TELEMETRY", device_id, last_event_time,
                  age_minutes=tolong(age_minutes), source_table="TelemetryRaw", severity="WARNING";
    let claims = claims_events
        | summarize last_event_time=max(event_timestamp)
        | extend age_minutes=datetime_diff("minute", now(), last_event_time)
        | where age_minutes > staleMinutes
        | project condition_name="STALE_CLAIMS", device_id="", last_event_time,
                  age_minutes=tolong(age_minutes), source_table="claims_events", severity="WARNING";
    telemetry | union claims | order by age_minutes desc
}
'@
    if (-not (Invoke-KustoMgmt -Command $operationsFreshness -Label "fn_OperationsFreshness" @kqlParams)) { throw "fn_OperationsFreshness deployment failed" }
    . (Join-Path $PSScriptRoot 'agent-grounding-backfills.ps1')
    Invoke-AgentGroundingBackfills @kqlParams


    if ($SkipSnapshotMaterialization) {
        Write-Host "  Payer snapshot materialization omitted; schemas and functions remain deployed." -ForegroundColor DarkGray
    } else {
        Write-Host "  Materializing payer scoring snapshots..." -ForegroundColor White
        if (-not (Invoke-KustoMgmt -Command ".set-or-append fraud_scores <| fn_FraudRisk(60) | project score_id, score_timestamp, claim_id, patient_id, provider_id, fraud_score, fraud_flags, risk_tier, latitude, longitude" -Label "fraud_scores snapshot" @kqlParams)) { throw "fraud_scores snapshot materialization failed" }
        if (-not (Invoke-KustoMgmt -Command ".set-or-replace highcost_alerts <| fn_HighCostTrajectory(90) | project alert_id, alert_timestamp, patient_id, rolling_spend_30d, rolling_spend_90d, ed_visits_30d, readmission_flag, risk_tier, cost_trend, latitude, longitude" -Label "highcost_alerts snapshot" @kqlParams)) { throw "highcost_alerts snapshot materialization failed" }
        if (-not (Invoke-KustoMgmt -Command ".set-or-replace care_gap_alerts <| fn_CareGapOnAlert(60) | project alert_id, alert_timestamp, patient_id, facility_id, measure_id, measure_name, gap_days_overdue, alert_priority, alert_text, latitude, longitude" -Label "care_gap_alerts snapshot" @kqlParams)) { throw "care_gap_alerts snapshot materialization failed" }
    }

    Write-Host "  Configuring Eventstream topology..." -ForegroundColor White
    $ehLocalAuthDisabled = az eventhubs namespace show --resource-group $ResourceGroupName --name $EventHubNamespace --query disableLocalAuth -o tsv 2>$null
    if ($ehLocalAuthDisabled -eq "true") {
        Write-Host "  Event Hub local auth is disabled; enabling SAS auth for Fabric Eventstream cloud connections..." -ForegroundColor Yellow
        $tagArgs = @()
        foreach ($kv in $Tags.GetEnumerator()) { $tagArgs += "$($kv.Key)=$($kv.Value)" }
        if ($tagArgs.Count -eq 0) { $tagArgs += "SecurityControl=Ignore" }
        az eventhubs namespace update --resource-group $ResourceGroupName --name $EventHubNamespace --tags @tagArgs --disable-local-auth false --output none
        if ($LASTEXITCODE -ne 0) { throw "Failed to enable local auth on Event Hub namespace $EventHubNamespace" }
        Start-Sleep -Seconds 15
    }
    $connStr = az eventhubs namespace authorization-rule keys list --resource-group $ResourceGroupName --namespace-name $EventHubNamespace --name emulator-access --query primaryConnectionString -o tsv
    $claimConnectionId = Ensure-EventHubConnection -WorkspaceId $workspaceId -Namespace $EventHubNamespace -HubName "claim-stream" -ConnectionString $connStr
    if (-not $claimConnectionId) { throw "Fabric Event Hub cloud connection for claim-stream was not created" }
    # Telemetry (MasimoTelemetryStream → TelemetryRaw) is owned by Phase 2 Fabric RTI and must not be
    # reconfigured here. Claims get a dedicated Eventstream because Fabric permits only one DefaultStream
    # per topology; telemetry and claims carry different schemas routed to different Eventhouse tables.
    $claimEs = Ensure-Eventstream -WorkspaceId $workspaceId -Name "ClaimsRTIStream" -Description "Ingests payer claim-stream events into the Eventhouse for fraud, care-gap, high-cost, and payer-operations scoring."
    if (-not $claimEs) { throw "ClaimsRTIStream was not created or discovered" }
    $claimDef = New-ClaimsEventstreamDefinition -ClaimConnectionId $claimConnectionId -WorkspaceId $workspaceId -KqlDbId $kqlDbId -KqlDbName $kqlDbName
    if (-not (Update-EventstreamDefinition -WorkspaceId $workspaceId -EventstreamId $claimEs.id -EventstreamName "ClaimsRTIStream" -Definition $claimDef)) {
        throw "ClaimsRTIStream definition update failed"
    }
    if (-not (Ensure-EventstreamRunning -WorkspaceId $workspaceId -EventstreamId $claimEs.id -EventstreamName "ClaimsRTIStream")) {
        throw "ClaimsRTIStream topology did not become active"
    }
    Write-Host "  ✓ ClaimsRTIStream configured: claim-stream → claims_events" -ForegroundColor Green
} else {
    Write-Host "Payer RTI skipped because -SkipPayerRti was supplied" -ForegroundColor Yellow
}

if (-not $SkipPayerActivator) {
    if ([string]::IsNullOrWhiteSpace($PayerOpsEmail)) {
        Write-Host "PayerOpsActivator skipped because -PayerOpsEmail was not supplied" -ForegroundColor Yellow
    } else {
        Write-Host ""; Write-Host "--- PayerOpsActivator ---" -ForegroundColor Cyan
        Deploy-PayerReflex -WorkspaceId $workspaceId -KqlDbId $kqlDbId -Email $PayerOpsEmail
    }
} else {
    Write-Host "PayerOpsActivator skipped" -ForegroundColor Yellow
}

$kqlElements = @(
    @{ id = [guid]::NewGuid().ToString(); display_name = "TelemetryRaw"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "AlertHistory"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "claims_events"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "fraud_scores"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "highcost_alerts"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "care_gap_alerts"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "agent_cross_domain_context"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "agent_imaging_summary"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "agent_payer_priority_summary"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "agent_high_cost_members"; type = "kusto.table"; is_selected = $true },
    @{ id = [guid]::NewGuid().ToString(); display_name = "agent_provider_fraud_claims"; type = "kusto.table"; is_selected = $true }
)
$payerKqlFewShots = @(
    @{ id = [guid]::NewGuid().ToString(); question = "Which providers have the highest active fraud risk, and what evidence supports the score?"; query = "fn_FraudRisk(60) | summarize arg_max(score_timestamp, fraud_score, risk_tier, fraud_flags, claim_id, patient_id) by provider_id | project provider_id, fraud_score, risk_tier, fraud_flags, claim_id, patient_id, score_timestamp | top 10 by fraud_score desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Show the current payer operations worklist"; query = "fn_PayerOpsWorklist(60) | order by priority asc, alert_time desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which members are trending toward high-cost status?"; query = "agent_high_cost_members | project patient_id, risk_tier, cost_trend, rolling_spend_30d, rolling_spend_90d, projected_cost_band, high_cost_score, ed_visits_30d, readmission_flag, refreshed_at | order by high_cost_score desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Show critical care gaps that should be routed for provider outreach."; query = "agent_CriticalCareGaps() | project alert_id, patient_id, measure_name, gap_days_overdue, alert_priority, alert_text, recommended_action | order by gap_days_overdue desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which alerts require immediate SIU, care-management, or provider-outreach review?"; query = "agent_payer_priority_summary | project alert_domain, priority, provider_id, alert_count, affected_members, affected_providers, max_metric, latest_alert, recommended_action | order by priority asc, alert_domain asc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Summarize the highest-priority issues by alert domain, severity, provider, and recommended action."; query = "agent_payer_priority_summary | project alert_domain, priority, provider_id, alert_count, affected_members, affected_providers, max_metric, latest_alert, recommended_action | order by priority asc, alert_count desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Choose the provider with the highest current fraud score, show their recent claims, and identify unusual patterns."; query = "agent_provider_fraud_claims | project provider_id, current_fraud_score, current_risk_tier, fraud_flags, claim_id, patient_id, claim_type, claim_amount, diagnosis_code, event_timestamp, injected_fraud_flags | order by event_timestamp desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which members have both high utilization and unresolved care gaps?"; query = "agent_cross_domain_context | where high_cost_status == 'AT_RISK' and care_gap_status == 'OPEN' | summarize arg_max(alert_time, *) by patient_id | project patient_id, patient_name, rolling_spend_30d, high_cost_status, care_gap_measure, care_gap_status, risk_tier, scenario_source" },
    @{ id = [guid]::NewGuid().ToString(); question = "Choose the highest-priority current claim, explain why it was prioritized, and recommend the next human-reviewed action."; query = "agent_HighestPriorityClaim()" },
    @{ id = [guid]::NewGuid().ToString(); question = "Return the single highest-priority current claim with provider and fraud score."; query = "agent_HighestPriorityClaim()" },
    @{ id = [guid]::NewGuid().ToString(); question = "Give me an executive summary of current fraud, high-cost, and care-gap exposure."; query = "agent_payer_priority_summary | project alert_domain, priority, provider_id, alert_count, affected_members, affected_providers, max_metric, latest_alert, recommended_action" },
    @{ id = [guid]::NewGuid().ToString(); question = "Show the relationship between a high-risk patient, their assigned device, active diagnoses, recent alerts, and payer."; query = "agent_CrossDomainContext() | top 1 by alert_time desc | project patient_id, patient_name, device_id, diagnosis_name, clinical_status, alert_time, alert_tier, payer_name, payer_category, risk_tier, risk_probability, scenario_source" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which patients have both a current care gap and recent abnormal device telemetry?"; query = "agent_CareGapAbnormalTelemetry()" },
    @{ id = [guid]::NewGuid().ToString(); question = "Trace a patient from device assignment through diagnosis, claim history, payer, and current risk classification."; query = "agent_CrossDomainContext() | top 1 by alert_time desc | project patient_id, patient_name, device_id, diagnosis_code, diagnosis_name, claim_id, claim_amount, payer_name, payer_category, risk_tier, risk_probability, scenario_source" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which devices are associated with patients who have elevated readmission risk?"; query = "agent_CrossDomainContext() | where risk_tier == 'HIGH' or risk_probability >= 0.7 | distinct patient_id, patient_name, device_id, risk_tier, risk_probability, scenario_source" },
    @{ id = [guid]::NewGuid().ToString(); question = "Find patients with recent critical clinical alerts and show their related claims, care gaps, and high-cost status."; query = "agent_CrossDomainContext() | where alert_tier == 'CRITICAL' | summarize arg_max(alert_time, *) by patient_id | project patient_id, patient_name, alert_time, alert_tier, claim_id, care_gap_measure, care_gap_status, high_cost_status, rolling_spend_30d, scenario_source" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which diagnoses are most common among patients with repeated device alerts?"; query = "agent_CommonDiagnosesWithRepeatedAlerts()" },
    @{ id = [guid]::NewGuid().ToString(); question = "Choose one patient with verified cross-domain links and show their connected clinical and payer context."; query = "agent_CrossDomainContext() | top 1 by alert_time desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Identify patients whose device telemetry, diagnoses, and utilization history suggest worsening risk."; query = "agent_CrossDomainContext() | where risk_tier == 'HIGH' and repeated_alert_count >= 2 | summarize arg_max(alert_time, *) by patient_id" }
)
$graphKqlFewShots = @(
    @{ id = [guid]::NewGuid().ToString(); question = "Show the current payer operations worklist from real-time data."; query = "fn_PayerOpsWorklist(60) | order by priority asc, alert_time desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which providers have the highest current fraud risk?"; query = "fn_FraudRisk(60) | summarize arg_max(score_timestamp, fraud_score, risk_tier, fraud_flags, claim_id, patient_id) by provider_id | top 10 by fraud_score desc" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which devices have current urgent clinical alerts?"; query = "fn_ClinicalAlerts(15) | where alert_tier in ('CRITICAL','URGENT') | project device_id, patient_id, alert_tier, alert_time" }
)
$goldFewShots = @(
    @{ id = [guid]::NewGuid().ToString(); question = "Summarize historical claim count and total paid by payer category from Reporting Gold."; query = "SELECT payer_category, COUNT(*) AS claim_count, SUM(paid_amount) AS total_paid FROM dbo.fact_claim GROUP BY payer_category ORDER BY total_paid DESC" },
    @{ id = [guid]::NewGuid().ToString(); question = "Which members have the highest historical paid amounts and claim counts?"; query = "SELECT TOP 10 patient_id, payer_category, total_paid, claim_count, denied_claims, is_stop_loss FROM dbo.agg_high_cost_claimants ORDER BY total_paid DESC" },
    @{ id = [guid]::NewGuid().ToString(); question = "Summarize open care gaps by measure from Reporting Gold."; query = "SELECT gap_type, COUNT(*) AS open_gap_count, MAX(days_overdue) AS max_days_overdue FROM dbo.care_gaps WHERE gap_status = 'OPEN' GROUP BY gap_type ORDER BY open_gap_count DESC" },
    @{ id = [guid]::NewGuid().ToString(); question = "Show the highest readmission-risk encounters from Reporting Gold."; query = "SELECT TOP 10 patient_id, encounter_id, risk_probability, risk_tier, los_days FROM dbo.readmission_risk_scores ORDER BY risk_probability DESC" }
)
$ontologyFewShots = @(
    @{ id = [guid]::NewGuid().ToString(); question = "How many Patient entities exist in DevicePayerOntology? Use an aggregate with no sample or LIMIT."; query = "MATCH (p:Patient) RETURN count(p) AS patient_count" },
    @{ id = [guid]::NewGuid().ToString(); question = "Show one patient-to-device relationship from the ontology."; query = "MATCH (p:Patient)-[:linkedToDevice]->(d:Device) RETURN p.patientId AS patient_id, d.deviceId AS device_id LIMIT 5" },
    @{ id = [guid]::NewGuid().ToString(); question = "Trace one patient to claims and care gaps in the ontology."; query = "MATCH (p:Patient)-[:hasClaim]->(c:Claim) OPTIONAL MATCH (p)-[:hasCareGap]->(g:CareGap) RETURN p.patientId AS patient_id, c.claimId AS claim_id, g.gapType AS care_gap LIMIT 10" },
    @{ id = [guid]::NewGuid().ToString(); question = "Count patient-to-claim relationships in the ontology."; query = "MATCH (:Patient)-[r:hasClaim]->(:Claim) RETURN count(r) AS claim_edges" }
)
$ontologyEntityTypes = @('Patient','Encounter','Condition','MedRequest','Observation','ImagingStudy','Device','DeviceAssoc','DeviceTelemetry','Claim','Payer','Diagnosis','PatientDiagnosis','MedAdherence','CareGap','PatientRisk','HighCostClaimant')

$payerKqlInstructions = "Use MasimoEventhouse only for current/live payer operations: claim events, active fraud/high-cost/care-gap alerts, current telemetry, and the current worklist. Do not use KQL as a substitute for Reporting Gold history or DevicePayerOntology relationships."
$graphKqlInstructions = "Use MasimoEventhouse only to enrich ontology entities with current/live telemetry, alerts, claim events, fraud scores, or the current worklist. Never answer graph, relationship, path, trace, or traversal questions from KQL."
$requiredKqlFunctions = @(
    'fn_AlertHistoryTransform', 'fn_VitalsTrend', 'fn_DeviceStatus', 'fn_LatestReadings', 'fn_TelemetryByDevice',
    'fn_SpO2Alerts', 'fn_PulseRateAlerts', 'fn_ClinicalAlerts', 'fn_AlertLocationMap', 'fn_FraudRisk',
    'fn_HighCostTrajectory', 'fn_CareGapOnAlert', 'fn_PayerOpsWorklist', 'agent_FraudRisk',
    'agent_HighCostTrajectory', 'agent_PayerOpsWorklist', 'fn_OperationsFreshness', 'agent_ImagingSummary',
    'agent_CurrentAlertSeverity', 'agent_LowOxygen', 'agent_TelemetrySevenDaySummary', 'agent_CurrentDeviceSummary',
    'agent_CrossDomainContext', 'agent_CommonDiagnosesWithRepeatedAlerts', 'agent_CareGapAbnormalTelemetry',
    'agent_PayerPrioritySummary', 'agent_CriticalCareGaps', 'agent_HighUtilizationCareGaps', 'agent_HighestPriorityClaim'
)
$payerDataSources = @((New-KqlDatasource -DisplayName $kqlDbName -KqlDbId $kqlDbId -WorkspaceId $workspaceId -Elements $kqlElements -FewShots $payerKqlFewShots -Instructions $payerKqlInstructions -Functions $requiredKqlFunctions))
$graphDataSources = @((New-KqlDatasource -DisplayName $kqlDbName -KqlDbId $kqlDbId -WorkspaceId $workspaceId -Elements $kqlElements -FewShots $graphKqlFewShots -Instructions $graphKqlInstructions -Functions $requiredKqlFunctions))
$goldUnavailableInstruction = ""
if ($goldLh) {
    $goldTables = @('fact_claim','dim_payer','care_gaps','agg_high_cost_claimants','readmission_risk_scores')
    $payerDataSources += (New-LakehouseDatasource -DisplayName $goldLh.displayName -LakehouseId $goldLh.id -WorkspaceId $workspaceId -Tables $goldTables -FewShots $goldFewShots -Instructions "PRIMARY source for historical and analytical facts: claims, paid/billed amounts, payer categories, care gaps, high-cost cohorts, and readmission risk. For mixed questions query Gold and KQL separately and label each result.")
    $graphDataSources += (New-LakehouseDatasource -DisplayName $goldLh.displayName -LakehouseId $goldLh.id -WorkspaceId $workspaceId -Tables $goldTables -FewShots $goldFewShots -Instructions "Use Reporting Gold only to enrich ontology entities with historical claims, paid amounts, payer category, care gaps, high-cost cohort, and readmission risk. Do not infer graph relationships from table co-occurrence.")
} else {
    $goldUnavailableInstruction = " Gold Lakehouse was not available at deployment time; say history enrichment is unavailable."
}
$devicePayerOntologyDs = $null
$graphOntologyDs = $null
if (-not $SkipSnapshotMaterialization) {
    $devicePayerOntologyDs = New-OntologyDatasourceIfAvailable -OntologyName "DevicePayerOntology" -WorkspaceId $workspaceId -UserDescription "Payer-oriented device ontology linking patients, devices, diagnoses, claims, payer categories, care gaps, risk, high-cost cohorts, alerts, and telemetry." -Instructions "Use DevicePayerOntology for every relationship, graph, path, connected-context, trace, and traversal question. For mixed questions obtain ontology identifiers first, then enrich from KQL or Reporting Gold." -EntityTypes $ontologyEntityTypes -FewShots $ontologyFewShots
    $graphOntologyDs = New-OntologyDatasourceIfAvailable -OntologyName "DevicePayerOntology" -WorkspaceId $workspaceId -UserDescription "Primary graph source linking clinical, payer, risk, cost, care-gap, device, and telemetry entities." -Instructions "PRIMARY SOURCE for this agent. Query DevicePayerOntology first for every entity count, relationship, connected path, graph, trace, or traversal question. Never substitute a KQL snapshot for ontology semantics." -EntityTypes $ontologyEntityTypes -FewShots $ontologyFewShots
    if ($devicePayerOntologyDs) { $payerDataSources += $devicePayerOntologyDs }
    if ($graphOntologyDs) { $graphDataSources += $graphOntologyDs }
}


function New-OperationsAgentDefinition {
    param(
        [Parameter(Mandatory)][string]$Instructions,
        [Parameter(Mandatory)][string]$KqlDatabaseId,
        [Parameter(Mandatory)][string]$WorkspaceId,
        [string]$Recipient
    )
    # GA Operations Agent schema contract, verified against the live service:
    #   * `goals` was removed in June 2026 — goals belong in `instructions`.
    #   * An empty `playbook` object is rejected with
    #     "No rule definitions available in the playbook."; omit the key entirely
    #     and let the portal Generate Playbook step author it.
    #   * Exactly one knowledge source is accepted; a second data source fails with
    #     "The agent setup only supports a single knowledge source."
    #   * The data source must be the KQLDatabase item id. Passing the Eventhouse
    #     item id stores an unreadable definition whose getDefinition returns 500.
    $configuration = [ordered]@{
        instructions = $Instructions
        dataSources  = @{ masimoKqlDb = @{ id = $KqlDatabaseId; type = "KustoDatabase"; workspaceId = $WorkspaceId } }
        actions      = @{}
    }
    if (-not [string]::IsNullOrWhiteSpace($Recipient)) {
        $configuration['messageDestination'] = @{ kind = "Recipient"; recipient = $Recipient }
    }
    return [ordered]@{
        '$schema'     = "https://developer.microsoft.com/json-schemas/fabric/item/operationsAgents/definition/1.0.0/schema.json"
        configuration = $configuration
        shouldRun     = $false
    }
}

if (-not $SkipOpsAgent) {
    Write-Host ""; Write-Host "--- Operations agents ---" -ForegroundColor Cyan
    $opsInstructions = @'
Monitor Fabric Real-Time Intelligence ingestion health for the BrakeKat healthcare platform using the MasimoEventhouse KQL database, and raise an operator finding when a stream stops delivering data.

Monitored property source: the materialized table agent_ops_stream_health. It is refreshed from agent_OperationsStreamHealth() and holds exactly one current row per monitored stream. Use this table directly; do not recompute it from raw telemetry.

Columns and meaning:
- stream_name: the monitored pipeline (MasimoTelemetryStream, ClaimsRTIStream, ClinicalAlertPipeline)
- source_table: the Eventhouse table the stream writes to (TelemetryRaw, claims_events, AlertHistory)
- last_event_time_utc: UTC timestamp of the newest row in that table
- age_minutes: whole minutes between now and last_event_time_utc
- events_5m: rows written in the last five minutes
- severity: HEALTHY, WARNING, URGENT, or CRITICAL
- condition_name: STREAM_HEALTHY or STREAM_STALE
- refreshed_at: UTC time the row was materialized

Rules, evaluated per stream_name:
- Raise a WARNING finding when age_minutes is above 5.
- Raise an URGENT finding when age_minutes is above 15.
- Raise a CRITICAL finding when age_minutes is above 30.
- Raise a CRITICAL finding when events_5m is 0 while severity is not HEALTHY.
- Do not raise a finding while severity is HEALTHY.

Supporting context, for explanation only and never as the trigger:
- agent_ClinicalAggregateSummary() for current alert, device, and low-oxygen totals.
- fn_PayerOpsWorklist(60) for current payer fraud, high-cost, and care-gap routing.

Reporting:
- Report only rows present in agent_ops_stream_health; never invent a stream, table, or timestamp.
- Always state stream_name, source_table, age_minutes, events_5m, severity, and last_event_time_utc as UTC.
- Recommend checking the owning Eventstream topology and its source connection for any STREAM_STALE finding.
- Never run an action without explicit human approval.
'@
    $opsConfig = New-OperationsAgentDefinition -Instructions $opsInstructions -KqlDatabaseId $kqlDbId -WorkspaceId $workspaceId -Recipient $PayerOpsEmail | ConvertTo-Json -Depth 30
    $opsPart = @{ path = "Configurations.json"; payload = (ConvertTo-Base64 $opsConfig); payloadType = "InlineBase64" }
    $opsAgentId = $null
    $opsAgentSupported = $true
    try {
        $opsItems = Invoke-FabricApi -Endpoint "/workspaces/$workspaceId/operationsAgents"
        $existingOps = $opsItems.value | Where-Object { $_.displayName -eq "HealthcareOpsAgent" }
        if ($existingOps -is [array]) { $existingOps = $existingOps[0] }
        if ($existingOps) { $opsAgentId = $existingOps.id }
    } catch {
        $opsAgentSupported = $false
        Write-Host "  ⚠ OperationsAgent item type unavailable in this tenant: $(Get-ErrorMessage $_)" -ForegroundColor Yellow
    }
    if ($opsAgentSupported) {
        # A definition rejection is a real defect, not an unavailable item type. Fail
        # loudly instead of silently degrading to a DataAgent that leaves the
        # OperationsAgent panes empty.
        if ($opsAgentId) {
            $null = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$workspaceId/operationsAgents/$opsAgentId/updateDefinition" -Body @{ definition = @{ format = "OperationsAgentV1"; parts = @($opsPart) } }
            Write-Host "  ✓ HealthcareOpsAgent OperationsAgent updated ($opsAgentId)" -ForegroundColor Green
        } else {
            $createdOps = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$workspaceId/operationsAgents" -Body @{ displayName = "HealthcareOpsAgent"; description = "Operations agent for payer RTI, claims worklists, fraud/high-cost/care-gap routing, and clinical-alert context."; definition = @{ format = "OperationsAgentV1"; parts = @($opsPart) } }
            $opsAgentId = $createdOps.id
            Write-Host "  ✓ HealthcareOpsAgent OperationsAgent created ($opsAgentId)" -ForegroundColor Green
        }
        $opsReadback = Invoke-FabricApi -Method POST -Endpoint "/workspaces/$workspaceId/operationsAgents/$opsAgentId/getDefinition" -Body @{}
        $opsConfigPart = @($opsReadback.definition.parts) | Where-Object { $_.path -eq "Configurations.json" } | Select-Object -First 1
        if (-not $opsConfigPart) { throw "HealthcareOpsAgent definition did not read back after update." }
        $opsStored = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($opsConfigPart.payload)) | ConvertFrom-Json
        if ($opsStored.configuration.instructions -ne $opsInstructions) { throw "HealthcareOpsAgent instructions did not persist." }
        $opsSourceCount = @($opsStored.configuration.dataSources.PSObject.Properties).Count
        if ($opsSourceCount -ne 1) { throw "HealthcareOpsAgent must expose exactly one knowledge source; found $opsSourceCount." }
        Write-Host "  ✓ HealthcareOpsAgent definition verified: 1 knowledge source, $($opsInstructions.Length) instruction characters" -ForegroundColor Green
        Write-Host "  ✓ OperationsAgent URL: https://app.fabric.microsoft.com/groups/$workspaceId/operationalagents/$opsAgentId/config" -ForegroundColor Cyan
        Write-Host "    Open the agent and select Generate Playbook, then Start. Playbook authoring has no public API." -ForegroundColor Gray
    } else {
        $opsFallbackInstructions = "Monitor payer RTI streaming tables, fn_PayerOpsWorklist(60), fraud_scores, highcost_alerts, care_gap_alerts, and clinical AlertHistory. Route CRITICAL fraud to SIU Investigation Queue, CRITICAL high-cost to Care Management Referral, and CRITICAL care gaps to Provider Outreach. Always show alert_time, patient_id, provider_id when present, priority, metric_name, metric_value, and recommended next action.$goldUnavailableInstruction"
        $null = Deploy-DataAgent -Name "HealthcareOpsAgent" -AiInstructions $opsFallbackInstructions -DataSources $payerDataSources -WorkspaceId $workspaceId -Description "Fallback DataAgent for payer RTI, claims worklists, fraud/high-cost/care-gap routing, and clinical-alert context."
    }
    # The function-first rules below otherwise steer the agent away from the raw claims table: it
    # answered "no data" for claim-volume questions, and a looser wording made it join claims_events
    # to a function (join type mismatch) or print the statement instead of running it.
    $sourceRouter = @"
SOURCE ROUTER — HIGHEST PRIORITY:
- Use MasimoEventhouse only for current/live operational facts: claim events, active fraud, current high-cost/care-gap alerts, current telemetry, and the current worklist.
- Use healthcare1_reporting_gold for historical or analytical facts: claim history, paid/billed amounts, payer categories, historical care gaps, high-cost cohorts, and readmission risk.
- Use DevicePayerOntology for entity counts, relationships, paths, connected context, and every question containing graph, ontology, relationship, connected, trace, or traverse.
- For a mixed question, query every applicable source separately and synthesize the results. Label each fact with its source. Never substitute a KQL snapshot for Gold history or ontology traversal. Do not join across engines; combine the evidence at the answer layer.

"@
    $triagePrefix = $sourceRouter + "PRIORITY RULE - raw claim volume. If the question asks how many claim events exist, for a breakdown by event_type, or for a total claim count, execute exactly this Kusto statement against the Kusto source and report the rows it returns: claims_events | summarize n=count() by event_type. Execute it - never print the statement instead of running it. Do not join it to any other table or function, do not add a time filter, and do not wrap it in another query. Report each event_type with its count plus the overall total and name claims_events as the data source. This rule outranks every function-first rule below, and you must never answer `"no data`" for a claim-volume question without running it first.`n`n"
    $triageInstructions = if ($SkipSnapshotMaterialization) {
        "You are Payer Ops Triage in definition-only mode. Use payer RTI KQL sources for current claims and alerts. Ontology and Gold history bindings are intentionally deferred.$goldUnavailableInstruction"
    } else {
        $triagePrefix + "You are Payer Ops Triage. Route each intent to the source contract above. Current worklist: fn_PayerOpsWorklist(60). Fraud: fn_FraudRisk(60). Highest-priority claim: agent_HighestPriorityClaim(). Route FRAUD to SIU, HIGH_COST to care management, and CARE_GAP to provider outreach. Never invent routing fields or collapse current and historical grains.$goldUnavailableInstruction"
    }
    $null = Deploy-DataAgent -Name "Payer Ops Triage" -AiInstructions $triageInstructions -DataSources $payerDataSources -WorkspaceId $workspaceId -Description "Payer operations agent for claims RTI, fraud/high-cost/care-gap signals, DevicePayerOntology, and worklist prioritization."
} else {
    Write-Host "HealthcareOpsAgent + Payer Ops Triage skipped" -ForegroundColor Yellow
}

if (-not $SkipGraphAgent) {
    Write-Host ""; Write-Host "--- Healthcare Graph Agent shell ---" -ForegroundColor Cyan
    # Without the counting rule the agent reports the row count of a sampled traversal as the total:
    # it answered "1 distinct patient" against a graph holding 100.
    $graphCountRule = "Ontology graph counts must come from an aggregate count query over the ontology with no sampling and no LIMIT. Never report the number of rows an example query returns as the total. Present examples separately from counts.`n`n"
    $graphOntologyRouter = @"
ONTOLOGY-FIRST ROUTING — HIGHEST PRIORITY:
- DevicePayerOntology is the primary source for every entity, relationship, path, graph, connected-context, trace, traverse, and cross-domain question. You MUST call the ontology runtime for those questions. Never substitute agent_cross_domain_context or another KQL snapshot for a requested ontology traversal.
- Use MasimoEventhouse only to enrich ontology entities with current/live telemetry, alerts, claim events, fraud scores, or the current worklist.
- Use healthcare1_reporting_gold only to enrich ontology entities with historical claim amounts, payer categories, care gaps, high-cost cohorts, and readmission risk.
- For mixed questions, first obtain identifiers and relationships from DevicePayerOntology, then query KQL and/or Gold separately with those identifiers. State which source produced each part of the answer.

"@
    $graphInstructions = if ($SkipSnapshotMaterialization) {
        "You are Healthcare Graph Agent in definition-only mode. Use payer RTI KQL sources for current claims and alerts. Ontology and Gold bindings are intentionally deferred.$goldUnavailableInstruction"
    } else {
        $graphOntologyRouter + $graphCountRule + "You are Healthcare Graph Agent. Use the ontology for semantics and use KQL or Reporting Gold only as separately labeled evidence enrichments.$goldUnavailableInstruction"
    }
    $null = Deploy-DataAgent -Name "Healthcare Graph Agent" -AiInstructions $graphInstructions -DataSources $graphDataSources -WorkspaceId $workspaceId -Description "Cross-domain graph agent for DevicePayerOntology traversal across patient, device, diagnoses, claims, payer, risk, care gaps, and clinical alerts."
    $manualSteps = @(
        ("1. Open Fabric workspace {0}." -f $FabricWorkspaceName),
        '2. Open `DevicePayerOntology`.',
        '3. Graph hydration runs automatically via jobType=RefreshGraph on the GraphModel item; use Preview > Refresh graph model only to re-check interactively.',
        '4. Open Data Agent `Healthcare Graph Agent`.',
        '5. Confirm `DevicePayerOntology` is attached and the published agent exposes its MCP server.',
        '6. Validate with: `For patient <patient_id>, trace device, diagnoses, clinical alerts, claims, payer category, RAF risk, high-cost profile, and open care gaps.`'
    ) -join [Environment]::NewLine
    $manualDirectory = Join-Path (Split-Path -Parent $ScriptRoot) "state-tracking"
    New-Item -ItemType Directory -Path $manualDirectory -Force | Out-Null
    $manualPath = Join-Path $manualDirectory ".graph-agent-manual-steps-$FabricWorkspaceName.txt"
    Set-Content -Path $manualPath -Value $manualSteps -Encoding UTF8
    Write-Host $manualSteps -ForegroundColor Yellow
    Write-Host "  ✓ Manual graph attach steps written: $manualPath" -ForegroundColor Green
} else {
    Write-Host "Healthcare Graph Agent skipped" -ForegroundColor Yellow
}

Write-Host ""; Write-Host "Phase 7 Payer RTI & Ops complete." -ForegroundColor Green

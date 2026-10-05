$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "../storage-access-trusted-workspace.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors -and $parseErrors.Count -gt 0) {
    throw "storage-access-trusted-workspace.ps1 has parse errors: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "Get-BronzeTableRowCount",
    "Invoke-LakehouseScalarQuery",
    "Get-LakehouseTableRowCount",
    "Assert-BronzeTableHasData",
    "Assert-LakehouseTableHasData",
    "Wait-LakehouseTableHasData",
    "Sync-LakehouseSqlEndpoint",
    "Assert-SilverFhirReferencesIntact",
    "Invoke-OptionalDataPipelineNonBlocking",
    "Invoke-OptionalDataPipelineSerialized",
    "Get-FabricShortcutByName",
    "Ensure-FabricAdlsShortcut",
    "Invoke-CustomerInsightsTableRegistration",
    "New-FabricAdlsConnection",
    "Test-FabricAdlsConnectionMatch",
    "Test-FabricAdlsShortcutTarget",
    "Invoke-FabricApiRequest",
    "Test-TransientFabricNotebookSessionFailure"
)) {

    $functionAst = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName
    }, $true)
    if (-not $functionAst) { throw "Function '$functionName' was not found in storage-access-trusted-workspace.ps1" }
    Invoke-Expression $functionAst.Extent.Text
}
$ProductionInvokeFabricApiRequest = ${function:Invoke-FabricApiRequest}

$script:Logs = @()
function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [string]$Level = 'INFO'
    )
    $script:Logs += "[$Level] $Message"
}

function Record-Step {
    param([string]$Name, [string]$Status, [double]$Seconds)
}


function Assert-ThrowsLike {
    param(
        [Parameter(Mandatory)][scriptblock]$ScriptBlock,
        [Parameter(Mandatory)][string]$ExpectedText,
        [Parameter(Mandatory)][string]$Message
    )
    try {
        & $ScriptBlock
    } catch {
        if ($_.Exception.Message -notlike "*$ExpectedText*") {
            throw "$Message Expected error containing '$ExpectedText', got '$($_.Exception.Message)'."
        }
        return
    }
    throw "$Message Expected an exception containing '$ExpectedText'."
}

function Assert-Equal {
    param(
        [Parameter(Mandatory)]$Expected,
        [Parameter(Mandatory)]$Actual,
        [Parameter(Mandatory)][string]$Message
    )
    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

Assert-ThrowsLike `
    -ScriptBlock { Get-BronzeTableRowCount -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "bronze" -TableName "Patient" -FabricHeaders @{} } `
    -ExpectedText "Unsupported Bronze readiness table 'Patient'." `
    -Message "Bronze readiness should only allow the synthesized ClinicalFhir/ImagingDicom tables."

Assert-ThrowsLike `
    -ScriptBlock { Get-LakehouseTableRowCount -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -TableName "ImagingStudy; DROP TABLE Patient" -FabricHeaders @{} -Label "Silver Lakehouse" } `
    -ExpectedText "Unsafe table name 'ImagingStudy; DROP TABLE Patient'." `
    -Message "Lakehouse table validation should reject unsafe SQL table names before querying."

function Get-BronzeTableRowCount {
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$LakehouseId,
        [Parameter(Mandatory)][string]$LakehouseName,
        [Parameter(Mandatory)][string]$TableName,
        [Parameter(Mandatory)][hashtable]$FabricHeaders
    )
    return $script:BronzeRowCount
}

$script:BronzeRowCount = 0
Assert-ThrowsLike `
    -ScriptBlock { Assert-BronzeTableHasData -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "bronze" -TableName "ClinicalFhir" -FabricHeaders @{} -Reason "Clinical pipeline completion" } `
    -ExpectedText "Synthesized data was selected, but Bronze table dbo.ClinicalFhir has 0 rows after Clinical pipeline completion." `
    -Message "Bronze readiness should fail closed when synthesized ClinicalFhir is empty."

$script:BronzeRowCount = 42
Assert-BronzeTableHasData -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "bronze" -TableName "ClinicalFhir" -FabricHeaders @{} -Reason "Clinical pipeline completion"
if (-not ($script:Logs -contains "[INFO]   ✓ Bronze table dbo.ClinicalFhir contains 42 rows.")) {
    throw "Bronze readiness should log the validated non-zero row count."
}

function Get-LakehouseTableRowCount {
    param(
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][string]$LakehouseId,
        [Parameter(Mandatory)][string]$LakehouseName,
        [Parameter(Mandatory)][string]$TableName,
        [Parameter(Mandatory)][hashtable]$FabricHeaders,
        [string]$Label = 'Lakehouse'
    )
    return $script:LakehouseRowCount
}

$script:LakehouseRowCount = 0
Assert-ThrowsLike `
    -ScriptBlock { Assert-LakehouseTableHasData -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -TableName "ImagingStudy" -FabricHeaders @{} -Reason "Imaging pipeline completion" -Label "Silver Lakehouse" } `
    -ExpectedText "Silver Lakehouse table dbo.ImagingStudy has 0 rows after Imaging pipeline completion. Downstream report visuals will be empty." `
    -Message "Silver validation should fail closed when required imaging report tables are empty."

$script:LakehouseRowCount = 7
Assert-LakehouseTableHasData -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -TableName "ImagingStudy" -FabricHeaders @{} -Reason "Imaging pipeline completion" -Label "Silver Lakehouse"
if (-not ($script:Logs -contains "[INFO]   ✓ Silver Lakehouse table dbo.ImagingStudy contains 7 rows.")) {
    throw "Silver validation should log the validated non-zero row count."
}


function Get-CachedTokenValue {
    param(
        [Parameter(Mandatory)][string]$Key,
        [string]$ResourceUrl = '',
        [string]$ResourceTypeName = ''
    )
    return "token"
}

function Invoke-FabricApiRequest {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][hashtable]$Headers,
        [object]$Body,
        [string]$Description = ''
    )
    return [pscustomobject]@{
        Response = [pscustomobject]@{
            properties = [pscustomobject]@{
                sqlEndpointProperties = [pscustomobject]@{ connectionString = "server.database.fabric.microsoft.com" }
            }
        }
    }
}

$cmaRegressionResult = Invoke-OptionalDataPipelineNonBlocking `
    -WorkspaceId "workspace-id" -PipelineName "healthcare1_msft_cma" `
    -Pipeline ([pscustomobject]@{ id = "pipeline-id" }) -FabricHeaders @{} `
    -StepName "CMA Pipeline"
Assert-Equal -Expected $true -Actual $cmaRegressionResult.Invoked `
    -Message "A successful 202 optional pipeline trigger must expose Invoked=true even when the API response has no Invoked property."
Assert-Equal -Expected "INVOKED" -Actual $cmaRegressionResult.Status `
    -Message "A successful optional pipeline trigger should report INVOKED status."

$SqlEndpointInvokeFabricApiRequest = ${function:Invoke-FabricApiRequest}
function Get-FabricApiHeaders {
    param([string]$AccessToken)
    return @{}
}
function Invoke-FabricApiRequest {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][hashtable]$Headers,
        [object]$Body,
        [string]$Description = ''
    )
    return [pscustomobject]@{
        Response = [pscustomobject]@{
            value = @([pscustomobject]@{ id = 'shortcut-id'; name = 'main'; path = '/Files' })
        }
    }
}
$normalizedShortcut = Get-FabricShortcutByName `
    -AccessToken 'token' -WorkspaceId 'workspace-id' -LakehouseId 'lakehouse-id' `
    -ShortcutName 'main' -ShortcutPath 'Files'
Assert-Equal -Expected 'shortcut-id' -Actual $normalizedShortcut.id `
    -Message 'Shortcut lookup should normalize Fabric API leading slashes in the path.'

$validConnection = [pscustomobject]@{
    connectionDetails = [pscustomobject]@{
        path = 'https://storage.dfs.core.windows.net/customer-insights'
        type = 'AzureDataLakeStorage'
    }
    credentialDetails = [pscustomobject]@{ credentialType = 'WorkspaceIdentity' }
}
Assert-Equal -Expected $true -Actual (Test-FabricAdlsConnectionMatch -Connection $validConnection -StorageAccountName 'storage' -ContainerName 'customer-insights') `
    -Message 'Exact Customer Insights ADLS connection details should be reusable.'
$validConnection.connectionDetails.path = 'https://storage.dfs.core.windows.net/wrong-container'
Assert-Equal -Expected $false -Actual (Test-FabricAdlsConnectionMatch -Connection $validConnection -StorageAccountName 'storage' -ContainerName 'customer-insights') `
    -Message 'A same-name connection with a stale container target must be rejected.'

$validShortcut = [pscustomobject]@{
    target = [pscustomobject]@{
        adlsGen2 = [pscustomobject]@{
            location = 'https://storage.dfs.core.windows.net'
            subpath = '/customer-insights'
            connectionId = 'connection-id'
        }
    }
}
Assert-Equal -Expected $true -Actual (Test-FabricAdlsShortcutTarget -Shortcut $validShortcut -ExpectedLocation 'https://storage.dfs.core.windows.net' -ExpectedSubpath '/customer-insights' -ExpectedConnectionId 'connection-id') `
    -Message 'Exact Customer Insights shortcut details should pass validation.'
$validShortcut.target.adlsGen2.subpath = '/wrong-container'
Assert-Equal -Expected $false -Actual (Test-FabricAdlsShortcutTarget -Shortcut $validShortcut -ExpectedLocation 'https://storage.dfs.core.windows.net' -ExpectedSubpath '/customer-insights' -ExpectedConnectionId 'connection-id') `
    -Message 'A same-name shortcut with a stale target must be rejected.'

$FabricManagementEndpoint = 'https://api.fabric.microsoft.com'
function Get-FabricApiHeaders {
    param([string]$AccessToken)
    return @{}
}
$script:DuplicateConnection = $null
$script:ConnectionLookupCount = 0
function Get-FabricConnectionByDisplayName {
    param([string]$AccessToken, [string]$DisplayName)
    $script:ConnectionLookupCount++
    if ($script:ConnectionLookupCount -eq 1) { return $null }
    return $script:DuplicateConnection
}
function Invoke-FabricApiRequest {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [object]$Body, [string]$Description = '')
    if ($Method -eq 'Get' -and $Uri -like '*supportedConnectionTypes') {
        return [pscustomobject]@{ Response = [pscustomobject]@{ value = @() }; StatusCode = 200; Headers = @{} }
    }
    if ($Method -eq 'Post' -and $Uri -like '*/connections') {
        throw 'FABRIC API Post connection returned 409 DuplicateConnectionName'
    }
    throw "Unexpected connection API call: $Method $Uri"
}
$script:DuplicateConnection = [pscustomobject]@{
    id = 'duplicate-id'
    connectionDetails = [pscustomobject]@{ path = 'https://storage.dfs.core.windows.net/wrong-container'; type = 'AzureDataLakeStorage' }
    credentialDetails = [pscustomobject]@{ credentialType = 'WorkspaceIdentity' }
}
Assert-ThrowsLike `
    -ScriptBlock { New-FabricAdlsConnection -AccessToken 'token' -DisplayName 'duplicate' -StorageAccountName 'storage' -ContainerName 'customer-insights' } `
    -ExpectedText "does not match ADLS target" `
    -Message 'Duplicate-name race must reject a stale connection target.'

$script:ConnectionLookupCount = 0
$script:DuplicateConnection = [pscustomobject]@{
    id = 'verified-duplicate-id'
    connectionDetails = [pscustomobject]@{ path = 'https://storage.dfs.core.windows.net/customer-insights'; type = 'AzureDataLakeStorage' }
    credentialDetails = [pscustomobject]@{ credentialType = 'WorkspaceIdentity' }
}
$verifiedDuplicateId = New-FabricAdlsConnection -AccessToken 'token' -DisplayName 'duplicate' -StorageAccountName 'storage' -ContainerName 'customer-insights'
Assert-Equal -Expected 'verified-duplicate-id' -Actual $verifiedDuplicateId `
    -Message 'Duplicate-name race may reuse only an exact validated connection.'

$script:ShortcutLookups = 0
function Get-FabricShortcutByName {
    param([string]$AccessToken, [string]$WorkspaceId, [string]$LakehouseId, [string]$ShortcutName, [string]$ShortcutPath)
    $script:ShortcutLookups++
    if ($script:ShortcutLookups -eq 1) { return $null }
    return [pscustomobject]@{
        id = 'concurrent-shortcut'
        name = 'main'
        path = '/Files'
        target = [pscustomobject]@{
            adlsGen2 = [pscustomobject]@{
                location = 'https://storage.dfs.core.windows.net'
                subpath = '/customer-insights'
                connectionId = 'connection-id'
            }
        }
    }
}
function Invoke-FabricApiRequest {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [object]$Body, [string]$Description = '')
    if ($Method -eq 'Post' -and $Uri -like '*shortcuts?shortcutConflictPolicy=Abort') {
        throw 'FABRIC API Post shortcut returned 409 EntityConflict'
    }
    throw "Unexpected shortcut API call: $Method $Uri"
}
$raceRecoveredShortcut = Ensure-FabricAdlsShortcut `
    -AccessToken 'token' -WorkspaceId 'workspace-id' -LakehouseId 'lakehouse-id' `
    -ShortcutName 'main' -ShortcutPath 'Files' `
    -ExpectedLocation 'https://storage.dfs.core.windows.net' `
    -ExpectedSubpath '/customer-insights' -ExpectedConnectionId 'connection-id' `
    -FabricHeaders @{}
Assert-Equal -Expected 'concurrent-shortcut' -Actual $raceRecoveredShortcut.id `
    -Message 'Shortcut duplicate-name race should re-read and validate the concurrently created shortcut.'
Assert-Equal -Expected 2 -Actual $script:ShortcutLookups `
    -Message 'Shortcut duplicate-name race should perform a readback after the 409 conflict.'

$FabricManagementEndpoint = 'https://api.fabric.microsoft.com'
$script:RegistrationDefinitionChecked = $false
$script:RegistrationRunChecked = $false
function Wait-FabricOperation { param($OperationResult, [hashtable]$Headers, [string]$Description, [int]$TimeoutSeconds = 600) }
function Start-Sleep { param([int]$Seconds) }
function Invoke-FabricApiRequest {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][hashtable]$Headers,
        [object]$Body,
        [string]$Description = ''
    )
    if ($Method -eq 'Get' -and $Uri -like '*items?type=Notebook') {
        return [pscustomobject]@{ Response = [pscustomobject]@{ value = @([pscustomobject]@{ id = 'repair-notebook'; type = 'Notebook'; displayName = 'Customer Insights Table Registration Repair' }) }; StatusCode = 200; Headers = @{} }
    }
    if ($Method -eq 'Post' -and $Uri -like '*updateDefinition') {
        $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$Body.definition.parts[0].payload))
        if ($decoded -notmatch 'Files/main/all_entities' -or $decoded -notmatch 'CREATE TABLE IF NOT EXISTS') {
            throw 'Registration notebook payload does not register populated Customer Insights Delta outputs.'
        }
        $script:RegistrationDefinitionChecked = $true
        return [pscustomobject]@{ Response = $null; StatusCode = 200; Headers = @{} }
    }
    if ($Method -eq 'Get' -and $Uri -like '*jobs/instances?limit=5') {
        return [pscustomobject]@{ Response = [pscustomobject]@{ value = @() }; StatusCode = 200; Headers = @{} }
    }
    if ($Method -eq 'Post' -and $Uri -like '*jobs/instances?jobType=RunNotebook') {
        Assert-Equal -Expected 'customer-insights-id' -Actual $Body.executionData.configuration.defaultLakehouse.id `
            -Message 'Registration notebook must run against the Customer Insights Lakehouse.'
        Assert-Equal -Expected 'healthcare1_msft_customer_insights' -Actual $Body.executionData.configuration.defaultLakehouse.name `
            -Message 'Registration notebook must retain the Customer Insights Lakehouse name.'
        $script:RegistrationRunChecked = $true
        return [pscustomobject]@{ Response = $null; StatusCode = 202; Headers = @{ Location = 'https://api.fabric.microsoft.com/job/registration' } }
    }
    if ($Method -eq 'Get' -and $Uri -eq 'https://api.fabric.microsoft.com/job/registration') {
        return [pscustomobject]@{ Response = [pscustomobject]@{ status = 'Completed' }; StatusCode = 200; Headers = @{} }
    }
    throw "Unexpected registration API call: $Method $Uri"
}
$registrationResult = Invoke-CustomerInsightsTableRegistration `
    -WorkspaceId 'workspace-id' -LakehouseId 'customer-insights-id' `
    -LakehouseName 'healthcare1_msft_customer_insights' -FabricHeaders @{}
Assert-Equal -Expected $true -Actual $registrationResult `
    -Message 'Customer Insights registration notebook should complete successfully.'
Assert-Equal -Expected $true -Actual $script:RegistrationDefinitionChecked `
    -Message 'Customer Insights registration must update the repair notebook definition.'
Assert-Equal -Expected $true -Actual $script:RegistrationRunChecked `
    -Message 'Customer Insights registration must execute the repair notebook.'
Remove-Item function:Start-Sleep -ErrorAction SilentlyContinue
$script:SerializedPosts = 0
$script:SerializedPolls = 0
$script:SerializedFailureMessage = 'DELTA_CONCURRENT_APPEND ConcurrentAppendException'
function Invoke-FabricApiRequest {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][hashtable]$Headers,
        [object]$Body,
        [string]$Description = ''
    )
    if ($Method -eq 'Post') {
        $script:SerializedPosts++
        return [pscustomobject]@{ Response = $null }
    }
    $script:SerializedPolls++
    $job = if ($script:SerializedPosts -eq 1) {
        [pscustomobject]@{
            status = 'Failed'
            startTimeUtc = (Get-Date).ToUniversalTime().ToString('o')
            failureReason = [pscustomobject]@{ message = $script:SerializedFailureMessage }
        }
    } else {
        [pscustomobject]@{
            status = 'Completed'
            startTimeUtc = (Get-Date).ToUniversalTime().ToString('o')
            failureReason = $null
        }
    }
    return [pscustomobject]@{ Response = [pscustomobject]@{ value = @($job) } }
}
function Start-Sleep { param([int]$Seconds) }
$skipResult = Invoke-OptionalDataPipelineSerialized `
    -WorkspaceId 'workspace-id' -PipelineName 'healthcare1_msft_customer_insights' `
    -Pipeline $null -FabricHeaders @{} -StepName 'Customer Insights Pipeline'
Assert-Equal -Expected 'SKIPPED' -Actual $skipResult.Status `
    -Message 'A null pipeline passed to the serialized helper should return SKIPPED status.'
Assert-Equal -Expected $false -Actual $skipResult.Invoked `
    -Message 'A skipped serialized pipeline should not be invoked.'

$ciResult = Invoke-OptionalDataPipelineSerialized `
    -WorkspaceId 'workspace-id' -PipelineName 'healthcare1_msft_customer_insights' `
    -Pipeline ([pscustomobject]@{ id = 'pipeline-id' }) -FabricHeaders @{} `
    -StepName 'Customer Insights Pipeline' -MaxAttempts 3 -TimeoutMinutes 1
Assert-Equal -Expected 'COMPLETED' -Actual $ciResult.Status `
    -Message 'Customer Insights should complete via the serialized helper.'
Assert-Equal -Expected $true -Actual $ciResult.Invoked `
    -Message 'A successful optional serialized pipeline trigger must expose Invoked=true.'
Assert-Equal -Expected 2 -Actual $script:SerializedPosts `
    -Message 'Customer Insights should retry exactly once after a concurrent append failure.'
$script:SerializedPosts = 0
$script:SerializedPolls = 0
$script:SerializedFailureMessage = 'AnalysisException: optional target table has no source rows'
$ciWarning = Invoke-OptionalDataPipelineSerialized `
    -WorkspaceId 'workspace-id' -PipelineName 'healthcare1_msft_customer_insights' `
    -Pipeline ([pscustomobject]@{ id = 'pipeline-id' }) -FabricHeaders @{} `
    -StepName 'Customer Insights Pipeline' -MaxAttempts 1 -TimeoutMinutes 1 -NonBlockingFailure
Assert-Equal -Expected 'WARN' -Actual $ciWarning.Status `
    -Message 'Customer Insights terminal failure should remain a warning when NonBlockingFailure is selected.'
Assert-Equal -Expected $true -Actual $ciWarning.Invoked `
    -Message 'A warning-only terminal failure should record that the optional pipeline was invoked.'
$script:SerializedPosts = 0
$script:SerializedPolls = 0
$script:SerializedFailureMessage = 'DELTA_CONCURRENT_APPEND ConcurrentAppendException'

$serializedResult = Invoke-OptionalDataPipelineSerialized `
    -WorkspaceId 'workspace-id' -PipelineName 'healthcare1_msft_cma' `
    -Pipeline ([pscustomobject]@{ id = 'pipeline-id' }) -FabricHeaders @{} `
    -StepName 'CMA Pipeline Retry' -MaxAttempts 3 -TimeoutMinutes 1
Assert-Equal -Expected 'COMPLETED' -Actual $serializedResult.Status `
    -Message 'CMA retry should recover from a Delta concurrent append conflict.'
Assert-Equal -Expected 2 -Actual $script:SerializedPosts `
    -Message 'CMA retry should invoke exactly one replacement run after a concurrent append failure.'
Remove-Item function:Start-Sleep -ErrorAction SilentlyContinue
Set-Item function:Invoke-FabricApiRequest $SqlEndpointInvokeFabricApiRequest

$script:SqlAttempts = 0
$script:LakehouseQueryExecutor = {
    param($Script)
    $script:SqlAttempts++
    if ($script:SqlAttempts -eq 1) {
        $global:LASTEXITCODE = 1
        return "pyodbc.OperationalError: ('08S01', 'TCP Provider: Error code 0x2746 (10054)')"
    }
    $global:LASTEXITCODE = 0
    return "42"
}
function Start-Sleep { param([int]$Seconds) }
$sqlResult = Invoke-LakehouseScalarQuery -Server 'server' -Database 'database' -Token 'token' -Query 'SELECT 42'
Assert-Equal -Expected '42' -Actual $sqlResult `
    -Message 'Transient Lakehouse SQL connection failures should be retried.'
Assert-Equal -Expected 2 -Actual $script:SqlAttempts `
    -Message 'Lakehouse SQL retry should stop immediately after success.'
Remove-Variable -Scope Script -Name LakehouseQueryExecutor -ErrorAction SilentlyContinue
Remove-Item function:Start-Sleep -ErrorAction SilentlyContinue

. (Join-Path $PSScriptRoot '../../utilities/python-runtime.ps1')
$hlsRepoRoot = Join-Path ([IO.Path]::GetTempPath()) ('hls-missing-venv-' + [guid]::NewGuid().ToString('N'))
$script:UnexpectedPythonCalls = 0
function python { $script:UnexpectedPythonCalls++; $global:LASTEXITCODE = 0; '42' }
$rejectedMissingRuntime = $false
try {
    Invoke-LakehouseScalarQuery -Server 'server' -Database 'database' -Token 'token' -Query 'SELECT 42' | Out-Null
} catch {
    $rejectedMissingRuntime = $true
} finally {
    Remove-Item function:python
}
Assert-Equal -Expected $true -Actual $rejectedMissingRuntime `
    -Message 'SQL diagnostics must reject a missing managed interpreter.'
Assert-Equal -Expected 0 -Actual $script:UnexpectedPythonCalls `
    -Message 'SQL diagnostics must not fall back to an unrelated PATH interpreter.'
Assert-Equal -Expected $false -Actual (Test-Path $hlsRepoRoot) `
    -Message 'SQL diagnostics must not create a missing venv.'
Assert-Equal -Expected $false -Actual (Test-Path Env:_HDS_SQL_TOKEN) `
    -Message 'Interpreter selection failure must clear SQL credentials.'


function Invoke-LakehouseScalarQuery {
    param(
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)][string]$Database,
        [Parameter(Mandatory)][string]$Token,
        [Parameter(Mandatory)][string]$Query
    )
    if ($Query -like "*INFORMATION_SCHEMA.TABLES*") {
        $script:SilverVisibilityChecks++
        return $script:SilverVisibleTables[[Math]::Min($script:SilverVisibilityChecks, $script:SilverVisibleTables.Count) - 1]
    }
    $script:SilverReferenceQueries += $Query
    return $script:SilverBrokenReferenceCount
}

$script:SilverReferenceQueries = @()
$script:SilverBrokenReferenceCount = 0
$script:SilverVisibleTables = @(13)
$script:SilverVisibilityChecks = 0
Assert-SilverFhirReferencesIntact -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -FabricHeaders @{}
if (-not ($script:SilverReferenceQueries[0] -like "*`$.reference*`$.msftSourceReference*`$.idOrig*`$.identifier.value*")) {
    throw "Silver reference validation should accept reference, HDS source fields, and FHIR identifier.value. Query was: $($script:SilverReferenceQueries[0])"
}
if (-not ($script:Logs -contains "[INFO]   ✓ Silver FHIR references/source identifiers are present for OMOP/CMA source tables.")) {
    throw "Silver reference validation should log success when reference/source identifiers exist."
}

$script:SilverReferenceQueries = @()
$script:SilverBrokenReferenceCount = 130
Assert-ThrowsLike `
    -ScriptBlock { Assert-SilverFhirReferencesIntact -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -FabricHeaders @{} } `
    -ExpectedText "Silver FHIR reference check failed for Condition.subject: 130 rows have missing $.reference/$.msftSourceReference/$.idOrig/$.identifier.value." `
    -Message "Silver reference validation should fail only when all supported HDS reference fields are missing."

function Start-Sleep { param([int]$Seconds) }
$script:EndpointSyncs = 0
Set-Item function:Invoke-FabricApiRequest {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [object]$Body, [string]$Description = '')
    if ($Uri -like '*/sqlEndpoints/endpoint-id/refreshMetadata') {
        $script:EndpointSyncs++
        return [pscustomobject]@{ StatusCode = 200; Headers = @{} }
    }
    return [pscustomobject]@{ Response = [pscustomobject]@{ properties = [pscustomobject]@{
        sqlEndpointProperties = [pscustomobject]@{ connectionString = "server.database.fabric.microsoft.com"; id = "endpoint-id" } } } }
}
$script:SilverReferenceQueries = @()
$script:SilverBrokenReferenceCount = 0
$script:SilverVisibleTables = @(0, 13)
$script:SilverVisibilityChecks = 0
Assert-SilverFhirReferencesIntact -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -FabricHeaders @{}
Assert-Equal -Expected 2 -Actual $script:SilverVisibilityChecks `
    -Message 'Silver validation should wait for a lagging SQL endpoint to list its tables before querying them.'
Assert-Equal -Expected 1 -Actual $script:EndpointSyncs `
    -Message 'Silver validation should ask the SQL endpoint to sync its metadata before re-checking.'

$script:SilverVisibleTables = @(5)
$script:SilverVisibilityChecks = 0
Assert-ThrowsLike `
    -ScriptBlock { Assert-SilverFhirReferencesIntact -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "silver" -FabricHeaders @{} } `
    -ExpectedText "Silver SQL endpoint lists 5 of 13 required tables after 20 minutes." `
    -Message "Silver validation should fail clearly when the endpoint never lists the required tables."

# The Lakehouse wrote rows, but the SQL endpoint still serves the empty table version until synced.
$script:EndpointSyncs = 0
Set-Item function:Get-LakehouseTableRowCount {
    param([string]$WorkspaceId, [string]$LakehouseId, [string]$LakehouseName, [string]$TableName, [hashtable]$FabricHeaders, [string]$Label)
    if ($script:EndpointSyncs -gt 0) { return 8794 } else { return 0 }
}
Wait-LakehouseTableHasData -WorkspaceId "ws" -LakehouseId "lh" -LakehouseName "bronze" -TableName "ImagingDicom" `
    -FabricHeaders @{} -Reason "Imaging pipeline completion" -PollSeconds 0
Assert-Equal -Expected 1 -Actual $script:EndpointSyncs `
    -Message 'A readiness wait should sync the SQL endpoint when it still reports an empty table.'
if (-not ($script:Logs -contains "[INFO]   ✓ Lakehouse table dbo.ImagingDicom contains 8794 rows.")) {
    throw "A readiness wait should report the rows the synced endpoint shows."
}
Remove-Item function:Start-Sleep -ErrorAction SilentlyContinue

if (-not (Test-TransientFabricNotebookSessionFailure -FailureText 'Failed to create session for executing notebook. SessionId: abc')) {
    throw "Notebook session creation failures should be classified as transient."
}
if (Test-TransientFabricNotebookSessionFailure -FailureText 'Notebook failed because a required table is missing') {
    throw "Deterministic notebook failures must not be classified as transient session failures."
}

Set-Item -Path function:Invoke-FabricApiRequest -Value $ProductionInvokeFabricApiRequest
$script:FabricRequestAttempts = 0
$script:AccessTokenCache = @{ fabric = @{ Token = 'expired'; ExpiresOn = (Get-Date).AddHours(1) } }
function Get-FabricApiAccessToken { return 'fresh-token' }
function Invoke-WebRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers,
        [string]$ErrorAction,
        [switch]$SkipHttpErrorCheck
    )
    $script:FabricRequestAttempts++
    if ($script:FabricRequestAttempts -eq 1) {
        return [pscustomobject]@{ StatusCode = 401; Content = '{"errorCode":"TokenExpired","message":"Access token has expired"}'; Headers = @{} }
    }
    Assert-Equal -Expected 'Bearer fresh-token' -Actual $Headers.Authorization `
        -Message 'Fabric retry should use a refreshed bearer token.'
    return [pscustomobject]@{ StatusCode = 200; Content = '{"value":[]}'; Headers = @{} }
}
$refreshHeaders = @{ Authorization = 'Bearer expired'; 'Content-Type' = 'application/json' }
$refreshResult = Invoke-FabricApiRequest -Method Get -Uri 'https://example.test/items' -Headers $refreshHeaders -Description 'token refresh test'
Assert-Equal -Expected 2 -Actual $script:FabricRequestAttempts `
    -Message 'Expired Fabric tokens should trigger exactly one retry.'
Assert-Equal -Expected 200 -Actual $refreshResult.StatusCode `
    -Message 'Fabric request should succeed after token refresh.'
Assert-Equal -Expected 'Bearer fresh-token' -Actual $refreshHeaders.Authorization `
    -Message 'Caller headers should retain the refreshed token.'
Write-Host "Storage validation helper tests passed."

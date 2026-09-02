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
    "Assert-SilverFhirReferencesIntact",
    "Invoke-OptionalDataPipelineNonBlocking",
    "Invoke-OptionalDataPipelineSerialized",
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
$script:SerializedPosts = 0
$script:SerializedPolls = 0
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
            failureReason = [pscustomobject]@{ message = 'DELTA_CONCURRENT_APPEND ConcurrentAppendException' }
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


function Invoke-LakehouseScalarQuery {
    param(
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)][string]$Database,
        [Parameter(Mandatory)][string]$Token,
        [Parameter(Mandatory)][string]$Query
    )
    $script:SilverReferenceQueries += $Query
    return $script:SilverBrokenReferenceCount
}

$script:SilverReferenceQueries = @()
$script:SilverBrokenReferenceCount = 0
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

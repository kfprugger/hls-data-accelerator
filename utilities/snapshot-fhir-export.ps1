# Invoked synchronously before any HDS ingestion can move fhir-export blobs.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroupName,
    [Parameter(Mandatory)][string]$SubscriptionId,
    [switch]$ReuseSnapshot,
    [switch]$ClearSnapshotOnly
)
$ErrorActionPreference = 'Stop'
$accounts = @(az storage account list -g $ResourceGroupName --subscription $SubscriptionId --query '[?isHnsEnabled].name' -o json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $accounts.Count -ne 1) { throw 'Expected exactly one HDS ADLS account for the Databricks snapshot.' }
$account = $accounts[0]
function Get-BlobManifest([string]$Container) {
    $raw = az storage blob list --account-name $account --container-name $Container --auth-mode login --num-results '*' --query '[].name' -o json --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot list $Container. The deploying user needs Storage Blob Data Contributor on $account (Phase 1 grants it to AdminSecurityGroup)."
    }
    [string[]]$names = @($raw | ConvertFrom-Json)
    [Array]::Sort($names, [StringComparer]::Ordinal)
    return $names
}
function Clear-DatabricksSnapshot {
    # Delete top-level directories recursively on the DFS service, not concurrently with their files.
    # Drain bounded batches so snapshots with more than one list page are also emptied.
    do {
        $raw = az storage fs file list --account-name $account --file-system fhir-export-databricks --auth-mode login --recursive false --num-results 5000 --only-show-errors -o json
        if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate the previous Databricks snapshot; ingestion remains blocked.' }
        $paths = @($raw | ConvertFrom-Json)
        foreach ($path in $paths) {
            if ($path.isDirectory -eq $true -or $path.isDirectory -eq 'true') {
                az storage fs directory delete --account-name $account --file-system fhir-export-databricks --name $path.name --auth-mode login --yes --only-show-errors -o none
            } else {
                az storage fs file delete --account-name $account --file-system fhir-export-databricks --path $path.name --auth-mode login --yes --only-show-errors -o none
            }
            if ($LASTEXITCODE -ne 0) { throw "Cannot remove snapshot path '$($path.name)'; ingestion remains blocked." }
        }
    } while ($paths.Count)
    if (@(Get-BlobManifest 'fhir-export-databricks').Count) { throw 'Databricks snapshot container is not empty; ingestion remains blocked.' }
}
if ($ClearSnapshotOnly) {
    if ($ReuseSnapshot) { throw 'ClearSnapshotOnly and ReuseSnapshot cannot be combined.' }
    az storage container create --account-name $account --name fhir-export-databricks --auth-mode login --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create snapshot container. Storage Blob Data Contributor is required.' }
    Clear-DatabricksSnapshot
    return
}
if ($ReuseSnapshot) {
    $count = @(Get-BlobManifest 'fhir-export-databricks').Count
    if ($count -lt 1) { throw 'No preserved Databricks export exists. Run a full export or add Databricks after deployment.' }
    Write-Host "Reusing preserved Databricks export ($count blobs); HDS source may already have been consumed."
    return
}
[string[]]$source = @(Get-BlobManifest 'fhir-export')
if ($source.Count -lt 1) { throw 'FHIR export is empty; refusing to start HDS ingestion without a Databricks snapshot.' }
az storage container create --account-name $account --name fhir-export-databricks --auth-mode login --only-show-errors -o none
if ($LASTEXITCODE -ne 0) { throw 'Cannot create snapshot container. Storage Blob Data Contributor is required.' }
$previousLogin = $env:AZCOPY_AUTO_LOGIN_TYPE
try {
    $env:AZCOPY_AUTO_LOGIN_TYPE = 'AZCLI'
    Clear-DatabricksSnapshot
    azcopy copy "https://$account.blob.core.windows.net/fhir-export/*" "https://$account.blob.core.windows.net/fhir-export-databricks" --recursive=true --overwrite=true --check-length=true --output-level=essential
    if ($LASTEXITCODE -ne 0) { throw 'Server-side Databricks export snapshot failed; ingestion remains blocked.' }
} finally {
    $env:AZCOPY_AUTO_LOGIN_TYPE = $previousLogin
}
[string[]]$destination = @(Get-BlobManifest 'fhir-export-databricks')
[string[]]$sourceAfterCopy = @(Get-BlobManifest 'fhir-export')
$expected = ConvertTo-Json -InputObject $source -Compress
if ((ConvertTo-Json -InputObject $destination -Compress) -cne $expected -or (ConvertTo-Json -InputObject $sourceAfterCopy -Compress) -cne $expected) {
    throw 'Snapshot blob-name manifest mismatch between source before/after and destination. HDS ingestion remains blocked; retry the snapshot.'
}
Write-Host "Databricks FHIR export snapshot verified: $($destination.Count) blob names; HDS ingestion can proceed."

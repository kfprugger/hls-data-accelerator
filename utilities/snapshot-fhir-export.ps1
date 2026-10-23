# Invoked synchronously before any HDS ingestion can move fhir-export blobs.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroupName,
    [Parameter(Mandatory)][string]$SubscriptionId,
    [switch]$ReuseSnapshot
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
    azcopy remove "https://$account.blob.core.windows.net/fhir-export-databricks/*" --recursive=true --output-level=essential
    if ($LASTEXITCODE -ne 0) { throw 'Cannot empty the previous Databricks snapshot; ingestion remains blocked.' }
    if (@(Get-BlobManifest 'fhir-export-databricks').Count) { throw 'Databricks snapshot container is not empty; ingestion remains blocked.' }
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

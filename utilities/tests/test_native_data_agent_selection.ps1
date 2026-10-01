#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../data-agent-selection.ps1')
function Assert-True($value,[string]$message){if(-not $value){throw $message}}
function Assert-Throws([scriptblock]$action,[string]$pattern){try{&$action}catch{if($_.Exception.Message -notmatch $pattern){throw};return};throw "Expected failure: $pattern"}
$script:patient=[pscustomobject]@{id='native+patient/=';type='Table';displayName='Patient';state='Available';isSelected=$false;hasSubElements=$false}
$script:condition=[pscustomobject]@{id='native-condition';type='Table';displayName='Condition';state='Available';isSelected=$true;hasSubElements=$false}
$script:function=[pscustomobject]@{id='native-fn';type='Function';displayName='fn_Count';state='Available';isSelected=$false;hasSubElements=$false}
$script:patches=0
$script:duplicate=$false
$api={
 param($method,$endpoint,$body)
 $query=[Web.HttpUtility]::ParseQueryString(([uri]('https://local.invalid'+$endpoint)).Query)
 if($method -eq 'PATCH'){
  $script:patches++
  $matches=@($script:patient,$script:condition,$script:function|Where-Object id -eq $query['id'])
  if($matches.Count -ne 1){throw 'Unknown native element ID'}
  $matches[0].isSelected=$body.isSelected
  return $matches[0]
 }
 if($query['rootId'] -eq 'schemas'){return [pscustomobject]@{value=@([pscustomobject]@{id='dbo';type='Schema';displayName='dbo';hasSubElements=$true});continuationToken=$null}}
 if($query['rootId'] -eq 'dbo'){return [pscustomobject]@{value=@([pscustomobject]@{id='tables';type='Tables';displayName='Tables';hasSubElements=$true});continuationToken=$null}}
 if($query['rootId'] -eq 'tables'){
  $values=@($script:patient)
  if($script:duplicate){$values+=($script:patient|Select-Object *)}
  if(-not $query['continuationToken']){return [pscustomobject]@{value=$values;continuationToken='next+page/='}}
  if($query['continuationToken'] -ne 'next+page/='){throw 'Continuation token was not preserved'}
  return [pscustomobject]@{value=@($script:condition);continuationToken=$null}
 }
 if($query['rootId'] -eq 'functions'){return [pscustomobject]@{value=@($script:function);continuationToken=$null}}
 return [pscustomobject]@{value=@([pscustomobject]@{id='schemas';type='Schemas';displayName='Schemas';hasSubElements=$true},[pscustomobject]@{id='functions';type='Functions';displayName='Functions';hasSubElements=$true});continuationToken=$null}
}
$selectionArgs=@{WorkspaceId='workspace';DataAgentId='agent';DatasourceId='source';Tables=@('Patient');Functions=@('fn_Count');InvokeApi=$api}
Set-DataAgentNativeSchemaSelection @selectionArgs
Assert-True ($patient.isSelected -and -not $condition.isSelected -and $function.isSelected) 'Select exactly the requested native table/function, including opaque IDs and pagination.'
$before=$script:patches
$missing=@{}+$selectionArgs
$missing.Tables=@('Missing')
Assert-Throws {Set-DataAgentNativeSchemaSelection @missing} 'Missing, ambiguous, or unavailable'
Assert-True ($script:patches -eq $before) 'Missing targets must fail before any native override changes.'
$script:duplicate=$true
Assert-Throws {Set-DataAgentNativeSchemaSelection @selectionArgs} 'Missing, ambiguous, or unavailable'
Assert-True ($script:patches -eq $before) 'Ambiguous same-schema tables must fail before writes.'
$script:duplicate=$false
$patient.isSelected=$false
Assert-Throws {Set-DataAgentNativeSchemaSelection @selectionArgs -VerifyOnly -Published} 'did not match'
Assert-True ($script:patches -eq $before) 'Published verification must never patch a mismatched selection.'
$tableOnly=@{}+$selectionArgs
$tableOnly.Remove('Functions')
Set-DataAgentNativeSchemaSelection @tableOnly
Assert-True ($patient.isSelected -and -not $condition.isSelected -and -not $function.isSelected) 'A table-only contract must not synthesize an empty function target or keep unrelated functions selected.'
Write-Host 'Native Data Agent selection boundary tests passed.'

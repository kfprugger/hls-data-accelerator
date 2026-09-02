@description('Required. Unique string for deployment resources name.')
param uniqueIdentifier string

@description('Optional. Wait time in seconds.')
param waitSeconds int

@description('Optional. Location for all resources.')
param location string = resourceGroup().location

@description('Generated. Do not provide a value! This date value is used to make sure the script run every time the template is deployed.')
param scriptForceUpdateTag string = utcNow('yyyy-MM-dd-HH-mm-ss')

@description('Optional. Tags of the resource.')
param tags object = {}

var azPowerShellVersion = '8.3'
var scriptRetentionInterval = 'PT1H'
var scriptCleanupPreference = 'Always'

resource delayDeployment 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: 'msft-ds-delayDeployment-${uniqueIdentifier}'
  location: location
  tags: contains(tags, 'Microsoft.Resources/deploymentScripts')
    ? tags['Microsoft.Resources/deploymentScripts']
    : json('{}')
  kind: 'AzurePowerShell'
  properties: {
    azPowerShellVersion: azPowerShellVersion
    arguments: '-waitSeconds ${waitSeconds}'
    scriptContent: '''
      param([string] $waitSeconds)
      Start-Sleep -Seconds $waitSeconds
    '''
    cleanupPreference: scriptCleanupPreference
    forceUpdateTag: scriptForceUpdateTag
    retentionInterval: scriptRetentionInterval
  }
}

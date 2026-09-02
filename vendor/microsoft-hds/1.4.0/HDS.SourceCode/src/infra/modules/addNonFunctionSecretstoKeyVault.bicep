@description('Required. Name of the azure key vault.')
param keyVaultName string

@description('Required. Name of the log analytics workspace.')
param logAnalyticsNamespaceName string

@description('Required. Name of the application insights.')
param appInsightsName string

@description('Required. Name of the export processor function app.')
param exportProcessorFunctionAppName string

@description('Optional. Id of the azure cognitive service for natural language processing.')
param languageServiceId string = ''

// Get the keyvault.
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// The language service id is in the following format. Extract the resource group and resource name from the it.
//     '/subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/{resource-provider-namespace}/{resource-type}/{resource-name}'
var languageServiceSelected = !empty(languageServiceId)
var parts = languageServiceSelected ? split(languageServiceId, '/') : array('')
var languageServiceResourceGroupName = languageServiceSelected ? parts[4] : ''
var languageServiceName = languageServiceSelected ? parts[8] : ''

// Get the text analytics cognitive service.
resource languageService 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (languageServiceSelected) {
  name: languageServiceName
  scope: resourceGroup(languageServiceResourceGroupName)
}

// Add the keyvault secret for the text analytics cognitive service.
resource languageServiceSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (languageServiceSelected) {
  parent: keyVault
  name: 'LanguageServiceKey'
  properties: {
    value: languageServiceSelected ? languageService.listKeys().key1 : ''
  }
}

// Add the text analytics cognitive service endpoint to keyvault.
resource languageServiceEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (languageServiceSelected) {
  parent: keyVault
  name: 'LanguageServiceEndpoint'
  properties: {
    value: languageServiceSelected ? languageService.properties.endpoint : ''
  }
}

// Get the export function app.
resource exportFunctionApp 'Microsoft.Web/sites@2023-12-01' existing = {
  name: exportProcessorFunctionAppName
}

// Add the export function endpoint to keyvault.
resource functionAppEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'FunctionAppEndpoint'
  properties: {
    value: 'https://${exportFunctionApp.properties.defaultHostName}'
  }
}

// Get the log analytics workspace.
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsNamespaceName
}

// Add the keyvault secret for the log analytics workspace key.
resource logAnalyticsWorkspaceKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'LogAnalyticsWorkspaceKey'
  properties: {
    value: logAnalyticsWorkspace.listKeys().primarySharedKey
  }
}

//  Get the app insights instance.
resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// Add the app insights instrumentation key to keyvault.
resource appInsightsInstrumentationKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'AppInsightsInstrumentationKey'
  properties: {
    value: appInsights.properties.InstrumentationKey
  }
}

// Add the app insights ingestion endpoint key to keyvault for capturing DTT telemetry.
resource appInsightsIngestionEndpointKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'AppInsightsIngestionEndpointKey'
  properties: {
    value: appInsights.properties.ConnectionString
  }
}

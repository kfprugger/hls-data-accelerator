@description('Optional. Language service id.')
param languageServiceId string = ''

@description('Optional. Tags for all resources.')
param tagsByResources object = {}

@description('Optional. Fhir Server Uri for export.')
param fhirServerUri string = 'NA'

@description('Optional. Export start date time in yyyy-MM-dd.')
param exportStartTime string = '2023-03-15'

@description('Optional. Location for all resources.')
param location string = resourceGroup().location

@description('Optional. Set to true to only update the function app package without recreating other resources')
param deployUpdatesOnly bool = false

@description('Optional. Set to true to skip ZipDeploy during Bicep deployment (code will be deployed separately via az functionapp deployment).')
param skipZipDeploy bool = false

@description('Optional. Set to true to restrict storage account network access (defaultAction=Deny). Only enable this for subscriptions whose Azure Policy requires it; the Consumption-plan function host content share is not supported behind a storage firewall, so leave false unless required.')
param restrictStorageNetworkAccess bool = false

@description('Optional. The base URI where artifacts required by this template are located including a trailing \'/\'')
param _artifactsLocation string = deployment().properties.templateLink.uri

@secure()
@description('The sasToken required to access _artifactsLocation.  When the template is deployed using the accompanying scripts, a sasToken will be automatically generated. Use the defaultValue if the staging location is not secured.')
param _artifactsLocationSasToken string = ''


var uniqueIdentifier = uniqueString(subscription().subscriptionId, resourceGroup().id)
var storageAccountName = 'msftst${uniqueIdentifier}'
var logAnalyticsNamespaceName = 'msft-log-hds-${uniqueIdentifier}'
var appInsightsName = 'msft-appi-hds-${uniqueIdentifier}'
var appServicePlanName = 'msft-asp-hds-${uniqueIdentifier}'
var exportProcessorFunctionAppName = 'msft-func-hds-export-${uniqueIdentifier}'
var keyVaultName = 'msft-kv-${uniqueIdentifier}'

// Try to set the sas token from parameter.
var token =  !empty(_artifactsLocationSasToken) && !startsWith(_artifactsLocationSasToken, '?') ? '?${_artifactsLocationSasToken}' : _artifactsLocationSasToken
// If sas token is still empty, try to set it from arm template's deployment link query string.
var sasToken = empty(token) && contains(_artifactsLocation, '?') ? '?${split(_artifactsLocation, '?')[1]}' : token

// Load the config files.
var blobContainersConfig = loadJsonContent('config/blobStorageContainersConfig.json')
var armArtifactsConfig = loadJsonContent('config/armArtifactsConfig.json')

// Deploy storage accounts and blob containers
module deploySharedComponents 'modules/deploySharedComponents.bicep' = if (!deployUpdatesOnly) {
  name: 'msft-mdl-hds-deploySharedComponents'
  scope: resourceGroup()
  params: {
    uniqueIdentifier: uniqueIdentifier
    location: location
    tags: tagsByResources
    hdsStorageAccountName: storageAccountName
    logAnalyticsNamespaceName:logAnalyticsNamespaceName
    appInsightsName: appInsightsName
    keyVaultName: keyVaultName
    blobContainersConfig: blobContainersConfig
    restrictStorageNetworkAccess: restrictStorageNetworkAccess
  }
}

// Deploy the function app.
module deployAppServices 'modules/deployAppServices.bicep' = {
  name: 'msft-mdl-hds-deployAppServices'
  scope: resourceGroup()
  params: {
    uniqueIdentifier: uniqueIdentifier
    location: location
    tags: tagsByResources
    appInsightsName: appInsightsName
    appServicePlanName: appServicePlanName
    exportDataStorageAccountName: storageAccountName
    exportProcessorFunctionAppName: exportProcessorFunctionAppName
    fhirServerUri: fhirServerUri
    exportStartTime: exportStartTime
    _artifactsLocation: _artifactsLocation
    _artifactsLocationSasToken: sasToken
    armArtifactsConfig: armArtifactsConfig
    blobContainersConfig: blobContainersConfig
    keyVaultName: keyVaultName
    deployUpdatesOnly: deployUpdatesOnly
    skipZipDeploy: skipZipDeploy
    restrictStorageNetworkAccess: restrictStorageNetworkAccess
  }
  dependsOn: deployUpdatesOnly ? [] : [
    deploySharedComponents
  ]
}

// Add non-function-dependent secrets to Key Vault immediately after deployment.
// These secrets (FunctionAppEndpoint, LogAnalyticsWorkspaceKey, AppInsights keys, Language Service)
// do NOT depend on function registration and can be stored right away.
// Note: ExportFunctionKey is stored as a post-deployment step by Deploy-FhirExportFunctionApp.ps1
// because RBAC propagation delays (5-10 min) and .NET 8 isolated worker cold-start make it
// impossible to reliably reference the function within the ARM deployment window.
module addNonFunctionSecretstoKeyVault 'modules/addNonFunctionSecretstoKeyVault.bicep' = if (!deployUpdatesOnly) {
  name: 'msft-mdl-hds-addNonFunctionSecrets'
  scope: resourceGroup()
  params: {
    keyVaultName: keyVaultName
    languageServiceId: languageServiceId
    exportProcessorFunctionAppName: exportProcessorFunctionAppName
    logAnalyticsNamespaceName: logAnalyticsNamespaceName
    appInsightsName: appInsightsName
  }
  dependsOn: [
    deploySharedComponents
    deployAppServices
  ]
}

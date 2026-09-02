@description('Required. Unique string for deployment resources name.')
param uniqueIdentifier string

@description('Required. Healthcare data solutions deployment storage account name.')
param hdsStorageAccountName string

@description('Required. Name of the log analytics workspace.')
param logAnalyticsNamespaceName string

@description('Required. Name of the application insights instance for Healthcare data solutions.')
param appInsightsName string

@description('Required. Name of the azure key vault.')
param keyVaultName string

@description('Required. Configurations for blob storage containers.')
param blobContainersConfig object

@description('Optional. Tags of the resource.')
param tags object = {}

@description('Optional. Location for all resources.')
param location string = resourceGroup().location

@description('Optional. Set to true to restrict storage account network access (defaultAction=Deny).')
param restrictStorageNetworkAccess bool = false

var hdsStorageAccountType = 'Standard_GRS'
var logAnalyticsWorkspaceSku = 'PerGB2018' // Pay as you go.
var logRetentionDays = 180

var hdsBlobContainers = [
  blobContainersConfig.blobStorageContainers.exportlandingzoneContainer.name
]

// Datalake storage resource
resource hdsStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: hdsStorageAccountName
  kind: 'StorageV2'
  location: location
  tags: contains(tags, 'Microsoft.Storage/storageAccounts')
    ? tags['Microsoft.Storage/storageAccounts']
    : json('{}')
  properties:{
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    defaultToOAuthAuthentication: true
    networkAcls: {
      defaultAction: restrictStorageNetworkAccess ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
  sku: {
    name: hdsStorageAccountType
  }
}

// Datalake storage default blob resource
resource hdsStorageAccountBlob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: hdsStorageAccount
  name:  'default'
}

// Fabric workspace storage account container.
resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [ for blobContainer in hdsBlobContainers: {
  parent: hdsStorageAccountBlob
  name: blobContainer
  properties: {
    publicAccess: 'None'
  }
}]

// Log analytics workspace
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01'= {
  name: logAnalyticsNamespaceName
  location: location
  tags: contains(tags, 'Microsoft.OperationalInsights/workspaces')
    ? tags['Microsoft.OperationalInsights/workspaces']
    : json('{}')
  properties: {
    sku: {
      name: logAnalyticsWorkspaceSku
    }
    retentionInDays: logRetentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// Workaround to wait for the log anaytics workspace be available.
// Adding a delay to fix the transient error - 'Could not retrieve the log anaytics workspace' while app insights deployment.
module delayAppInsightsDeployment 'delayDeployment.bicep' = {
  name: 'msft-mdl-hds-delayAppInsightsDeployment'
  params: {
    uniqueIdentifier: uniqueIdentifier
    location: location
    tags: tags
    waitSeconds: 120
  }
}

// App Insights to stream to the log analytics workspace.
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'string'
  tags: contains(tags, 'Microsoft.Insights/components')
    ? tags['Microsoft.Insights/components']
    : json('{}')
  properties: {
    Application_Type: 'web'
    Request_Source: 'rest'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
  dependsOn: [
    delayAppInsightsDeployment
  ]
}

// Deploy the keyvault.
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: contains(tags, 'Microsoft.KeyVault/vaults')
    ? tags['Microsoft.KeyVault/vaults']
    : json('{}')
  properties: {
    enableSoftDelete: true 
    enablePurgeProtection: true
    tenantId: subscription().tenantId
    sku: {
      name: 'standard'
      family: 'A'
    }
    enableRbacAuthorization: true
  }
}

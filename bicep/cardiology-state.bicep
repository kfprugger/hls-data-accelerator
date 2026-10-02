@description('Short application prefix used in deterministic storage naming.')
param prefix string

param location string = resourceGroup().location
param tags object = {}

@description('Application user-assigned managed identity principal ID.')
param appPrincipalId string

var storageName = 'cs${uniqueString(resourceGroup().id, prefix)}'
var blobContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')

resource stateStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: union(tags, { 'hls-workload': 'cardiology-state', dataClassification: 'synthetic-only' })
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: stateStorage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource workflowContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'workflow-state'
  properties: { publicAccess: 'None' }
}

resource authContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'auth-tokens'
  properties: { publicAccess: 'None' }
}

resource workflowAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(workflowContainer.id, appPrincipalId, 'blob-data-contributor')
  scope: workflowContainer
  properties: {
    roleDefinitionId: blobContributor
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource tokenAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(authContainer.id, appPrincipalId, 'blob-data-contributor')
  scope: authContainer
  properties: {
    roleDefinitionId: blobContributor
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output storageAccountName string = stateStorage.name
output stateBlobUrl string = '${stateStorage.properties.primaryEndpoints.blob}${workflowContainer.name}/operations.json'
output authContainerUri string = '${stateStorage.properties.primaryEndpoints.blob}${authContainer.name}'

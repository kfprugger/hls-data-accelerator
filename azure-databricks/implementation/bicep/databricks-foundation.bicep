// databricks-foundation.bicep
// Adds the Azure Databricks destination plane beside the existing HLS source estate.
// It never recreates FHIR, ADLS, Event Hubs, ACR, ACI, or Key Vault.

@description('Location for the workspace and access connector. Must match the existing ADLS account region.')
param location string = resourceGroup().location

@description('Existing ADLS Gen2 account that already holds fhir-export and dicom-output.')
param storageAccountName string

@description('Container created for Databricks-managed Delta data. Source containers stay read-only.')
param managedContainerName string = 'databricks-managed'

@description('Existing Event Hubs namespace that already carries telemetry-stream and claim-stream.')
param eventHubNamespaceName string

@description('Entra object ID of the deployment administrator group.')
param adminGroupObjectId string = ''

@description('Base name for the Databricks resources.')
param appName string = 'hlsdbx${uniqueString(resourceGroup().id)}'

param resourceTags object = {}

var storageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var storageQueueDataContributor = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var eventHubsDataReceiver = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde'

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' existing = {
  parent: storage
  name: 'default'
}

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2021-11-01' existing = {
  name: eventHubNamespaceName
}

// Managed Delta storage for the environment catalog. Source paths are never written.
resource managedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: managedContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Unity Catalog reaches storage through this first-party managed identity, not a secret.
resource accessConnector 'Microsoft.Databricks/accessConnectors@2023-05-01' = {
  name: '${appName}-ac'
  location: location
  tags: resourceTags
  identity: {
    type: 'SystemAssigned'
  }
}

// Premium is required for Unity Catalog controls and Databricks Apps.
resource workspace 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: '${appName}-ws'
  location: location
  tags: resourceTags
  sku: {
    name: 'premium'
  }
  properties: {
    managedResourceGroupId: subscriptionResourceId('Microsoft.Resources/resourceGroups', '${appName}-managed-rg')
    publicNetworkAccess: 'Enabled'
  }
}

// Read-only on the whole account keeps fhir-export and dicom-output ingestible but unwritable.
resource connectorSourceRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, accessConnector.id, storageBlobDataReader)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReader)
    principalId: accessConnector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Read/write is scoped to the managed container only.
resource connectorManagedWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(managedContainer.id, accessConnector.id, storageBlobDataContributor)
  scope: managedContainer
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
    principalId: accessConnector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Queue access is only needed when Auto Loader file events are enabled.
resource connectorFileEvents 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, accessConnector.id, storageQueueDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributor)
    principalId: accessConnector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Databricks reads both hubs. It never gains Send on the producer path.
resource connectorEventHubsRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventHubNamespace.id, accessConnector.id, eventHubsDataReceiver)
  scope: eventHubNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventHubsDataReceiver)
    principalId: accessConnector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource adminWorkspaceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adminGroupObjectId)) {
  name: guid(workspace.id, adminGroupObjectId, 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  scope: workspace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: adminGroupObjectId
    principalType: 'Group'
  }
}

output workspaceName string = workspace.name
output workspaceId string = workspace.id
output workspaceUrl string = 'https://${workspace.properties.workspaceUrl}'
output accessConnectorId string = accessConnector.id
output accessConnectorPrincipalId string = accessConnector.identity.principalId
output managedContainerName string = managedContainer.name
var dfsHost = '${storageAccountName}.dfs.${environment().suffixes.storage}'
output managedLocationUrl string = 'abfss://${managedContainer.name}@${dfsHost}'
output fhirExportUrl string = 'abfss://fhir-export@${dfsHost}'
output dicomOutputUrl string = 'abfss://dicom-output@${dfsHost}'

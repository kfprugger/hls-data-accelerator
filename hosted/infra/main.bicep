targetScope = 'resourceGroup'

param location string = 'westus2'
param gatewayImage string
param sandboxImage string
param clientId string
param allowedUsers string = '8d038e6a-9b7d-4cb8-bbcf-e84dff156478:joey@brakekat.com,c77e97fc-1859-4575-8c8b-53d74bc35a63:joey@jbatl.dev,72f988bf-86f1-41af-91ab-2d7cd011db47:jbrakefield@microsoft.com'
param allowedTenants string = ''
param customDomain string = ''

@description('Foundation-only bootstrap before images and Key Vault secrets exist.')
param deployGateway bool = true

@description('First register the custom domain with Disabled binding; enable only after public DNS resolves.')
param enableManagedCertificate bool = false

var acrPullRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acrhlsdeployer'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource gatewayIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-hls-gateway'
  location: location
}

resource sandboxIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-hls-sandbox'
  location: location
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'sthlsdeployer'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}
resource files 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: files
  name: 'sandboxes'
  properties: {
    enabledProtocols: 'SMB'
    shareQuota: 100
  }
}
resource tables 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource sandboxTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tables
  name: 'sandboxes'
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-hls-deployer'
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-hls-deployer'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}
resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-hls-deployer'
  location: location
  properties: {
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}
resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'sandboxes'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

resource gatewayContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, gatewayIdentity.id, 'Contributor')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: gatewayIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource gatewayTables 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, gatewayIdentity.id, 'Storage Table Data Contributor')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
    principalId: gatewayIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource gatewaySecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, gatewayIdentity.id, 'Key Vault Secrets User')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: gatewayIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource gatewayIdentityOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: sandboxIdentity
  name: guid(sandboxIdentity.id, gatewayIdentity.id, 'Managed Identity Operator')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f1a07417-d97a-45cb-824c-7a7467783830')
    principalId: gatewayIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource gatewayPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, gatewayIdentity.id, acrPullRole)
  properties: {
    roleDefinitionId: acrPullRole
    principalId: gatewayIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource sandboxPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, sandboxIdentity.id, acrPullRole)
  properties: {
    roleDefinitionId: acrPullRole
    principalId: sandboxIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// DNS and the Disabled app binding must already exist before this second pass.
resource certificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' = if (deployGateway && !empty(customDomain) && enableManagedCertificate) {
  parent: environment
  name: 'hls-gateway-managed'
  location: location
  properties: {
    subjectName: customDomain
    domainControlValidation: 'CNAME'
  }
}

resource gateway 'Microsoft.App/containerApps@2024-03-01' = if (deployGateway) {
  name: 'hls-gateway'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${gatewayIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        customDomains: empty(customDomain) ? [] : [
          union({
            name: customDomain
            bindingType: enableManagedCertificate ? 'SniEnabled' : 'Disabled'
          }, enableManagedCertificate ? { certificateId: certificate!.id } : {})
        ]
      }
      registries: [{ server: registry.properties.loginServer, identity: gatewayIdentity.id }]
      secrets: [
        {
          name: 'gateway-client-secret'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/gateway-client-secret'
          identity: gatewayIdentity.id
        }
        {
          name: 'gateway-session-key'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/gateway-session-key'
          identity: gatewayIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'gateway'
          image: gatewayImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'HLS_CLIENT_ID', value: clientId }
            { name: 'HLS_CLIENT_SECRET', secretRef: 'gateway-client-secret' }
            { name: 'HLS_SESSION_KEY', secretRef: 'gateway-session-key' }
            { name: 'HLS_ALLOWED_USERS', value: allowedUsers }
            { name: 'HLS_ALLOWED_TENANTS', value: allowedTenants }
            { name: 'HLS_MAX_SANDBOXES', value: '5' }
            { name: 'HLS_IDLE_MINUTES', value: '120' }
            { name: 'HLS_SUBSCRIPTION_ID', value: subscription().subscriptionId }
            { name: 'HLS_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'HLS_ENVIRONMENT_ID', value: environment.id }
            { name: 'HLS_ENV_DEFAULT_DOMAIN', value: environment.properties.defaultDomain }
            { name: 'HLS_SANDBOX_IMAGE', value: sandboxImage }
            { name: 'HLS_SANDBOX_IDENTITY_ID', value: sandboxIdentity.id }
            { name: 'HLS_STORAGE_ACCOUNT', value: storage.name }
            { name: 'AZURE_CLIENT_ID', value: gatewayIdentity.properties.clientId }
            { name: 'HLS_PUBLIC_BASE_URL', value: empty(customDomain) ? 'https://hls-gateway.${environment.properties.defaultDomain}' : 'https://${customDomain}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [gatewayContributor, gatewayTables, gatewaySecrets, gatewayIdentityOperator, gatewayPull, sandboxPull, environmentStorage, sandboxTable]
}

output gatewayFqdn string = deployGateway ? gateway!.properties.configuration.ingress.fqdn : ''
output environmentDefaultDomain string = environment.properties.defaultDomain
output customDomainVerificationId string = deployGateway ? gateway!.properties.customDomainVerificationId : ''
output acrLoginServer string = registry.properties.loginServer

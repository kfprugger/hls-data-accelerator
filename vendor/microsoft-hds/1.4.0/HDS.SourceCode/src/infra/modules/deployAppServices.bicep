@description('Required. Unique string for deployment resources name.')
param uniqueIdentifier string

@description('Required. Name of the app service plan.')
param appServicePlanName string

@description('Required. Name of the export processor function app.')
param exportProcessorFunctionAppName string

@description('Required. Name of the application insights instance for Healthcare data solutions.')
param appInsightsName string

@description('Required. Fhir Server Uri app setting value.')
param fhirServerUri string

@description('Required. Export start date time app setting value.')
param exportStartTime string

@description('Required. Export output storage account name app setting value.')
param exportDataStorageAccountName string

@description('Required. Configurations for arm supporting artifacts.')
param armArtifactsConfig object

@description('Required. Configurations for blob storage containers.')
param blobContainersConfig object

@description('Required. The base URI where artifacts required by this template are located including a trailing \'/\'')
param _artifactsLocation string = deployment().properties.templateLink.uri

@secure()
@description('Required. The sasToken required to access _artifactsLocation.  When the template is deployed using the accompanying scripts, a sasToken will be automatically generated. Use the defaultValue if the staging location is not secured.')
param _artifactsLocationSasToken string = ''

@description('Required. Name of the azure key vault.')
param keyVaultName string

@description('Optional. Tags of the resource.')
param tags object = {}

@description('Optional. Location for all resources.')
param location string = resourceGroup().location

@description('Set to true to only update the function app package without recreating other resources')
param deployUpdatesOnly bool = false

@description('Set to true to skip ZipDeploy during Bicep deployment (code will be deployed separately via az functionapp deployment).')
param skipZipDeploy bool = false

@description('Set to true to restrict storage account network access (defaultAction=Deny).')
param restrictStorageNetworkAccess bool = false

// App Service Plan ('Consumption')
var skuTier = 'dynamic'
var skuName = 'Y1'

// Export App settings value
var resourcesToExport = 'Account,ActivityDefinition,AdverseEvent,AllergyIntolerance,Appointment,AppointmentResponse,AuditEvent,Basic,Binary,BiologicallyDerivedProduct,BodyStructure,Bundle,CapabilityStatement,CarePlan,CareTeam,CatalogEntry,ChargeItem,ChargeItemDefinition,Claim,ClaimResponse,ClinicalImpression,CodeSystem,Communication,CommunicationRequest,CompartmentDefinition,Composition,ConceptMap,Condition,Consent,Contract,Coverage,CoverageEligibilityRequest,CoverageEligibilityResponse,DetectedIssue,Device,DeviceDefinition,DeviceMetric,DeviceRequest,DeviceUseStatement,DiagnosticReport,DocumentManifest,DocumentReference,EffectEvidenceSynthesis,Encounter,Endpoint,EnrollmentRequest,EnrollmentResponse,EpisodeOfCare,EventDefinition,Evidence,EvidenceVariable,ExampleScenario,ExplanationOfBenefit,FamilyMemberHistory,Flag,Goal,GraphDefinition,Group,GuidanceResponse,HealthcareService,ImagingStudy,Immunization,ImmunizationEvaluation,ImmunizationRecommendation,ImplementationGuide,InsurancePlan,Invoice,Library,Linkage,List,Location,Measure,MeasureReport,Media,Medication,MedicationAdministration,MedicationDispense,MedicationKnowledge,MedicationRequest,MedicationStatement,MedicinalProduct,MedicinalProductAuthorization,MedicinalProductContraindication,MedicinalProductIndication,MedicinalProductIngredient,MedicinalProductInteraction,MedicinalProductManufactured,MedicinalProductPackaged,MedicinalProductPharmaceutical,MedicinalProductUndesirableEffect,MessageDefinition,MessageHeader,MolecularSequence,NamingSystem,NutritionOrder,Observation,ObservationDefinition,OperationDefinition,OperationOutcome,Organization,OrganizationAffiliation,Parameters,Patient,PaymentNotice,PaymentReconciliation,Person,PlanDefinition,Practitioner,PractitionerRole,Procedure,Provenance,Questionnaire,QuestionnaireResponse,RelatedPerson,RequestGroup,ResearchDefinition,ResearchElementDefinition,ResearchStudy,ResearchSubject,RiskAssessment,RiskEvidenceSynthesis,Schedule,SearchParameter,ServiceRequest,Slot,Specimen,SpecimenDefinition,StructureDefinition,StructureMap,Subscription,Substance,SubstancePolymer,SubstanceProtein,SubstanceReferenceInformation,SubstanceSpecification,SubstanceSourceMaterial,SupplyDelivery,SupplyRequest,Task,TerminologyCapabilities,TestReport,TestScript,ValueSet,VerificationResult,VisionPrescription'
var exportRetryCount = '3'

var functionAppsRelativePath = armArtifactsConfig.functionApps.relativePath
var exportFunctionZipName = armArtifactsConfig.functionApps.exportFunctionAppZipName
var functionAppStorageAccountName = 'msftstexprt${uniqueIdentifier}'
var functionAppStorageAccountType = 'Standard_RAGRS'
var blobDataContributorAzureRbacRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var keyVaultSecretsUserRoleDefinitionId= '4633458b-17de-408a-b874-0445c86b69e6'

// Reference to existing function app when only updating the ZIP
resource existingExportFunctionApp 'Microsoft.Web/sites@2023-12-01' existing = if (deployUpdatesOnly) {
  name: exportProcessorFunctionAppName
}

//  Get the app insights instance.
resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

// Create the storage account for the function app.
resource functionAppStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = if (!deployUpdatesOnly) {
  name: functionAppStorageAccountName
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
    name: functionAppStorageAccountType
  }
  kind: 'StorageV2'
}

// Create the app service plan.
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = if (!deployUpdatesOnly) {
  name: appServicePlanName
  location: location
  tags: contains(tags, 'Microsoft.Web/serverfarms')
    ? tags['Microsoft.Web/serverfarms']
    : json('{}')
  sku: {
    name: skuName
    tier: skuTier
  }
}

// Create the function app.
resource exportFunctionApp 'Microsoft.Web/sites@2023-12-01' = if (!deployUpdatesOnly) {
  name: exportProcessorFunctionAppName
  location: location
  tags: contains(tags, 'Microsoft.Web/sites')
    ? tags['Microsoft.Web/sites']
    : json('{}')
  kind: 'functionapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    clientAffinityEnabled: true
    siteConfig: {
      minTlsVersion: '1.2'
      netFrameworkVersion: 'v8.0'
      use32BitWorkerProcess: false
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
      ]
    }
  }
}

var storageAccountConnectionStringSecretKey = 'FunctionAppStorageAccountKey'

// Add the function app storage account key to keyvault.
resource functionAppStorageAccountKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!deployUpdatesOnly) {
  parent: keyVault
  name: storageAccountConnectionStringSecretKey
  properties: {
    value: 'DefaultEndpointsProtocol=https;AccountName=${functionAppStorageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${functionAppStorageAccount.listKeys().keys[0].value}'
  }
}

var keyVaultReferenceFunctionAppStorageAccountKey = '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${storageAccountConnectionStringSecretKey})'
var exportFunctionAppSettings = {
  APPINSIGHTS_INSTRUMENTATIONKEY: appInsights.properties.InstrumentationKey
  dataStart: exportStartTime
  fhirServerUri: fhirServerUri
  exportContainerName: blobContainersConfig.blobStorageContainers.exportlandingzoneContainer.name
  jobOutputContainerName: blobContainersConfig.blobStorageContainers.exportlandingzoneContainer.name
  jobOutputStorageAccountName: exportDataStorageAccountName
  resources: resourcesToExport
  retryCount: exportRetryCount
  AzureWebJobsStorage: keyVaultReferenceFunctionAppStorageAccountKey
  WEBSITE_CONTENTAZUREFILECONNECTIONSTRING: keyVaultReferenceFunctionAppStorageAccountKey
  WEBSITE_CONTENTSHARE: exportProcessorFunctionAppName
  FUNCTIONS_EXTENSION_VERSION: '~4'
  FUNCTIONS_WORKER_RUNTIME: 'dotnet-isolated'
  WEBSITE_RUN_FROM_PACKAGE: '1'
  AzureWebJobsSecretStorageType: 'Files'
  WEBSITE_USE_PLACEHOLDER_DOTNETISOLATED: '1'
}

// Workaround to wait for the keyvault secret and reader role access to become available.
// Adding a delay to fix the error while function app config deployment.
module delayAppServiceSettingsDeployment 'delayDeployment.bicep' = if (!deployUpdatesOnly) {
  name: 'msft-mdl-hds-delayAppServiceSettingsDeployment'
  params: {
    uniqueIdentifier: uniqueIdentifier
    location: location
    tags: tags
    waitSeconds: 120
  }
  dependsOn: [
    functionAppStorageAccount
    exportFunctionAppKeyVaultSecretsUserRoleAssignment
  ]
}

// Deploy the app settings for export function app.
resource deployExportFunctionAppSettings 'Microsoft.Web/sites/config@2023-12-01' = if (!deployUpdatesOnly) {
  name: 'appsettings'
  parent: exportFunctionApp
  properties: exportFunctionAppSettings
  dependsOn: [
    delayAppServiceSettingsDeployment
  ]
}

// Disable FTP and SCM publishing
resource scmPublishBasicAuthExportFunctionApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = if (!deployUpdatesOnly) {
  name: 'scm'
  location: location
  parent: exportFunctionApp
  properties: {
    allow: false
  }
}

resource ftpPublishBasicAuthExportFunctionApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = if (!deployUpdatesOnly) {
  name: 'ftp'
  location: location
  parent: exportFunctionApp
  properties: {
    allow: false
  }
}


//Deploy ZIP to newly created function app (normal deployment)
// When skipZipDeploy is true, code deployment is handled externally via 'az functionapp deployment source config-zip'.
resource fullDeployZip 'Microsoft.Web/sites/extensions@2023-12-01' = if (!deployUpdatesOnly && !skipZipDeploy) {
  parent: exportFunctionApp
  name: any('ZipDeploy') // Known issue: https://github.com/Azure/bicep-types-az/issues/968
  properties: {
    packageUri: uri(_artifactsLocation, '${functionAppsRelativePath}${exportFunctionZipName}${_artifactsLocationSasToken}')
    skipAppData: true
  }
  dependsOn: [
    deployExportFunctionAppSettings
  ]
}

// Deploy ZIP to existing function app (update only)
// When skipZipDeploy is true, code deployment is handled externally via 'az functionapp deployment source config-zip'.
resource updateOnlyZip 'Microsoft.Web/sites/extensions@2023-12-01' = if (deployUpdatesOnly && !skipZipDeploy) {
  parent: existingExportFunctionApp
  name: any('ZipDeploy') // Known issue: https://github.com/Azure/bicep-types-az/issues/968
  properties: {
    packageUri: uri(_artifactsLocation, '${functionAppsRelativePath}${exportFunctionZipName}${_artifactsLocationSasToken}')
    skipAppData: true
  }
}

// Get the export data storage account.
resource exportDataStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: exportDataStorageAccountName
}

// Get the key vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// Assign 'Storage blob data contributor' Azure RBAC role (scope = storage account) to export function app so it is enabled to write to storage account to trigger downstream pipelines.
var exportFunctionAppBlobDataContributorRoleUniqueId = guid(resourceId('Microsoft.Storage/storageAccounts', exportDataStorageAccountName), exportProcessorFunctionAppName, blobDataContributorAzureRbacRoleId)
resource exportFunctionAppBlobDataContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!deployUpdatesOnly) {
  name: exportFunctionAppBlobDataContributorRoleUniqueId
  scope: exportDataStorageAccount
  properties:{
    principalId: exportFunctionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorAzureRbacRoleId)
  }
}

// Assign 'Key Vault Secrets User' Azure RBAC role (scope = Key Vault) to allow read access to the secret
var exportFunctionSecretUserRoleUniqueId = guid(keyVault.id, exportProcessorFunctionAppName, keyVaultSecretsUserRoleDefinitionId)
resource exportFunctionAppKeyVaultSecretsUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!deployUpdatesOnly) {
  name: exportFunctionSecretUserRoleUniqueId
  scope: keyVault
  properties: {
    principalId: exportFunctionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleDefinitionId)
  }
}

// TODO: 
// Since, we are using an existing fhir service resource, there are two potential problems:
//    1. The Fhir service resource could be in a different resource group, so using 'existing' keyword to reference the resource may fail. We could workaround this with deploymentScript (Get-AzResource module).
//    2. Updating existing azure resource has few limitations with ARM because ARM template being idempotent in nature.
//       For e.g: you need to rebuild whole ARM definition for fhir service, even for updating a single property - https://learn.microsoft.com/en-us/azure/architecture/guide/azure-resource-manager/advanced-templates/update-resource
// Given above two limitations, Following fhir service configuration need to be done manually:
//    1. Update fhir service to have a system assigned identity.
//    2. Update fhir service's export storage account name to the Healthcare data solutions's storage account.
//    3. On the Healthcare data solutions's storage acccount, Assign 'Storage Blob Data Contributor' Azure RBAC role to fhir Service so it is enabled to read/write to storage account
//    4. On the Fhir Service, Assign 'FHIR Data Exporter' Azure RBAC role to export function app so it is enabled to execute fhir $export apis. ('FHIR Data Reader' alone does NOT grant the $export operation.)
//    5. Update the 'Fhir Service Uri' and 'Export start time' app settings on the export function app.

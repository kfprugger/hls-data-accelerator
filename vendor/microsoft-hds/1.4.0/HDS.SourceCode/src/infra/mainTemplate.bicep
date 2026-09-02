/*
  This template is a wrapper on top of main.bicep to deploy Healthcare data solutions.
  This template will deploy Healthcare data solutions and also deploy market place offer usage attribute.
*/

@description('Optional. Language service id.')
param languageServiceId string = ''

@description('Optional. Tags for resources.')
param tagsByResources object = {}

@description('Optional. Fhir Server Uri for export.')
param fhirServerUri string = 'NA'

@description('Optional. Export start date time in yyyy-MM-dd.')
param exportStartTime string = '2023-03-15'

@description('Optional. Location for all resources.')
param location string = resourceGroup().location

@description('Optional. Set to true to only update the function app package without recreating other resources')
param deployUpdatesOnly bool = false

@description('Optional. The base URI where artifacts required by this template are located including a trailing \'/\'')
param _artifactsLocation string = deployment().properties.templateLink.uri

@secure()
@description('The sasToken required to access _artifactsLocation.  When the template is deployed using the accompanying scripts, a sasToken will be automatically generated. Use the defaultValue if the staging location is not secured.')
param _artifactsLocationSasToken string = ''

// Add the customer usage pid resource to the template for market place offer deployment.
// https://learn.microsoft.com/en-us/partner-center/marketplace/azure-partner-customer-usage-attribution#add-a-guid-to-a-resource-manager-template
resource customerUsagePidResource 'Microsoft.Resources/deployments@2023-07-01' = {
  name: 'pid-e6d6687b-1f0a-4663-9c85-ab5f679a1355-partnercenter'
  properties: {
    mode: 'Incremental'
    template: {
      '$schema': 'https://schema.management.azure.com/schemas/2015-01-01/deploymentTemplate.json#'
      contentVersion: '1.0.0.0'
      resources: []
    }
  }
}

// Deploy Healthcare data solutions.
module deployHds 'main.bicep' = {
  name: 'msft-mdl-hds-deployHdsMain'
  params: {
    languageServiceId: languageServiceId
    tagsByResources: tagsByResources
    fhirServerUri: fhirServerUri
    exportStartTime: exportStartTime
    location: location
    _artifactsLocation: _artifactsLocation
    _artifactsLocationSasToken: _artifactsLocationSasToken
    deployUpdatesOnly: deployUpdatesOnly
  }
}

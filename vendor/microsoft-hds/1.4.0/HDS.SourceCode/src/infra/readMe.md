- **This folder contains the infra code that needs to be deployed as part of Integrated Data Platform for Health**
  - modules - bicep modules
  - config - configuration files for deployment (variables for bicep modules etc.)
  - scripts - powershell/cli/other scripts to execute using deployment script extension of ARM
  - main.bicep - driver bicep file to call modules
  - createUiDefinition.json - This file is needed to render UI in Azure portal, when shipped as an Azure offer & can be used to test the underlying scripts for install/update scenarios. 
- [Install Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?tabs=azure-cli)
- Please ensure that you have the **Contributor, User Access Administrator** roles on the resource group you are deploying into.
- The deployment artifacts can be downloaded from [DataManager.Healthcare](https://dev.azure.com/dynamicscrm/Solutions/_artifacts/feed/DataManager.Healthcare/UPack/datamanager-analytics-health-all/overview) feed. The artifacts must be placed in a blob container with name `datamanager-deployment`
- Following is the script to deploy the main bicep file to Azure resource group (Dev environment):
  ```powershell
  # Update following deployment parameters as needed. These are the configuration for the resource group you are deploying into
  $tenantId = '72f988bf-86f1-41af-91ab-2d7cd011db47'
  $subscriptionId = 'efaddd1f-3f03-43d2-bf06-0868f8d9da3a'
  $resourceGroupName = 'rg-idp-deployment-test'
  $languageServiceId = '/subscriptions/efaddd1f-3f03-43d2-bf06-0868f8d9da3a/resourceGroups/dmh-dev-sharedrg/providers/Microsoft.CognitiveServices/accounts/idpdevlanguageservice'
  $fhirServerUri = 'https://idpfhirserverdev-fhirserver.fhir.azurehealthcareapis.com'
  $location = 'eastus'
  $deployUpdatesOnly = $false
  $exportStartTime = (Get-date).AddDays(-30)
  $tagsByResources = @{
    'Microsoft.Storage/storageAccounts'= @{ 'key1' = 'value1'; }
    'Microsoft.KeyVault/vaults'= @{ 'key1' = 'value1' ; 'key2' = 'value2' ; }
  }
  $deploymentParameters = @{
    languageServiceId = $languageServiceId;
    fhirServerUri = $fhirServerUri;
    exportStartTime = $exportStartTime;
    location = $location
    tagsByResources = $tagsByResources
    deployUpdatesOnly = $deployUpdatesOnly
  }

  # Login to Azure.
  Connect-AzAccount
  Set-AzContext -SubscriptionId $subscriptionId -TenantId $tenantId

  # Following is the script to generate a SAS token for deployment artifacts. 
  # Update these parameters in case you have placed the artifacts in a different storage account.
  $resourceGroup1P = "idp-1P-rg"
  $storageAccount1P = "idpdeploymentartifacts"
  $container1P = "datamanager-deployment"
  $storageAccount1PKey = (Get-AzStorageAccountKey -ResourceGroupName $resourceGroup1P -Name $storageAccount1P).Value[0]
  $context = New-AzStorageContext -StorageAccountName $storageAccount1P -UseConnectedAccount
  $startTime = (Get-Date).AddMinutes(-15)
  $endTime = $startTime.AddHours(3.15)
  $sasToken = New-AzStorageContainerSASToken -Name $container1P -Permission r -Protocol HttpsOnly -StartTime $startTime -ExpiryTime $endTime -Context $context

  # Following is the main template uri for deployment.
  $templateUri = "https://${storageAccount1P}.blob.core.windows.net/datamanager-deployment/mainTemplate.json?${sasToken}"

  # Following is the script to deploy the main template.
  $suffix = Get-Random -Maximum 1000
  $deploymentName = "hds-azure-deployment" + $suffix
  New-AzResourceGroupDeployment -Name $deploymentName -ResourceGroupName $resourceGroupName -TemplateUri $templateUri -TemplateParameterObject  $deploymentParameters
  ```
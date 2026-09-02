## Automation (Test) Framework

The Automation (Test) Framework was created to aid in developing integration tests. While the framework can be used for tests, it is generic enough as a composeable runner for any automation task related to to Fabric. 


## Related work

Automating tests any developer tasks is not a novel concept, we should try to re-use existing code and ideas to accelerate time to value. This section details solutions that were used as inspiration in the design of the automation framework.

### Config-drive deployments
Given Fabric is still a new and developing platform, it is missing tooling and support found in platformas like Azure. One tool that is missing is an easy way to orchestrate artifact/item deployments. We should be able to easily deploy and manage a set of artifacts without writing client code.

#### ARM Templates

An Azure Resource Manager (ARM) template is a JSON file that defines the infrastructure and configuration for your Azure resources in a declarative manner. It allows you to specify what resources you need, their properties, and dependencies, enabling you to deploy, update, and manage them consistently and repeatedly. ARM templates are useful because they provide a way to automate the deployment of complex environments, ensure consistency across deployments, and enable infrastructure as code (IaC) practices, which improve efficiency, reduce errors, and facilitate version control and collaboration.

The following evaluates ARM templates as a config-driven solution, highlighting pros/cons

Pros:
- Supports basic / fundamental structured resource deployment 
- Supports templates / parameters

Cons:
- Supports Azure resources but not Fabric
- Closed source runtime (not able to see how these steps are executed)

Here's a shorted example of how to deployed a storage account:
```json
{
  "$schema": "...",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "location": {
      "type": "string",
      "defaultValue": "[resourceGroup().location]",
      "metadata": {
        "description": "Location for the storage account."
      }
    },
    "storageAccountName": {
      "type": "string",
      "metadata": {
        "description": "Name of the storage account."
      }
    }
  },
  "resources": [
    {
      "type": "Microsoft.Storage/storageAccounts",
      "apiVersion": "2021-04-01",
      "name": "[parameters('storageAccountName')]",
      "location": "[parameters('location')]",
      "sku": {
        "name": "Standard_LRS"
      },
      "kind": "StorageV2",
      "properties": {}
    }
  ],
  "outputs": {
    "storageAccountName": {
      "type": "string",
      "value": "[parameters('storageAccountName')]"
    }
  }
}
```

### ADO Pipelines

Azure DevOps (ADO) pipelines are a cloud-based service that provides continuous integration (CI) and continuous delivery (CD) capabilities for building, testing, and deploying applications. They enable automation of the software development lifecycle, allowing teams to deliver high-quality software faster and more reliably.

1. **Continuous Integration (CI)**: Automatically build and test code every time a change is pushed to the repository, ensuring that the codebase is always in a deployable state.
2. **Continuous Delivery (CD)**: Automate the deployment of applications to various environments, such as development, staging, and production.
4. **Integration with Version Control Systems**: Seamless integration with popular version control systems like GitHub, Azure Repos, and Bitbucket.
5. **Extensibility**: Support for custom tasks and extensions to tailor the pipeline to specific needs.

The following analyzes pros/cons of using ADO pipelines to setup and run HDS Fabric infra. We plan on using ADO pipelines to run the Automation Framework. The framework pulled some ideas from ADO pipeline concepts (steps/tasks and input/output)

Pros:
- Config driven, domain agnostic, composeable
- Runs a pipeline as a service, not tied to local development allowing scheduled long-running jobs
- Allows for parameterized inputs and outputs at each step/stage/task in the pipeline

Cons:
- Tailored for ADO, not local dev
- No Fabric support out of the box (which is expected)
- requires scripts to be developed outside of pipeline definition

Here's an exmaple of a simple pipeline that installs requirements, pulls auth from key vault and runs a python script using that auth as an argument:

```yml
trigger:
- main

pool:
  vmImage: 'ubuntu-latest'

variables:
  keyVaultName: 'your-keyvault-name'  # Replace with your Key Vault name
  secretName: 'your-secret-name'      # Replace with your secret name

steps:
- task: UsePythonVersion@0
  inputs:
    versionSpec: '3.x'
  displayName: 'Use Python 3.x'

- task: AzureKeyVault@2
  inputs:
    azureSubscription: 'your-azure-subscription'  # Replace with your Azure subscription
    KeyVaultName: '$(keyVaultName)'
    SecretsFilter: '$(secretName)'
  displayName: 'Pull secret from Azure Key Vault'

- script: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
  displayName: 'Install dependencies'

- script: |
    python your_script.py --secret $(your-secret-name)
  displayName: 'Run Python script with secret'
```

### HDS Capability Manifest

Our own DMH Workload consumes a capability manifest file to help orchestrate deployments.

The following are some initial thoughts on how the capability manifest and its design is relevant to automation testing. This is not a pros/cons of how the capability manifest is used in the DMH workload but evaluating general design concepts.

Pros:

- Forms a Directed Acyclical Graph (DAG) of logically grouped capabilities as to not re-write the same spec over and over
- Simple enough to follow, not deeply nested
- Easy to extend and add additional capabilities or artifacts to existing capabilities

Cons: 
- Versioning is great but not immediately applicable for our tests
- Handles artifact definition but not used for additional setup or other tasks
- Contained to a single file

```json
    {
      "version": "1.0.0",
      "featureFlightName": "hdsEnforceLifecycleManagement",
      "capabilities": [
        {
          "capabilityKey": "relational-fhir-data-foundations",
          "version": "1.0.0",
          "activitiesGlobalParameters": {
            "systemConfigurations": [...],
            "userConfigurations": [...]
          },
          "artifacts": [
            {
              "artifactType": "Environment",
              "artifactKey": "hds-environment",
              "displayName": "{0}_msft_hds_environment",
              "deploymentSequence": 1,
              "version": "1.0.0",
              "artifactConfigValues": {
                "EnvironmentId": "Id"
              }
            },
            {
              "artifactType": "Lakehouse",
              "artifactKey": "bronze-lakehouse",
              "displayName": "{0}_msft_bronze",
              "deploymentSequence": 2,
              "version": "1.0.0",
              "artifactConfigValues": {
                "BronzeDatabaseId": "Id",
                "BronzeDatabaseName": "DisplayName"
              },
              "lakehouseTablePath": "1.0.0/Bronze"
            },
            {
              "artifactType": "Notebook",
              "artifactKey": "setup-and-config-notebook",
              "displayName": "{0}_msft_config_notebook",
              "deploymentSequence": 3,
              "version": "1.0.0",
              "artifactPayloadParts": [
                {
                  "payload": "Notebooks/msft_config_notebook.ipynb",
                  "payloadPath": "artifact.content.ipynb",
                  "payloadContentType": "Embedded",
                  "payloadPlaceholdersToArtifactConfigMap": {}
                }
              ],
              "artifactConfigValues": {
                "SetupAndConfigNotebookName": "DisplayName"
              }
            },
          ]
        }
      ]
    }
  }
```

### Infrastructure as Code (IAC)

#### Bicep
Bicep is a domain-specific language (DSL) for deploying Azure resources declaratively. It is designed to simplify the authoring of Azure Resource Manager (ARM) templates by providing a more concise and readable syntax. Bicep aims to improve the developer experience by reducing the complexity and verbosity associated with JSON-based ARM templates. While the automation framework is more of a config driven approach, Bicep

Bicep provides an IAC solution that would be ideal for Fabric solutions. 

Pros:
 - Makes config more programmatic
 - Simplified Syntax: Bicep provides a more concise and readable syntax compared to JSON-based ARM templates.
- Modularity: Bicep supports modularity, allowing you to break down complex deployments into reusable components.
- Type Safety: Bicep includes type safety features, such as parameter and output types, to catch errors early in the development process.

Cons:
- Seemingly not extensible, and we don't want to invest in implemented our own DSL

Sample Bicep:
```
// Parameters
param location string = resourceGroup().location
param storageAccountName string

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2021-04-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {}
}

// Outputs
output storageAccountName string = storageAccountName
```

## Framework Concepts

This section details concepts and patterns used in the framework.

### Tasks

The Automation Framework runs one or many processes using configuration files. A process is just a set of tasks. One can create a custom task by creating a new class under the `tasks` folder that inherits the `BaseTask`. After creating a custom task, you can reference it by class name in a config file.

```py

from .base_task import BaseTask
from ..exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class SampleTask(BaseTask):
    
    def __init__(self, fabric_client, context):
        super().__init__(fabric_client, context)

    def execute(self, **kwargs):
        print("Executing a sample step")
        
    def onComplete(self, **kwargs):
        print(f"Sample step completed!")

    def validate_args(self, **kwargs) -> bool:
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
```

#### Fabric Client

Classes that inherit from the `BaseTask` class will be able to access a `FabricClient` which has a handful of Fabric methods for:

- Workspaces
- Capacities
- Lakehouse
- Notebooks
- Environments
- Data Pipelines
- Jobs
- DMH Workload
- Git Integration

### Parameters

Each task can have a variety of inputs. A task is responsible for calling the helper method `get_value` to resolve a value from a given string. The helper method will check the params parsed from the config as well as the runtime context.

Here's an example of passing in a handful of params used for notebook creation. Note that values starting with `$` reference a value expected to be in the context. There is currently no type checking so the parameter can be of any type (see `lakehouseConfig`) as an example.

```json
  "params": {
      "workspace": "$test_workspace",
      "environment": "$test_environment",
      "notebookName": "msft_dm4h_raw_bronze_ingestion",
      "notebooks_path": "$notebooks_path",
      "lakehouseConfig": {
          "default_lakehouse_name": "Bronze",
          "known_lakehouses": [
          "Config",
          "Bronze"
          ]
      },
      "notebook_parameters": {}
  }
```
### Runtime Context

When creating new artifacts, you might need to access certain information at runtime. For example, an artifact id won't be available until the artifact is created. To circumvent this issue, a runtime context is provided to each task -- it's just a dictionary of key value pairs. You can read and write to this context. 

### Outputs

A task can return a value or list of values and have it added to the runtime context to be referenced downstream. For HDS, this is useful when creating a new workspace or environment which other artifacts depend upon.

Here's an example where a workspace was returned in a task
```py
    def execute(self, **kwargs):
        
        #Some code ommitted for brevity
        create_workspace_request = CreateWorkspaceRequest(...)
        ws = self.fabric_client.create_workspace(create_workspace_request)
        return ws
```

The config file will try to map the returned value(s) to the provided string name
```json
  "outputs": [
      "test_workspace"
  ]
```

In a later task, this workspace can then be references as follows: 

```json
"params": {
  "workspace": "$test_workspace",
}
```

# Onboarding

Before onboarding, first review existing tasks and configs/tests and decide if you can re-use anything for your use case.

### Creating a pipeline config

To start creating your own process or workflow, you need to create a new json config following this format:

```json
{
    "name": "A sample runnable config",
    "description": "An sample description",
    "targetEnvironment": "MSIT",
    "initial_context": {},
    "tasks": []
}
```

You can then populate the "tasks" section to build your pipeline.

### Creating a custom task
Create a new task class in the `tasks` folder

- Make sure to implement the execute method
- Set parameters that are required to be in the config file in `validate_args`
- Implement optional callbacks like `onComplete`

```py

class SampleTask(BaseTask):
    
    def __init__(self, fabric_client, context):
        super().__init__(fabric_client, context)

    def execute(self, **kwargs):
        print("Executing a sample step")
        
    def onComplete(self, **kwargs):
        print(f"Sample step completed!")

    def validate_args(self, **kwargs) -> bool:
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
```

3. Running the pipeline config

```
> python automation_framework --config_file <path to your config>
```

4. That's it! You should start seeing output logged to the console as each task is being executed. You can easily setup a debug profile and step through the code with breakpoints.

## Pipeline Integration

TODO


## Use cases

- Bug bash workspace provisioning
- ALM multi workspace provisioning
- Feature testing required fabric resources
- Integration Tests

## Remaining Work Items

- Running many config files in parallel
- Add Task for pulling artifacts from ADO branches
- Add support for running multiple **__Tests__** in parallel
- Add support for running multiple **__Steps__** in parallel
- Add support for DMH Workload API calls
  - Code exists, just need to add steps
- Add support for Git Integration calls
    - Create an E2E test
- Consider clean up callback for newly created resources

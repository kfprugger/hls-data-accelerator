
## Overview

The Integration Test Framework is a tool used to automate validating Health Data Solutions (HDS) on Fabric. The purpose of these tests are to increase confidence in our ability to release bug-free code and decrease time developers spend on tedious processes. The purpose of this doc is to provide context on high level test framework concepts and help you get started running these tests locally.

## How it works

Each test is defined by a config file and contains a series of steps to execute. These steps target Fabric APIs including the HDS Workload.

## Important Concepts

**Automation Framework** (automation_framework.py) - The entry point to the framework is a script called `automation_framework.py` which takes some environment configurations (ex. where to deploy? msit? dxt?) and auth configurations (ex. Certificate based auth). The script is able to run a single test or a series of tests if configured. Each test is converted into a Pipeline Runner instance.

**Tasks** - Similar to ADO Pipelines, tasks here are an abstraction to aid in a config driven design. Tasks are just function calls and represent logical units of work. Each task will inherit from `BaseTask` and need to implement some abstract method, some of these are optional.

**Runtime Context** - The deployment of Fabric artifacts often have dependencies on other artifacts. For example, notebooks will often require metadata about both a Lakehouse and an Environment. Until runtime, this metadata (ex. Artifact Ids) are not known, so the test framework maintains a context in memory to keep track of new information. The developer has the option to both read and write to this context, it's just a dictionary.

**Pipeline Runner** - A pipeline runner is a light abstraction that executes a test config file. Each pipeline runner has it's own context and access to a Fabric client. The pipeline runner also maintains and state manager to keep track of the current and previous steps. The pipeline runner will operate like a factory, creating instances of each `BaseTask` that is then executed.

**Fabric Client** - The Fabric Client is a facade that encapsulate several other Fabric (an some Azure) clients to manipulate the artifacts in a workspace. This client will be able to perform CRUD operations on lakehouses, notebooks, environments, datapipelines, etc. It also supports **running** notebooks and data pipelines, copying data into a lakehouse from azure storage, and git integration.

## Anatomy of a Test

Most Integration tests against HDS services will follow the same pattern. While the config file might appear large at first, there are 3 basic steps:
     1. Deploying a Capability
     2. Running a data pipeline
     3. Validating the results

## Anatomy of a Test Config

Test configs can be quite large but contain simple building blocks. At the root of the config contain simple metadata like the test name and a description. And then there are the two main sections:

`initial_context` - You can think of these as global variables to be used throughout the test, these are loaded into the context
`tasks` - An array outlining which steps to execute as part of the test.

### Task Concepts

**Task Type**: The task type is the name of the class for a specific `BaseTask` implementation. When the automation framework is initialized, it will automaticlaly pick up and register these classes. If you do not provide a valid type, the test will error before execution.

**Parameters**: Each task will have it's own set of named parameters. Tasks should validate arugments before execution. 

**Variables**: Test configs can leverage the runtime context to template arguments that are not known before runtime.

Note: The values of the items in the context can be any object
Note: Notebook parameters use a slightly different notation, we're working on consolidating to a single convention

**Outputs**: Each task has the option to emit a list of outputs. The config can capture these outputs and put them in the runtime context by providing a matching list of names. In the example below, the `CreateWorkspace` task returns a workspace object, which is stored in the context and then accessed in the `CreateLakehouse` task by referencing `$workspace`.

Note: There are no checks at the moment for using the same name for outputs/variables, the developer is responsible for providing unique names.

**Ignoring Tasks** - Throughout the development process you might want to ignore certain steps without removing them from the test config. You can add a flag `"ignore": "false"` to achieve this, this will be logged to the console to indicate it was ignored.

**Sample Automation/Test**

Here is a sample test config which deploys a new workspace and a lakehouse. 

```json
{
    "name": "Sample Test / Automation",
    "description": "A simple example of orchestrating a workspace and notebook",
    "initial_context": {
        "targetEnvironment": "mist",
        "workspaceDisplayName": "HDS_Sample",
    },
    "tasks": [
        {
            "type": "CreateWorkspace",
            "description": "Creating a new test workspace",
            "parameters": {
                "displayName": "$workspaceDisplayName",
                "description": "A test ws"
            },
            "outputs": [
                "workspace",
                "capacityId"
            ]
        },
        {
            "type": "CreateLakehouse",
            "description": "Creating a Sample Lakehouse with folders",
            "ignore": "false",
            "parameters": {
                "displayName": "Sample",
                "description": "A sample lakehouse",
                "workspace": "$workspace",
                "subfolders": []
            },
            "outputs": [
                "sample_lakehouse"
            ]
        },
    ]
}
```

## Validation Notebooks

While the automation of capability deployment and pipeline execution adds a significant amount of value by ensuring our P0 goals are met and code changes are not break, there's more we can do to prevent regressions.

There are two areas we are interested in validating: deployments and data. As we continue to add features, we want to make sure that the deployment includes critical changes (new lakehouses, new tables, new config files, etc.). In addition, we also want to make sure we can attest to the work of our services. If we're processing data in a pipeline, we should check the inputs and outputs at each stage. Given that these two areas of validation are separate, we are asking teams to provide different notebooks for each type of test. This makes a clear distinction as to what types of tests go where and allows us to track onboarding progress.

Validation notebooks are notebooks that are run as jobs and use an `xml-runner` package to collect tests compatible with JUnit. The reason being is that eventually we will have these tests run in a pipeline and want to them exposed to the Azure DevOps UX. This can be accomplished using the ADO Pipeline task below, but notice it is limited to the expected file type.

```yml
# Publish test results to Azure Pipelines.
- task: PublishTestResults@2
  inputs:
    testResultsFormat: 'JUnit' # 'JUnit' | 'NUnit' | 'VSTest' | 'XUnit' | 'CTest'. Alias: testRunner. Required. Test result format. Default: JUnit.
    testResultsFiles: '**/TEST-*.xml' # string. Required. Test results files. Default: **/TEST-*.xml.
```

By running these tests in notebooks in Fabric, we're also able to harness the power of spark to perform complex queries on the data itself. If you're onboarding to either deployment tests or data integrity tests, it is recommended to take a look at what Clinical/OMOP has done so far:

>/src/tools/automation/AutomationFramework/resources/notebooks/clinical/hds_clinical_foundations_data_validation_tests.ipynb

![](./validation_tests_arch.png)


## Known Limitations

- Workspace retention is not automated, we're looking into adding this especially when these tests are run in a pipeline.
- Parameters/variables in the test config **_does not_** support resolution of concatenation or other types of replacements, example:
    - "key": "some/url/{$workspaceId}" or
    - "key": $workspaceId + "test"
- Tests are always re-run from the beginning, it might be possible to support picking up where it left off if the runtime context is serializable
- Attempting to deploy capabilities in parallel can lead to throttling TIPS. The pipeline runner supports running tests sequentially as well as in parallel, but this needs to be addressed, otherwise the tests will never get past capability deployment.
- Shortcuts for a storage account are not supported, the Fabric APIs did not support creating new connections during development, that appears to be available now



# FAQ


**How do I configure the environment? (daily, dxt, msit)** 

First, make sure you are part of the security group allowing you to access Daily/DXT without a Fabric Test account. If you're using an environment config file, you can modify it there. Otherwise, in `automation_framework.py` you can change the default environment from `msit`. 

**Does every tests create a new workspace? Are workspaces removed after the test completes?**

- Each test creates a new workspace
- Workspaces are not removed after the test completes

If you find yourself creating several workspaces throughout development, you can run `remove_workspaces.py`.

Example usage that previews workspaces to delete that follow a pattern (recommended to run first):
> python remove_workspaces.py -p HDS_IT_OMOP

Follow up command to actually remove workspaces. Note: This might fail if the workspace is attached to a deployment pipeline.

> python remove_workspaces.py -p HDS_IT_OMOP -d



**How do I use the HDS libraries I build locally?**

We can configure a test to target the Workload deployment to manage most of the infrastrucutre. During the deployment, each artifact is deployed and the Workload environment is published. We can cancel that publish request, modify the existing environment, and publish again. This is accomplished in the following tasks:

Note: Depending on how the `PublishEnvironment` task is configured, it might be replacing .whl files, or it could include uploading an `environment.yml` file and/or uploading other system configuration files (ex. table schemas)

```json
{
    "type": "RemoveEnvironmentLibraries",
    "description": "Removing libraries from default environment",
    "parameters": {
        "workspace": "$workspace",
        "environment": "$environment"
    }
},
{
    "type": "PublishEnvironment",
    "description": "Publishing an environment with local libraries",
    "ignore": "false",
    "parameters": {
        "workspace": "$workspace",
        "environment": "$environment",
        "dist_path": "$dist_path",
        "libraries_relative_path": "/healthcare-libraries/1.1.0/",
        "environment_yml_path": "src/tools/automation/AutomationFramework/resources/configs/environment.yml"
    },
    "outputs": []
}
```

**How do I configure which capabilities I want deployed?**

There is a task, usually early in the test config, for deploying capabilities via the Workload endpoints

```json
{
    "type": "DeployHdsCapabilities",
    "description": "Deploy foundations capablity",
    "parameters": {
        "capacityId": "$capacityId",
        "workspace": "$workspace",
        "solution_artifact_id": "$solution_artifact_id",
        "capabilities": [
            {
                "capabilityKey":"relational-fhir-data-foundations",
                "userParameters":[]
            },
            {
                "capabilityKey":"sample-data",
                "userParameters":[]
            },
            {
                "capabilityKey": "omop-analytics",
                "userParameters": []
            }
        ],
        "uniquePrefix": "$uniquePrefix"
    },
    "outputs": []
}
```

**How long does each test take?**

It depends on the size of the sample data and the activities in the associated date pipeline, but here's what we've observed for OMOP Analytics E2E Test:

 - ~2-3 minutes for Capability deployment
 - ~12-20 minutes for the environment to publish
 - ~45 minutes for the data pipline (4 activities) to complete
 - ~10 minutes for validation notebooks to complete

**Can I run a test without using the Workload APIs?**

Yes, but it's limited.  There is a config that will setup a dev environment from scratch (/src/tools/automation/AutomationFramework/samples/clinical_foundations.json). This is coded for clinical only and would need further development to support the rest of the modalities. It does, however, deploy and configure all resources as the workload would, and uses a Config lakehouse to mimic the storage of an HDS artifact.

This config allows us to quickly test new features without being constrained by what is deployed to the workload. One could also take a hybrid approach and call the workload apis and then modifiy/create additional artifacts.

If this is of interest to your team, please reach out.

**How can I monitor the run of each test?** 

There is a simple html template that is update when a test is run, you can open in a browser, location: CRM.Solutions.Healthcare.DataPlatform/pipeline_status.html

**How can I write my own test?**

It is recommended to start by taking a look at the foundations test (src/tools/automation/AutomationFramework/integrationTests/foundations/foundations_e2e.json) -- it should contain the general structure of an E2E test.

**How do I update the library versions for the tests?**

In preparation of a new version upgrade, peform a search on  the current version: `healthcare-artifacts/1.x.x` and replace with the expected, newer version.

In addition, update instances of `expected_installed_capabilities` if using a workload deployment, otherwise some tests will fail.

**How can I add my own task to be used in a test config?**

To create and use your own custom task, you need to create a new class that extends `BaseTask` and save it under `src/tools/automation/AutomationFramework/tasks`

The framework will automatically pick up class and run it's `execute` method. Here is a simple example that can get you started:

```py
class SampleTask(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        
        # Note: You get have access to a fabric client, context 
        # and a logger for free
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        # Start by parsing arugments
        display_name = get_value('displayName', self.context, kwargs)

        # DO SOMETHING

        # Optionally return a value that can be consumed later
        return "this is a test"

    def onComplete(self, **kwargs):
        # Optional callback
        self.logger.info(f"Successfully completed task")

    def validate_args(self, **kwargs) -> bool:

        # Perform simple argument validation
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
```
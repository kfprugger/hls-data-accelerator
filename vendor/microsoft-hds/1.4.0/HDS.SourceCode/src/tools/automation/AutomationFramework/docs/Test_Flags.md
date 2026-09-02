## Test Flags

In an effort to reduce the number of test config files we need to maintain, we introduce the concept of test flags. These flags change the behavior of the tasks that are run for a test. Each task in the config has options now for "include_when" and "exclude_when" that include/exclude the task if there is a matching flag.

**NOTE**: You do not need to modify existing tests, and these flags do not change how existing tests are executed.

- Flags are defined in each test config, not in automation_framework.py
- Flags are self documenting and the framework validates arguments
- Flags can be inclusive and exclusive

```json
    "flags": {
        "core": "run the core integration tests",
        "deployment": "Mark tasks used only in deployment but not pipeline runs or testing",
        "do_not_run_tests": "do not run tasks that setup and run the test infra",
        "do_not_run_data_pipeline": "do not run the data pipeline",
        "do_not_use_sample_data": "Use another data source instead of copying sample data",
        "useExistingWorkspace": "Use an existing workspace instead of creating a new one",
        "upload_local_libraries": "Use local libraries in the environment"
    },
```

**NOTE**: Test flags should be separate from the named arguments used by the main automation_framework.py script, for example `preview` should not be used.

## Flag Validation

If you attempt to run the `automation_framework.py` script without valid flags, you will receive an error and a printout of the available options.

For example:

```
python automation_framework.py --bad_flag
```

would yeild the following in the console log for the foundations test config:

```
Test flags:  ['bad_flag']
Applying flags to tasks...
Flag bad_flag not found in config
Available flags:
         do_not_run_tests : do not run tasks that setup and run the test infra
         do_not_run_data_pipeline : do not run the data pipeline
         do_not_use_sample_data : Use another data source instead of copying sample data
         use_existing_workspace : Use an existing workspace instead of creating a new one
         upload_local_libraries : Use local libraries in the environment
```

## Previewing a Test Plan

To help validate that your test is about to execute the expected tasks, you can run the automation framework with the `--preview` argument (other args not shown):

```
> python automation_framework --preview
```

This flag will only show the test plan with the tasks filtered (or applied) based on present flags.

### Test Plan

Prior to executing a test, the framework will log the input flags and which tasks are impacted (either added or removed) based on the presence of the flag. Then, the framework will log the modified test plan.

In the example below, the `--do_not_run_tests` flag reduces the tasks from 26 to 10:
```
Test flags:  ['do_not_run_tests']
Applying flags to tasks...
Exclusion detected for 'do_not_run_tests', removing task: Creating an environment used by test notebooks
Exclusion detected for 'do_not_run_tests', removing task: Add deployed bronze lakehouse to the runtime context
Exclusion detected for 'do_not_run_tests', removing task: Creating a Test lakehouse
Exclusion detected for 'do_not_run_tests', removing task: Setting up bronze ingestion tests notebook
Exclusion detected for 'do_not_run_tests', removing task: Setting up capability deployment tests notebook
Exclusion detected for 'do_not_run_tests', removing task: Setting up data validation notebook
Exclusion detected for 'do_not_run_tests', removing task: Running bronze ingestion tests notebook
Exclusion detected for 'do_not_run_tests', removing task: Running clinical foundations deployment tests notebook
Exclusion detected for 'do_not_run_tests', removing task: Running data validation tests notebook
Exclusion detected for 'do_not_run_tests', removing task: Polling validation notebook completion
Exclusion detected for 'do_not_run_tests', removing task: Polling validation notebook completion
Exclusion detected for 'do_not_run_tests', removing task: Polling validation notebook completion
Exclusion detected for 'do_not_run_tests', removing task: Parse test results

Filtered tasks: 26 -> 10
Planning to run the following tasks
  - Creating a new test workspace
  - Create a new hds item
  - Deploy foundations capablity
  - Get deployed environment
  - Setting up notebook to copy sample data
  - Running copy sample data notebook
  - Polling copy sample data notebook completion
  - Waiting for test env to publish
  - Running Omop analytics pipelines
  - Poll data pipeline completion
```

## Inclusion / Exclusion Modifiers

Consider the following task definitions below for either creating a workspace or using an existing workspace.

The task `CreateWorkspace` is "excluded when" the flag `use_existing_workspace` is present

The task `FindWorkspace` is "included when" the `use_existing_workspace`

**NOTE**: Tasks with and empty include_when are added by default, the introduction of a single flag means the tasks would not be included unless one of the flag is present. In the example below, the first task is included by default, the second task is not.

```json
{
    "type": "CreateWorkspace",
    "description": "Creating a new test workspace",
    "include_when": [],
    "exclude_when": ["use_existing_workspace"],
    "parameters": {
        "displayName": "$workspaceDisplayName",
        "description": "A test ws",
        "add_datetime_postfix": "true"
    },
    "outputs": []
},
{
    "type": "FindWorkspace",
    "description": "Use an existing workspace",
    "include_when": ["use_existing_workspace"],
    "exclude_when": [],
    "parameters": {
        "workspaceId": ""
    },
    "outputs": []
},
```

## Run the integration tests with an existing workspace
> python automation_framework.py --file foundations.json --use_existing_workspace

## Update HDS with an existing workspace
> python automation_framework.py --file foundations.json --use_existing_workspace

## Use an exising workspace and do not run tests
> python automation_framework.py --file foundations.json --use_existing_workspace --do_not_run_tests

## Run using local wheel files
> python automation_framework.py --file foundations.json --upload_local_libraries

## Run the test using sample data copied from blob storage

Note: A separate `copy_from_blob` task would need to be present in the config, the dev is responsible for orchestrating when tasks are executed, the framework does not automatically know that by disabling one task another task is enabled.

> python automation_framework.py --file foundations.json --do_not_use_sample_data --copy_from_blob
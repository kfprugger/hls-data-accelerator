import argparse
import glob
import inspect
import os
import pkgutil
import importlib
import tasks
from typing import List
from utils.framework_state_manager import FrameworkStateManager
from utils.pipeline_runner import PipelineRunner
from utils.default_azure_credential_token_provider import DefaultAzureCredentialTokenProvider
from utils.static_token_provider import StaticTokenProvider
from utils.certificate_based_auth_token_provider import CertificateBasedAuthTokenProvider
from utils.config_utility import load_config
from tasks.base_task import BaseTask

def register_tasks(module, base_class):
    tasks = {}
    for _, name, _ in pkgutil.iter_modules([module.__path__[0]]):
        m = importlib.import_module(f"{module.__name__}.{name}")        
        classes = inspect.getmembers(m, inspect.isclass)
        module_classes = [
            cls for cls in classes
            if module.__name__ in cls[1].__module__ and issubclass(cls[1], base_class) and cls[0] != base_class.__name__]

        for c in module_classes:
            tasks[c[0]] = c[1]

    return tasks
    
def print_task_header(pipeline_name, task_index, task_type, task_description = None):
    if task_description:
        header = f"\n[{pipeline_name} - Task {task_index}: {task_description}"
    else:
        header = f"\n[{pipeline_name}] -Task {task_index}: {task_type}"
    
    print(header)
    print("-" * (len(header)))

def createTokenProvider(token, envConfig):
    if token is not None and token != "":
        return StaticTokenProvider(token)
    elif envConfig is not None and len(envConfig) > 0:
        return CertificateBasedAuthTokenProvider(envConfig)
    else:
        return DefaultAzureCredentialTokenProvider()

def run_pipelines(pipeline_config_files, env_config_file, environment, token, max_parallelism = 1, flags=[], preview=False):

    # Register available tasks
    registered_tasks = register_tasks(tasks, BaseTask)
    baseDire = os.path.dirname(__file__)
    env_config = {}
    if env_config_file:
        env_config = load_config(os.path.join(baseDire,"config"), env_config_file)
    token_provider = createTokenProvider(token, env_config)

    framework_state_manager = FrameworkStateManager()
    runners: List[PipelineRunner] = []
    for config_file in pipeline_config_files:
        config = load_config(baseDire, config_file)
        if env_config:
            (config["initial_context"]).update(capacityId=env_config.get("capacityId", None))
            (config["initial_context"]).update(targetEnvironment=env_config.get("targetEnvironment", None))
            (config["initial_context"]).update(subscriptionId=env_config.get("subscriptionId", None))
            (config["initial_context"]).update(resourceGroupName=env_config.get("resourceGroupName", None))
        elif environment:
            (config["initial_context"]).update(targetEnvironment=environment)
        print("Test flags: ", flags)
        print("Applying flags to tasks...")
        original_task_set = len(config['tasks'])
        if "flags" in config:
            available_flags = config["flags"].keys()
            valid_flags = True
            
            flag_config = { key: False for key in available_flags }
            for flag in flags:
                if flag not in available_flags:
                    print(f"Flag {flag} not found in config")
                    valid_flags = False
            
                flag_config[flag] = True

            if not valid_flags:
                print("Available flags:")
                for key, value in config["flags"].items():
                    print(f"\t {key} : {value}")

                return

            filtered_tasks = []
            for task in config['tasks']:
                inclusion_flags = task.get('include_when', [])
                include_task = False
                for in_flag in inclusion_flags:
                    if in_flag in flags:
                        print(f"Inclusion detected for '{in_flag}', adding task: {task.get('description', '')}")
                        include_task = True
                if len(inclusion_flags) == 0 or include_task:
                    filtered_tasks.append(task)

            config['tasks'] = filtered_tasks
            filtered_tasks = []
            for task in config['tasks']:
                exclusion_flags = task.get('exclude_when', [])
                exclude_task = False
                for ex_flag in exclusion_flags:
                    if ex_flag in flags:
                        print(f"Exclusion detected for '{ex_flag}', removing task: {task.get('description', '')}")
                        exclude_task = True
                if not exclude_task:
                    filtered_tasks.append(task)

            config['tasks'] = filtered_tasks

        if len(config['tasks']) < original_task_set:
            print(f"\nFiltered tasks: {original_task_set} -> {len(config['tasks'])}")

        print("Planning to run the following tasks")
        for task in config['tasks']:
            print(f"  - {task.get('description', '')}")

        if not preview:
            pipeline_runner = PipelineRunner(
                registered_tasks,
                config,
                framework_state_manager,
                token_provider
            )
            runners.append(pipeline_runner)
        else:
            print("\nPreview mode enabled, not executing tasks.")

    def run_single_pipeline(runner: PipelineRunner):
        runner.run()
    
    for runner in runners:
        runner.run()
    
    # with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallelism) as executor:
    #     futures = [executor.submit(run_single_pipeline, runner) for runner in runners]
    #     for future in concurrent.futures.as_completed(futures):
    #         try:
    #             future.result()
    #         except Exception as e:
    #             raise e

def main():
    parser = argparse.ArgumentParser(description="Runner for executing configured automation.")
    parser.add_argument('--token', type=str, help='an auth token for making Fabric API calls')
    parser.add_argument('--pipeline_config_files', type=str, nargs='*', help='List of config files to run')
    parser.add_argument('--config_folder', type=str, help='Pattern to match config files in a directory')
    parser.add_argument('--envConfig', type=str, help='Configuration file for the environment where the test should run')
    parser.add_argument('--env', type=str, choices=["dxt", "daily", "msit"], help='Environment name where this test should run')
    parser.add_argument('--preview', action='store_true', help='Preview the tasks in the test')
    #parser.add_argument('--include', type=str, nargs='*', help='List of filters to apply to tasks')
    #parser.add_argument('--exclude', type=str, nargs='*', help='List of filters to apply to tasks')

    args, unknown_args = parser.parse_known_args()
    flags = [arg.replace("--", "") for arg in unknown_args]

    token = args.token
    pipeline_config_files = args.pipeline_config_files
    config_folder = str(args.config_folder)
    envConfig = args.envConfig
    preview = args.preview
    if config_folder is not None and pipeline_config_files is not None and len(pipeline_config_files) == 0:
        pipeline_config_files = glob.glob(config_folder)

    if pipeline_config_files is None or (pipeline_config_files[0] == 'None' or len(pipeline_config_files) == 0):
        pipeline_config_files = [
            # "integrationTests/alm/alm_e2e.json",
            "integrationTests/all/all_test_against_deployment.json",
            # "integrationTests/foundations/foundations_e2e_local_changes.json",
            #"integrationTests/foundations/omop_analytics_deployment_tests.json"
            # "integrationTests/alm/alm_e2e.json",
            # "integrationTests/foundations/foundations_no_compression.json",
            # "integrationTests/foundations/foundations_no_file_movement.json",
            # "integrationTests/ci/customer_insights_test_against_deployment.json",
            # "integrationTests/imaging/dicom_imaging_test_against_deployment.json",
            # "integrationTests/ci/customer_insights_ingestion_e2e.json"
            #"integrationTests/sdoh/sdoh_ingestion_e2e.json",
            # "integrationTests/cma/cma_ingestion_e2e.json"
            # "integrationTests/sdoh/sdoh_ingestion_e2e.json"
            # "integrationTests/imaging/imaging_data_ingestion_e2e.json",
            #"integrationTests/dax/dax_conversational_data_enrichments_deployment_test.json",
            #"integrationTests/ai_enrichments/ai_enrichments_ta4h_test.json",
            #"integrationTests/ai_enrichments/ai_enrichments_med_image_parse_test.json",
            #"integrationTests/ai_enrichments/ai_enrichments_med_image_insight_test.json"
        ]

    run_pipelines(pipeline_config_files, envConfig, args.env, token, max_parallelism=1, flags=flags, preview=preview)

# Example usage
if __name__ == "__main__":
    main()
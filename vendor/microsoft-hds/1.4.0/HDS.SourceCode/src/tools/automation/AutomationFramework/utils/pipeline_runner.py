import json
import datetime
import logging
from uuid import uuid4
from clients.fabric_client import FabricClient
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from tasks.base_task import BaseTask
from utils.token_provider import TokenProvider
from .framework_state_manager import FrameworkStateManager
from .context_logger import ContextLoggerAdapter
from clients.fabric_client import FabricClient
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from tasks.base_task import BaseTask
from .context_logger import ContextLoggerAdapter

logging.basicConfig(level=logging.INFO, format='%(message)s')

class PipelineRunner:

    def __init__(self, registered_tasks, config, framework_state_manager: FrameworkStateManager, token_provider: TokenProvider):
        self.registered_tasks = registered_tasks
        self.config = config
        self.framework_state_manager: FrameworkStateManager = framework_state_manager
        self.token_provider = token_provider

        total_steps = len(self.config["tasks"])
        
        self.pipeline_id = self.framework_state_manager.register_pipeline(config["name"], total_steps)
        
        self.logger = logging.getLogger(__name__)

    def run(self):

        # Load the initial context with global parameters
        context = self.config["initial_context"]
        
        # Make important services available to the tasks
        context["registered_tasks"] = self.registered_tasks
        context["pipeline_id"] = self.pipeline_id
        context["framework_state_manager"] = self.framework_state_manager
        context["root_name"] = self.config["name"]
        context["token_provider"] = self.token_provider

        self.framework_state_manager.update_pipeline_state(self.pipeline_id, state="In Progress")

        # Run through each step
        self._run_tasks(context)

        if "workspace" in context and "targetEnvironment" in context:
            workspace = context["workspace"]
            env = context["targetEnvironment"]
            print(f"https://{env}.powerbi.com/groups/{workspace.id}/list?experience=power-bi")

    def get_current_time(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _run_tasks(self, context):
        
        for task_index, task_config in enumerate(self.config["tasks"]):
            context_logger = ContextLoggerAdapter(self.logger, {'index': self.pipeline_id[0:5], 'config_name': self.config["name"], 'task_index': task_index})

            if "type" not in task_config or "parameters" not in task_config:
                self.logger.error(json.dumps(task_config, indent=2))
                raise AutomationFrameworkValidationException(f"The task is missing a type or parameters")

            task_class = context["registered_tasks"][task_config["type"]](None, context, context_logger, 0)
            try:
                task_class.validate_args(**task_config["parameters"])
            except AutomationFrameworkValidationException as e:
                self.framework_state_manager.update_pipeline_state(self.pipeline_id, state="Failed", details="Validation Failed:" + str(e))
    
        pipeline_completed_successfully = True
        pipeline_details = ""
        for task_index, task_config in enumerate(self.config["tasks"]):
        
            target_environment = context["targetEnvironment"]
            context_logger = ContextLoggerAdapter(self.logger, {'index': self.pipeline_id[0:5], 'config_name': self.config["name"], 'task_index': task_index})
            fabric_client = FabricClient(token_provider=self.token_provider, env=target_environment, logger=context_logger)
            
            # Keep track of expected outputs from each task,
            # updating context using return values
            outputs = task_config.get("outputs", [])
            task_type = task_config["type"]
            task_id = str(uuid4())
            task: BaseTask = self.registered_tasks[task_type](fabric_client, context, context_logger, task_index)
            if "ignore" not in task_config or task_config["ignore"] == "false":
                
                self.framework_state_manager.update_pipeline_state(
                    self.pipeline_id,
                    task_index=task_index + 1,
                    current_task_name=task_config.get("type", ""), 
                    details=task_config.get("description", "")
                )
                
                # TODO - refactor to include task and pipeline ids as part of ctor
                # keep as is to reduce files touched
                task_id = str(uuid4())
                task.pipeline_id = self.pipeline_id
                task.task_id = task_id
                
                self.framework_state_manager.register_task(self.pipeline_id, task_id, task_config)
                task_config["parameters"]["description"] = task_config["description"]
                [task_succeeded, details] = task.run(task_config["parameters"], outputs)
                
                task_state = "Completed" if task_succeeded else "Failed"
                self.framework_state_manager.update_task_state(self.pipeline_id, task_id, task_state=task_state, set_end_time=True)

                if task_succeeded == False:
                    print(f"{task_type} failed, exiting test.")
                    pipeline_completed_successfully = False
                    pipeline_details = details.get("Reason", f"Exception occurred running task of type: " + task_type)
                    break

                task_index = task_index + 1
            else:
                print(f"Ignoring {task_type}")

        pipeline_state = "Completed" if pipeline_completed_successfully else "Failed"
        self.framework_state_manager.update_pipeline_state(self.pipeline_id, state=pipeline_state, set_end_time=True, details=pipeline_details)

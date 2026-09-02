from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from utils.pipeline_runner import PipelineRunner
from .base_task import BaseTask
from utils.context_utils import get_value
from utils.config_utility import load_config

class RunPipeline(BaseTask):
    
    def __init__(self, fabric_client, context):
        super().__init__(fabric_client, context)

    def execute(self, **kwargs):

        configFilePath: str = get_value('configFilePath', self.context, kwargs)
        configEdits = get_value('configEdits', self.context, kwargs)
        
        registered_tasks = self.context["registered_tasks"]
        framework_state_manager = self.context["framework_state_manager"]
        pipeline_id = self.context["pipeline_id"]    
        config = load_config(os.path.dirname(__file__).split("/tasks")[0], configFilePath)

        # Apply updates to the json if configured
        if configEdits:
            config = self.update_json(config, configEdits)

        PipelineRunner(
            registered_tasks,
            config,
            framework_state_manager,
            self.fabric_client.token_provider,
            parent_pipeline_id=pipeline_id).run()

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        if "configFilePath" not in kwargs:
            raise AutomationFrameworkValidationException("configFile is required")

    def update_json(self, config, configEdits):
        tasks = config.get("tasks", [])

        for edit in configEdits:
            action = edit.get("action")
            index = edit.get("index")
            task = edit.get("task")
            task_type = edit.get("task_type")
            nth_instance = edit.get("nth_instance", 1)
            position = edit.get("position", "at")  # Default position is "at"

            if action == "insert":
                if task_type:
                    task_index = self.find_nth_instance(tasks, task_type, nth_instance)
                    if task_index is not None:
                        if position == "before":
                            tasks.insert(task_index, task)
                        elif position == "after":
                            tasks.insert(task_index + 1, task)
                        else:
                            raise AutomationFrameworkValidationException(f"Unknown position {position} for inserting task.")
                    else:
                        raise AutomationFrameworkValidationException(f"Task type {task_type} with {nth_instance} instance not found.")
                elif index == "first":
                    tasks.insert(0, task)
                elif index == "last":
                    tasks.append(task)
                else:
                    tasks.insert(index, task)
            elif action == "remove":
                if index == "first":
                    if tasks:
                        tasks.pop(0)
                    else:
                        raise AutomationFrameworkValidationException("No tasks to remove.")
                elif index == "last":
                    if tasks:
                        tasks.pop()
                    else:
                        raise AutomationFrameworkValidationException("No tasks to remove.")
                elif 0 <= index < len(tasks):
                    tasks.pop(index)
                else:
                    raise AutomationFrameworkValidationException(f"Index {index} out of range for removing task.")
            elif action == "edit":
                if task_type:
                    task_index = self.find_nth_instance(tasks, task_type, nth_instance)
                    if task_index is not None:
                        tasks[task_index] = task
                    else:
                        raise AutomationFrameworkValidationException(f"Task type {task_type} with {nth_instance} instance not found.")
                elif index == "first":
                    if tasks:
                        tasks[0] = task
                    else:
                        raise AutomationFrameworkValidationException("No tasks to edit.")
                elif index == "last":
                    if tasks:
                        tasks[-1] = task
                    else:
                        raise AutomationFrameworkValidationException("No tasks to edit.")
                elif 0 <= index < len(tasks):
                    tasks[index] = task
                else:
                    raise AutomationFrameworkValidationException(f"Index {index} out of range for editing task.")
            else:
                raise AutomationFrameworkValidationException(f"Unknown action {action} in configEdits.")

        config["tasks"] = tasks
        return config

    def find_nth_instance(self, tasks, task_type, nth_instance):
        count = 0
        for i, task in enumerate(tasks):
            if task.get("type") == task_type:
                count += 1
                if count == nth_instance:
                    return i
        return None
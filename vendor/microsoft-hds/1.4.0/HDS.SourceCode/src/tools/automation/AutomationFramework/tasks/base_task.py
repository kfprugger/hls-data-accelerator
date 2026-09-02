from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from clients.fabric_client import FabricClient
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from logging import Logger

class BaseTask(ABC):
    task_id = None
    pipeline_id = None
    fabric_client = None
    logger = None
    context = None

    def __init__(self, fabric_client: FabricClient, context: Dict, logger: Logger, task_index: int = 0):
        
        # TODO - refactor to include in the constructor arguments
        self.task_id = None
        self.pipeline_id = None        
        
        self.fabric_client = fabric_client
        self.context = context
        self.logger = logger
        self.task_index = task_index
        
        
    def run(self, kwargs, outputs = []) -> Tuple[bool, Dict]:

        description = kwargs.get("description", None)
        if description:
            self.logger.info(f"Started running {self.__class__.__name__}. Description: {description}")
        else:
            self.logger.info(f"Started running task {self.__class__.__name__}")
        
        try:
            self.validate_args(**kwargs)
            result = self.execute(**kwargs)
            if isinstance(result, list):
                
                # Only handle outputs if they are configured
                if len(outputs) > 0:
                    
                    # Handle when a list of values are returned
                    if len(result) != len(outputs):
                        raise AutomationFrameworkRuntimeException("Return value did not match expected length")
                
                    for idx, ret_value in enumerate(result):
                        self.context[outputs[idx]] = ret_value

            elif len(outputs) == 1:
                # Handle when a single value is returned
                self.context[outputs[0]] = result
            
            self.onComplete()
            return [True, None]

        except Exception as e:
            self.logger.error(e)
            return [False, {"Reason": str(e)}]

    @abstractmethod
    def execute(self, **kwargs):
        pass
    
    @abstractmethod
    def validate_args(self, **kwargs):
        raise NotImplementedError()

    def onComplete(self, **kwargs):
        self.logger.info(f"Completed task {self.__class__.__name__}")

    def onFail(self, exception, **kwargs):
        self.logger.error(f"Task failed {self.__class__.__name__}")
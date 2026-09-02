
from .base_task import BaseTask
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class SampleTask(BaseTask):
    
    def __init__(self, fabric_client, context, logger):
        super().__init__(fabric_client, context)

    def execute(self, **kwargs):
        self.logger.info("Executing a sample step")
        
    def onComplete(self, **kwargs):
        self.logger.info(f"Sample step completed!")

    def validate_args(self, **kwargs) -> bool:
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
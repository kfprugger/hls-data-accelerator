
import json
from typing import Dict

from utils.copy_job_utils import create_copy_job
from utils.data_connection_utils import get_connections
from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value, get_value_from_context, update_context
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class CreateCopyJob(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        copy_job_name = get_value('copy_job_name', self.context, kwargs)
        storage_account_name = get_value('storage_account_name', self.context, kwargs)
        container_name = get_value('container_name', self.context, kwargs)
        source_subpath = get_value('source_subpath', self.context, kwargs)
        destination_lakehouse_name = get_value('destination_lakehouse_name', self.context, kwargs)
        destination_subpath = get_value('destination_subpath', self.context, kwargs)
        
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        
        target_lakehouse_id = None
        target_lakehouse_name = destination_lakehouse_name.lower()
        for lakehouse in lakehouses:
            if lakehouse.displayName.lower() == target_lakehouse_name.lower():
                target_lakehouse_id = lakehouse.id
                break

        if target_lakehouse_id is None:
            self.logger.info(f"Data configuration lakehouse: {target_lakehouse_name} not found")
        
        data_connections = get_connections(self.fabric_client.token_provider.get_token())
        
        account_names = set()
        source_data_connection = None
        for data_connection in data_connections:
            
            account_names.add(data_connection["accountName"])
            if data_connection["accountName"].lower() == storage_account_name.lower():
                source_data_connection = data_connection
                break        
        
        if source_data_connection == None:
            self.logger.info("Data connection with account name {} not found. Not copying data")
            self.logger.info("Here are the available connection account names: ")
            for ac in account_names:
                self.logger.info(ac)
        
        create_copy_job(
            workspace.id,
            copy_job_name,
            target_lakehouse_id,
            destination_subpath,
            data_connection["connectionId"],
            container_name,
            source_subpath,
            self.logger,
            self.fabric_client.token_provider,
            self.fabric_client.env)

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        if "copy_job_name" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: copy_job_name is a required parameter.")
        
        if "storage_account_name" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: storage_account_name is a required parameter.")
        
        if "container_name" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: container_name is a required parameter.")
        
        if "source_subpath" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: source_subpath is a required parameter.")
        
        if "destination_lakehouse_name" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: destination_lakehouse_name is a required parameter.")
        
        if "destination_subpath" not in kwargs:
            raise AutomationFrameworkValidationException("CreateCopyJob: destination_subpath is a required parameter.")
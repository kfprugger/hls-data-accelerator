import os
from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from utils.upload_files import upload_assets, upload_tables
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class UploadConfigurationFiles(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        local_directory_path = get_value("dist_path", self.context, kwargs)
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        
        if workspace is None:
            self.logger.error("Workspace is none")
            
        if local_directory_path is None:
            self.logger.error("Dir path is none")
        else:
            root_dir = os.path.dirname(__file__).split("src")[0]
            local_directory_path = os.path.join(root_dir, local_directory_path)
            self.logger.debug(local_directory_path)

        lakehouse_dict = {}
        for lakehouse in lakehouses:
            self.logger.debug(lakehouse.displayName)
            lakehouse_dict[lakehouse.displayName] = lakehouse

        if "Administration" in lakehouse_dict:
            upload_assets(workspace.id, lakehouse_dict["Administration"].id, local_directory_path + "/healthcare-configuration/1.2.0/system-configurations", "/system-configurations")
            upload_tables(workspace.id, lakehouse_dict["Administration"].id, local_directory_path + "/healthcare-tables/1.2.0/Administrative", "")

        if "Bronze" in lakehouse_dict:
            upload_tables(workspace.id, lakehouse_dict["Bronze"].id, local_directory_path + "/healthcare-tables/1.2.0/Bronze", "")
        
        if "Silver" in lakehouse_dict:
            upload_tables(workspace.id, lakehouse_dict["Silver"].id, local_directory_path + "/healthcare-tables/1.2.0/Silver", "")
                    
        if "OMOP" in lakehouse_dict:
            upload_tables(workspace.id, lakehouse_dict["OMOP"].id, local_directory_path + "/healthcare-tables/1.2.0/OMOP", "")
        
        if "Config" in lakehouse_dict:
            target_folder_root = "DMHConfiguration/_internal"
            upload_assets(workspace.id, lakehouse_dict["Config"].id, local_directory_path + "/healthcare-configuration/1.2.0/_internal", target_folder_root)
            upload_assets(workspace.id, lakehouse_dict["Config"].id, local_directory_path + "/healthcare-libraries/1.2.0", target_folder_root + "/packages")

    def onComplete(self, **kwargs):
        self.logger.info(f"Successfully uploaded configuration files")

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("UploadConfigurationFiles: workspaceName is a required parameter.")
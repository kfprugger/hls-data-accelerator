# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class used for organizing DICOM files in the lakehouse
"""
import os
import json
from typing import Callable
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.file_orchestrator_util import FileOrchestratorUtil
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.constants import FileOrchestratorConstants as C
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.file_orchestrator import FileOrchestrator
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class FileOrchestrationService(BaseRunnableService):
    """
    Class used for organizing files in the lakehouse
    """
    
    def __init__(self, 
                spark: SparkSession,
                workspace_name: str,
                solution_name: str,
                admin_lakehouse_name: str,
                inline_params: dict = None,
                one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Args:
            - spark: spark session
            - workspace_name: Name of the Fabric Workspace
            - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """
        super().__init__(spark=spark,
            workspace_name=workspace_name,
            solution_name=solution_name,
            admin_lakehouse_name=admin_lakehouse_name,
            inline_params=inline_params,
            one_lake_endpoint=one_lake_endpoint,
            mssparkutils_client=mssparkutils_client)
    
    def _setup(self) -> None:
        """
        The setup method for initializing the FileOrchestrationService variables
        """
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)

        self.modality = self.parameter_service.get_activity_config_value(GC.MODALITY_KEY, "")
        self.modality_format = self.parameter_service.get_activity_config_value(GC.MODALITY_FORMAT_KEY, "")
        
        self._max_archive_file_size_in_gb = int(self.parameter_service.get_activity_config_value(
            GC.MAX_ARCHIVE_FILE_SIZE_IN_GB_KEY,
            C.MAX_ARCHIVE_FILE_SIZE_IN_GB_DEFAULT
        ))
        self._max_thread_to_extract_archive_file = int(self.parameter_service.get_activity_config_value(
            GC.MAX_THREAD_TO_EXTRACT_ARCHIVE_FILE_KEY,
            C.MAX_THREAD_TO_EXTRACT_ARCHIVE_FILE_DEFAULT
        ))
        self._max_thread_to_move_file = int(self.parameter_service.get_activity_config_value(
            GC.MAX_THREAD_TO_MOVE_FILE_KEY,
            C.MAX_THREAD_TO_MOVE_FILE_DEFAULT
        ))
        
        try:
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name
            )
            
            self.file_orchestration_config_path = self.parameter_service.get_foundation_config_value(
                GC.FILE_MOVEMENT_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_file_orchestration_config_path(self.config_files_root_path)
            )
            
            self.file_orchestration_config = self.read_file_orchestration_config()
            
            lakehouse_files_base_path = FolderPath.get_fabric_files_path(
                                workspace_name=self.workspace_name,
                                one_lake_endpoint=self.one_lake_endpoint,
                                lakehouse_name=self.lakehouse_name)
            
            self.root_file_ingestion_path = self.parameter_service.get_activity_config_value(
                GC.ROOT_FILE_INGESTION_PATH_KEY,
                f"{lakehouse_files_base_path}/{C.INGEST_FOLDER}"
            )
            self.root_target_file_path = self.parameter_service.get_activity_config_value(
                GC.ROOT_TARGET_FILE_PATH_KEY,
                f"{lakehouse_files_base_path}/{C.PROCESS_FOLDER}"
            )
            
            self.modality_paths = self.get_modality_paths()
        
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise
    
    def read_file_orchestration_config(self) -> dict:
        """
        Reads the file orchestration configuration file.
        
        Returns:
            dict: The file orchestration configuration.
        """
        self._logger.info(
            f"{LC.READING_FILE_ORCHESTRATION_CONFIG_INFO_MSG.format(file_orchestration_config_path=self.file_orchestration_config_path)}"
        )
        config_content = self.spark.sparkContext.wholeTextFiles(
            self.file_orchestration_config_path
        ).collect()[0][1]
        config = json.loads(config_content)
        return config
    
    def get_modality_paths(self) -> list:
            """
            Gets the modality paths based on file orchestration config and modality and modality format.

            Returns:
                list: The modality paths and corresponding extensions
            """
            if self.modality is not None:
                modality_list = [modality.strip().lower() for modality in self.modality.split(',') if self.modality]
            if self.modality_format is not None:
                if len(modality_list) == 1:
                    modality_format_list = [modality_format.strip().lower() for modality_format in self.modality_format.split(',') if self.modality_format]
                else:
                    modality_format_list = []

            modality_paths = []
            for modality_name, modality_formats in self.file_orchestration_config.items():
                if len(modality_list) == 0 or modality_name.lower() in modality_list:
                    for modality_format in modality_formats:
                        if len(modality_format_list) == 0 or modality_format["format"].lower() in modality_format_list:
                            modality_paths.extend(self.create_modality_paths(modality_format, modality_name))
            return modality_paths        
        
    def create_modality_paths(self, modality_format: dict, modality_name : str) -> dict:
        """
        Creates list of modality path dictionaries based on the modality format configuration
        
        Args:
            modality_format (dict): The modality format configuration
        
        Returns:
            dict: The modality paths and corresponding extensions.
        """
        modality_paths = []
        modality_path = os.path.join(modality_format['folder_path'])
        source_file_path = os.path.join(self.root_file_ingestion_path, modality_path)
        target_file_path = os.path.join(self.root_target_file_path, modality_path)
        source_mount_name = os.path.join(C.SOURCE_MOUNT_NAME,modality_path)
        target_mount_name = os.path.join(C.TARGET_MOUNT_NAME,modality_path)
        file_extensions = modality_format["file_extensions"]
        
        modality_path_dict = {
            "source_file_path": source_file_path,
            "target_file_path": target_file_path,
            "source_mount_name": source_mount_name,
            "target_mount_name": target_mount_name,
            "file_extensions": list(file_extensions),
            "modality_name" : modality_name,
            "modality_path": modality_path
        }
        modality_paths.append(modality_path_dict)
        return modality_paths            

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.root_file_ingestion_path,
            sourceLakehouseName= self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetType=ExecutionDataType.file,
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetPath=self.root_target_file_path
        )
    
    def _get_internal_activity_name(self) -> str:
        return C.LOGGING_FILE_EXTRACTION_ORCHESTRATION
    
    def _execute(self, **kwargs) -> None:
        """
        Executes the Start function to kick start the FileOrchestrationService (file archive_extraction and movement)
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.        
        """
        self.start()
           
    def start(self) -> None:
        """
        This method extract ".zip" files and move supported file extensions into ready to process folder.
        Basically, organizes the modality data files in <yyyy>/<mm>/<dd> folder structure in the lakehouse.        """
        accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id()
        _file_orchestrator = FileOrchestrator(
                            self.spark, 
                            self._max_archive_file_size_in_gb,
                            self._max_thread_to_extract_archive_file,
                            self._max_thread_to_move_file,
                            self.mssparkutils_client)
                
        _file_orchestrator.start_process(self.modality_paths, 
                                        self.execution_metrics_collector,
                                        accumulator_activity_id)
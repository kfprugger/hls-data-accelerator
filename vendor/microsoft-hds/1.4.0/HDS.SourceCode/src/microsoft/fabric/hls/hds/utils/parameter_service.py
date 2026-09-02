# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.fabric_utils import FabricClientUtils
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC

class ParameterService:
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        admin_lakehouse_name: str,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None,
        inline_params: dict = None
    ):
        """Ingest vocabulary data into target tables

        Args:
            - spark (SparkSession): Spark Session
            - workspace_name (str): the workspace name
            - admin_lakehouse_name (str): The lakehouse name where the admin table is located
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """
        self.spark = spark
        self.workspace_name = workspace_name
        self.admin_lakehouse_name = admin_lakehouse_name
        self.one_lake_endpoint = one_lake_endpoint
        self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)
        self._logger = LoggingHelper.get_generic_logger(
            self.spark, self.__class__.__name__, GC.LOGGING_LEVEL)
        
        self.hds_config_path = f"{FolderPath.get_fabric_files_path(workspace_name=self.workspace_name, one_lake_endpoint=self.one_lake_endpoint, lakehouse_name=self.admin_lakehouse_name)}/{GC.PARAMETERS_CONFIGS_FOLDER}/{GC.PARAMETERS_DEPLOYMENT_CONFIG}"
        self.config_df = self.spark.read.json(self.hds_config_path, multiLine=True)
        self.inline_params = inline_params
        
    def get_foundation_config_value(self, key_name: str, default: str | bool | int | None = None, value_type: str = "string") -> str | bool | int:
        """Get the value of the key from the foundation config

        Args:
            key_name (str): The key name

        Returns:
            str | bool: The value of the key
        """
        try:
            if self.inline_params and key_name in self.inline_params:
                value = self.inline_params[key_name]
                self._logger.info(f"{LC.PARAMETER_USING_INLINE_PARAM_VALUE.format(key_name=key_name, value=value)}")
            else:
                value = self.config_df.select(f"activitiesGlobalParameters.{key_name}").collect()[0][0]
                self._logger.info(f"{LC.PARAMETER_USING_FOUNDATION_CONFIG_VALUE.format(key_name=key_name, value=value, config_path=self.hds_config_path)}")
            return Utils.cast_to_type(value, value_type)
        except Exception as e:
            self._logger.info(f"{LC.PARAMETER_ERROR_FOUNDATION_CONFIG_VALUE.format(key_name=key_name, config_path=self.hds_config_path)}")
            return default
            
    def get_activity_config_value(self, key_name: str, default: str | bool | int | None = None, value_type: str = "string") -> str | bool | int | None:
        """Get the value of the key from the activity config

        Args:
            key_name (str): The key name

        Returns:
            str | bool: The value of the key
        """
        try:
            if self.inline_params and key_name in self.inline_params:
                value = self.inline_params[key_name]
                self._logger.info(f"{LC.PARAMETER_USING_INLINE_PARAM_VALUE.format(key_name=key_name, value=value)}")
            else:
                notebook_id = self.mssparkutils_client.get_runtime_context().get('currentNotebookId')
                value = self.config_df.select(f"activities.{notebook_id}.parameters.{key_name}").collect()[0][0]
                self._logger.info(f"{LC.PARAMETER_USING_ACTIVITY_CONFIG_VALUE.format(key_name=key_name, value=value, config_path=self.hds_config_path)}")
            return Utils.cast_to_type(value, value_type)
        except Exception as e:
            self._logger.info(f"{LC.PARAMETER_ERROR_ACTIVITY_CONFIG_VALUE.format(key_name=key_name, config_path=self.hds_config_path)}")
            return default
        
    def update_spark_properties(self, activity_key_to_spark_property_dict: dict):
        
        # Check to see if the customer is setting properties in their environment
        # before attempting to update. Unable to discern whether the setting is default or explicit by
        # just looking at spark.conf.
        runtime_context = self.mssparkutils_client.get_runtime_context()
        environment_spark_properties = {}
        
        if "environmentId" in runtime_context and len(runtime_context["environmentId"]) > 0:
            environment_id = runtime_context["environmentId"]
            workspace_id = runtime_context["currentWorkspaceId"]
            environment_spark_properties = FabricClientUtils.get_environment_spark_properties(workspace_id, environment_id)

        # For each activity parameter to spark config mapping
        for activity_key, spark_property in activity_key_to_spark_property_dict.items():
            parameter_value = self.get_activity_config_value(activity_key) or self.get_foundation_config_value(activity_key)
            
            # If the parameter value is not none and the spark setting is not present in the environment settings
            if parameter_value and spark_property not in environment_spark_properties:
                self._logger.debug(f"Setting spark property: {spark_property} to {parameter_value}")
                self.spark.conf.set(spark_property, parameter_value)
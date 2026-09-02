# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with class for doing orchestrating flattening functionality
based on provided configuration values
"""

from typing import Dict, Union
from pyspark.sql import SparkSession, DataFrame, types as T, functions as F
from microsoft.fabric.hls.hds.flatten.core import FlattenCore as fc
from microsoft.fabric.hls.hds.utils.dataframe_utils import upsert_unique_to_delta_managed
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as C
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils

class FlattenManager:
    """
    Flatten manager class for orchestrating flattening functionality
    """

    def __init__(self,
                 spark: SparkSession,
                 workspace_name: str = None,
                 solution_name: str = None,
                 **kwargs):
        """
        Initialize FlattenManager instance

        Args:
            - spark: SparkSession - spark session to access resources/files/load dataframes
            - workspace_name: Name of the Fabric Workspace
            - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            - kwargs: dict - An optional dictionary of keyword arguments 
            to pass to the FlattenManager:
                - unique_columns: List[str] - The list of columns to use for unique index.
                - child_unique_columns: List[str] - The list of columns to append for
                unique index for child resources.
                - source_schema_root_dir: str - the root directory of where the source schema is located. Default is 
                "abfss://{workspace_name}@{one_lake_endpoint}/{solution_name}/DMHConfiguration/_internal/fhir4/schema/silver"
                - transformation_config_root_dir: str - the root directory of where the transformation config is located. Default is
                "abfss://{workspace_name}@{one_lake_endpoint}/{solution_name}/DMHConfiguration/_internal/fhir4/transformation/flatten" 
                - source_modified_on_column: Timestamp column of when the source data was last modified. 
                Used to identify the latest version of the source data. Default is 'meta_lastUpdated'
                - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
        """
        self.spark = spark
        self._logger = LoggingHelper.get_silveringestion_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)
        self.workspace_name = workspace_name
        self.solution_name = solution_name
        self.one_lake_endpoint = kwargs.get("one_lake_endpoint", GlobalConstants.DEFAULT_ONE_LAKE_ENDPOINT)
        self.unique_columns = kwargs.get(
            'unique_columns', C.DEFAULT_UNIQUE_RESOURCE_COLUMNS)

        self.child_unique_columns = kwargs.get(
            'child_unique_columns', C.CHILD_UNIQUE_COLUMN_ADDITION)
        
        self.source_modified_on_column = kwargs.get(
            'source_modified_on_column', GlobalConstants.DEFAULT_SOURCE_MODIFIED_ON_COLUMN)
        try:
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(workspace_name=self.workspace_name,
                                                                                one_lake_endpoint=self.one_lake_endpoint,
                                                                                solution_name=self.solution_name)
            self.source_schema_root_dir = kwargs.get(
                'source_schema_root_dir',
                f'{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GlobalConstants.DEFAULT_SILVER_LAKEHOUSE_NAME}',
            )
        
            self.transformation_config_root_dir = kwargs.get(
                'transformation_config_root_dir', 
                FolderPath.get_fabric_workload_files_flatten_config_root_folder_path(root_path=self.config_files_root_path),
            )
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

         # initialize flatten core
        self.core = fc(spark=self.spark, source_schema_root_dir=self.source_schema_root_dir, transformation_config_root_dir=self.transformation_config_root_dir)

    # pylint: disable=broad-exception-caught
    def execute_flatten_lib_and_save(self, df, config, target_tables_path, **kwargs):
        """
        Executes flattening of the given dataframe. The flattened output dataframes are then saved as 
        Delta tables using the `save_to_delta_table_managed` function, 
        with a unique index based on the 'id' and 'meta_lastUpdated' columns.

        Args:
            df: The `df` parameter is a  DataFrame that represents the resource to be
                processed. It can be None.
            config - dict: The `config` parameter is a dictionary that contains configuration settings for
                processing the resource. It includes information such as file paths, column mappings,
                data types, and other relevant settings
            target_tables_path - str: The parameter "target_lakehouse_name" is a string that represents
                the name of the target path where the processed resource will be saved.
        Keyword Args:
            collect_metrics_fn: Callable - A function to collect metrics for the delta table operation
        """
  
        resource_type = config[GlobalConstants.SILVER_CONFIG_NAME_KEY]
 
        try:
            self._logger.info(
                f"{LC.FLATTENING_RESOURCE_START_INFO_MSG} {resource_type}")
            result_dfs = self.core.process_dataframe(
                    config,
                    input_df=df)
            self._logger.info(
                f"{LC.FLATTENING_RESOURCE_END_INFO_MSG} {resource_type}")
        except Exception as handled_exception:
            self._logger.error(f"{LC.FLATTENING_RESOURCE_ERR_MSG} {resource_type}: {str(handled_exception)}")
            raise
        
        if result_dfs:
            for resource, res_df in result_dfs.items():
                self._logger.info(
                    f"{LC.SAVING_FLATTENED_RESOURCE_START_INFO_MSG} {resource}")
                try:
                    uniq_columns = self.unique_columns
                    # check if child level resource
                    if resource.lower() != resource_type.lower():
                        # we need to persist because delta reevaluate all tree which
                        # can lead to errors with already dropped columns
                        res_df.persist()
                        # for child we need to include "index" to unique columns
                        uniq_columns = uniq_columns+self.child_unique_columns

                    upsert_unique_to_delta_managed(spark_session=self.spark,
                                                   data_manager_logger=self._logger,
                                                   df_to_process=res_df,
                                                   unique_columns=uniq_columns,
                                                   delta_table_path=f"{target_tables_path}/{resource}",
                                                   source_modified_on_column=self.source_modified_on_column,
                                                   **kwargs
                                                   )
                    self._logger.info(
                    f"{LC.SAVING_FLATTENED_RESOURCE_END_INFO_MSG} {resource}")
                except Exception as handled_exception:
                    self._logger.error(
                        f"{LC.SAVING_FLATTENED_RESOURCE_ERR_MSG} {resource}: {str(handled_exception)}")
                    raise
                finally:
                    if 'res_df' in locals():
                        res_df.unpersist()
    
    def process_resource(self,
                         df: DataFrame | None, 
                         batchid: int | None, 
                         config: Dict, 
                         target_tables_path: str,
                         **kwargs
                        ):
        """
        The function processes a dataframe by flattening it using the given config and saving it to a target lakehouse.
        
        Args:
            df: The `df` parameter is a  DataFrame that represents the resource to be
                processed. It can be None.
            batchid: The `batchid` parameter is used to identify the foreachbatch of the dataframe in structured streaming
            config - dict: The `config` parameter is a dictionary that contains configuration settings for
                processing the resource. It includes information such as file paths, column mappings,
                data types, and other relevant settings
            target_tables_path - str: Represents the target path where the processed resource will be saved.
        Keyword Args:
            collect_metrics_fn: Callable - A function to collect metrics for the delta table operation
        """
        
        resource = config[GlobalConstants.SILVER_CONFIG_NAME_KEY]
        
        if df is None:
            self._logger.info(message=LC.FLATTENING_NONE_DATAFRAME.format(resource=resource))
            self.create_flatten_tables(config=config, target_tables_path=target_tables_path)
        else: 
            self.execute_flatten_lib_and_save(df, config, target_tables_path=target_tables_path, **kwargs)
    
    def create_flatten_tables(self, config: Dict, target_tables_path: str):
        
        """Create tables in target_lakehouse based on the given config
        Args:
            config - dict: The `config` parameter is a dictionary that contains configuration settings for
                processing the resource. It includes information such as file paths, column mappings,
                data types, and other relevant settings
            target_tables_path - str: The parameter "target_lakehouse_name" is a string that represents
                the name of the target path where the processed resource will be saved.
        """
        
        self._logger.info(f"{LC.FLATTEN_MANAGER_CREATE_FLATTEN_TABLES_STARTED_INFO_MSG}")
        df = self.create_empty_dataframe_for_resource(config=config)
        self.execute_flatten_lib_and_save(df, config, target_tables_path=target_tables_path)
        self._logger.info(f"{LC.FLATTEN_MANAGER_CREATE_FLATTEN_TABLES_COMPLETED_INFO_MSG}")

    def create_empty_dataframe_for_resource(self, config: dict) -> DataFrame:
        """
        Creates an empty dataframe for the given config 
        
        Args:
            - config: dict - The configuration for the resource. It contains the relative source schema path for the resource
        
        Return:
            - Dataframe - An empty dataframe with the given schema 
        """

        spark_schema = self.get_avro_schema(config)
        resource_type = config[GlobalConstants.SILVER_CONFIG_NAME_KEY]
        if spark_schema is None:
            raise ValueError(
                f"{LC.CREATING_TABLE_ERR_MSG} {resource_type}: {LC.SCHEMA_NOT_FOUND_ERR_MSG}")
                # create empty dataframe with schema
        return self.spark.createDataFrame([], spark_schema)\
                    .withColumn(GlobalConstants.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL, F.lit(None).cast(T.StringType()))\
                    .withColumn(GlobalConstants.DEFAULT_SILVER_FHIR_TABLE_MSFT_FILE_PATH_COL, F.lit(None).cast(T.StringType()))\
        
    def get_avro_schema(self, resource_config: Dict) -> Union[T.StructType,None]:
        """
        Returns avro schema for specified resource config

        Args:
        - resource_config: dict - The configuration for the resource. It contains the relative source schema path for the resource 
        """
        # find resource configuration
        if resource_config is not None:
            schema_conf = resource_config[C.MAIN_CONFIG_SECT_SCHEMA]
            schema_path = schema_conf[C.SCHEMA_CONFIG_ATTR_PATH]
            # loading file(s) specified in path with schema specified
            schema_content = Utils.load_config_file(self.spark, f'{self.source_schema_root_dir}/{schema_path}')
            return Utils.load_schema_from_avro_schema(self.spark, schema_content)
        return None
          
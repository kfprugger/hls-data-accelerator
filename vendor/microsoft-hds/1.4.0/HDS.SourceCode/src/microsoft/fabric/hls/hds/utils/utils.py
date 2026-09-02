from datetime import datetime
import re
import json
import os
from typing import Any, Callable, List, Tuple
from requests.models import Response
from pyspark.sql import SparkSession, types as T
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.mssparkutils_client import MSSparkUtilsClient

def get_suffix(stringValue: str,prefix: str) -> str:
    if(stringValue.startswith(prefix)):
        return stringValue[len(prefix):].lstrip()
    return None

class Utils:
    @staticmethod
    def mount_and_create(mount_path: str, mount_location: str, mssparkutils_client: MSSparkUtilsClientBase) -> str:
        """
        This method mounts to the given mount_path and creates it if it does not exist, then returns the mount local path
        
        Args: 
            mount_path : Path to mount to
            mount_location: Location to mount
            mssparkutils_client: mssparkutils client
        """
        mount_options = {
            "fileCacheTimeout": GlobalConstants.MOUNT_FILE_CACHE_TIMEOUT,
            "timeout": GlobalConstants.MOUNT_TIMEOUT
        }
        try:
            mssparkutils_client.fs_mount(mount_path, mount_location, mount_options)
            return mssparkutils_client.fs_get_mount_path(mount_location)
        except Exception as e:
            mssparkutils_client.fs_mkdirs(mount_path)
            mssparkutils_client.fs_mount(mount_path, mount_location, mount_options)
            return mssparkutils_client.fs_get_mount_path(mount_location)

    @staticmethod
    def to_bool(val: str | bool) -> bool:
        """
        This method is used to typecast a value to boolean
        
        Args: 
            val : the value which need to be typecasted
        
        Returns:
            bool : the typcasted boolean value
        """
        
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() == 'true'
        
        raise ValueError(LoggingConstants.BOOLEAN_CONVERSION_FAILED_MSG(value=val))
    
    @staticmethod
    def cast_to_type(val: str | bool | int, type: str = "string") -> str | bool | int:
        """
        This method is used to typecast a value to a given type
        
        Args: 
            val: the value which need to be typecasted
            type: the type to which the value will be cast
        
        Returns:
            bool | str | int : the typcasted boolean value
        """
        try:
            if type == "string":
                return str(val)
            elif type == "int":
                return int(val)
            elif type == "bool":
                return Utils.to_bool(val)
        except Exception as e:
            raise ValueError(LoggingConstants.CASTING_FAILED_EXCEPTION_MSG.format(value=val, type=type, exception=e))
        raise ValueError(LoggingConstants.CASTING_UNSUPPORTED_MSG.format(value=val, type=type))
    
    @staticmethod
    def validate_required_parameters(params: dict) -> None:
        """
        Validate that no required parameters (params) are None

        Arguments:
        - params: dictionary of parameter values
        """
        none_keys = [key for key, value in params.items() if value is None]
        if none_keys:
            raise ValueError(LoggingConstants.REQUIRED_PARAMS_MISSING_ERR_MSG.format(missing_params=none_keys))
    
    @staticmethod
    def load_config_file(spark: SparkSession, config_path: str) -> str:
        """
        Load file content specified in config_path

        Arguments:
        - spark: SparkSession object
        - config_path: the path to the configuration file
        
        Returns:
            str: the content of the file as string
        """
        try:
            schema_content = spark.sparkContext.wholeTextFiles(config_path).first()[1]
            return schema_content
        except Exception as e:
            raise RuntimeError(f"Failed to load config file from {config_path}: {str(e)}")
    
    @staticmethod
    def load_schema_from_avro_schema(spark: SparkSession, avro_schema: str) -> T.StructType:
        """
        Transform AVRO schema to spark internal StructType

        The function requires spark avro library (spark-avro_2.12-3.2.1.jar) 
        to be installed/run with spark
        
        Argument:
        - spark: SparkSession - spark session to access schemaconverter
        - avro_schema: str - the string representation of avro schema
        
        Returns:
            T.StructType - the avro schema as StructType
        """
        # It uses SchemaConverters to convert avro schema to StructType
        # Other option (without protected methods) would be construction like below:
        # create empty dataframe using avro schema provided:
        # df_schema_only = spark.read.format("avro").option("avroSchema", avro_schema).load()
        # df_schema_only.schema - contains suitable schema for loading other file
        
        java_schema_type = spark.\
            _jvm.org.apache.spark.sql.avro.SchemaConverters.toSqlType(  # type: ignore
            spark._jvm.org.apache.avro.Schema.Parser().parse(avro_schema)  # type: ignore
            )
        json_schema = json.loads(java_schema_type.dataType().json())
        return T.StructType.fromJson(json_schema)
    
    @staticmethod
    def load_config(spark: SparkSession, config_path: str):
        """
        Load main configuration and initialize internal list with supported resources
        """
        config_content = spark.sparkContext.wholeTextFiles(
            config_path).collect()[0][1]

        main_config_json = json.loads(str(config_content))
        return {
            entry[GlobalConstants.SILVER_CONFIG_NAME_KEY]: entry
            for entry in main_config_json[
                GlobalConstants.SILVER_CONFIG_RESOURCES_KEY
            ]
        }
        
    @staticmethod
    def set_delta_table_retention_properties(spark: SparkSession, table_path: str, 
                                            log_retention_duration: str = None,
                                            deleted_file_retention_duration: str = None) -> None:
        """
        Sets the Delta table retention properties for log and deleted file retention.
        Only updates properties if they differ from the desired values.
        
        Args:
            table_path (str): The path to the Delta table
            log_retention_duration (str, optional): Log retention duration. If None, uses configured value.
            deleted_file_retention_duration (str, optional): Deleted file retention duration. If None, uses configured value.
        """
        # Use configured values if not provided as parameters
        log_retention = log_retention_duration 
        deleted_file_retention = deleted_file_retention_duration 
               
        properties_df = spark.sql(f"SHOW TBLPROPERTIES delta.`{table_path}`")
        current_properties = {row['key']: row['value'] for row in properties_df.collect()}
        
        # Define desired properties
        desired_properties = {
            GlobalConstants.SPARK_DELTA_LOG_RETENTION_DURATION_PROPERTY: log_retention,
            GlobalConstants.SPARK_DELTA_DELETED_FILE_RETENTION_DURATION_PROPERTY: deleted_file_retention
        }
        
        # Filter to only properties that need updating
        properties_to_update = {
            key: value for key, value in desired_properties.items()
            if current_properties.get(key) != value
        }
                    
        # Only update if there are differences
        if properties_to_update:
            properties_list = [f"'{key}' = '{value}'" for key, value in properties_to_update.items()]
            properties_string = ', '.join(properties_list)
            
        spark.sql(f"""
            ALTER TABLE delta.`{table_path}`
            SET TBLPROPERTIES ({properties_string})
        """)
  
    @staticmethod
    def is_files_in_path(spark: SparkSession, path: str) -> bool:
        """Checks for any files in the path

        Args:
            spark (SparkSession): Spark Session
            path (str): The file path to check

        Returns:
            bool: True if there are files in the path, false otherwise
        """
        hpath = spark._jvm.org.apache.hadoop.fs.Path(path)
        fs = hpath.getFileSystem(spark._jsc.hadoopConfiguration())
        return len(fs.globStatus(hpath)) > 0
    
    @staticmethod
    def path_exists(path: str, mssparkutils_client: MSSparkUtilsClientBase) -> bool:
        """
        This method is used to check if the path exists
        Args:
            path (str): the file path to check
        Returns:
            bool: True if path exists and false otherwise
        """        
        # mssparkutils_client.fs_exists(path)
        try:
            mssparkutils_client.fs_ls(path)
        except Exception as e:
            return False
        return True
    
    @staticmethod
    def file_exists(path: str, mssparkutils_client: MSSparkUtilsClientBase) -> bool:
        """
        This method is used to check if the file exists
        Args:
            path (str): the file path to check
        Returns:
            bool: True if file exists and false otherwise
        """        
        try:
            return mssparkutils_client.fs_exists(path)
        except Exception as e:
            return False
    
    @staticmethod
    def list_files(directory_to_iterate: str, mssparkutils_client: MSSparkUtilsClientBase):  
        """
        This method is used to list all the files from the specified folder
        """      
        files = mssparkutils_client.fs_ls(directory_to_iterate)
        return files
    
    @staticmethod 
    def create_folder(folderpath: str, mssparkutils_client: MSSparkUtilsClientBase):  
        """
        This method is used to create folders in the specified folder
        """      
        mssparkutils_client.fs_mkdirs(folderpath)  
    
    @staticmethod 
    def join_path(*path_list: str) -> str :        
        """
        This method is used to join all the input path and return the final path
        """      
        return  os.path.join(*path_list)   
    
    @staticmethod 
    def move_files(from_path: str, to_path: str, files: list, mssparkutils_client: MSSparkUtilsClientBase):
        """
        This method is used to move files from one path to another

        Args:
            from_path (str): the path from where files needs to be moved
            to_path (str): the path to which files needs to be moved
            files (list): list of files to be moved
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
        """        
        
        for file in files:
            mssparkutils_client.fs_mv(os.path.join(from_path, file), os.path.join(to_path, file) )

    @staticmethod  
    def move_folders_files(from_path: str, to_path: str, mssparkutils_client: MSSparkUtilsClientBase):
        """
        Move folders and files from one path to another using the provided MSSparkUtilsClientBase object.

        Args:
            from_path (str): The source path from where the folders and files will be moved.
            to_path (str): The destination path where the folders and files will be moved to.
            mssparkutils_client (MSSparkUtilsClientBase): The MSSparkUtilsClientBase object used to perform the move operation.

        Returns:
            None
        """
        if not mssparkutils_client.fs_exists(from_path):
            raise FileNotFoundError(f"Source path {from_path} does not exist.")

        mssparkutils_client.fs_mv(from_path, to_path)
            
    @staticmethod
    def get_file_names(dir_path: str, mssparkutils_client: MSSparkUtilsClientBase) -> list:
        """
        This method is used to get all the file names present inside a directory

        Args:
            dir_path (str): directory path from where file names are to be fetched
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
        Returns:
            list: list of file names
        """ 
        return [file.name for file in mssparkutils_client.fs_ls(dir_path)]
    
    @staticmethod
    def remove_dir(dir_path: str, mssparkutils_client: MSSparkUtilsClientBase, recursive : bool = True):
        """
        This method is used to remove a directory
        Args:
            dir_path (str): directory path to be removed
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
            recursive (bool): set the last parameter as True to remove all files and directories recursively
        """        

        mssparkutils_client.fs_rm(dir_path, recursive)
    
    @staticmethod
    def is_guid(identifier: str) -> bool:
        """
        Validates if the identifier is a GUID.
        """
        guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        return bool(guid_pattern.match(identifier))
    
    @staticmethod
    def is_valid_artifact_identifiers(workspace_identifier: str, artifact_identifier) -> bool:
        """
        Validates to ensure there is no mismatch in Identifiers. They should both be artifact GUIDs or Names.
        """
        return Utils.is_guid(identifier=workspace_identifier) == Utils.is_guid(identifier=artifact_identifier)
    
    @staticmethod
    def get_app_insights_instrumentation_key(spark: SparkSession, mssparkutils_client: MSSparkUtilsClientBase):
        """
        Parses the app insights connection string and returns the instrumentation key
                
        Args:
            spark (SparkSession): Spark Session
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
        """
        app_insights_connection_string = Utils.get_app_insights_connection_string(spark, mssparkutils_client)
        if not app_insights_connection_string:
            return None
        app_insights_connection_string_components = app_insights_connection_string.split(";")
        for component in app_insights_connection_string_components:
            key, value = component.split("=")
            if key == 'InstrumentationKey':
                return component
        return None
    @staticmethod
    def get_app_insights_connection_string(spark: SparkSession, mssparkutils_client: MSSparkUtilsClientBase):
        """
        Retrieves app insights connection string from Key Vault. Returns none if the secret for app insights is not found as it is optional.
        
        Args:
            spark (SparkSession): Spark Session
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
        """
        try:
            return Utils.get_key_vault_secret(spark, GlobalConstants.APPINSIGHTS_INGESTION_ENDPOINT_KEY_SECRET_NAME, mssparkutils_client)
        except Exception:
            return None
    
    @staticmethod
    def set_dtt_app_insights_connection_string(spark: SparkSession, mssparkutils_client: MSSparkUtilsClientBase, on_set_fn: Callable[[], None] = None):
        """
        Sets the DTT's application insights instrumentation key and ingestion endpoint to spark configuration
        
        Args:
            spark (SparkSession): Spark Session
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
            on_set_fn: Callable[[], None]: A callback when the connection string is set
        """
        spark_dtt_app_insights_connection_string = spark.conf.get(GlobalConstants.SPARK_DTT_APP_INSIGHTS_CONNECTION_STRING, None)
        
        if spark_dtt_app_insights_connection_string is None:
            app_insights_connection_string = Utils.get_app_insights_connection_string(
                spark=spark,
                mssparkutils_client=mssparkutils_client,
            )

            if app_insights_connection_string:
                spark.conf.set(
                    GlobalConstants.SPARK_DTT_APP_INSIGHTS_CONNECTION_STRING,
                    app_insights_connection_string,
                )
                if on_set_fn is not None:
                    on_set_fn()

    @staticmethod
    def get_key_vault_secret(spark: SparkSession, kv_secret_name: str, mssparkutils_client: MSSparkUtilsClientBase):
        """
        Returns Key Vault secret value given the key that stored in the key vault
        
        Args:
            spark (SparkSession): Spark Session
            key_secret_name (str): The name of the secret
            mssparkutils_client (MSSparkUtilsClientBase): mssparkutils client
        """

        kv_name = spark.conf.get(GlobalConstants.SPARK_KEY_VAULT_NAME, None)
        if not kv_name:
            return None
        
        kv_uri = FolderPath.get_key_vault_uri(kv_name)

        kv_secret_value = mssparkutils_client.credentials_getSecret(kv_uri, kv_secret_name)
        
        return kv_secret_value
    
    @staticmethod
    def set_key_vault_name(spark: SparkSession, kv_name: str | None):
        """
        Sets the key vault name to the spark configuration
        
        Args:
            spark (SparkSession): Spark Session
            kv_name (str): The name of the key vault
        """
        if kv_name:
            spark.conf.set(GlobalConstants.SPARK_KEY_VAULT_NAME, kv_name)
    
    @staticmethod
    def get_enable_hds_logs_config(spark: SparkSession) -> bool:
        """
        Retrieves the 'enable_hds_logs' configuration value from the Spark session and parses it to a boolean.

        Args:
            spark (SparkSession): The Spark Session from which to retrieve the configuration.

        Returns:
            bool: The value of the 'enable_hds_logs' configuration as a boolean. Defaults to True if not set or invalid.
        """
        
        enable_hds_logs = spark.conf.get(GlobalConstants.SPARK_ENABLE_HDS_LOGS, "True")

        return enable_hds_logs.lower() in ("true", "1")
    
    @staticmethod
    def get_error_message(response: Response) -> str:
        """
        Retrieves error message from response object
        
        Args:
            response (Response): response object from http call

        Returns:
            str: The error message (output) from the http response
        """
        try:
            response = response.json()
            output_str = response.get("output")
            if (output_str):
                return output_str
            return LoggingConstants.FHIREXPORTSERVICE_NO_ERROR_MSG
        except Exception:
            return LoggingConstants.FHIREXPORTSERVICE_UNABLE_TO_PARSE_ERR_MSG
        
    @staticmethod
    def get_mssparkutils_client(mssparkutils_client: MSSparkUtilsClientBase | None):
        """
        Gets an instance of a MSSparkUtilsClientBase
        
        Args:
            mssparkutils_client: MSSparkUtilsClientBase | None, an optional client

        Returns:
            mssparkutils_client: MSSparkUtilsClientBase | None, a new or existing client
        """
        if mssparkutils_client is None:
            return MSSparkUtilsClient()
        return mssparkutils_client
    
    @staticmethod
    def split(items: List[Any], predicate: Callable[[List[Any]], bool]):
        """
        Split a list based on a boolean predicate
        
        Args:
            items: A list of items
            predicate: A predicate for evaluating each item

        Returns:
            A tuple of lists, the first list contains items that satisfy the predicate,
            the second list contains items that do not satisfy the predicate
        """
        pred_true = []
        pred_false = []

        for item in items:
            if(predicate(item)):
                pred_true.append(item)
            else:
                pred_false.append(item)

        return pred_true, pred_false
    
    @staticmethod
    def get_root_path_from_source_path_pattern(source_path_pattern: str) -> str:
        """
        Get the root path from the source path pattern
        
        Args:
            source_path_pattern: The source path pattern
        
        Returns:
            str: The root path
        """
        parts = source_path_pattern.split("/")
        if len(parts) > 6:
            return "/".join(parts[:6])
        return source_path_pattern

    @staticmethod
    def get_target_anchor_tables_from_dtt_config(spark: SparkSession, dtt_config_path: str) -> List[str]:
        """
        Reads the given JSON file using Spark and returns a list of unique target table names.
        It extracts the "targetAnchorTables" field from each enabled source table in the JSON.

        Args:
            spark (SparkSession): The Spark session.
            dtt_config_path (str): Path to the dtt adapter JSON configuration file.

        Returns:
            List[str]: A list of unique table names found in targetAnchorTables of enabled source tables.
        """
        target_tables = []
        try:
            # Use the multiLine option to properly read multi-line JSON files.
            df = spark.read.option("multiline", "true").json(str(dtt_config_path))
            rows = df.collect()
            if not rows:
                return target_tables
            
            # Convert the first row to a dictionary recursively.
            data = rows[0].asDict(recursive=True)
            for source_table in data.get("sourceTables", []):
                if source_table.get("enabled", False):
                    for anchor in source_table.get("targetAnchorTables", []):
                        table_name = anchor.get("tableName")
                        if table_name:
                            target_tables.append(table_name)
        except Exception as error:
            raise RuntimeError(f"Error reading dtt target anchor tables from {dtt_config_path}: {error}")
            
        # Remove duplicates while preserving order.
        unique_target_tables = list(dict.fromkeys(target_tables))
        return unique_target_tables
    
class FolderPath:
    
    @staticmethod
    def get_fabric_tables_path(workspace_name: str, one_lake_endpoint: str, lakehouse_name: str) -> str:
        if not Utils.is_valid_artifact_identifiers(workspace_identifier=workspace_name, artifact_identifier=lakehouse_name):
            raise ValueError(LoggingConstants.FABRIC_MISMATCHED_IDENTIFIERS_ERR_MSG.format(workspace_name=workspace_name, lakehouse_name=lakehouse_name))
        
        suffix = '' if Utils.is_guid(lakehouse_name) else '.Lakehouse'
        return f'abfss://{workspace_name}@{one_lake_endpoint}/{lakehouse_name}{suffix}/Tables'
    
    @staticmethod
    def get_fabric_files_path(workspace_name: str, one_lake_endpoint: str, lakehouse_name: str) -> str:
        if not Utils.is_valid_artifact_identifiers(workspace_identifier=workspace_name, artifact_identifier=lakehouse_name):
            raise ValueError(LoggingConstants.FABRIC_MISMATCHED_IDENTIFIERS_ERR_MSG.format(workspace_name=workspace_name, lakehouse_name=lakehouse_name))
        
        suffix = '' if Utils.is_guid(lakehouse_name) else '.Lakehouse'
        return f'abfss://{workspace_name}@{one_lake_endpoint}/{lakehouse_name}{suffix}/Files'
    
    @staticmethod
    def get_fabric_workload_files_root_path(workspace_name: str, one_lake_endpoint: str, solution_name: str) -> str:
        if not Utils.is_valid_artifact_identifiers(workspace_identifier=workspace_name, artifact_identifier=solution_name.split('/')[0]):
            raise ValueError(LoggingConstants.WORKLOAD_MISMATCHED_IDENTIFIERS_ERR_MSG.format(workspace_name=workspace_name, solution_name=solution_name))
        return f'abfss://{workspace_name}@{one_lake_endpoint}/{solution_name}'
    
    @staticmethod
    def get_fabric_vocab_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_OMOP_VOCABULARY_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_checkpoint_folder_path(root_path: str, checkpoint_folder_name: str) -> str:
        return f"{root_path}/{GlobalConstants.DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{checkpoint_folder_name}"
    
    @staticmethod
    def get_fabric_workload_cma_files_checkpoint_folder_path(root_path: str, checkpoint_folder_name: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_CHKPOINT_FOLDER}/{checkpoint_folder_name}"
    
    @staticmethod
    def get_fabric_workload_files_schema_root_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SCHEMA_PATH}"
        
    @staticmethod
    def get_fabric_workload_files_validation_config_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_VALIDATION_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_file_orchestration_config_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_FILE_ORCHESTRATION_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_flatten_config_root_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_FLATTEN_CONFIG_DIR}"
    
    @staticmethod
    def get_fabric_workload_files_flatten_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_FLATTEN_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_omop_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_OMOP_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_cma_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_CONFIG_CLINICAL_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_omop_scripts_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_OMOP_SCRIPTS_PATH}"
    
    @staticmethod
    def get_fabric_workload_dtt_file_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DTT_FILE_PATH}"
    
    @staticmethod
    def get_fabric_workload_cma_dtt_file_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_DTT_FILE_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_rmt_mapping_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_RMT_MAPPING_FOLDER_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_cma_rmt_mapping_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_RMT_MAPPING_FOLDER_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_poa_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_PATIENT_OUTREACH_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_cma_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_dmf_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DMF_CONFIG_PATH}"
    
    @staticmethod
    def get_cma_dmf_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_DMF_CONFIG_PATH}"
    
    @staticmethod
    def get_rmt_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_RMT_CONFIG_PATH}"

    @staticmethod
    def get_key_vault_uri(kv_name: str) -> str:
        return f'https://{kv_name}.vault.azure.net/'
    
    @staticmethod
    def get_dmf_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DMF_CONFIG_PATH}"
    
    @staticmethod
    def get_rmt_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_RMT_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_idm_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_idm_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_idm_dmf_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_DMF_CONFIG_PATH}"
    
    @staticmethod
    def get_idm_rmt_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_RMT_CONFIG_PATH}"
    
    @staticmethod
    def get_idm_environment_configuration_file(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_ENV_CONFIG_PATH}"
    
    @staticmethod
    def get_idm_fabric_workload_files_rmt_mapping_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_IDM_RMT_REFERENCE_DATA_FOLDER}"
    
    @staticmethod
    def get_fabric_workload_files_sdoh_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_sdoh_dtt_secondary_lake_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_DTT_SECONDARY_LAKE_PATH}"
    
    @staticmethod
    def get_sdoh_dmf_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_DMF_CONFIG_PATH}"
    
    @staticmethod
    def get_sdoh_rmt_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_RMT_CONFIG_PATH}"
    
    @staticmethod
    def get_sdoh_environment_configuration_file(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_ENV_CONFIG_PATH}"
    
    @staticmethod
    def get_sdoh_fabric_workload_files_rmt_mapping_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_RMT_REFERENCE_DATA_FOLDER}"
    
    @staticmethod
    def get_sdoh_dmf_adapter_configuration_files(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_SDOH_DMF_ADAPTER_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_cma_gold_config_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_CM_ANALYTICS_CONFIG_PATH}"
    
    @staticmethod
    def get_fabric_workload_files_ai_enrichment_resource_types_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_AI_ENRICHMENT_RESOURCES_PATH}"
     

    @staticmethod
    def get_fabric_workload_files_dax_resources_folder_path(root_path: str) -> str:
        return f"{root_path}/{GlobalConstants.DEFAULT_DAX_RESOURCES_PATH}"

import json
import re
from delta import DeltaTable
from pyspark import StorageLevel
from pyspark.sql import SparkSession, DataFrame, types as T, Column
from pyspark.sql.functions import *
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.orchestrate.file_movement.file_compressor import FileCompressor
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase

class ValidationService:
    """
    Class for applying validations on dataframes
    
    """
    def __init__(self,
                 spark: SparkSession,
                 workspace_name: str,
                 validation_config_path: str,
                 business_events_lakehouse_name: str,
                 business_events_schema_path: str,
                 validation_config_key: str,
                 mssparkutils_client: MSSparkUtilsClientBase = None,
                 **kwargs) -> None:
        """_summary_

        Args:
            - spark (SparkSession): spark session
            - workspace_name (str): the workspace name
            - validation_config_path (str): The path to the validation config file
            - business_events_lakehouse_name (str): The lakehouse name where the validation table is located
            - business_events_schema_path (str): The path to the schema for the business events table
            - validation_config_key (str): The key in the validation configuration to be applied
            - **kwargs (dict): An optional dictionary that customer can use to configure the validation service
                - business_events_table_path (str): The path to the business events table. Default will be `abfss://{workspace_name}@{one_lake_endpoint}/{business_events_lakehouse_name}.Lakehouse/Tables`
                - one_lake_endpoint (str): The one lake endpoint, Default is `onelake.dfs.fabric.microsoft.com`
                - source_file_path (str): The path to the source file (can be a column or a literal)
                - source_table_name (str): The source table name
                - source_lakehouse_name (str): The source lakehouse name
                - target_file_path (str): The path to the target file
                - target_table_name (str): The target table name
                - target_lakehouse_name (str): The target lakehouse name
                - record_identifier_source (str) : The source col/jsonpath of the record identifier
                - run_id (str): The run id for the execution
                - activity_name (str): The activity name
                - move_failed_files_enabled (bool): Flag to move failed files to a 'Failed' folder. Default is False, else True
                - source_root_path (str): The source root path for the file. Used only for failed file movement
                - failed_root_path (str): The failed root path for the file. Used only for failed file movement
                - modality_name (str): the name of the modality as used in the file movement config file. This is used for partial file movement only.
        """
        self.spark: SparkSession = spark
        self.workspace_name = workspace_name
        self.validation_config_path = validation_config_path
        self.business_events_lakehouse_name = business_events_lakehouse_name
        self.business_events_schema_path = business_events_schema_path
        self.validation_config_key = validation_config_key
        self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client)
        
        self.one_lake_endpoint = kwargs.get("one_lake_endpoint", GC.DEFAULT_ONE_LAKE_ENDPOINT)
        self.move_failed_files_enabled = kwargs.get("move_failed_files_enabled", False)
        self.source_root_path = kwargs.get("source_root_path")
        self.failed_root_path = kwargs.get("failed_root_path")
        self._logger = LoggingHelper.get_generic_logger(
            self.spark, self.__class__.__name__, GC.LOGGING_LEVEL)
        
        self.business_events_table_path = kwargs.get(
            "business_events_table_path",
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.business_events_lakehouse_name)
        )
        
        # Optional kwargs for validation dataframe
        self.source_file_path = kwargs.get("source_file_path")
        self.source_table_name = kwargs.get("source_table_name")
        self.source_lakehouse_name = kwargs.get("source_lakehouse_name")
        self.activity_name = kwargs.get("activity_name")
        self.target_file_path = kwargs.get("target_file_path")
        self.target_table_name = kwargs.get("target_table_name")
        self.target_lakehouse_name = kwargs.get("target_lakehouse_name")
        self.run_id = kwargs.get("run_id")
        self.source_mount_path = None
        self.target_mount_path = None
        # Optional kwargs for partial file movement
        self.partial_file_movement_enabled = kwargs.get("partial_file_movement_enabled", False)
        self.modality_name =  kwargs.get("modality_name")
        self.data_column_name = kwargs.get("data_column_name")
        
        self.validation_config = self.read_validation_config()
        self.create_business_events_table_if_not_exists()
        
        if self.move_failed_files_enabled and self.source_root_path and self.failed_root_path and self.source_file_path:            
            self.source_mount_path = Utils.mount_and_create(self.source_root_path, GC.VALIDATION_FAILED_FILES_SOURCE_MOUNT_LOCATION, self.mssparkutils_client)
            self.target_mount_path = Utils.mount_and_create(self.failed_root_path, GC.VALIDATION_FAILED_FILES_TARGET_MOUNT_LOCATION, self.mssparkutils_client)
            self.file_compressor = FileCompressor(
                self.spark,
                self.source_root_path,
                self.source_mount_path,
                self.failed_root_path,
                self.target_mount_path
            )
    
    def load_business_events_schema(self) -> T.StructType:
        """
        Summary:
            Load business events schema
            
        Args:
            schema_fullpath (str): the path to the schema
        """
        self._logger.info(
            f"{LC.LOADING_BUSINESS_EVENTS_SCHEMA_INFO_MSG.format(business_events_schema_path=self.business_events_schema_path)}"
        )
        schema_content = self.spark.sparkContext.wholeTextFiles(
            self.business_events_schema_path
        ).collect()[0][1]
        parsed_schema = self.spark._jvm.org.apache.avro.Schema.Parser().parse(
            str(schema_content)
        )

        java_schema_type = (
            self.spark._jvm.org.apache.spark.sql.avro.SchemaConverters.toSqlType(
                parsed_schema
            )
        )  # type: ignore

        json_schema = json.loads(java_schema_type.dataType().json())
        
        return T.StructType.fromJson(json_schema)
        
    def create_business_events_table_if_not_exists(self) -> None:
        """
        Summary:
            Create business events table if not exists
        """
        business_events_table_path = f"{self.business_events_table_path}/{GC.BUSINESS_EVENTS_TABLE}"
        if not DeltaTable.isDeltaTable(self.spark, business_events_table_path):
            self._logger.debug(
                f"{LC.CREATING_BUSINESS_EVENTS_TABLE_INFO_MSG.format(delta_table_path=business_events_table_path)}"
            )
            empty_df = self.spark.createDataFrame([], schema=self.load_business_events_schema())
            append_to_delta_table_using_path(
                df_to_process=empty_df,
                delta_table_path=business_events_table_path,
                logger=self._logger
            )
        
    def read_validation_config(self) -> dict:
        """
        Summary:
            read validation configuration file
        
        Returns:
            dict: validation configuration dictionary
        """
        if self.mssparkutils_client.fs_exists(self.validation_config_path):
            self._logger.debug(
                f"{LC.READING_VALIDATION_CONFIG_INFO_MSG.format(validation_config_path=self.validation_config_path)}"
            )
            config_content = self.spark.sparkContext.wholeTextFiles(
                self.validation_config_path
            ).collect()[0][1]
            config = json.loads(config_content)
            return config.get(self.validation_config_key)
        else:
            self._logger.info(
                f"{LC.VALIDATION_CONFIG_DOES_NOT_EXIST_MSG.format(validation_config_path=self.validation_config_path)}"
            )
            return {}
    
    @staticmethod
    def nested_field_exists(df: DataFrame, field_path: str, delimiter: str = ".") -> bool:
        schema = df.schema
        fields = field_path.split(delimiter)
        current_schema = schema
        for field in fields:
            if isinstance(current_schema, StructType):
                field_names = [f.name for f in current_schema.fields]
                if field in field_names:
                    current_schema = current_schema[field_names.index(field)].dataType
                else:
                    return False
            else:
                return False
        return True
    
    def generate_exists_expression(self, df: DataFrame, validation: dict) -> Column:
        """
        Summary:
            read validation configuration file
            
        Args:
            validation (dict): validation configuration dict for a specific validation
        
        Returns:
            Column: Column expression for the validation rule
        """
        if self.nested_field_exists(df, validation["attributeName"]):
            if validation.get("jsonpath") is not None:
                return expr(f"get_json_object({validation['attributeName']}, '{validation['jsonpath']}') IS NULL")
            else:
                return col(validation["attributeName"]).isNull()
        return lit(False)
    
    def generate_validation_rules(self, df: DataFrame, severity: str, validations: list, table_name: str) -> list:
        """
        Summary:
            read validation configuration file
            
        Args:
            - severity (str): severity of the validation rules to be retrieved from validation configuration
            - validations (dict): dictionary representation of validation configuration
            - table_name(str): table name to be validated
        
        Returns:
            list: list of Column expressions for given severity
        """
        validation_expressions = []
        for validation in validations:
            if validation["severity"] == severity and ((table_name in validation["tableName"]) or ("*" in validation["tableName"])):
                if validation['validationType'] == "exists":
                    validation_expression = self.generate_exists_expression(df, validation)
                    validation_expressions.append((validation["validationMessage"], validation_expression))
        return validation_expressions
    
    def process_col_value(self, input_value: str, df: DataFrame, json_path: str = None) -> Column:
        """
        Process the input value (either column name or literal) and update the DataFrame.
        If input_value is a column name, retrieve the values from that column using jsonpath if applicable.
        If input_value is a literal, insert it into the target_column.
        """
        if input_value in df.columns:
            # Input value is a column name
            if json_path:
                return get_json_object(col(input_value), json_path)
            else:
                return col(input_value)
        else:
            # Input value is a literal
            return lit(input_value)
    
    def create_validation_df(self, df: DataFrame, validation_col_name: str, severity: str):
        """
        Create validation dataframe to be written to validation table

        Args:
            df (DataFrame): Input dataframe.
            validation_column (str): Name of the new JSON column.
            severity (str): severity for the dataframe

        Returns:
            DataFrame: New dataframe to be written to validation table
        """
        record_identifier = self.validation_config.get("recordIdentifier")
        record_identifier_source = json.dumps(record_identifier)
        
        df = df \
            .withColumn(GC.BE_RECORD_IDENTIFIER_COL, self.process_col_value(record_identifier["attributeName"], df, record_identifier.get("jsonpath"))) \
            .withColumn(GC.BE_SOURCE_FILE_PATH_COL, self.process_col_value(self.source_file_path, df))

        df = df.select(
            expr("uuid()").alias(GC.BE_ID_COL),
            current_timestamp().alias(GC.BE_EVENT_DATE_TIME_COL),
            lit(True).alias(GC.BE_ACTIVE_COL),
            lit(GC.VALIDATION_EVENT_TYPE).alias(GC.BE_EVENT_TYPE_COL),
            lit(self.activity_name).alias(GC.BE_ACTIVITY_NAME_COL),
            lit(severity).alias(GC.BE_SEVERITY_COL),
            lit(self.source_table_name).alias(GC.BE_SOURCE_TABLE_NAME_COL),
            lit(self.target_table_name).alias(GC.BE_TARGET_TABLE_NAME_COL),
            lit(self.run_id).alias(GC.BE_RUN_ID_COL), 
            lit(self.target_file_path).alias(GC.BE_TARGET_FILE_PATH_COL),
            lit(record_identifier_source).alias(GC.BE_RECORD_IDENTIFIER_SOURCE_COL),
            lit(self.source_lakehouse_name).alias(GC.BE_SOURCE_LAKEHOUSE_NAME_COL),
            lit(self.target_lakehouse_name).alias(GC.BE_TARGET_LAKEHOUSE_NAME_COL),
            df[GC.BE_RECORD_IDENTIFIER_COL].alias(GC.BE_RECORD_IDENTIFIER_COL),
            df[validation_col_name].alias(GC.BE_MESSAGE_COL),
            df[GC.BE_SOURCE_FILE_PATH_COL].alias(GC.BE_SOURCE_FILE_PATH_COL)
        )

        return df
    
    def write_results(self, errors_df: DataFrame, warnings_df: DataFrame) -> None:
        """
        Summary:
            Write validation results to lakehouse
        Args:
            validated_dfs (dict): dictionary of validation results in the format of
            {
                "successes": DataFrame,
                "warnings": DataFrame,
                "errors": DataFrame
            }
        """
        if errors_df:
            errors = self.create_validation_df(errors_df, GC.VALIDATION_ERRORS_COL, "error")
            append_to_delta_table_using_path(
                df_to_process=errors,
                delta_table_path=f"{self.business_events_table_path}/{GC.BUSINESS_EVENTS_TABLE}",
                logger=self._logger
            )
        if warnings_df:
            warnings = self.create_validation_df(warnings_df, GC.VALIDATION_WARNINGS_COL, "warning")
            append_to_delta_table_using_path(
                df_to_process=warnings,
                delta_table_path=f"{self.business_events_table_path}/{GC.BUSINESS_EVENTS_TABLE}",
                logger=self._logger
            )
            
    def unmount(self) -> None:
        """
        Summary:
            Unmount source and target mount paths
        """
        if self.source_mount_path is not None:
            self.mssparkutils_client.fs_unmount(GC.VALIDATION_FAILED_FILES_SOURCE_MOUNT_LOCATION)
        if self.target_mount_path is not None:
            self.mssparkutils_client.fs_unmount(GC.VALIDATION_FAILED_FILES_TARGET_MOUNT_LOCATION)
    
    def validate_df(self, df: DataFrame, **kwargs) -> Dict[str, DataFrame]:
        """
        Summary:
            Apply validation on dataframe
        Args:
            df (DataFrame): dataframe to apply validation
            
        Keyword Args:
            table_name (str): The target table name for the validation results. Default is None.   
            delete_enabled (bool): Flag to delete the source file after moving it to the failed folder. Default is False.
            run_id (str): The run id for the execution. Default is the run id provided during the service initialization.
        Returns:
            dict: dictionary of validation results in the format of {"successes": DataFrame, "warnings": DataFrame, "errors": DataFrame}
        """

        self.target_table_name = kwargs.get("table_name")
        delete_enabled = kwargs.get("delete_enabled", False)
        self.run_id = kwargs.get("run_id", self.run_id)
        
        validated_dfs = {
            GC.VALIDATION_DF_SUCCESSES_KEY: df,
            GC.VALIDATION_DF_ERRORS_KEY: None,
            GC.VALIDATION_DF_WARNINGS_KEY: None
        }
        
        if self.validation_config:
            validations = self.validation_config.get("validations")
            
            error_validation_rules = self.generate_validation_rules(df, "error", validations, self.target_table_name)
            warning_validation_rules = self.generate_validation_rules(df, "warning", validations, self.target_table_name)

            df_with_validation = df \
                .withColumn(GC.VALIDATION_ERRORS_COL, concat_ws(", ", *[when(rule, message).otherwise(None) for message, rule in error_validation_rules])) \
                .withColumn(GC.VALIDATION_WARNINGS_COL, concat_ws(", ", *[when(rule, message).otherwise(None) for message, rule in warning_validation_rules]))
            
            success_df = df_with_validation.filter(
                (col(GC.VALIDATION_ERRORS_COL).isNull() | (col(GC.VALIDATION_ERRORS_COL) == "")) &
                (col(GC.VALIDATION_WARNINGS_COL).isNull() | (col(GC.VALIDATION_WARNINGS_COL) == ""))
            )
            errors_df = df_with_validation.filter(col(GC.VALIDATION_ERRORS_COL).isNotNull() & (col(GC.VALIDATION_ERRORS_COL) != ""))
            warnings_df = df_with_validation.filter(col(GC.VALIDATION_WARNINGS_COL).isNotNull() & (col(GC.VALIDATION_WARNINGS_COL) != ""))

            # If partial file movement is enabled, we want to keep the valid rows part of the successes_df
            if not self.partial_file_movement_enabled:
                success_df = success_df.join(errors_df, success_df[self.source_file_path] == errors_df[self.source_file_path], "left_anti")
                warnings_df = warnings_df.join(errors_df, warnings_df[self.source_file_path] == errors_df[self.source_file_path], "left_anti")
            

            if self.move_failed_files_enabled and self.failed_root_path and self.source_root_path and self.source_file_path and not self.partial_file_movement_enabled:

                self._logger.info(
                    f"{LC.COMPRESSING_AND_MOVING_FAILED_FILES_INFO_MSG.format(failed_folder_path=self.failed_root_path)}"
                )
                failed_files_count = errors_df.select(approx_count_distinct(self.source_file_path)).first()[0]
                compressed_df = self.file_compressor.run_movement_and_compression_from_df(errors_df, 
                                                                                        failed_files_count, 
                                                                                        file_path_column=self.source_file_path, 
                                                                                        delete_enabled= delete_enabled)
                errors_df = compressed_df
                
            self.write_results(errors_df, warnings_df)
            
            validated_dfs[GC.VALIDATION_DF_SUCCESSES_KEY] = success_df.drop(GC.VALIDATION_ERRORS_COL, GC.VALIDATION_WARNINGS_COL)
            validated_dfs[GC.VALIDATION_DF_ERRORS_KEY] = errors_df.drop(GC.VALIDATION_ERRORS_COL, GC.VALIDATION_WARNINGS_COL)
            validated_dfs[GC.VALIDATION_DF_WARNINGS_KEY] = warnings_df.drop(GC.VALIDATION_ERRORS_COL, GC.VALIDATION_WARNINGS_COL)
        else:
            self._logger.info(LC.NO_VALIDATION_RULES_MSG)
            
        return validated_dfs

    def partial_file_movement_from_df(
        self,
        invalid_rows_df: DataFrame,
    ) -> None:
        """
        Summary:
            Move failed files to a 'Failed' folder. This method is used for partial file movement.
            This method only supports json and ndjson file types.
            if the file is json, the entire file is moved to the 'Failed' folder.
            if the file is ndjson, only the failed lines are moved to the 'Failed' folder.
            For partial file movement, 'modality_name' and 'data_column_name' must be provided during the service initialization in addition to the 'partial_file_movement_enabled' flag set to true.
        Args:
            invalid_rows_df (DataFrame): dataframe that contains invalid rows
        Returns:
            None
        """
        self._logger.info(
            "Partial file movement is enabled. Moving failed lines of the file to 'Failed' folder."
        )

        if not self.partial_file_movement_enabled:
            self._logger.warning(
                "Partial file movement is not enabled. Skipping partial file movement."
            )
            return
        
        if not self.modality_name or not self.data_column_name:
            self._logger.warning(
                "Partial file movement is enabled but 'modality_name' or 'data_column_name' is not provided. Skipping partial file movement."
            )
            return

        def extract_file_path_for_modality(file_path: str, modality_name: str) -> str:
            pattern = rf"{modality_name}.*"
            match = re.search(pattern, file_path)
            return match.group(0) if match else ""

        def move_file_content(file_path: str) -> None:

            try:
                target_failed_file_path = f"{self.failed_root_path}/{extract_file_path_for_modality(file_path,self.modality_name)}"

                if target_failed_file_path.endswith(".json"):

                    self.mssparkutils_client.fs_mv(
                        file_path, target_failed_file_path, True
                    )
                    self._logger.info(
                        f"File: '{file_path}' moved to '{target_failed_file_path}'."
                    )

                elif target_failed_file_path.endswith(".ndjson"):

                    file_rows = invalid_rows_df.filter(
                        invalid_rows_df[self.source_file_path] == file_path
                    )
                    lines = [
                        row[self.data_column_name]
                        for row in file_rows.select(self.data_column_name).collect()
                    ]
                    self.mssparkutils_client.fs_mkdirs(
                        target_failed_file_path.rsplit("/", 1)[0]
                    )
                    lines_str = "\n".join(lines) + "\n"
                    self.mssparkutils_client.fs_append(
                        target_failed_file_path, lines_str, True
                    )
                    self._logger.info(
                        f"Lines appended to file: '{target_failed_file_path}'."
                    )
                else:
                    self._logger.warning(f"Unrecognized file type for '{file_path}'.")
            except Exception as e:
                self._logger.error(
                    LC.PARTIAL_FILE_MOVEMENT_ERROR_MSG.format(
                        error=e, file_path=file_path
                    )
                )

        # Move failed lines of the file to 'Failed' folder. Use local iterator to avoid memory issues.
        for row in (
            invalid_rows_df.select(self.source_file_path).distinct().toLocalIterator()
        ):
            file_path = row[self.source_file_path]
            if file_path:
                move_file_content(file_path)                

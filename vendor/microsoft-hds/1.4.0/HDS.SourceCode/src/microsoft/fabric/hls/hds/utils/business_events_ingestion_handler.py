from datetime import datetime
import json
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from pyspark.sql import SparkSession, types as T
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.global_constants.global_constants import (
    GlobalConstants as GC,
)
class BusinessEventsIngestion:
    """
    Class for handling the ingestion of business events into the business events Delta table.
    """

    def __init__(self, spark: SparkSession, workspace_name: str, one_lake_endpoint: str, lakehouse_name: str, parameter_service, solution_name: str):
        """
        Initializes the BusinessEventsIngestion class.

        Args:
            spark (SparkSession): The Spark session object.
            workspace_name (str): The name of the workspace.
            one_lake_endpoint (str): The OneLake endpoint.
            lakehouse_name (str): The name of the lakehouse.
            parameter_service: The parameter service object.
            solution_name (str): The name of the solution.
        """
        self.spark = spark
        self.workspace_name = workspace_name
        self.one_lake_endpoint = one_lake_endpoint
        self.lakehouse_name = lakehouse_name
        self.parameter_service = parameter_service
        self.solution_name = solution_name
        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(workspace_name=self.workspace_name,
                                                                                one_lake_endpoint=self.one_lake_endpoint,
                                                                                solution_name=self.solution_name)
        self.business_events_table_path = (
            self.parameter_service.get_activity_config_value(
                GC.BUSINESS_EVENTS_TABLE_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.lakehouse_name
                    )
            )
        )

        self.business_events_schema_dir_path = self.parameter_service.get_activity_config_value(
            GlobalConstants.BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY,
            f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GlobalConstants.BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER}"
            ) 
        self.business_events_schema_path = f"{self.business_events_schema_dir_path}/{GlobalConstants.BUSINESS_EVENTS_TABLE}.avsc"     
        self.schema = self.load_business_events_schema()
        self._logger = LoggingHelper.get_business_events_ingestion_logger(
            self.spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )
   
    def insert_business_events(self, records: list):
        """
        Inserts business event records into the business events Delta table.

        This method creates a DataFrame from the provided records and appends it to the existing
        business events Delta table. If an error occurs during the append operation, it logs the
        error and raises an exception.

        Args:
            records (list): A list of records to be inserted into the business events table.

        Raises:
            Exception: If an error occurs during the append operation, the error is logged and
                       the exception is re-raised.
        """
        if not records:
            self._logger.info("No business event records to insert.")
            return
        business_events_table_path = f"{self.business_events_table_path}/{GlobalConstants.BUSINESS_EVENTS_TABLE}"
        business_events_df = self.spark.createDataFrame(records, schema=self.schema)
        try:
            append_to_delta_table_using_path(
                df_to_process=business_events_df,
                delta_table_path=business_events_table_path,
                logger=self._logger
                )
        except Exception as ex:
            self._logger.error(str(ex))
            raise
        
    def load_business_events_schema(self) -> T.StructType:
        """
        Loads the business events schema from an Avro file.

        Returns:
            T.StructType: The schema of the business events.
        """
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
        )

        json_schema = json.loads(java_schema_type.dataType().json())
        
        return T.StructType.fromJson(json_schema) 
    
    def create_new_business_event_row(self, id: str = "", activityName: str = "NA", targetTableName: str = "NA", targetFilePath: str = "NA", sourceTableName: str = "NA", sourceLakehouseName: str = "NA",
                                      targetLakehouseName: str = "NA", sourceFilePath: str = "NA", runId: str = "NA", severity: str = "NA", eventType: str = "NA", recordIdentifier: str = "NA", recordIdentifierSource: str = "NA",
                                      active: bool = True, message: str = "NA", exception: str = "NA", customDimensions: str = "NA") -> dict:
        """
        Creates a new row for the DataFrame with the specified schema.
        
        Returns:
            dict: A dictionary representing the new row.
        """
        return {
        GlobalConstants.BE_ID_COL: id,
        GlobalConstants.BE_ACTIVITY_NAME_COL: activityName,
        GlobalConstants.BE_TARGET_TABLE_NAME_COL: targetTableName,
        GlobalConstants.BE_TARGET_FILE_PATH_COL: targetFilePath,
        GlobalConstants.BE_SOURCE_TABLE_NAME_COL: sourceTableName,
        GlobalConstants.BE_SOURCE_LAKEHOUSE_NAME_COL: sourceLakehouseName,
        GlobalConstants.BE_TARGET_LAKEHOUSE_NAME_COL: targetLakehouseName,
        GlobalConstants.BE_SOURCE_FILE_PATH_COL: sourceFilePath,
        GlobalConstants.BE_RUN_ID_COL: runId,
        GlobalConstants.BE_SEVERITY_COL: severity,
        GlobalConstants.BE_EVENT_TYPE_COL: eventType,
        GlobalConstants.BE_RECORD_IDENTIFIER_COL: recordIdentifier,
        GlobalConstants.BE_RECORD_IDENTIFIER_SOURCE_COL: recordIdentifierSource,
        GlobalConstants.BE_ACTIVE_COL: active,
        GlobalConstants.BE_MESSAGE_COL: message,
        GlobalConstants.BE_EXCEPTION_COL: exception,
        GlobalConstants.BE_CUSTOMDIMENSIONS_COL: customDimensions,
        GlobalConstants.BE_EVENT_DATE_TIME_COL: datetime.now(),
        GlobalConstants.BE_CREATEDDATE_COL: datetime.now()
        }
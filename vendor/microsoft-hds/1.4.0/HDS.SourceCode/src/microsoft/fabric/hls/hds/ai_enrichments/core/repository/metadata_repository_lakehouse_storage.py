import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pyspark.sql import SparkSession, Row, DataFrame
import pyspark.sql.types as T
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path, delete_record, get_record, get_active_records,upsert_unique_to_delta_managed
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC
from microsoft.fabric.hls.hds.ai_enrichments.core.base_classes.metadata_repository_base import MetadataRepositoryBase
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
class MetadataRepositoryLakehouseStorage(MetadataRepositoryBase):
    def __init__(self, spark: SparkSession, tables_path: str, logger: DataManagerLogger):
        self.spark = spark
        self.tables_path = tables_path
        self._logger = logger

    def create_record(self, schema: T.StructType, data: Dict[str, Any], table_name: str) -> str:
        self._save_to_table(schema, data, table_name)
        self._logger.info(LC.ENRICHMENT_METADATA_CREATED.format(table_name, data["id"]))
        return data["id"]

    def _save_to_table(self, schema: T.StructType, data: Dict[str, Any], table_name: str) -> None:
        df = self.spark.createDataFrame([Row(**data)], schema)
        append_to_delta_table_using_path(df, f"{self.tables_path}/{table_name}", self._logger)
        self._logger.info(LC.ENRICHMENT_DATA_SAVED.format(table_name))

    def delete_record(self, table_name: str, record_id: str) -> None:
        try:
            delete_record(self.spark, self.tables_path, table_name, record_id, self._logger)
        except Exception as e:
            self._logger.error(LC.ERROR_DELETING_RECORD.format(record_id, table_name, e))

    def get_record_info(self, record_id: str, table_name: str, model_class: Any, id_column: str = "id") -> Optional[Any]:
        try:
            return get_record(self.spark, id_column, record_id, self.tables_path, table_name, model_class, self._logger)
        except Exception as e:
            self._logger.error(LC.ERROR_RETRIEVING_RECORD_INFO.format(table_name, record_id, e))
            return None 
        
    def get_active_records(self, records: list[str], table_name: str, id_column) -> Optional[set]:
        try:
            return get_active_records(self.spark, id_column, records, self.tables_path, table_name, self._logger)
        except Exception as e:
            self._logger.error(LC.ERROR_RETRIEVING_RECORD_INFO.format(table_name, id_column, e))
            return None
    
    def upsert_to_table(self, df: DataFrame, table_name: str, unique_columns: List[str], source_modified_on_column:str ) -> None:
        """
        Upsert the given DataFrame to a specified Delta table.
        This method attempts to upsert the DataFrame into a Delta table located at the specified path.
        If an error occurs during the process, it raises a RuntimeError with additional context.
        Args:
            df (DataFrame): The DataFrame to append to the Delta table.
            table_name (str): The name of the Delta table to append the DataFrame to.
        Raises:
            RuntimeError: If the DataFrame could not be written to the specified table.
        """
        try:
            upsert_unique_to_delta_managed(
            spark_session=self.spark,
            data_manager_logger=self._logger,
            df_to_process=df,
            delta_table_path= f"{self.tables_path}/{table_name}",
            unique_columns=unique_columns,
            source_modified_on_column=source_modified_on_column,
            )
        except Exception as e:
            self._logger.error(LC.ERROR_UPSERTING_CONTEXT_DATA.format(e))
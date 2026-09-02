from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
import pyspark.sql.types as T
from pyspark.sql import DataFrame
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import AIEnrichmentsLoggingConstants as LC


class MetadataRepositoryBase(ABC):
    """
    Abstract base class for metadata repository operations.
    """

    @abstractmethod
    def create_record(self, schema: T.StructType, data: Dict[str, Any], table_name: str) -> str:
        """
        Create a new record in the specified table.

        :param schema: The schema of the table.
        :param data: The data to be inserted.
        :param table_name: The name of the table.
        :return: The ID of the created record.
        """
        raise NotImplementedError(LC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)

    @abstractmethod
    def delete_record(self, table_name: str, record_id: str) -> None:
        """
        Delete a record from the specified table.

        :param table_name: The name of the table.
        :param record_id: The ID of the record to be deleted.
        """
        raise NotImplementedError(LC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)

    @abstractmethod
    def get_record_info(self, record_id: str, table_name: str, model_class: Any, id_column: str = "id") -> Optional[Any]:
        """
        Retrieve information about a specific record from the specified table.

        :param record_id: The ID of the record.
        :param table_name: The name of the table.
        :param model_class: The class model to map the record data.
        :param id_column: The name of the ID column (default is "id").
        :return: An instance of model_class with the record data, or None if not found.
        """
        raise NotImplementedError(LC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)
    
    
    @abstractmethod
    def get_active_records(self, records: list[str], table_name: str, id_column) -> Optional[list[str]]:
        """
        Retrieve the current records from the specified table.

        Args:
            records (list[str]): A list of records to check and to retrieve.
            table_name (str): The name of the table to query.
            id_column (str): The name of the column .

        Returns:
            Optional[list[str]]: A list of current records if found, otherwise None.
        """
        raise NotImplementedError(LC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)
    
    @abstractmethod
    def upsert_to_table(self, df: DataFrame, table_name: str, unique_columns: List[str], source_modified_on_column:str ) -> None:
        """
        Upsert a PySpark DataFrame to the specified table.

        :param df: The DataFrame to be written.
        :param table_name: The name of the table.
        Options include "append", "overwrite", "errorifexists", "ignore".
        """
        raise NotImplementedError(LC.AI_ENRICHMENT_MODEL_EXECUTION_IMPLEMENTATION_ERROR)
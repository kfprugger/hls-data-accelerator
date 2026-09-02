from typing import List

from pyspark.sql import SparkSession

from rmt.core.data_export.authoring_mapping_schema import AuthoringMappingSchema
from rmt.core.data_export.authoring_mapping_writer import AuthoringMappingWriter
from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.file_model.data_management.authoring_files_constants import AUTHORING_MAPPING_FILE_NAME
from rmt.file_model.data_management.data_management_context import DataManagementContext


class AuthoringMappingFileWriter(AuthoringMappingWriter):

    def __init__(self, spark: SparkSession, data_management_context: DataManagementContext):
        self.file_system_client = data_management_context.file_system_client
        self.authoring_folder_path = data_management_context.authoring_folder_path
        self._spark = spark

    def write(self, authoring_mapping_entries: List[AuthoringMappingEntry]):
        rows = []

        for authoring_mapping_entry in authoring_mapping_entries:
            rows.append(
                (
                    authoring_mapping_entry.contributor_name,
                    authoring_mapping_entry.table_name,
                    authoring_mapping_entry.source_value,
                    authoring_mapping_entry.target_key,
                )
            )

        df = self._spark.createDataFrame(rows, AuthoringMappingSchema.schema)

        self.file_system_client.write_csv_file(self.file_system_client.join_paths(self.authoring_folder_path, AUTHORING_MAPPING_FILE_NAME), df)

from typing import List

from pyspark.sql import SparkSession

from rmt.core.data_export.authoring_data_schema import AuthoringDataSchema
from rmt.core.data_export.authoring_data_writer import AuthoringDataWriter
from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry
from rmt.file_model.data_management.authoring_files_constants import AUTHORING_DATA_FILE_NAME
from rmt.file_model.data_management.data_management_context import DataManagementContext


class AuthoringDataFileWriter(AuthoringDataWriter):

    def __init__(self, spark: SparkSession, data_management_context: DataManagementContext):
        self.file_system_client = data_management_context.file_system_client
        self.authoring_folder_path = data_management_context.authoring_folder_path
        self._spark = spark

    def write(self, authoring_data_entries: List[AuthoringDataEntry]):
        rows = []

        for authoring_data_entry in authoring_data_entries:
            rows.append(
                (
                    authoring_data_entry.contributor_name,
                    authoring_data_entry.table_name,
                    authoring_data_entry.name,
                    authoring_data_entry.key,
                )
            )

        df = self._spark.createDataFrame(rows, AuthoringDataSchema.schema)

        self.file_system_client.write_csv_file(self.file_system_client.join_paths(self.authoring_folder_path, AUTHORING_DATA_FILE_NAME), df)

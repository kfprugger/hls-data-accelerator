from pyspark.sql import SparkSession

import rmt.core.logger as CoreLogger
from rmt.runners.notebook_utils_file_system_client import NotebookUtilsFileSystemClient
from rmt.runners.runner import Runner
from rmt.tools.logging import Logger


class FabricRunner:
    @staticmethod
    def create_reference_values_mapping(
        spark: SparkSession,
        rmt_spec_path: str,
        ordered_mapping_definitions_folders: list[str] = None,
        number_of_partition_files: int = -1,
        staging_reference_data_folder_path=None,
    ):

        CoreLogger.set_logger(Logger.init_logger())
        spark_file_system_client = NotebookUtilsFileSystemClient(spark)
        Runner(spark, spark_file_system_client, rmt_spec_path).create_reference_values_mapping(
            ordered_mapping_definitions_folders, number_of_partition_files, staging_reference_data_folder_path
        )

    @staticmethod
    def create_reference_data_tables(
        spark: SparkSession, rmt_spec_path: str, target_path: str, reference_tables_folders_paths: list[str] = None, staging_reference_data_folder_path=None
    ):
        """
        This static method is used to create reference data tables.

        Args:
            spark (SparkSession): The SparkSession object to use for Spark operations.
            rmt_spec_path (str): The path to the RMT (Reference Mapping Table) specification file.
            target_path (str): The path where the reference data tables will be created.
            reference_tables_folders_paths (list[str]): A list of paths to folders containing reference tables source data.
            staging_reference_data_folder_path: path to reference staging folder so the paths to reference data foldes will be resolved by code
            only one of reference_tables_folders_paths or staging_reference_data_folder_path should be provided

        This method is used to create  reference data tables at the specified target path using the provided RMT
        specification.
        """

        CoreLogger.set_logger(Logger.init_logger())
        file_system_client = NotebookUtilsFileSystemClient(spark)
        Runner(spark=spark, file_system_client=file_system_client, rmt_spec_path=rmt_spec_path).create_reference_data_tables(
            target_path, reference_tables_folders_paths, staging_reference_data_folder_path
        )

    @staticmethod
    def update_staging_reference_data(spark: SparkSession, rmt_spec_path: str, authoring_folder_path: str, staging_reference_data_folder_path: str):

        CoreLogger.set_logger(Logger.init_logger())
        file_system_client = NotebookUtilsFileSystemClient(spark)
        Runner(spark=spark, file_system_client=file_system_client, rmt_spec_path=rmt_spec_path).update_staging_reference_data(
            authoring_folder_path, staging_reference_data_folder_path
        )

    @staticmethod
    def generate_reference_data_authoring_files(spark: SparkSession, rmt_spec_path: str, staging_reference_data_folder_path: str, target_authoring_folder_path: str):

        CoreLogger.set_logger(Logger.init_logger())
        file_system_client = NotebookUtilsFileSystemClient(spark)
        Runner(spark=spark, file_system_client=file_system_client, rmt_spec_path=rmt_spec_path).generate_reference_data_authoring_files(
            target_authoring_folder_path, staging_reference_data_folder_path
        )

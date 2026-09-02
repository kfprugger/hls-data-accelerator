import traceback
from typing import List

from common.model.base_source_configuration import BaseSourceConfiguration
from pyspark.sql import SparkSession

import rmt.core.logger as logger
from rmt.app.authoring_files_generator import AuthoringFilesGenerator
from rmt.app.reference_tables_creator import ReferenceTablesCreator
from rmt.app.reference_values_mapper import ReferenceValuesMapper
from rmt.app.repository_updater import RepositoryUpdater
from rmt.contract.configuration.internal.rmt_spec_reader import RMTSpecReader
from rmt.core.core_exceptions import AuthoringFileError, AuthoringFilesGenerationError, UpdateError
from rmt.file_model.data_export.authoring_data_file_writer import AuthoringDataFileWriter
from rmt.file_model.data_export.authoring_mapping_file_writer import AuthoringMappingFileWriter
from rmt.file_model.data_management.authoring_data_file_reader import AuthoringDataFileReader
from rmt.file_model.data_management.authoring_mapping_file_reader import AuthoringMappingFileReader
from rmt.file_model.data_management.contributors_json_reader import ContributorsFileReader
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.repository_folder import RepositoryFolder
from rmt.file_model.data_management.repository_folder_table_data_reader import RepositoryFolderTableDataReader
from rmt.file_model.data_management.repository_folder_table_data_writer import RepositoryFolderTableDataWriter
from rmt.file_model.data_management.repository_folder_table_mapping_reader import RepositoryFolderTableMappingReader
from rmt.file_model.data_management.repository_folder_table_mapping_writer import RepositoryFolderTableMappingWriter
from rmt.file_model.tables_creating.reference_tables_data_file_reader import ReferenceTablesDataFileReader
from rmt.file_model.values_mapping.mapping_definitions_file_reader import MappingDefinitionsFileReader
from rmt.filesystem.file_system_client import FileSystemClient
from rmt.runners.paths_parameters_handler import PathsParametersHandler
from rmt.source_processor.source_processor import SourceProcessor

REFERENCE_MAPPING_PATH = "REFERENCE_MAPPING"


class Runner:
    def __init__(
        self,
        spark: SparkSession,
        file_system_client: FileSystemClient,
        rmt_spec_path: str,
    ) -> None:
        self._spark = spark
        self._file_system_client = file_system_client
        logger.info("RMT execution started")
        logger.info(f"RMT Spec file: {rmt_spec_path}")
        self._rmt_spec = RMTSpecReader.read(rmt_spec_path, file_system_client)
        self._paths_parameters_handler = PathsParametersHandler(file_system_client, self._rmt_spec.source_domain)

    def create_reference_values_mapping(self, ordered_mapping_definitions_folders: List[str] = None, number_of_partition_files: int = -1, staging_reference_data_folder_path=None):

        try:
            logger.info(
                f"Running RMT to map values using mapping definitions.Input parameters:"
                f"ordered_mapping_definitions_folders: {ordered_mapping_definitions_folders}, "
                f"number_of_partition_files: {number_of_partition_files}"
                f"staging_reference_data_folder_path: {staging_reference_data_folder_path}"
            )

            mapping_folder_paths = self._paths_parameters_handler.get_mapping_folder_paths(ordered_mapping_definitions_folders, staging_reference_data_folder_path)

            logger.info(f"Mapping from the following folders: {mapping_folder_paths}")
            mapping_definitions_reader = MappingDefinitionsFileReader(
                self._file_system_client,
                mapping_folder_paths,
                self._rmt_spec.reference_tables,
            )
            ReferenceValuesMapper.create_reference_values_mapping(
                self._spark,
                self._rmt_spec.source_domain,
                mapping_definitions_reader,
                self._file_system_client.join_paths(self._rmt_spec.secondary_lake_location, REFERENCE_MAPPING_PATH),
                number_of_partition_files,
            )

            logger.info("RMT execution ended")

        except Exception as e:
            logger.error(f"RMT ends with error.{e}")
            logger.error(traceback.format_exc())
            raise

    def create_reference_data_tables(self, target_path: str, reference_tables_folders_paths: list[str] = None, staging_reference_data_folder_path=None):

        try:
            logger.info(
                f"Running RMT to create tables from data folders.Input parameters:"
                f"reference_tables_folders_paths: {reference_tables_folders_paths}, "
                f"staging_reference_data_folder_path: {staging_reference_data_folder_path}"
            )
            data_folder_paths = self._paths_parameters_handler.get_data_folder_paths(reference_tables_folders_paths, staging_reference_data_folder_path)

            logger.info(f"Creating reference tables from the following data folders {data_folder_paths}")
            file_reader = ReferenceTablesDataFileReader(self._file_system_client, data_folder_paths, set(self._rmt_spec.reference_tables.keys()))
            ReferenceTablesCreator.create_reference_data_tables(self._spark, target_path, self._rmt_spec.reference_tables, file_reader)

            logger.info("RMT execution ended")

        except Exception as e:
            logger.error(f"RMT ended with error.{e}")
            logger.error(traceback.format_exc())
            raise

    def update_staging_reference_data(self, authoring_folder_path, staging_reference_data_folder_path: str):
        try:
            logger.info(
                f"Running RMT to update staging folder.Input Parameters:"
                f"authoring_folder_path: {authoring_folder_path}, "
                f"staging_reference_data_folder_path: {staging_reference_data_folder_path}"
            )

            self._paths_parameters_handler.raise_error_if_folder_not_exist(staging_reference_data_folder_path)
            self._paths_parameters_handler.raise_error_if_folder_not_exist(authoring_folder_path)

            authoring_repository_folder = RepositoryFolder(self._file_system_client, self._rmt_spec.source_domain, authoring_folder_path)

            authoring_data_management_context = DataManagementContext(self._file_system_client, authoring_folder_path, authoring_repository_folder, self._rmt_spec.reference_tables)

            staging_repository_folder = RepositoryFolder(self._file_system_client, self._rmt_spec.source_domain, staging_reference_data_folder_path)

            staging_data_management_context = DataManagementContext(self._file_system_client, authoring_folder_path, staging_repository_folder, self._rmt_spec.reference_tables)

            authoring_data_reader = AuthoringDataFileReader(authoring_data_management_context)
            authoring_mapping_reader = AuthoringMappingFileReader(authoring_data_management_context)
            repository_contributors_reader = ContributorsFileReader(staging_data_management_context)
            repository_folder_table_mapping_reader = RepositoryFolderTableMappingReader(staging_data_management_context)
            repository_folder_table_data_reader = RepositoryFolderTableDataReader(staging_data_management_context)
            repository_folder_table_mapping_writer = RepositoryFolderTableMappingWriter(staging_data_management_context)
            repository_folder_table_data_writer = RepositoryFolderTableDataWriter(staging_data_management_context)

            RepositoryUpdater.update_repository_folder_reference_data(
                authoring_data_reader,
                authoring_mapping_reader,
                repository_contributors_reader,
                repository_folder_table_mapping_reader,
                repository_folder_table_data_reader,
                repository_folder_table_mapping_writer,
                repository_folder_table_data_writer,
            )
            logger.info("RMT execution ended")

        except UpdateError as ue:
            logger.error(f"RMT ends with error.{ue}")
            raise
        except AuthoringFileError as afe:
            logger.error(f"RMT ends with error.{afe}")
            raise
        except Exception as e:
            logger.error(f"RMT ended with error.{e}")
            logger.error(traceback.format_exc())
            raise

    def generate_reference_data_authoring_files(self, target_authoring_folder_path: str, staging_reference_data_folder_path: str):

        try:

            logger.info(
                f"Running RMT to generate authoring files.Input Parameters:"
                f"target_authoring_folder_path: {target_authoring_folder_path}, "
                f"staging_reference_data_folder_path: {staging_reference_data_folder_path}"
            )

            self._paths_parameters_handler.raise_error_if_folder_not_exist(staging_reference_data_folder_path)
            repository_folder = RepositoryFolder(self._file_system_client, self._rmt_spec.source_domain, staging_reference_data_folder_path)
            data_management_context = DataManagementContext(self._file_system_client, target_authoring_folder_path, repository_folder, self._rmt_spec.reference_tables)

            source_processors = self._create_source_processors(list(self._rmt_spec.source_configurations))

            repository_folder_data_reader = RepositoryFolderTableDataReader(data_management_context)
            repository_folder_mapping_reader = RepositoryFolderTableMappingReader(data_management_context)

            authoring_data_writer = AuthoringDataFileWriter(self._spark, data_management_context)
            authoring_mapping_writer = AuthoringMappingFileWriter(self._spark, data_management_context)

            repository_contributors_reader = ContributorsFileReader(data_management_context)

            mapping_definitions_file_reader = MappingDefinitionsFileReader(
                self._file_system_client, [str(value) for value in repository_folder.get_mapping_folder_paths().values()], self._rmt_spec.reference_tables
            )

            AuthoringFilesGenerator.generate_reference_data_authoring_files(
                self._spark,
                self._rmt_spec.source_domain,
                source_processors,
                mapping_definitions_file_reader,
                repository_contributors_reader,
                repository_folder_mapping_reader,
                repository_folder_data_reader,
                authoring_data_writer,
                authoring_mapping_writer,
            )
        except AuthoringFilesGenerationError as ge:
            logger.error(f"RMT ends with error.{ge}")
            raise
        except Exception as e:
            logger.error(f"RMT ended with error.{e}")
            logger.error(traceback.format_exc())
            raise

    def _create_source_processors(self, source_configs: list[BaseSourceConfiguration]) -> List[SourceProcessor]:

        if not source_configs:
            raise ValueError("No source configs found")

        processors = []
        for source_config in source_configs:
            processor = SourceProcessor(self._spark, source_config)
            try:
                processor.validate()
                processors.append(processor)
            except Exception as e:
                logger.error(f"Validation failed for source configuration {source_config.source_name} with error: {e}")
                raise EnvironmentError(f"Validation failed for source configuration {source_config.source_name} " f"with error {e}") from e

        return processors

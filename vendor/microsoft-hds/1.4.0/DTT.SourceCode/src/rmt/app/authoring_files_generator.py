from typing import List

from pyspark.sql import SparkSession

from rmt.app.common.values_mapper import ValuesMapper
from rmt.core import logger
from rmt.core.data_export.authoring_data_writer import AuthoringDataWriter
from rmt.core.data_export.authoring_mapping_writer import AuthoringMappingWriter
from rmt.core.data_export.source_values_reader import SourceValuesReader
from rmt.core.data_export.source_values_schema import SourceValuesSchema
from rmt.core.data_export.table_data_adapter import TableDataAdapter
from rmt.core.data_export.table_mapping_adapter import TableMappingAdapter
from rmt.core.data_export.unmapped_source_value_retriever import UnmappedSourceValuesRetriever
from rmt.core.data_management.abstract_contributors_reader import AbstractContributorsReader
from rmt.core.data_management.abstract_repository_folder_table_data_reader import AbstractRepositoryFolderTableDataReader
from rmt.core.data_management.abstract_repository_folder_table_mapping_reader import AbstractRepositoryFolderTableMappingReader
from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry
from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.core.data_management.contributor import ContributorType
from rmt.core.values_mapping.mapping_definitions_reader import MappingDefinitionsReader


class AuthoringFilesGenerator:

    @staticmethod
    def generate_reference_data_authoring_files(
        spark: SparkSession,
        source_domain: str,
        source_values_readers: List[SourceValuesReader],
        mapping_definitions_reader: MappingDefinitionsReader,
        repository_contributors_reader: AbstractContributorsReader,
        repository_folder_table_mapping_reader: AbstractRepositoryFolderTableMappingReader,
        repository_folder_table_data_reader: AbstractRepositoryFolderTableDataReader,
        authoring_data_writer: AuthoringDataWriter,
        authoring_mapping_writer: AuthoringMappingWriter,
    ):

        # read source distinct values
        source_distinct_values_df = spark.createDataFrame([], SourceValuesSchema.schema)
        for source_values_reader in source_values_readers:
            source_distinct_values_df = source_distinct_values_df.unionByName(source_values_reader.read_source_distinct_values()).distinct()

        # create mapping dataframe from repository
        mapping_df = ValuesMapper.create_and_validate_reference_values_mapping(spark, source_domain, mapping_definitions_reader)

        # join source distinct values with mapping dataframe to get unmapped source values
        unmapped_source_values_df = UnmappedSourceValuesRetriever.retrieve_unmapped_source_values(source_distinct_values_df, mapping_df)

        authoring_unmapped_entries = TableMappingAdapter.get_authoring_entries_from_dataframe(unmapped_source_values_df)

        # read contributors
        contributors = repository_contributors_reader.read()

        for contributor in contributors:
            if contributor.name == ContributorType.Customer.name:
                customer_contributor = contributor
                break
        if customer_contributor is None:
            logger.error("Customer contributor not found")
            return

        repository_authoring_data_entries: List[AuthoringDataEntry] = []
        repository_authoring_mapping_entries: List[AuthoringMappingEntry] = []

        for contributor in contributors:
            # read table data for the relevant tables from repository folder
            contributor_table_data_list = repository_folder_table_data_reader.read(contributor.name)
            if contributor_table_data_list is not None:
                contributor_authoring_data_entries = TableDataAdapter.get_authoring_entries(contributor.name, contributor_table_data_list)
                repository_authoring_data_entries = repository_authoring_data_entries + contributor_authoring_data_entries

            # read table mapping for the relevant tables from repository folder
            contributor_table_mapping_list = repository_folder_table_mapping_reader.read(contributor.name)
            if contributor_table_mapping_list is not None:
                contributor_authoring_mapping_entries = TableMappingAdapter.get_authoring_entries(contributor.name, contributor_table_mapping_list)
                repository_authoring_mapping_entries = repository_authoring_mapping_entries + contributor_authoring_mapping_entries

        #  optional 1. here should be logic to order the authoring data  entries by table name and key
        #  optional 2a here should be logic to order the authoring mapping entries by table name and target key
        all_authoring_mapping_entries = repository_authoring_mapping_entries + authoring_unmapped_entries
        #  optional 2b here should be logic to order the authoring mapping entries by table name and target key

        authoring_data_writer.write(repository_authoring_data_entries)
        authoring_mapping_writer.write(all_authoring_mapping_entries)

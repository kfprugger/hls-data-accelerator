from typing import Optional

from pyspark.sql import DataFrame

from dmf.ids_mapping.adrm_ids_enricher import AdrmIdsEnricher
from dmf.ids_mapping.adrm_ids_mapper import AdrmIdsMapper
from common.utils.logging import Logger
from common.model.data_access_definition import DataAccessDefinition
from common.model.data_source_type_enum import DataSourceTypeEnum
from dmf.transformations.processor.source_processor import SourceProcessor
from common.reader.reader_factory import ReaderFactory
from dmf.utils.data_lake_utils import get_mapping_tables_location




def map_source_to_ids(ids_table_name: str,
                      source_system_id: str,
                      source_df: DataFrame,
                      source_internal_id_column_name: str,
                      source_external_id_column_name: Optional[str],
                      mapped_column_name: str,
                      secondary_lake_location: str) -> DataFrame:
    """
        Maps source system ids to ids of the ids_table_name table

        Parameters:
             ids_table_name (str): Name of the table containing the ids.
             source_system_id (str): Name of the source system.
             source_df (DataFrame): A dataframe containing the id that needs to be mapped.
             source_internal_id_column_name (str): A name of the column containing the internal id of the source system.
              Internal id is the id that identifies and entity in the source system and is unique within the source system.
             source_external_id_column_name (str): A name of the  containing the external id of the source system.
              External id is the id that uniquely identifies an entity in the source system and is unique across all
              source systems. This parameter is mandatory in case this API is used to synchronize data between multiple source systems.
             mapped_column_name (str): A name of the column in the output DataFrame that will contain the ids from the ids_table_name table that match the source system ids.
             secondary_lake_location (str): Absolute path of the location of the secondary lake.

        Returns:
            DataFrame: The original DataFrame with additional column containing the ids from the ids_table_name table that match the source system ids.
        """

    Logger.init_logger()
    id_mapping_tables_location = get_mapping_tables_location(secondary_lake_location)
    AdrmIdsMapper().map(
        spark=source_df.sparkSession,
        given_df=source_df,
        feed_id=source_system_id,
        internal_id_column_name=source_internal_id_column_name,
        external_id_column_name=source_external_id_column_name,
        id_mapping_table_db_name=None,
        id_mapping_table_name=AdrmIdsMapper.get_mapping_table_name(ids_table_name),
        id_mapping_tables_location=id_mapping_tables_location,
        id_mapping_table_entity_type=DataSourceTypeEnum.STORAGE
    )

    source_id_column = SourceProcessor.calc_source_id_column_name(source_external_id_column_name,
                                                                  source_internal_id_column_name)
    ids_mapping_table_name = AdrmIdsMapper.get_mapping_table_name(ids_table_name)
    mapping_table_location = AdrmIdsMapper.specific_table_location(id_mapping_tables_location, ids_mapping_table_name)
    reader = ReaderFactory.get_instance(DataAccessDefinition(data_source_id=ids_mapping_table_name,
                                                             data_source_owner_id=mapping_table_location,
                                                             data_format=AdrmIdsMapper.DATA_FORMAT,
                                                             data_source_type=DataSourceTypeEnum.STORAGE))
    id_mapping_df = reader.read(source_df.sparkSession)
    return AdrmIdsEnricher.enrich(source_df, source_system_id, source_id_column, id_mapping_df, mapped_column_name)

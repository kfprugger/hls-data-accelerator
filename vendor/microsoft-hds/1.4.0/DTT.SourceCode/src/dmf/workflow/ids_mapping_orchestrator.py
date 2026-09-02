from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from pyspark.sql import SparkSession

from common.model.data_access_definition import DataAccessDefinition
from common.model.types import DataSourceId
from common.model.data_source_type_enum import DataSourceTypeEnum
from dmf.model.data_feed_configuration import DataFeedConfiguration
from dmf.ids_mapping.adrm_ids_mapper import AdrmIdsMapper
from common.utils.logging import Logger
from dmf.transformations.model.id_mapping_info import IdMappingInfo
from dmf.transformations.processor.source_processor import SourceProcessor
from dmf.utils.data_lake_utils import get_mapping_tables_location


class IdsMappingOrchestrator:

    @staticmethod
    def map_source_ids_to_target_ids(
            spark: SparkSession,
            config: DataFeedConfiguration,
            source_processors: List[SourceProcessor]) -> Dict[DataSourceId, DataAccessDefinition]:

        ids_mapping_dag: Dict[str, List[IdMappingInfo]] = \
            IdsMappingOrchestrator._build_ids_mapping_dag(config, source_processors)

        return IdsMappingOrchestrator._id_mapping_table_data_access_definitions(spark, config, ids_mapping_dag)

    @staticmethod
    def _id_mapping_table_data_access_definitions(spark: SparkSession,
                                                  config: DataFeedConfiguration,
                                                  ids_mapping_dag: Dict[str, List[IdMappingInfo]]) -> \
            Dict[DataSourceId, DataAccessDefinition]:

        # run thread for each 'key' to process 'values' sequentially
        def _map_ids(id_mapping_info_list: List[IdMappingInfo]) -> Dict[DataSourceId, DataAccessDefinition]:
            if not id_mapping_info_list:
                raise ValueError("No ID mapping table was provided for mapping.")

            ordered_id_mapping_info_list = IdsMappingOrchestrator._order_id_mapping_info_list(id_mapping_info_list)

            id_mapping_table_db_name = None
            id_mapping_entity_type = None
            id_mapping_target_table_name = None
            id_mapping_table_name = None
            id_mapping_tables_location = None
            for id_mapping_info in ordered_id_mapping_info_list:
                mapping_definition = id_mapping_info.mapping_definition
                id_mapping_target_table_name = mapping_definition.target_mapping_table_name
                id_mapping_table_name = AdrmIdsMapper.get_mapping_table_name(id_mapping_target_table_name)
                id_mapping_table_db_name = mapping_definition.db
                id_mapping_entity_type = mapping_definition.mapping_entity_type
                id_mapping_tables_location = get_mapping_tables_location(mapping_definition.secondary_lake_location)

                try:
                    AdrmIdsMapper().map(
                        spark=spark,
                        given_df=id_mapping_info.source_df,
                        feed_id=config.feed_id,
                        internal_id_column_name=mapping_definition.internal_id_column_name,
                        external_id_column_name=mapping_definition.external_id_column_name,
                        id_mapping_table_name=id_mapping_table_name,
                        id_mapping_table_db_name=id_mapping_table_db_name,
                        id_mapping_tables_location=id_mapping_tables_location,
                        id_mapping_table_entity_type=id_mapping_entity_type,
                    )
                except Exception as inner_exp:
                    msg = f"Failed perform ID mapping for mapping_definition={id_mapping_info.mapping_definition}"
                    Logger.error(msg)
                    raise Exception(msg) from inner_exp

            data_format = None
            data_source_owner = id_mapping_table_db_name
            if id_mapping_entity_type == DataSourceTypeEnum.STORAGE:
                data_source_owner = AdrmIdsMapper.specific_table_location(id_mapping_tables_location, id_mapping_table_name)
                data_format = AdrmIdsMapper.DATA_FORMAT

            return {
                id_mapping_target_table_name:
                    DataAccessDefinition(data_source_id=id_mapping_table_name,
                                         data_source_type=id_mapping_entity_type,
                                         data_source_owner_id=data_source_owner,
                                         data_format=data_format)
            }

        id_mapping_info_lists = list(ids_mapping_dag.values())
        if not id_mapping_info_lists:
            return {}

        with ThreadPoolExecutor(max_workers=IdsMappingOrchestrator._compute_workers(id_mapping_info_lists), thread_name_prefix="id_mapper") as executor:
            mapping_table_access_definitions_iter = executor.map(_map_ids, id_mapping_info_lists)

        mapping_table_access_definitions = {}
        for mapping_table_access_definition in mapping_table_access_definitions_iter:
            mapping_table_access_definitions = {**mapping_table_access_definitions,
                                                **mapping_table_access_definition}

        return mapping_table_access_definitions

    @staticmethod
    def _order_id_mapping_info_list(id_mapping_info_list: list[IdMappingInfo]):
        return sorted(id_mapping_info_list,
                      key=lambda id_mapping_info:
                      (id_mapping_info.mapping_definition.external_id_column_name is not None,
                       id_mapping_info.mapping_definition.external_id_column_name),
                      reverse=True)

    @staticmethod
    def _compute_workers(id_mapping_info_lists):
        return len(id_mapping_info_lists)

    @staticmethod
    def _build_ids_mapping_dag(config: DataFeedConfiguration, source_processors: List[SourceProcessor]) -> Dict[str, List[IdMappingInfo]]:

        source_processor_by_source_table_name: Dict[str, SourceProcessor] = \
            IdsMappingOrchestrator._map_source_table_name_to_df(source_processors)

        # Handle IDs mapping - Start
        # Group mapping definitions by key (target mapping table name)
        id_mapping_info_list_by_target_mapping_table: Dict[str, List[IdMappingInfo]] = defaultdict(list)
        for source_config in config.source_configurations:
            for mapping_definition in source_config.mapping_definitions:
                source_processor = source_processor_by_source_table_name[mapping_definition.source_mapping_table_name]
                if not source_processor.is_empty:
                    # only map source ids to target ids if the source dataframe is not empty
                    id_mapping_info = IdMappingInfo(
                        source_df=source_processor.df,
                        mapping_definition=mapping_definition
                    )
                    id_mapping_info_list_by_target_mapping_table[mapping_definition.target_mapping_table_name].append(
                        id_mapping_info)

        return dict(id_mapping_info_list_by_target_mapping_table)

    @staticmethod
    def _map_source_table_name_to_df(source_processors: List[SourceProcessor]) -> Dict[str, SourceProcessor]:
        dataframes_dict = {}
        for source_processor in source_processors:
            dataframes_dict[source_processor.config.data_access_definition.data_source_id] = source_processor

        return dataframes_dict

from typing import List

from common.utils.logging import Logger
from pyspark.sql import DataFrame

from dmf.ids_mapping.adrm_ids_enricher import AdrmIdsEnricher
from dmf.transformations.model.transformation_types import TransformationData, TransformationMetaData
from dmf.transformations.processor.conditions.conditioned_ids import ConditionedNullIdsFilter
from dmf.transformations.steps.duplicates_filter import DuplicatesFilter
from dmf.transformations.steps.latest_change_filter import LatestChangeFilter
from dmf.transformations.steps.partition_manager import PartitionManager
from dmf.transformations.steps.source_schema_manipulator import SourceSchemaManipulator
from dmf.transformations.transformer.transformer import Transformer


class SimpleTransformer(Transformer):

    def __init__(self, id: str, target_id: str):
        self.id = id
        self.target_id = target_id

    def __str__(self):
        return f"SimpleTransformer[{self.id}](target={self.target_id})"

    def __repr__(self) -> str:
        return self.__str__()

    def transform(self,
                  data: TransformationData,
                  metadata: TransformationMetaData) -> DataFrame:

        # filter source to contain only one change per day
        source_df = LatestChangeFilter.filter(
            data.source_df,
            metadata.source_key_col_names,
            metadata.source_modified_date_col_name)

        source_data_cols_names: List[str] = list(metadata.source_data_col_names)

        # remove duplicates values from source
        source_df = DuplicatesFilter.filter(source_df,
                                            metadata.source_key_col_names,
                                            source_data_cols_names,
                                            metadata.source_modified_date_col_name,
                                            True)
        # enrich source with adrm ids: enrich source key/s to adrm is + optional other source foreign key/s to adrm id
        for id_cols_names_mapping in metadata.source_to_target_ids_mapping:
            if id_cols_names_mapping.target_id_col_name in source_df.columns:
                raise ValueError(
                    f"Simple transformation: target id column '{id_cols_names_mapping.target_id_col_name}' "
                    f"already exists in source dataframe")
            source_df = AdrmIdsEnricher.enrich(
                source_df,
                metadata.feed_id,
                id_cols_names_mapping.source_id_col_name,
                data.id_mappings_df[id_cols_names_mapping.id_mapping_df_name],
                id_cols_names_mapping.target_id_col_name)

        source_df = ConditionedNullIdsFilter.filter(source_df, metadata.source_ids_with_conditions)
        target_partition_columns = PartitionManager.get_partition_column_names(metadata.source_partitions_configs)
        # cast source data fields to target field names and types.
        mixed_df = SourceSchemaManipulator.adjust_to_target(
            source_df,
            metadata.source_to_target_col_names_mapping,
            metadata.synthetically_nulled_primary_keys,
            data.target_df.dtypes,
            self.target_id,
            metadata.source_to_target_ids_mapping,
            target_partition_columns)

        # add partition/s columns to source
        source_with_partitions_df = PartitionManager.add_partition(
            mixed_df,
            metadata.source_partitions_configs)

        target_schema_columns = metadata.target_schema_col_names
        if target_schema_columns.intersection(set(target_partition_columns)):
            raise ValueError(
                f"Simple transformation: some partition columns are part of target schema. That is not allowed. "
                f"Check configuration for target table {self.target_id}. "
                f"Target schema columns: {target_schema_columns}, partition columns: {target_partition_columns}")

        all_target_columns = target_schema_columns.union(frozenset(target_partition_columns))

        try:
            transformed_df = source_with_partitions_df.select(*all_target_columns)
        except Exception as e:
            msg = (f" Selecting target columns failed. "
                   f"Dataframe columns: {source_with_partitions_df.columns}, "
                   f"Target schema columns: {target_schema_columns}, "
                   f"Partition columns: {target_partition_columns}. ")

            Logger.error(f"{msg} \n {e}")
            raise ValueError(msg)

        return transformed_df

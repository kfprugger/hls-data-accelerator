from typing import List

from pyspark.sql import DataFrame

from dmf.ids_mapping.adrm_ids_enricher import AdrmIdsEnricher
from dmf.transformations.model.transformation_types import TransformationData, TransformationMetaData
from dmf.transformations.processor.conditions.conditioned_ids import ConditionedNullIdsFilter
from dmf.transformations.steps.activeness_status_enricher import ActivenessStatusEnricher
from dmf.transformations.steps.duplicates_filter import DuplicatesFilter
from dmf.transformations.steps.intra_day_latest_changes_filter import IntraDayLatestChangeFilter
from dmf.transformations.steps.partition_manager import PartitionManager
from dmf.transformations.steps.range_manager import RangeManager
from dmf.transformations.steps.source_schema_manipulator import SourceSchemaManipulator
from dmf.transformations.steps.target_changeable_selector import TargetChangeableSelector
from dmf.transformations.steps.target_unifier import TargetUnifier
from dmf.transformations.transformer.transformer import Transformer


class DurationTransformer(Transformer):
    def __init__(self, id: str, target_id: str):
        self.id = id
        self.target_id = target_id

    def __str__(self) -> str:
        return f"DurationTransformer[{self.id}](target={self.target_id})"

    def __repr__(self) -> str:
        return self.__str__()

    def transform(self,
                  data: TransformationData,
                  metadata: TransformationMetaData) -> DataFrame:

        # filter source to contain only one change per day
        source_df = IntraDayLatestChangeFilter.filter(data.source_df, metadata.source_key_col_names,
                                                      metadata.source_modified_date_col_name)
        status_enriched_src_df = ActivenessStatusEnricher.enrich_source(
            source_df,
            metadata.source_active_status_col_name,
            metadata.source_deleted_status_col_name)
        source_data_and_status_cols_names: List[str] = list(metadata.source_data_col_names) + [
            ActivenessStatusEnricher.CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME]
        # remove duplicates values from source
        source_df = DuplicatesFilter.filter(status_enriched_src_df,
                                            metadata.source_key_col_names,
                                            source_data_and_status_cols_names,
                                            metadata.source_modified_date_col_name)
        # enrich source with adrm ids: enrich source key/s to adrm is + optional other source foreign key/s to adrm id
        for id_cols_names_mapping in metadata.source_to_target_ids_mapping:
            if id_cols_names_mapping.target_id_col_name in source_df.columns:
                raise ValueError(
                                        f"Duration transformation error. Target id column '{id_cols_names_mapping.target_id_col_name}' already exists in source dataframe")
            source_df = AdrmIdsEnricher.enrich(
                source_df,
                metadata.feed_id,
                id_cols_names_mapping.source_id_col_name,
                data.id_mappings_df[id_cols_names_mapping.id_mapping_df_name],
                id_cols_names_mapping.target_id_col_name)

        source_df: DataFrame = ConditionedNullIdsFilter.filter(source_df, metadata.source_ids_with_conditions)
        partition_column_names = PartitionManager.get_partition_column_names(metadata.source_partitions_configs)

        # cast source data fields to target field names and types.
        mixed_df = SourceSchemaManipulator.adjust_to_target(
            source_df,
            metadata.source_to_target_col_names_mapping,
            metadata.synthetically_nulled_primary_keys,
            data.target_df.dtypes,
            self.target_id,
            metadata.source_to_target_ids_mapping,
            partition_column_names)

        target_schema_columns = metadata.target_schema_col_names
        if target_schema_columns.intersection(set(partition_column_names)):
            raise ValueError(
                f"Simple transformation: some partition columns are part of target schema. That is not allowed. "
                f"Check configuration for target table {self.target_id}. "
                f"Target schema columns: {target_schema_columns}, partition columns: {partition_column_names}")

        # add partition/s columns to source
        source_with_partitions_df = PartitionManager.add_partition(
            mixed_df,
            metadata.source_partitions_configs)

        # filter target dataframe by source partitions
        target_df = PartitionManager.filter_target_by_source_partitions(source_with_partitions_df, data.target_df,
                                                                        partition_column_names)

        target_key_column_names = metadata.target_key_col_names_for_duration_transformation
        target_changeable_df = TargetChangeableSelector.get_changeable(
            source_with_partitions_df,
            target_df,
            target_key_column_names,
            metadata.target_modified_date_col_name)

        status_enriched_target_df = ActivenessStatusEnricher.enrich_target(target_changeable_df,
                                                                           metadata.target_period_end_col_name)

        target_and_source_changeable_df = TargetUnifier.union(
            status_enriched_target_df, source_with_partitions_df)

        # remove duplicates values from source and target
        target_data_and_activeness_status_column_names: List[str] = list(metadata.target_data_col_names) + [
            ActivenessStatusEnricher.CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME]

        target_and_source_deduped_df = DuplicatesFilter.filter(target_and_source_changeable_df,
                                                               target_key_column_names,
                                                               target_data_and_activeness_status_column_names,
                                                               metadata.target_modified_date_col_name)

        # compute range for the normalized dataframe and remove delete and active rows
        target_and_source_ranged_df = RangeManager.calculate_range(target_and_source_deduped_df,
                                                                   target_key_column_names,
                                                                   list(metadata.target_data_col_names),
                                                                   metadata.target_modified_date_col_name,
                                                                   metadata.target_period_start_col_name,
                                                                   metadata.target_period_end_col_name)

        target_and_source_intra_day_reduced_df = IntraDayLatestChangeFilter.filter(target_and_source_ranged_df,
                                                                                   target_key_column_names,
                                                                                   metadata.target_modified_date_col_name)

        return target_and_source_intra_day_reduced_df.select(*data.target_df.columns)

from collections import defaultdict
from typing import Dict, FrozenSet, List, Optional

from dmf.model.source_configuration import SourceTableSchema
from dmf.model.target_configuration.target_configuration import TargetConfiguration
from dmf.model.target_configuration.target_transformation import ColumnTransformation
from dmf.transformations.model.transformation_types import (
    PartitionConfig,
    Source2TargetIdMapping,
    TransformationMetaData,
)
from dmf.utils.immutable_dict import ImmutableDict


class TransformationMetaDataFactory:
    def __init__(
        self,
        source_schema: SourceTableSchema,
        target_config: TargetConfiguration,
        source_partitions_configs: List[PartitionConfig],
        source_to_target_ids_mapping: List[Source2TargetIdMapping],
        source_ids_with_conditions: List[str],
    ):
        self._target_config = target_config
        self._source_schema = source_schema
        self._source_partitions_configs = source_partitions_configs
        if target_config.temporal_tables_semantics:
            self._target_period_start_col_name = target_config.temporal_tables_semantics.start_col_name
            self._target_period_end_col_name = target_config.temporal_tables_semantics.end_col_name
        else:
            self._target_period_start_col_name = ""
            self._target_period_end_col_name = ""

        self._source_to_target_ids_mapping = source_to_target_ids_mapping
        self._source_ids_with_conditions = source_ids_with_conditions

        self._feed_id = target_config.feed_id
        self._target_primary_keys = frozenset(c.name for c in target_config.table_schema.columns if c.is_primary_key)
        self._target_key_col_names = self._calc_target_key_col_names()
        self._source_to_target_col_names_mapping = self._calc_source_to_target_col_names_mapping()
        self._target_data_col_names = self._calc_target_data_col_names()
        self._synthetically_nulled_primary_keys = self._calc_synthetically_nulled_primary_keys()
        self._source_data_col_names = self._source_data_columns_for_dedup()

    def create(self) -> TransformationMetaData:
        self._validate()
        return TransformationMetaData(
            source_partitions_configs=self._source_partitions_configs,
            source_modified_date_col_name=self._source_schema.source_modified_date_column_name,
            source_key_col_names=self._source_key_column_names(),
            source_data_col_names=self._source_data_col_names,
            source_deleted_status_col_name=self._source_schema.source_deleted_status_column_name,
            source_active_status_col_name=self._source_schema.source_active_status_column_name,
            target_key_col_names=self._target_key_col_names,
            target_key_col_names_for_duration_transformation=self._calc_target_key_col_names_for_duration_transformation(),
            target_data_col_names=self._target_data_col_names,
            target_schema_col_names=self._target_config.table_schema.column_names,
            target_modified_date_col_name=self._target_config.target_modified_date_column_name,
            target_period_start_col_name=self._target_period_start_col_name,
            target_period_end_col_name=self._target_period_end_col_name,
            source_to_target_ids_mapping=self._source_to_target_ids_mapping,
            source_ids_with_conditions=self._source_ids_with_conditions,
            source_to_target_col_names_mapping=self._source_to_target_col_names_mapping,
            synthetically_nulled_primary_keys=self._synthetically_nulled_primary_keys,
            feed_id=self._feed_id,
        )

    def _source_key_column_names(self) -> List[str]:
        return [ct.source_field_name for ct in self._target_config.target_columns_transformations
                if ct.is_source_primary_key]

    def _validate(self):
        self._validate_target_key_col_names()

    def _validate_target_key_col_names(self):
        if not self._target_key_col_names:
            raise ValueError("Transformation spec error. metadata.target_key_col_names should be non-empty. Primary key mapping may be missing")

    def _calc_source_to_target_col_names_mapping(self) -> Dict[str, List[str]]:
        """Returns a dictionary mapping source column names to a list of target column names.
        should not contain any transformations that use the ids mapping mechanism."""
        target_columns_with_id_mapping = [mapping.target_id_col_name for mapping in self._source_to_target_ids_mapping]
        mappings = defaultdict(list)
        raw_source_to_target_column_names_mapping = self._calc_raw_source_to_target_column_names_mapping()
        for source_field_name, target_field_names in raw_source_to_target_column_names_mapping.items():
            for target_field_name in target_field_names:
                if target_field_name in target_columns_with_id_mapping:
                    continue
                mappings[source_field_name].append(target_field_name)
        return dict(mappings)

    def _transformed_target_columns_names(self):
        def flatten(list_of_lists: List[List]):
            return [item for sublist in list_of_lists for item in sublist]

        all_values = list(self._source_to_target_col_names_mapping.values())
        return frozenset(name for name in flatten(all_values))

    def _calc_target_key_col_names(self) -> List[str]:
        target_primary_keys = [c.name for c in self._target_config.table_schema.columns if c.is_primary_key]
        return target_primary_keys

    def _calc_target_key_col_names_for_duration_transformation(self) -> Optional[List[str]]:
        """used to dedupe source and target data"""
        if self._target_config.table_schema.duration_semantics:
            return list(self._target_config.table_schema.duration_semantics.group_by_cols)

        return None

    def _calc_target_data_col_names(self) -> FrozenSet[str]:
        def is_data_col(col_name):
            if col_name == self._target_config.target_modified_date_column_name:
                return False
            if col_name in self._target_primary_keys:
                return False
            return True

        return frozenset(filter(is_data_col, self._transformed_target_columns_names()))

    def _has_source_table(self, tct: ColumnTransformation) -> bool:
        return tct.has_source_field

    def _calc_synthetically_nulled_primary_keys(self) -> FrozenSet[str]:
        def _has_no_source_table(tct):
            return not self._has_source_table(tct)

        target_columns_transformations = filter(
            _has_no_source_table, self._target_config.target_columns_transformations
        )
        return frozenset(tct.target_field_name for tct in target_columns_transformations)

    def _calc_raw_source_to_target_column_names_mapping(self) -> Dict[str, List[str]]:
        """Returns a dictionary mapping source column names to a list of target column names (groupby).
        This is based directly on the target_columns_transformations (filtered by the _has_source_table).
        """
        target_columns_transformations = filter(
            self._has_source_table, self._target_config.target_columns_transformations
        )
        target_cols_by_src_col = defaultdict(list)
        for tct in target_columns_transformations:
            target_cols_by_src_col[tct.source_field_name].append(tct.target_field_name)
        return ImmutableDict(target_cols_by_src_col)

    def _source_data_columns_for_dedup(self) -> FrozenSet[str]:
        id_mapped_source_columns = [im.source_id_col_name for im in self._source_to_target_ids_mapping]

        def relevant_for_dedupe(tct: ColumnTransformation) -> bool:
            if tct.source_field_name in id_mapped_source_columns:
                # this is a id mapped pk in source
                return False
            if not self._has_source_table(tct):
                return False
            return True

        return frozenset(
            tct.source_field_name
            for tct in self._target_config.target_columns_transformations
            if relevant_for_dedupe(tct)
        )

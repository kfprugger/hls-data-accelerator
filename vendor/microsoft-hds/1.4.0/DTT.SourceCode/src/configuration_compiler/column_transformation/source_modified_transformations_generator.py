from typing import Set

from pyspark.sql.types import StringType, TimestampType
from common.model.types import DataSourceId, FeedId, TargetId
from dmf.model.source_configuration import SourceConfiguration, SourceTableSchema
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class SourceModifiedTransformationsGenerator:
    @staticmethod
    def add_transformations_for_all_target_tables(
        source_schemas: dict[DataSourceId, SourceTableSchema],
        all_transformations: dict[DataSourceId, dict[DataSourceId, Set[ColumnTransformation]]],
        feed_id: str,
        target_modified_date_column_name: str,
        source_table_column_name: str,
    ) -> None:
        for source_id, transformations_for_source in all_transformations.items():
            all_target_tables = set()
            for target_transformations in transformations_for_source.values():
                for target_transformation in target_transformations:
                    all_target_tables.add(target_transformation.transformation_target_id)

            SourceModifiedTransformationsGenerator._add_mappings_for_single_source(
                all_transformations,
                source_id,
                feed_id,
                target_modified_date_column_name,
                source_schemas[source_id],
                all_target_tables,
                source_table_column_name,
            )

    @staticmethod
    def _add_mappings_for_single_source(
        all_transformations: dict[DataSourceId, dict[DataSourceId, Set[ColumnTransformation]]],
        source_id: DataSourceId,
        feed_id: FeedId,
        target_modified_date_column_name: str,
        source_table_schema: SourceTableSchema,
        target_ids: Set[TargetId],
        source_table_column_name: str,
    ) -> None:
        for target_id in target_ids:
            source_modified_date_mapping = ColumnTransformation(
                transformation_target_id=target_id,
                original_source_field_name=source_table_schema.source_modified_date_column_name,
                target_field_name=target_modified_date_column_name,
                target_field_type=TimestampType(),
                source_field_type=TimestampType(),
                target_field_value=None,
                is_source_primary_key=False,
                target_field_condition=None,
                owner_target_id=target_id,
                should_be_id_mapped=False,
            )
            unique_id = SourceConfiguration.gen_unique_id(source_id, feed_id)
            source_modified_date_source_table_mapping = ColumnTransformation(
                transformation_target_id=target_id,
                original_source_field_name=source_table_schema.source_modified_date_column_name,
                target_field_name=source_table_column_name,
                target_field_type=StringType(),
                source_field_type=StringType(),
                target_field_value=f"'{unique_id}'",
                # add quotes to avoid values being parse as column name
                is_source_primary_key=False,
                target_field_condition=None,
                owner_target_id=target_id,
                should_be_id_mapped=False,
            )
            all_transformations[source_id][target_id].add(source_modified_date_mapping)
            all_transformations[source_id][target_id].add(source_modified_date_source_table_mapping)

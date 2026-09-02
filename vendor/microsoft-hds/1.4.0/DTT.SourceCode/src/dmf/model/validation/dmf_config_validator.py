from collections import defaultdict

from dmf.model.data_feed_configuration import DataFeedConfiguration
from dmf.model.target_configuration.target_configuration import TargetConfiguration
from dmf.model.validation.validation_exception import ValidationException


class MissingPrimaryKeysTransformationException(ValidationException):
    pass


class MissingPrimaryKeysInTargetTransformationException(ValidationException):
    pass


class TargetIdMismatchException(ValidationException):
    pass


class DMFConfigValidator:
    def __init__(self, config: DataFeedConfiguration):
        self.config = config

    def validate(self):
        self._validate_all_transformations_write_to_the_the_same_target()
        self._validate_missing_primary_keys_in_target_schema()
        self._validate_primary_keys_written_target()
        self._validate_multiple_sources_to_same_target()

    def _validate_missing_primary_keys_in_target_schema(self):
        """for each target configuration, validate that all primary keys are being written to the target"""
        tables_without_primary_keys = defaultdict(list)
        for source_config in self.config.source_configurations:
            for target_config in source_config.target_configurations:
                primary_keys = self._target_config_required_primary_keys(target_config)
                if not primary_keys:
                    tables_without_primary_keys[source_config.source_id].append(target_config.target_id)
        if tables_without_primary_keys:
            raise MissingPrimaryKeysTransformationException(f"Primary keys not defined for targets {tables_without_primary_keys}. "
                                                            f"For duration tables, a groupBy field may be missing.",
                                                            target_ids=tables_without_primary_keys, )

    def _validate_primary_keys_written_target(self):
        """for each target configuration, validate that all primary keys are being written to the target"""
        for source_config in self.config.source_configurations:
            for target_config in source_config.target_configurations:
                primary_keys = self._target_config_required_primary_keys(target_config)
                columns_written_to_target = []
                for transformation in target_config.target_columns_transformations:
                    columns_written_to_target.append(transformation.target_field_name)
                for pk in primary_keys:
                    if pk not in columns_written_to_target:
                        raise MissingPrimaryKeysInTargetTransformationException(
                            f"primary key {pk} is not written to target {target_config.target_id}",
                            target_id=target_config.target_id,
                            target_primary_keys=primary_keys,
                            missing_primary_key=pk,
                            columns_written_to_target=columns_written_to_target,
                            source_id=source_config.source_id,
                        )

    def _target_config_required_primary_keys(self, target_config: TargetConfiguration):
        primary_keys = [col.name for col in target_config.table_schema.columns if col.is_primary_key]
        if target_config.table_schema.duration_semantics:
            primary_keys = target_config.table_schema.duration_semantics.group_by_cols
        return primary_keys

    def _validate_all_transformations_write_to_the_the_same_target(self):
        for source_config in self.config.source_configurations:
            for target_config in source_config.target_configurations:
                target_id = target_config.target_id
                for transformation in target_config.target_columns_transformations:
                    if transformation.transformation_target_id != target_id:
                        raise TargetIdMismatchException(f"transformation {transformation} writes to target {transformation.transformation_target_id} "
                                                        f"but target configuration {target_id} was specified in source configuration {source_config.source_id}")

    def _validate_multiple_sources_to_same_target(self):

        def fail(field_name, other_field_name):
            already_mapped_source = mapped_source_fields_by_target[field_name]
            raise ValueError(
                "Mapping multiple source columns to same target column is not yet supported"
                "(should be supported in transformations that create multiple rows in target per row in source) "
                f"conflicting sources: {already_mapped_source}, {other_field_name} "
                f"target: {field_name}"
            )

        for source_config in self.config.source_configurations:
            for target_config in source_config.target_configurations:
                for target_column_transformation in target_config.target_columns_transformations:
                    mapped_source_fields_by_target = {}
                    if target_column_transformation.target_field_name in mapped_source_fields_by_target:
                        fail(target_column_transformation.target_field_name,
                             target_column_transformation.original_source_field_name)
                    mapped_source_fields_by_target[target_column_transformation.target_field_name] = target_column_transformation.source_field_name

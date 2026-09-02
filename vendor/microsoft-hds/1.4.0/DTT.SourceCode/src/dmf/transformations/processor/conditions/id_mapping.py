from typing import List, Tuple

from dmf.transformations.model.transformation_types import Source2TargetIdMapping


class ConditionedIdMappingAdjuster:
    @staticmethod
    def adjust(target_config, target_id_mappings: List[Source2TargetIdMapping]) -> Tuple[List[Source2TargetIdMapping], List[str]]:
        """Changed mapping metadata so it will have the correct source id for mapping of ids with conditions"""
        target_id_mappings_with_conditions = []
        source_ids_with_conditions = []

        for target_id_mapping in target_id_mappings:
            amended_source_field_name = None
            for target_column_mapping in target_config.target_columns_transformations:
                if ConditionedIdMappingAdjuster.should_amend_mapping(target_id_mapping, target_column_mapping):
                    amended_source_field_name = target_column_mapping.source_field_name
                    if target_column_mapping.is_source_primary_key:
                        source_ids_with_conditions.append(target_column_mapping.source_field_name)
                    break

            if amended_source_field_name is not None:
                target_id_mappings_with_conditions.append(Source2TargetIdMapping(
                    source_id_col_name=amended_source_field_name,
                    target_id_col_name=target_id_mapping.target_id_col_name,
                    id_mapping_df_name=target_id_mapping.id_mapping_df_name
                ))
            else:
                target_id_mappings_with_conditions.append(target_id_mapping)

        return target_id_mappings_with_conditions, source_ids_with_conditions

    @staticmethod
    def should_amend_mapping(target_id_mapping, target_column_mapping):
        return (target_column_mapping.target_field_condition is not None
                and target_id_mapping.source_id_col_name == target_column_mapping.original_source_field_name
                and target_id_mapping.target_id_col_name == target_column_mapping.target_field_name)

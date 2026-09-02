from collections import defaultdict
from typing import List

from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.common.field_type import CommonParsing
from configuration_compiler.config_files_models.common.types import SourceColumnName
from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId
from dmf.model.target_configuration.target_configuration import ColumnTransformation


class ReferenceColumnsMappingParser:
    # TODO: unify this iteration with the one in ColumnMappingParser (during the refactoring)
    @staticmethod
    def parse_reference_column_mappings(
        dmf_adaptor: AdapterModel,
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
    ) -> dict[DataSourceId, dict[DataSourceId, dict[SourceColumnName, List[ColumnTransformation]]]]:
        mapping = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for source_table, source_field, target_field in dmf_adaptor.target_fields:
            if source_table.bypassKeysHarmonization and not source_field.enforceKeyHarmonization:
                continue
            target_id = target_field.tableName
            if target_tables_schemas[target_id].is_ref_table:
                target_schema = target_tables_schemas[target_id]
                column_mapping = ColumnTransformation(
                    transformation_target_id=target_id,
                    original_source_field_name=source_field.fieldName,
                    target_field_name=target_field.fieldName,
                    target_field_type=TargetTableSchemaUtils.get_column_type(target_schema, target_field.fieldName),
                    source_field_type=CommonParsing.parse_field_type(source_field.fieldType),
                    is_source_primary_key=False,
                    target_field_value=target_field.fieldValue,
                    target_field_condition=None,
                    owner_target_id=target_id,
                    should_be_id_mapped=False,
                    has_source_field=True,
                )
                mapping[source_table.tableName][target_id][source_field.fieldName].append(column_mapping)
        return defaultdict_to_dict(mapping)


def defaultdict_to_dict(d):
    if isinstance(d, defaultdict):
        # Convert the defaultdict to dict
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    return d
